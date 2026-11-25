"""Reproducible v2 quantitative audit runner: python -m src.eval.run_v2"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import ROUND_TRIP_FEE
from src.eval.features import ORIG_FEATURES, prepare_eval_dataframe
from src.eval.h1_volatility import run_h1_evaluation
from src.eval.h2_mean_reversion import run_h2_evaluation
from src.eval.snapshot import apply_liquidity_and_segments, load_snapshot
from src.eval.stats_v2 import date_clustered_bootstrap_ci, independent_bootstrap_ci, random_baseline_matched

ROOT_DIR = Path(__file__).resolve().parents[2]
EXP_V2_CSV = ROOT_DIR / "experiments" / "experiments_v2.csv"
REPORT_V2_MD = ROOT_DIR / "reports" / "evaluation_v2.md"

HORIZON = 5
FEE = ROUND_TRIP_FEE


def _ema_smooth(probs: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    out = np.empty_like(probs, dtype=float)
    out[0] = float(probs[0])
    for i in range(1, len(probs)):
        out[i] = alpha * float(probs[i]) + (1.0 - alpha) * out[i - 1]
    return out


def _non_overlapping_idx(mask: np.ndarray, hold: int = 5) -> np.ndarray:
    keep = np.zeros_like(mask, dtype=bool)
    cd = 0
    for i in range(len(mask)):
        if cd > 0:
            cd -= 1
            continue
        if mask[i]:
            keep[i] = True
            cd = hold
    return keep


def _reaudit_v1_on_lock_recent(
    data: dict[str, pd.DataFrame],
    jkse_df: pd.DataFrame,
) -> dict[str, Any]:
    """
    Fixes cacat (a)-(f) for v1 A0 vs A1_th58 on LOCK-RECENT (126 bars) as reference only.
    Demonstrates cacat (d): old _eval_config_holdout forced purge=5 even for A0 (use_purge=False).
    """
    feat_cols = list(ORIG_FEATURES)

    def _run_v1_model(use_purge: bool, thresh: float) -> dict[str, Any]:
        dates_all, preds_all, probs_all, act_all, rets_all, ew_all = [], [], [], [], [], []
        no_ov_dates, no_ov_rets, no_ov_ew = [], [], []

        # Precompute equal-weight 5d return per date across liquid bars
        ew_rows = []
        for t, df in data.items():
            p = prepare_eval_dataframe(df, jkse_df=jkse_df, horizon_days=HORIZON, fee=FEE)
            sub = p[(p["segment"] == "LOCK-RECENT") & p["liq_ok"]].dropna(subset=["fwd_ret"])
            if not sub.empty:
                ew_rows.append(sub[["date", "fwd_ret"]])
        ew_map = pd.concat(ew_rows, ignore_index=True).groupby("date")["fwd_ret"].mean()

        for t, df in data.items():
            p = prepare_eval_dataframe(df, jkse_df=jkse_df, horizon_days=HORIZON, fee=FEE)
            labeled = p[p["liq_ok"]].dropna(subset=feat_cols + ["fwd_ret"]).reset_index(drop=True)
            if len(labeled) < 200:
                continue
            lock_mask = labeled["segment"] == "LOCK-RECENT"
            if not lock_mask.any():
                continue
            lock_start = int(np.where(lock_mask.to_numpy())[0][0])
            tr_end = lock_start - (HORIZON if use_purge else 0)
            train_df = labeled.iloc[:tr_end]
            test_df = labeled.iloc[lock_start:]
            if len(test_df) == 0 or train_df["target_up"].nunique() < 2:
                continue

            m = Pipeline([("s", StandardScaler()), ("clf", LogisticRegression(C=0.5, max_iter=500, random_state=42))])
            m.fit(train_df[feat_cols], train_df["target_up"].astype(int))
            probs = _ema_smooth(m.predict_proba(test_df[feat_cols])[:, 1], alpha=0.5)
            preds = (probs >= thresh).astype(int)

            d_arr = test_df["date"].to_numpy()
            r_arr = test_df["fwd_ret"].to_numpy(dtype=float)
            ew_arr = pd.Series(d_arr).map(ew_map).fillna(0.0).to_numpy(dtype=float)

            dates_all.extend(d_arr.tolist())
            preds_all.extend(preds.tolist())
            probs_all.extend(probs.tolist())
            act_all.extend(test_df["target_up"].astype(int).to_numpy().tolist())
            rets_all.extend(r_arr.tolist())
            ew_all.extend(ew_arr.tolist())

            keep_no = _non_overlapping_idx(preds == 1, HORIZON)
            if keep_no.any():
                no_ov_dates.extend(d_arr[keep_no].tolist())
                no_ov_rets.extend(r_arr[keep_no].tolist())
                no_ov_ew.extend(ew_arr[keep_no].tolist())

        preds_np = np.array(preds_all)
        probs_np = np.array(probs_all)
        act_np = np.array(act_all)
        rets_np = np.array(rets_all)
        ew_np = np.array(ew_all)
        dates_np = np.array(dates_all)

        bm = preds_np == 1
        n_sig = int(bm.sum())
        net_rets = (rets_np[bm] - FEE) * 100.0
        excess_rets = ((rets_np[bm] - FEE) - ew_np[bm]) * 100.0

        ci_old = independent_bootstrap_ci(net_rets, block_size=5, n_boot=2000, seed=42)
        ci_new = date_clustered_bootstrap_ci(dates_np[bm], net_rets, block_size=10, n_boot=5000, seed=42)
        ex_ci = date_clustered_bootstrap_ci(dates_np[bm], excess_rets, block_size=10, n_boot=5000, seed=42)

        no_ov_ex = ((np.array(no_ov_rets) - FEE) - np.array(no_ov_ew)) * 100.0
        no_ov_ci = date_clustered_bootstrap_ci(np.array(no_ov_dates), no_ov_ex, block_size=10, n_boot=5000, seed=42)

        all_ex = ((rets_np - FEE) - ew_np) * 100.0
        rand_matched = random_baseline_matched(dates_np, all_ex, n_sig, n_seeds=500, seed=42)
        auc = round(float(roc_auc_score(act_np, probs_np)), 4) if len(np.unique(act_np)) > 1 else None
        ew_mkt_ci = date_clustered_bootstrap_ci(dates_np, (ew_np - FEE) * 100.0, block_size=10, n_boot=5000, seed=42)

        return {
            "n_total": len(act_np),
            "n_sig": n_sig,
            "n_eff": round(n_sig / 5.0, 1),
            "auc": auc,
            "acc": round(float(np.mean(preds_np == act_np)) * 100.0, 2),
            "maj_acc": round(max(float(np.mean(act_np)), 1.0 - float(np.mean(act_np))) * 100.0, 2),
            "ci_old_indep": ci_old,
            "ci_new_clustered": ci_new,
            "excess_ci": ex_ci,
            "no_overlap_n": len(no_ov_rets),
            "no_overlap_ex_ci": no_ov_ci,
            "rand_matched": rand_matched,
            "ew_market_net_ci": ew_mkt_ci,
        }

    # JKSE 5d return on LOCK-RECENT
    jk_ret5 = pd.DataFrame()
    if not jkse_df.empty:
        jc = jkse_df["close"].astype(float)
        jk = jkse_df[["date"]].copy()
        jk["fwd5"] = ((jc.shift(-HORIZON) / jc) - 1.0 - FEE) * 100.0
        lock_dates = set()
        for df in data.values():
            lock_dates.update(df[df["segment"] == "LOCK-RECENT"]["date"].astype(str).tolist())
        jk = jk[jk["date"].isin(lock_dates)].dropna()
        jk_ci = date_clustered_bootstrap_ci(jk["date"].to_numpy(), jk["fwd5"].to_numpy(), block_size=10, n_boot=5000, seed=42)
    else:
        jk_ci = {"mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}

    return {
        "A0_true_nopurge": _run_v1_model(use_purge=False, thresh=0.55),
        "A1_th58_purge": _run_v1_model(use_purge=True, thresh=0.58),
        "jkse_net_ci": jk_ci,
    }


def main() -> None:
    prereg_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT_DIR), text=True).strip()
    raw_data, jkse_df, manifest = load_snapshot()
    data, liq_stats = apply_liquidity_and_segments(raw_data)

    print("Step 1: Re-auditing v1 on LOCK-RECENT with fixed protocol...")
    v1_reaudit = _reaudit_v1_on_lock_recent(data, jkse_df)

    print("Step 2: Running H1 (volatility & calibrated cones)...")
    h1_res = run_h1_evaluation(data, jkse_df)

    print("Step 3: Running H2 (mean reversion)...")
    h2_res = run_h2_evaluation(data, jkse_df)

    # Save experiments/experiments_v2.csv
    EXP_V2_CSV.parent.mkdir(parents=True, exist_ok=True)
    with EXP_V2_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "id", "description", "segment", "metric_1", "metric_2", "ci_or_detail"])
        for cid, m in h1_res["disc_table"].items():
            w.writerow(["H1_vol", cid, f"Vol candidate {cid}", "DISCOVERY", f"qlike={m['qlike']}", f"mae_log={m['mae_log']}", f"dm_vs_v0={m['dm_vs_v0']}"])
        w.writerow(["H1_vol", h1_res["best_cand"], "Selected H1 candidate", "LOCK-RECENT", f"qlike={h1_res['lock_qlike_best']}", f"cov68={h1_res['lock_cone_best']['cov68_5d']}", f"cov90={h1_res['lock_cone_best']['cov90_5d']}"])
        for rid, m in h2_res["disc_res"].items():
            w.writerow(["H2_mr", rid, f"Mean reversion {rid}", "DISCOVERY", f"n={m.get('n_sig')}", f"ex_mean={m.get('excess_ci',{}).get('mean')}", f"p_holm={m.get('p_holm')}"])
        if h2_res["chosen_rule"]:
            cr = h2_res["chosen_rule"]
            if h2_res["fresh_res"]:
                w.writerow(["H2_mr", cr, "Chosen H2 rule", "FRESH-PAST", f"n={h2_res['fresh_res']['n_sig']}", f"ex={h2_res['fresh_res']['excess_ci']['mean']}", f"ci={h2_res['fresh_res']['excess_ci']}"])
            if h2_res["lock_res"]:
                w.writerow(["H2_mr", cr, "Chosen H2 rule", "LOCK-RECENT", f"n={h2_res['lock_res']['n_sig']}", f"ex={h2_res['lock_res']['excess_ci']['mean']}", f"ci={h2_res['lock_res']['excess_ci']}"])

    _write_v2_report(prereg_hash, manifest, liq_stats, v1_reaudit, h1_res, h2_res)
    print(f"Done! Written {REPORT_V2_MD} and {EXP_V2_CSV}")


def _write_v2_report(
    prereg_hash: str,
    manifest: dict[str, Any],
    liq_stats: dict[str, Any],
    v1_reaudit: dict[str, Any],
    h1: dict[str, Any],
    h2: dict[str, Any],
) -> None:
    REPORT_V2_MD.parent.mkdir(parents=True, exist_ok=True)
    a0 = v1_reaudit["A0_true_nopurge"]
    a1 = v1_reaudit["A1_th58_purge"]

    h1_lbl = "**LOLOS**" if h1["h1_passed"] else "**TIDAK TERBUKTI**"
    h2_lbl = f"**{h2['h2_status'].upper()}**"

    lines = [
        "# Audit Kuantitatif v2 (`idx-alert-bot`) — Protokol Terkoreksi, H1 & H2",
        "",
        f"**Commit Pra-Registrasi:** `{prereg_hash}` (`reports/prereg.md`)",
        f"**Snapshot Data:** `{manifest['created_at_utc']}` (`data_snapshot/manifest.json`, range `{manifest['range_str']}`)",
        "",
        "## Ringkasan Eksekutif",
        f"1. **H1 (Volatilitas & Cone):** {h1_lbl} — kandidat terpilih `{h1['best_cand']}` pada `LOCK-RECENT` mencatat coverage 5H `68%`: `{h1['lock_cone_best']['cov68_5d']}%` dan `90%`: `{h1['lock_cone_best']['cov90_5d']}%` (QLIKE `{h1['lock_qlike_best']}` vs `V0` `{h1['lock_qlike_v0']}`).",
        f"2. **H2 (Mean Reversion):** {h2_lbl} — varian terpilih di `DISCOVERY`: `{h2['chosen_rule'] or 'Tidak ada yang lolos koreksi Holm'}`.",
        f"3. **Perbandingan CI (Cacat a):** Pada `A1_th58` di `LOCK-RECENT`, CI lama (independen) adalah `{a1['ci_old_indep']}` sedangkan CI baru berkluster tanggal adalah `[{a1['ci_new_clustered']['ci_lo']}, {a1['ci_new_clustered']['ci_hi']}]` — CI lama terlalu sempit karena mengabaikan korelasi silang harian.",
        f"4. **Audit ulang v1 (Cacat d):** AUC `A0` dan `A1_th58` sebelumnya identik (`0.4728`) karena bug di `_eval_config_holdout` yang memaksa `holdout_start - HORIZON` (purge=5) untuk `A0` juga. Setelah diperbaiki, `A0` (tanpa purge) AUC=`{a0['auc']}` vs `A1_th58` AUC=`{a1['auc']}`.",
        f"5. **Produksi:** Model direksional probabilistik v1 (`P(Naik 5H)`, `BULLISH/BEARISH/NETRAL`) dihapus dari tampilan default (disimpan di balik `LEGACY_ML_SIGNAL=False`) dan diganti indikator deskriptif.",
        "",
        "## 1. Snapshot Data & Filter Likuiditas",
        f"- **Saham sebelum filter:** `{liq_stats['total_tickers']}` | **Lolos filter likuiditas (median 60H >= Rp 5 Miliar):** `{liq_stats['kept_tickers']}` | **Dieliminasi:** `{liq_stats['eliminated_tickers']}`",
        f"- **Bar mentah:** `{liq_stats['total_bars_raw']}` | **Lolos likuiditas:** `{liq_stats['total_bars_after_liq']}` (`FRESH-PAST`: `{liq_stats['fresh_past_bars']}`, `DISCOVERY`: `{liq_stats['discovery_bars']}`, `LOCK-RECENT`: `{liq_stats['lock_recent_bars']}`).",
        "",
        "## 2. Audit Ulang v1 pada `LOCK-RECENT` (Perbaikan Cacat a–f, Referensi Saja)",
        "| Model | Sinyal (n_eff) | Non-Overlap n | AUC | Acc (Maj) | CI Independen (v1) | CI Kluster Tanggal (v2) | Excess vs EW Market (95% CI) | Random Matched (p2.5/p50/p97.5) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| `A0` (true no-purge) | {a0['n_sig']} ({a0['n_eff']}) | {a0['no_overlap_n']} | {a0['auc']} | {a0['acc']}% ({a0['maj_acc']}%) | {a0['ci_old_indep']} | [{a0['ci_new_clustered']['ci_lo']}, {a0['ci_new_clustered']['ci_hi']}] | {a0['excess_ci']['mean']}% [{a0['excess_ci']['ci_lo']}, {a0['excess_ci']['ci_hi']}] | {a0['rand_matched']} |",
        f"| `A1_th58` (purge=5) | {a1['n_sig']} ({a1['n_eff']}) | {a1['no_overlap_n']} | {a1['auc']} | {a1['acc']}% ({a1['maj_acc']}%) | {a1['ci_old_indep']} | [{a1['ci_new_clustered']['ci_lo']}, {a1['ci_new_clustered']['ci_hi']}] | {a1['excess_ci']['mean']}% [{a1['excess_ci']['ci_lo']}, {a1['excess_ci']['ci_hi']}] | {a1['rand_matched']} |",
        f"- **Baseline Pasar `LOCK-RECENT`:** Equal-weight universe net = `{a1['ew_market_net_ci']['mean']}%` `[{a1['ew_market_net_ci']['ci_lo']}, {a1['ew_market_net_ci']['ci_hi']}]`; `^JKSE` net = `{v1_reaudit['jkse_net_ci']['mean']}%` `[{v1_reaudit['jkse_net_ci']['ci_lo']}, {v1_reaudit['jkse_net_ci']['ci_hi']}]`.",
        f"- **Non-overlapping `A1_th58` excess return:** `{a1['no_overlap_ex_ci']['mean']}%` `[{a1['no_overlap_ex_ci']['ci_lo']}, {a1['no_overlap_ex_ci']['ci_hi']}]`.",
        "",
        "## 3. Pengujian H1: Prediksi Volatilitas & Cone Terkalibrasi",
        f"*Catatan: `V4` (GARCH(1,1)) dilewati karena pustaka `arch` tidak terpasang.* Total kandidat diuji: `7` (`V0, V1, V2, V3, V5, V6, V7`).",
        "",
        "### Perbandingan Kandidat di `DISCOVERY`",
        "| Kandidat | QLIKE | MAE log-vol | DM Loss Diff vs V0 (95% CI Kluster Tanggal) |",
        "| :--- | ---: | ---: | :--- |",
    ]
    for cid, m in h1["disc_table"].items():
        dm = m["dm_vs_v0"]
        lines.append(f"| `{cid}` | {m['qlike']} | {m['mae_log']} | {dm['mean']} [{dm['ci_lo']}, {dm['ci_hi']}] (p={dm['p_val']}) |")

    lc = h1["lock_cone_best"]
    lv0 = h1["lock_cone_v0"]
    lines.extend([
        "",
        f"### Evaluasi Tunggal `LOCK-RECENT` (`{h1['best_cand']}` vs `V0`)",
        f"- **QLIKE:** `{h1['best_cand']}` = `{h1['lock_qlike_best']}` vs `V0` = `{h1['lock_qlike_v0']}` | **DM Diff:** `{h1['lock_dm_diff']['mean']}` `[{h1['lock_dm_diff']['ci_lo']}, {h1['lock_dm_diff']['ci_hi']}]`",
        f"- **Coverage Pooled +1..+5H (`{h1['best_cand']}`):** 68% = `{lc['cov68_by_h']}` | 90% = `{lc['cov90_by_h']}`",
        f"- **Coverage Pooled +5H (`V0`):** 68% = `{lv0['cov68_5d']}%` | 90% = `{lv0['cov90_5d']}%`",
        f"- **Saham individual dalam +-6 poin (`{h1['best_cand']}`):** 68% = `{lc['pct_tickers_within_6pp_68']}%`, 90% = `{lc['pct_tickers_within_6pp_90']}%`",
        f"- **Coverage bersyarat 68% (`{h1['best_cand']}`):** Vol Tinggi = `{lc['cond_hi_vol_68']}%`, Vol Rendah = `{lc['cond_lo_vol_68']}%`, IHSG Turun = `{lc['cond_jkse_down_68']}%`",
        f"- **Skala empiris vs sqrt(h):** Empiris = `{lc['empirical_scale_by_h']}` vs `sqrt(h)` = `{lc['sqrt_h_ref']}`",
        "",
        "## 4. Pengujian H2: Mean Reversion (6 Varian, Koreksi Holm)",
        "| Varian | Sinyal (n_eff) | Excess Return vs EW (95% CI Kluster) | p-val (p-Holm) | Random (p2.5/p50/p97.5) | % Thn Pos | % Saham Pos | Fee 0.6% / 1.0% | Open t+1 | Non-Overlap Excess |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for rid, m in h2["disc_res"].items():
        if m.get("n_sig", 0) == 0:
            lines.append(f"| `{rid}` | 0 (0) | - | 1.0 (1.0) | - | - | - | - | - | - |")
            continue
        ec = m["excess_ci"]
        no = m["non_overlap_ex_ci"]
        lines.append(
            f"| `{rid}` | {m['n_sig']} ({m['n_eff']}) | {ec['mean']}% [{ec['ci_lo']}, {ec['ci_hi']}] | {ec['p_val']} ({m['p_holm']}) | {m['rand_pct']['p2_5']}/{m['rand_pct']['p50']}/{m['rand_pct']['p97_5']}% | {m['pct_pos_years']}% | {m['pct_pos_tickers']}% | {m['ex_fee_06']}% / {m['ex_fee_10']}% | {m['ex_open_t1']}% | {no['mean']}% [{no['ci_lo']}, {no['ci_hi']}] |"
        )

    if h2["chosen_rule"]:
        cr = h2["chosen_rule"]
        lines.append(f"\n### Evaluasi Konfirmasi `{cr}` pada `FRESH-PAST` dan `LOCK-RECENT`")
        for seg_lbl, sres in [("FRESH-PAST", h2["fresh_res"]), ("LOCK-RECENT", h2["lock_res"])]:
            if sres:
                ec = sres["excess_ci"]
                lines.append(
                    f"- **{seg_lbl}:** n=`{sres['n_sig']}` (`n_eff={sres['n_eff']}`), excess=`{ec['mean']}%` `[{ec['ci_lo']}, {ec['ci_hi']}]`, random_p97.5=`{sres['rand_pct']['p97_5']}%`, %thn_pos=`{sres['pct_pos_years']}%`, fee_0.6%=`{sres['ex_fee_06']}%`, open_t1=`{sres['ex_open_t1']}%`"
                )
    else:
        lines.append(f"\n- **Status H2:** `{h2['h2_status']}` — tidak ada varian yang lolos koreksi Holm di `DISCOVERY`, sehingga `FRESH-PAST` dan `LOCK-RECENT` tidak dievaluasi.")

    lines.extend([
        "",
        "## 5. Keterbatasan",
        "1. **Rezim pasar:** Data 10 tahun IDX tetap terikat siklus spesifik Indonesia dan tidak menjamin stabilitas di luar rezim tersebut.",
        "2. **Tanpa broker flow historis:** Fitur hanya OHLCV; dinamika bandarmologi/asing belum dimodelkan.",
        "3. **Biaya & likuiditas:** Meskipun ada filter median transaksi Rp 5 Miliar/hari dan sensitivitas fee 0.6%/1.0%, eksekusi riil tetap dipengaruhi spread bid-ask dan batas ARA/ARB.",
        "4. **Korelasi silang & label tumpang tindih:** Ditangani dengan bootstrap berkluster tanggal (blok 10 hari) dan versi posisi tunggal tidak tumpang tindih.",
        "",
        "## 6. Perubahan Produksi (Langkah 6)",
        "- Menghapus `P(Naik 5H)`, label `BULLISH/BEARISH/NETRAL` berbasis model, dan skor probabilitas dari tampilan default (`LEGACY_ML_SIGNAL=False`).",
        "- Mengganti ringkasan sinyal dengan indikator deskriptif non-probabilistik (RSI14, jarak MA20/MA50, posisi range 20H, rasio volume, volatilitas).",
        f"- Cone volatilitas pada chart: {'ditampilkan sebagai rentang volatilitas historis 68%/90% tanpa klaim arah' if h1['h1_passed'] else 'dihapus karena H1 tidak memenuhi kriteria adopsi'}.",
        f"- Sinyal mean reversion: {'ditambahkan sebagai kondisi oversold historis' if h2['h2_status'] == 'H2 LOLOS PENUH' else 'tidak ditambahkan karena H2 tidak lolos konfirmasi penuh'}.",
    ])
    REPORT_V2_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
