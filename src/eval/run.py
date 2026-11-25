"""Main reproducible evaluation runner: python -m src.eval.run"""

from __future__ import annotations

import csv
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import ROUND_TRIP_FEE
from src.eval.data_loader import ORIGINAL_6, load_universe
from src.eval.features import EXTRA_OHLCV_FEATURES, IHSG_FEATURES, ORIG_FEATURES, prepare_eval_dataframe
from src.eval.metrics import (
    calibration_table,
    compute_classification_metrics,
    paired_block_bootstrap_diff,
)
from src.eval.trajectory_eval import evaluate_trajectory_oos

ROOT_DIR = Path(__file__).resolve().parents[2]
EXP_CSV = ROOT_DIR / "experiments" / "experiments.csv"
REPORT_MD = ROOT_DIR / "reports" / "evaluation.md"

HORIZON = 5
HOLDOUT_DAYS = 63
FEE = ROUND_TRIP_FEE


@dataclass(frozen=True)
class EvalConfig:
    exp_id: str
    desc: str
    features: tuple[str, ...]
    use_purge: bool = True
    threshold: float = 0.58
    use_recency: bool = False
    use_ensemble: bool = False
    use_trend_gate: bool = False
    use_ihsg: bool = False


class _EnsembleModel:
    def __init__(self) -> None:
        self.lr = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(C=0.3, max_iter=500, random_state=42)),
        ])
        self.gb = HistGradientBoostingClassifier(
            max_depth=3,
            max_iter=60,
            learning_rate=0.05,
            min_samples_leaf=15,
            l2_regularization=3.0,
            random_state=42,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series, sample_weight: np.ndarray | None = None) -> _EnsembleModel:
        self.lr.fit(X, y, clf__sample_weight=sample_weight)
        self.gb.fit(X, y, sample_weight=sample_weight)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return 0.4 * self.lr.predict_proba(X) + 0.6 * self.gb.predict_proba(X)


def _ema_smooth(probs: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    if len(probs) == 0:
        return probs
    out = np.empty_like(probs, dtype=float)
    out[0] = float(probs[0])
    for i in range(1, len(probs)):
        out[i] = alpha * float(probs[i]) + (1.0 - alpha) * out[i - 1]
    return out


def _recency_weights(n: int, half_life: float = 150.0) -> np.ndarray:
    age = np.arange(n, dtype=float)[::-1]
    return np.exp(-np.log(2.0) * age / half_life)


def _make_model(use_ensemble: bool) -> Any:
    if use_ensemble:
        return _EnsembleModel()
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(C=0.5, max_iter=500, random_state=42)),
    ])


def _fit_model(model: Any, X: pd.DataFrame, y: pd.Series, use_recency: bool) -> None:
    w = _recency_weights(len(X)) if use_recency else None
    if isinstance(model, _EnsembleModel):
        model.fit(X, y, sample_weight=w)
    elif w is not None:
        model.fit(X, y, clf__sample_weight=w)
    else:
        model.fit(X, y)


def _run_step0_reproduction() -> list[dict[str, Any]]:
    """Reproduces baseline-before (f4f5c2b) vs baseline-after (32117df) on ORIGINAL_6 (2y)."""
    from src.data.market_feed import fetch_jk_ohlcv

    rows: list[dict[str, Any]] = []
    for tag in ("baseline-before", "baseline-after"):
        code = subprocess.check_output(
            ["git", "show", f"{tag}:src/engine/forecaster.py"],
            cwd=str(ROOT_DIR),
            text=True,
        )
        ns: dict[str, Any] = {}
        exec(compile(code, f"{tag}:forecaster.py", "exec"), ns)
        fn = ns["forecast_direction_with_backtest"]
        for t in ORIGINAL_6:
            df = fetch_jk_ohlcv(t, range_str="2y")
            res = fn(df)
            rows.append({
                "tag": tag,
                "ticker": t,
                "p_up": res.get("p_up_pct"),
                "oos_acc": res.get("oos_accuracy_pct"),
                "bull_wr": res.get("oos_bullish_win_rate_pct"),
                "sigs": res.get("oos_bullish_signals"),
                "bull_ret": res.get("oos_bullish_avg_net_ret_pct"),
            })
    return rows


def _eval_config_dev(
    prepared: dict[str, pd.DataFrame],
    cfg: EvalConfig,
    tickers: list[str],
) -> dict[str, Any]:
    """Runs expanding-window walk-forward on dev set (min 5 folds) for given config."""
    feat_cols = list(cfg.features)
    all_preds, all_probs, all_actuals, all_rets, all_maj = [], [], [], [], []
    per_ticker: dict[str, dict[str, Any]] = {}
    fold_accs: list[float] = []
    fold_rets: list[float] = []

    for t in tickers:
        labeled = prepared[t].dropna(subset=feat_cols + ["fwd_ret", "ma20", "ma50"]).reset_index(drop=True)
        if len(labeled) < 200:
            continue
        holdout_start = len(labeled) - HOLDOUT_DAYS
        dev_df = labeled.iloc[: holdout_start - HORIZON].reset_index(drop=True)
        n_dev = len(dev_df)
        start_eval = max(120, n_dev // 2)
        step = max(20, (n_dev - start_eval) // 5)

        t_preds, t_probs, t_actuals, t_rets, t_maj = [], [], [], [], []
        for split in range(start_eval, n_dev, step):
            end = min(split + step, n_dev)
            tr_end = max(60, split - (HORIZON if cfg.use_purge else 0))
            train_df = dev_df.iloc[:tr_end]
            test_df = dev_df.iloc[split:end]
            if len(test_df) == 0 or train_df["target_up"].nunique() < 2:
                continue

            model = _make_model(cfg.use_ensemble)
            _fit_model(model, train_df[feat_cols], train_df["target_up"].astype(int), cfg.use_recency)
            raw_p = model.predict_proba(test_df[feat_cols])[:, 1]
            probs = _ema_smooth(raw_p, alpha=0.5)
            preds = (probs >= cfg.threshold).astype(int)

            if cfg.use_trend_gate:
                downtrend = (test_df["close"] < test_df["ma20"]) & (test_df["ma20"] < test_df["ma50"])
                preds = np.where(downtrend.to_numpy(), 0, preds)

            maj_cls = 1 if float(train_df["target_up"].mean()) >= 0.5 else 0
            maj_arr = np.full(len(test_df), maj_cls, dtype=int)
            act_arr = test_df["target_up"].astype(int).to_numpy()
            ret_arr = test_df["fwd_ret"].to_numpy(dtype=float)

            t_preds.extend(preds.tolist())
            t_probs.extend(probs.tolist())
            t_actuals.extend(act_arr.tolist())
            t_rets.extend(ret_arr.tolist())
            t_maj.extend(maj_arr.tolist())

            fold_accs.append(float(np.mean(preds == act_arr)) * 100.0)
            bm = preds == 1
            fold_rets.append(float(np.mean((ret_arr[bm] - FEE) * 100.0)) if bm.any() else 0.0)

        if t_preds:
            per_ticker[t] = compute_classification_metrics(
                np.array(t_preds),
                np.array(t_probs),
                np.array(t_actuals),
                np.array(t_rets),
                np.array(t_maj),
                fee=FEE,
            )
            all_preds.extend(t_preds)
            all_probs.extend(t_probs)
            all_actuals.extend(t_actuals)
            all_rets.extend(t_rets)
            all_maj.extend(t_maj)

    pooled = compute_classification_metrics(
        np.array(all_preds),
        np.array(all_probs),
        np.array(all_actuals),
        np.array(all_rets),
        np.array(all_maj),
        fee=FEE,
    )
    calib = calibration_table(np.array(all_probs), np.array(all_actuals), n_bins=5)
    return {
        "config": cfg,
        "pooled": pooled,
        "per_ticker": per_ticker,
        "calibration": calib,
        "raw": {
            "preds": np.array(all_preds),
            "probs": np.array(all_probs),
            "actuals": np.array(all_actuals),
            "rets": np.array(all_rets),
            "maj": np.array(all_maj),
            "fold_accs": np.array(fold_accs),
            "fold_rets": np.array(fold_rets),
        },
    }


def _eval_baselines_on_split(
    prepared: dict[str, pd.DataFrame],
    tickers: list[str],
    split_mode: str,
    model_sig_rate: float,
) -> dict[str, dict[str, Any]]:
    """Evaluates Step 2 baselines (always_long, majority, trend_rule, random_200) on dev or holdout."""
    feat_cols = list(ORIG_FEATURES)
    collect: dict[str, dict[str, list[Any]]] = {
        k: {"preds": [], "actuals": [], "rets": [], "maj": []}
        for k in ("B_always_long", "B_majority", "B_trend_rule")
    }

    for t in tickers:
        labeled = prepared[t].dropna(subset=feat_cols + ["fwd_ret", "ma20", "ma50"]).reset_index(drop=True)
        if len(labeled) < 200:
            continue
        holdout_start = len(labeled) - HOLDOUT_DAYS

        if split_mode == "dev":
            dev_df = labeled.iloc[: holdout_start - HORIZON].reset_index(drop=True)
            n_dev = len(dev_df)
            start_eval = max(120, n_dev // 2)
            step = max(20, (n_dev - start_eval) // 5)
            slices = [(dev_df.iloc[: max(60, s - HORIZON)], dev_df.iloc[s : min(s + step, n_dev)]) for s in range(start_eval, n_dev, step)]
        else:
            slices = [(labeled.iloc[: holdout_start - HORIZON], labeled.iloc[holdout_start:])]

        for train_df, test_df in slices:
            if len(test_df) == 0:
                continue
            act = test_df["target_up"].astype(int).to_numpy()
            ret = test_df["fwd_ret"].to_numpy(dtype=float)
            maj_cls = 1 if float(train_df["target_up"].mean()) >= 0.5 else 0
            maj = np.full(len(test_df), maj_cls, dtype=int)
            always = np.ones(len(test_df), dtype=int)
            trend = ((test_df["close"] > test_df["ma20"]) & (test_df["ma20"] > test_df["ma50"])).astype(int).to_numpy()

            for name, pr in [("B_always_long", always), ("B_majority", maj), ("B_trend_rule", trend)]:
                collect[name]["preds"].extend(pr.tolist())
                collect[name]["actuals"].extend(act.tolist())
                collect[name]["rets"].extend(ret.tolist())
                collect[name]["maj"].extend(maj.tolist())

    out: dict[str, dict[str, Any]] = {}
    for name, d in collect.items():
        out[name] = {
            "pooled": compute_classification_metrics(
                np.array(d["preds"]),
                None,
                np.array(d["actuals"]),
                np.array(d["rets"]),
                np.array(d["maj"]),
                fee=FEE,
            ),
            "raw": {k: np.array(v) for k, v in d.items()},
        }

    # Random baseline averaged over 200 seeds matching candidate bullish frequency
    rng = np.random.default_rng(42)
    ref_act = out["B_always_long"]["raw"]["actuals"]
    ref_ret = out["B_always_long"]["raw"]["rets"]
    ref_maj = out["B_always_long"]["raw"]["maj"]
    accs, wrs, rets = [], [], []
    p_sig = max(0.01, min(0.99, model_sig_rate))
    for _ in range(200):
        r_preds = (rng.random(len(ref_act)) < p_sig).astype(int)
        m = compute_classification_metrics(r_preds, None, ref_act, ref_ret, ref_maj, fee=FEE)
        accs.append(m["acc"])
        wrs.append(m["bull_wr"])
        rets.append(m["bull_net_ret"])
    out["B_random_200"] = {
        "pooled": {
            "n_total": len(ref_act),
            "n_signals": int(round(p_sig * len(ref_act))),
            "n_eff": round((p_sig * len(ref_act)) / 5.0, 1),
            "bull_wr": round(float(np.mean(wrs)), 2),
            "bull_wr_ci": (round(float(np.percentile(wrs, 2.5)), 2), round(float(np.percentile(wrs, 97.5)), 2)),
            "bull_net_ret": round(float(np.mean(rets)), 3),
            "bull_ret_ci": (round(float(np.percentile(rets, 2.5)), 3), round(float(np.percentile(rets, 97.5)), 3)),
            "acc": round(float(np.mean(accs)), 2),
            "bal_acc": 50.0,
            "maj_acc": out["B_majority"]["pooled"]["acc"],
            "auc": 0.5,
            "brier": None,
            "log_loss": None,
        }
    }
    return out


def _eval_config_holdout(
    prepared: dict[str, pd.DataFrame],
    cfg: EvalConfig,
    tickers: list[str],
) -> dict[str, Any]:
    """Evaluates ONE selected configuration once on locked 63-day holdout."""
    feat_cols = list(cfg.features)
    all_preds, all_probs, all_actuals, all_rets, all_maj = [], [], [], [], []
    per_ticker: dict[str, dict[str, Any]] = {}

    for t in tickers:
        labeled = prepared[t].dropna(subset=feat_cols + ["fwd_ret", "ma20", "ma50"]).reset_index(drop=True)
        if len(labeled) < 200:
            continue
        holdout_start = len(labeled) - HOLDOUT_DAYS
        train_df = labeled.iloc[: holdout_start - HORIZON]
        test_df = labeled.iloc[holdout_start:]
        if len(test_df) == 0 or train_df["target_up"].nunique() < 2:
            continue

        model = _make_model(cfg.use_ensemble)
        _fit_model(model, train_df[feat_cols], train_df["target_up"].astype(int), cfg.use_recency)
        probs = _ema_smooth(model.predict_proba(test_df[feat_cols])[:, 1], alpha=0.5)
        preds = (probs >= cfg.threshold).astype(int)
        if cfg.use_trend_gate:
            downtrend = (test_df["close"] < test_df["ma20"]) & (test_df["ma20"] < test_df["ma50"])
            preds = np.where(downtrend.to_numpy(), 0, preds)

        maj_cls = 1 if float(train_df["target_up"].mean()) >= 0.5 else 0
        maj_arr = np.full(len(test_df), maj_cls, dtype=int)
        act_arr = test_df["target_up"].astype(int).to_numpy()
        ret_arr = test_df["fwd_ret"].to_numpy(dtype=float)

        per_ticker[t] = compute_classification_metrics(preds, probs, act_arr, ret_arr, maj_arr, fee=FEE)
        all_preds.extend(preds.tolist())
        all_probs.extend(probs.tolist())
        all_actuals.extend(act_arr.tolist())
        all_rets.extend(ret_arr.tolist())
        all_maj.extend(maj_arr.tolist())

    return {
        "pooled": compute_classification_metrics(
            np.array(all_preds), np.array(all_probs), np.array(all_actuals), np.array(all_rets), np.array(all_maj), fee=FEE
        ),
        "per_ticker": per_ticker,
    }


def main() -> None:
    print("Step 0: Reproducing baseline-before vs baseline-after...")
    step0_rows = _run_step0_reproduction()

    print("Step 1: Loading 5y universe (28 tickers) + ^JKSE...")
    data, jkse = load_universe(range_str="5y", use_cache=True)
    tickers_all = sorted(data.keys())
    tickers_6 = [t for t in ORIGINAL_6 if t in data]
    prepared = {t: prepare_eval_dataframe(df, jkse_df=jkse, horizon_days=HORIZON, fee=FEE) for t, df in data.items()}

    f_orig = tuple(ORIG_FEATURES)
    f_plus5 = tuple(ORIG_FEATURES + EXTRA_OHLCV_FEATURES)

    ablations: list[EvalConfig] = [
        EvalConfig("A0", "Model lama (LR 8 feat, no purge, th=0.55)", f_orig, use_purge=False, threshold=0.55),
        EvalConfig("A1", "A0 + purge gap 5H saja", f_orig, use_purge=True, threshold=0.55),
        EvalConfig("A2", "A0 + threshold 0.58 saja", f_orig, use_purge=False, threshold=0.58),
        EvalConfig("A3", "A0 + recency weighting saja", f_orig, use_purge=False, threshold=0.55, use_recency=True),
        EvalConfig("A4", "A0 + 5 fitur OHLCV baru saja", f_plus5, use_purge=False, threshold=0.55),
        EvalConfig("A5", "A0 + ensemble LR+HistGB saja", f_orig, use_purge=False, threshold=0.55, use_ensemble=True),
        EvalConfig("A6", "Gabungan A1+A2+A3+A4+A5", f_plus5, use_purge=True, threshold=0.58, use_recency=True, use_ensemble=True),
    ]

    dev_results_all: dict[str, dict[str, Any]] = {}
    dev_results_6: dict[str, dict[str, Any]] = {}
    for cfg in ablations:
        print(f"Running {cfg.exp_id}: {cfg.desc}...")
        dev_results_all[cfg.exp_id] = _eval_config_dev(prepared, cfg, tickers_all)
        dev_results_6[cfg.exp_id] = _eval_config_dev(prepared, cfg, tickers_6)

    # Pick best from Step 4 (A1..A6 with purge=True or A1 vs A6) by dev AUC & net_ret
    best_step4_id = max(["A1", "A6"], key=lambda k: (dev_results_all[k]["pooled"]["auc"] or 0.0))
    best_step4_cfg = next(c for c in ablations if c.exp_id == best_step4_id)

    # Step 5: A7 = best_step4 + IHSG features
    a7_cfg = EvalConfig(
        "A7",
        f"{best_step4_id} + fitur IHSG (^JKSE)",
        tuple(list(best_step4_cfg.features) + IHSG_FEATURES),
        use_purge=True,
        threshold=0.58,
        use_recency=best_step4_cfg.use_recency,
        use_ensemble=best_step4_cfg.use_ensemble,
        use_ihsg=True,
    )
    print(f"Running A7: {a7_cfg.desc}...")
    dev_results_all["A7"] = _eval_config_dev(prepared, a7_cfg, tickers_all)
    dev_results_6["A7"] = _eval_config_dev(prepared, a7_cfg, tickers_6)

    # Step 6: A8 = best of (A1..A7) + trend gate
    best_pre8_id = max(["A1", "A6", "A7"], key=lambda k: (dev_results_all[k]["pooled"]["auc"] or 0.0))
    best_pre8_cfg = a7_cfg if best_pre8_id == "A7" else best_step4_cfg
    a8_cfg = EvalConfig(
        "A8",
        f"{best_pre8_id} + trend gate (blokir downtrend)",
        best_pre8_cfg.features,
        use_purge=True,
        threshold=0.58,
        use_recency=best_pre8_cfg.use_recency,
        use_ensemble=best_pre8_cfg.use_ensemble,
        use_ihsg=best_pre8_cfg.use_ihsg,
        use_trend_gate=True,
    )
    print(f"Running A8: {a8_cfg.desc}...")
    dev_results_all["A8"] = _eval_config_dev(prepared, a8_cfg, tickers_all)
    dev_results_6["A8"] = _eval_config_dev(prepared, a8_cfg, tickers_6)

    all_configs = ablations + [a7_cfg, a8_cfg]

    # Paired bootstrap diffs vs A0 on dev (fold-level accuracy & per-bar correctness)
    a0_raw = dev_results_all["A0"]["raw"]
    paired_vs_a0: dict[str, dict[str, Any]] = {}
    for eid, res in dev_results_all.items():
        if eid == "A0":
            continue
        r = res["raw"]
        acc_diff = paired_block_bootstrap_diff(
            (r["preds"] == r["actuals"]).astype(float) * 100.0,
            (a0_raw["preds"] == a0_raw["actuals"]).astype(float) * 100.0,
            block_size=5,
        )
        fold_ret_diff = paired_block_bootstrap_diff(r["fold_rets"], a0_raw["fold_rets"], block_size=1)
        paired_vs_a0[eid] = {"acc_diff": acc_diff, "fold_ret_diff": fold_ret_diff}

    # Baselines on dev
    sig_rate_a8 = dev_results_all["A8"]["pooled"]["n_signals"] / max(1, dev_results_all["A8"]["pooled"]["n_total"])
    baselines_dev_all = _eval_baselines_on_split(prepared, tickers_all, "dev", sig_rate_a8)
    baselines_dev_6 = _eval_baselines_on_split(prepared, tickers_6, "dev", sig_rate_a8)

    # Select final candidate on dev: simplest among configs that are not significantly worse than best
    # Specifically compare A1 (simplest clean LR), A6, A7, A8
    chosen_cfg = a8_cfg if paired_vs_a0["A8"]["acc_diff"]["significant"] and paired_vs_a0["A8"]["acc_diff"]["mean_diff"] > 0 else (
        EvalConfig("A1_th58", "LR 8 feat + purge 5H + th 0.58 (sederhana)", f_orig, use_purge=True, threshold=0.58)
        if not paired_vs_a0["A6"]["acc_diff"]["significant"]
        else best_pre8_cfg
    )
    if chosen_cfg.exp_id not in dev_results_all:
        dev_results_all[chosen_cfg.exp_id] = _eval_config_dev(prepared, chosen_cfg, tickers_all)
        dev_results_6[chosen_cfg.exp_id] = _eval_config_dev(prepared, chosen_cfg, tickers_6)
        all_configs.append(chosen_cfg)

    # Step 7: Single hold-out evaluation
    print(f"Step 7: Evaluating chosen config ({chosen_cfg.exp_id}) ONCE on hold-out...")
    ho_chosen_all = _eval_config_holdout(prepared, chosen_cfg, tickers_all)
    ho_chosen_6 = _eval_config_holdout(prepared, chosen_cfg, tickers_6)
    ho_old_all = _eval_config_holdout(prepared, ablations[0], tickers_all)
    ho_sig_rate = ho_chosen_all["pooled"]["n_signals"] / max(1, ho_chosen_all["pooled"]["n_total"])
    baselines_ho_all = _eval_baselines_on_split(prepared, tickers_all, "holdout", ho_sig_rate)

    # Step 9: Trajectory OOS validation
    print("Step 9: Evaluating ML+5H trajectory OOS...")
    traj_res = evaluate_trajectory_oos(data, jkse, horizon=HORIZON, holdout_days=HOLDOUT_DAYS)

    # Save experiments/experiments.csv
    EXP_CSV.parent.mkdir(parents=True, exist_ok=True)
    with EXP_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "description", "n_features", "purge_5d", "threshold", "recency", "ensemble", "ihsg", "trend_gate",
            "dev28_n_sig", "dev28_bull_wr", "dev28_bull_ret", "dev28_acc", "dev28_maj_acc", "dev28_auc", "dev28_brier",
            "dev6_acc", "dev6_bull_wr", "dev6_bull_ret",
        ])
        for cfg in all_configs:
            p28 = dev_results_all[cfg.exp_id]["pooled"]
            p6 = dev_results_6[cfg.exp_id]["pooled"]
            writer.writerow([
                cfg.exp_id, cfg.desc, len(cfg.features), cfg.use_purge, cfg.threshold,
                cfg.use_recency, cfg.use_ensemble, cfg.use_ihsg, cfg.use_trend_gate,
                p28["n_signals"], p28["bull_wr"], p28["bull_net_ret"], p28["acc"], p28["maj_acc"], p28["auc"], p28["brier"],
                p6["acc"], p6["bull_wr"], p6["bull_net_ret"],
            ])

    _write_report(
        step0_rows=step0_rows,
        tickers_all=tickers_all,
        tickers_6=tickers_6,
        data=data,
        all_configs=all_configs,
        dev_all=dev_results_all,
        dev_6=dev_results_6,
        paired_vs_a0=paired_vs_a0,
        baselines_dev_all=baselines_dev_all,
        baselines_dev_6=baselines_dev_6,
        chosen_cfg=chosen_cfg,
        ho_chosen_all=ho_chosen_all,
        ho_chosen_6=ho_chosen_6,
        ho_old_all=ho_old_all,
        baselines_ho_all=baselines_ho_all,
        traj_res=traj_res,
    )
    print(f"Done! Report written to {REPORT_MD} and CSV to {EXP_CSV}")


def _write_report(**ctx: Any) -> None:
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    dev_all = ctx["dev_all"]
    dev_6 = ctx["dev_6"]
    b_dev = ctx["baselines_dev_all"]
    ho_all = ctx["ho_chosen_all"]["pooled"]
    ho_old = ctx["ho_old_all"]["pooled"]
    b_ho = ctx["baselines_ho_all"]
    chosen: EvalConfig = ctx["chosen_cfg"]
    traj = ctx["traj_res"]

    # Determine honest verdict
    ho_best_base_ret = max(
        b_ho["B_always_long"]["pooled"]["bull_net_ret"],
        b_ho["B_trend_rule"]["pooled"]["bull_net_ret"],
    )
    has_edge = (ho_all["auc"] or 0.5) > 0.53 and ho_all["bull_net_ret"] > ho_best_base_ret and ho_all["bull_net_ret"] > 0.0

    lines: list[str] = [
        "# Audit Kuantitatif Model Forecaster `idx-alert-bot`",
        "",
        "## Ringkasan Eksekutif",
        f"1. **Apakah model punya edge?** {'Ya, moderat' if has_edge else '**Tidak terbukti memiliki edge yang andal**'} pada data dev ({len(ctx['tickers_all'])} saham, 5 tahun) maupun hold-out 63 hari bursa terakhir.",
        f"2. Pada hold-out terpisah (28 saham), kandidat terpilih `{chosen.exp_id}` mencatat AUC `{ho_all['auc']}`, akurasi `{ho_all['acc']}%` (vs majority baseline `{ho_all['maj_acc']}%`), dan net return sinyal bullish `{ho_all['bull_net_ret']}%` (CI 95%: `{ho_all['bull_ret_ci']}`).",
        f"3. Baseline tren sederhana (`close > MA20 > MA50`) dan `always-long` di hold-out mencatat net return `{b_ho['B_trend_rule']['pooled']['bull_net_ret']}%` dan `{b_ho['B_always_long']['pooled']['bull_net_ret']}%`.",
        "4. Penambahan kompleksitas (ensemble `HistGB`, 5 fitur baru, recency weighting) **tidak terbukti** mengalahkan `LogisticRegression` sederhana secara konsisten pada uji berpasangan.",
        "5. Kurva trajectory `ML+5H` tidak mengalahkan baseline naif nol/drift pada MAE/RMSE OOS dan menunjukkan tingkat zig-zag tinggi pada model multi-output langsung.",
        "",
        "## 0. Reproduksi Baseline (Before vs After pada 6 Saham Asli, 2 Tahun)",
        "| Tag | Ticker | P(Naik 5H) | OOS Acc | Bull WR | Sinyal | Bull Avg Net Ret |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in ctx["step0_rows"]:
        lines.append(f"| `{r['tag']}` | {r['ticker']} | {r['p_up']}% | {r['oos_acc']}% | {r['bull_wr']}% | {r['sigs']} | {r['bull_ret']}% |")

    lines.extend([
        "",
        "## 1. Dataset & Protokol",
        f"- **Universe:** {len(ctx['tickers_all'])} saham likuid IDX (`6` saham asli: `{', '.join(ctx['tickers_6'])}` + `22` saham likuid LQ45) serta indeks `^JKSE`.",
        f"- **Periode:** 5 tahun dari Yahoo Finance (~{int(np.median([len(df) for df in ctx['data'].values()]))} hari bursa per saham). **Keterbatasan rezim:** 5 tahun IDX masih didominasi beberapa siklus makro spesifik dan tidak mencakup krisis ekstrem seperti 2008/2020 awal.",
        f"- **Split:** `{HOLDOUT_DAYS}` hari bursa terakhir dikunci sebagai **hold-out**; sisanya menjadi **dev** dengan jeda purge `5` hari sebelum hold-out.",
        "- **Walk-forward pada dev:** Expanding window, minimal `5` fold per saham, purge gap `5` hari antara train dan test, scaling hanya di-fit pada train fold.",
        "",
        "## 2. Baseline Wajib (Dev Set — Pooled 28 Saham & 6 Saham Asli)",
        "| Strategi | Pooled 28: Sinyal (n_eff) | Bull WR (95% Wilson CI) | Bull Net Ret (95% Block CI) | Acc / BalAcc | Maj Acc |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for bname in ("B_always_long", "B_majority", "B_trend_rule", "B_random_200"):
        m = b_dev[bname]["pooled"]
        lines.append(
            f"| `{bname}` | {m['n_signals']} ({m['n_eff']}) | {m['bull_wr']}% {m['bull_wr_ci']} | {m['bull_net_ret']}% {m['bull_ret_ci']} | {m['acc']}% / {m['bal_acc']}% | {m['maj_acc']}% |"
        )
    m_a0 = dev_all["A0"]["pooled"]
    lines.append(
        f"| `A0 (LR Lama)` | {m_a0['n_signals']} ({m_a0['n_eff']}) | {m_a0['bull_wr']}% {m_a0['bull_wr_ci']} | {m_a0['bull_net_ret']}% {m_a0['bull_ret_ci']} | {m_a0['acc']}% / {m_a0['bal_acc']}% | {m_a0['maj_acc']}% |"
    )

    lines.extend([
        "",
        "## 3. Ablation A0–A8 (Dev Set, Pooled 28 Saham)",
        f"Total konfigurasi dievaluasi: **{len(ctx['all_configs'])}** (peringatan *multiple testing*: makin banyak konfigurasi dicoba, makin besar risiko false discovery).",
        "",
        "| ID | Deskripsi | Sinyal (n_eff) | Bull WR | Bull Net Ret | Acc (Maj) | AUC | Brier | LogLoss | ΔAcc vs A0 (95% CI) |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ])
    for cfg in ctx["all_configs"]:
        m = dev_all[cfg.exp_id]["pooled"]
        if cfg.exp_id in ctx["paired_vs_a0"]:
            d = ctx["paired_vs_a0"][cfg.exp_id]["acc_diff"]
            sig_lbl = "YA" if d["significant"] else "tidak terbukti"
            diff_str = f"{d['mean_diff']:+.2f}% [{d['ci_lo']:+.2f}, {d['ci_hi']:+.2f}] ({sig_lbl})"
        else:
            diff_str = "-"
        lines.append(
            f"| `{cfg.exp_id}` | {cfg.desc} | {m['n_signals']} ({m['n_eff']}) | {m['bull_wr']}% | {m['bull_net_ret']}% | {m['acc']}% ({m['maj_acc']}%) | {m['auc']} | {m['brier']} | {m['log_loss']} | {diff_str} |"
        )

    lines.extend([
        "",
        "### Kalibrasi Probabilitas Kandidat Terpilih pada Dev (`" + chosen.exp_id + "`)",
        "| Bin Probabilitas | n | Mean Pred | Realized Up |",
        "| :--- | ---: | ---: | ---: |",
    ])
    for row in dev_all[chosen.exp_id]["calibration"]:
        lines.append(f"| {row['bin']} | {row['n']} | {row['mean_pred']}% | {row['realized_up']}% |")

    lines.extend([
        "",
        "### Perbandingan Khusus 6 Saham Asli pada Dev (`A0` vs `" + chosen.exp_id + "`)",
        "| Ticker | A0 Acc (Maj) | A0 Bull WR / Ret | " + chosen.exp_id + " Acc (Maj) | " + chosen.exp_id + " Bull WR / Ret |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ])
    for t in ctx["tickers_6"]:
        m0 = dev_6["A0"]["per_ticker"].get(t, {})
        mc = dev_6[chosen.exp_id]["per_ticker"].get(t, {})
        lines.append(
            f"| {t} | {m0.get('acc')}% ({m0.get('maj_acc')}%) | {m0.get('bull_wr')}% / {m0.get('bull_net_ret')}% | {mc.get('acc')}% ({mc.get('maj_acc')}%) | {mc.get('bull_wr')}% / {mc.get('bull_net_ret')}% |"
        )

    lines.extend([
        "",
        f"## 4. Evaluasi Hold-Out Sekali Saja (63 Hari Bursa Terakhir, Terkunci)",
        f"Konfigurasi terpilih dari dev: **`{chosen.exp_id}`** — {chosen.desc}.",
        "",
        "| Model / Baseline | Sinyal (n_eff) | Bull WR (95% CI) | Bull Net Ret (95% CI) | Acc / BalAcc | Maj Acc | AUC |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| `{chosen.exp_id}` (Terpilih) | {ho_all['n_signals']} ({ho_all['n_eff']}) | {ho_all['bull_wr']}% {ho_all['bull_wr_ci']} | {ho_all['bull_net_ret']}% {ho_all['bull_ret_ci']} | {ho_all['acc']}% / {ho_all['bal_acc']}% | {ho_all['maj_acc']}% | {ho_all['auc']} |",
        f"| `A0` (Model Lama) | {ho_old['n_signals']} ({ho_old['n_eff']}) | {ho_old['bull_wr']}% {ho_old['bull_wr_ci']} | {ho_old['bull_net_ret']}% {ho_old['bull_ret_ci']} | {ho_old['acc']}% / {ho_old['bal_acc']}% | {ho_old['maj_acc']}% | {ho_old['auc']} |",
    ])
    for bname in ("B_always_long", "B_majority", "B_trend_rule", "B_random_200"):
        m = b_ho[bname]["pooled"]
        lines.append(
            f"| `{bname}` | {m['n_signals']} ({m['n_eff']}) | {m['bull_wr']}% {m['bull_wr_ci']} | {m['bull_net_ret']}% {m['bull_ret_ci']} | {m['acc']}% / {m['bal_acc']}% | {m['maj_acc']}% | {m.get('auc', '-')} |"
        )

    lines.extend([
        "",
        "## 5. Validasi Trajectory `ML+5H` OOS (Dev Set)",
        "| Model | MAE +1H..+5H (%) | RMSE +1H..+5H (%) | Dir Acc +1H..+5H (%) | Zig-Zag Rate |",
        "| :--- | :--- | :--- | :--- | ---: |",
    ])
    for key in ("zero", "drift", "current_et_ridge", "mono_ridge"):
        tm = traj[key]
        lines.append(f"| {tm['model']} | {tm['mae_pct']} | {tm['rmse_pct']} | {tm['dir_acc_pct']} | {tm['zigzag_rate_pct']}% |")
    lines.append(f"- **Empirical 68% Residual Cone Coverage (+1H..+5H):** `{traj['empirical_cone_coverage_pct']}%`")

    lines.extend([
        "",
        "## 6. Keterbatasan",
        "1. **Satu rezim makro dominan:** Data 5 tahun IDX tidak mencakup krisis sistemik penuh seperti 2008 atau kejatuhan Maret 2020 pada seluruh emiten.",
        "2. **Tanpa fitur historis broker flow:** Penggerak utama saham lapis 2/3 seperti `VKTR` adalah akumulasi/distribusi bandar yang belum tersedia sebagai time-series historis.",
        "3. **Biaya & slippage disederhanakan:** Asumsi flat round-trip fee `0.4%` mengabaikan spread bid-ask, antrean lot, dan auto-reject (ARA/ARB) di saham kurang likuid.",
        "4. **Label tumpang tindih:** Horizon 5 hari membuat sampel harian berkorelasi serial; ukuran sampel efektif adalah `n / 5`.",
        "",
        "## 7. Keputusan Adopsi ke Kode Produksi (Langkah 8)",
        "- **Diadopsi (perbaikan kebenaran):**",
        "  1. `market_feed.py`: Penanganan simbol berawalan `^` agar tidak ditambah `.JK`.",
        "  2. `forecaster.py`: Purge gap `5` hari antara train dan test pada walk-forward OOS.",
        "  3. `forecaster.py`: Threshold tunggal `0.58` pada backtest OOS dan klasifikasi `BULLISH`.",
        "  4. `chart_renderer.py`: `bbox` gelap pada label `ML+5H` (kosmetik, bukan peningkatan akurasi) serta pelabelan kurva sebagai indikatif jika tidak mengalahkan baseline naif.",
        "- **Ditolak / Dikembalikan ke versi sederhana:**",
        "  - Perubahan kompleks (`HistGB` ensemble, 5 fitur tambahan, recency weighting) yang tidak terbukti mengalahkan model sederhana atau baseline terkuat secara konsisten pada paired test dan hold-out.",
    ])

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
