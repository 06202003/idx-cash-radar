"""
Trains IDX Cash Radar's proprietary, self-contained quantitative & NLP models:
1. L2-Regularized Logistic Solvency Classifier (trained on idx_cash_radar.db XBRL filings)
2. Multinomial Naive Bayes Indonesian Financial News Classifier (trained on daily_news_sentiment.json + BEI anchors)

Outputs lightweight JSON artifacts (<150 KB) into data/models/ for zero-dependency inference.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "idx_cash_radar.db"
NEWS_PATH = ROOT_DIR / "data" / "daily_news_sentiment.json"
MODELS_DIR = ROOT_DIR / "data" / "models"
SOLVENCY_OUT = MODELS_DIR / "idx_solvency_model.json"
MLP_OUT = MODELS_DIR / "idx_solvency_mlp_v1.json"
NEWS_NB_OUT = MODELS_DIR / "idx_news_nb.json"

FEATURE_NAMES = [
    "log_cash_coverage",
    "sloan_ratio",
    "cfo_margin",
    "receivable_intensity",
    "negative_cfo_flag",
]


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z_clip = np.clip(z, -20.0, 20.0)
    return 1.0 / (1.0 + np.exp(-z_clip))


def _roc_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    pos = y_prob[y_true == 1]
    neg = y_prob[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    wins = 0.0
    for p in pos:
        wins += float(np.sum(p > neg)) + 0.5 * float(np.sum(p == neg))
    return wins / (len(pos) * len(neg))


def _fit_l2_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0) -> tuple[float, np.ndarray]:
    n_features = X.shape[1]

    def loss_fn(params: np.ndarray) -> float:
        b0 = params[0]
        w = params[1:]
        p = np.clip(_sigmoid(b0 + X @ w), 1e-9, 1.0 - 1e-9)
        nll = -np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))
        reg = 0.5 * (l2 / len(y)) * float(np.sum(w ** 2))
        return float(nll + reg)

    # Monotonicity bounds matching FEATURE_NAMES:
    # [intercept, log_cash_coverage <= 0, sloan_ratio >= 0.05, cfo_margin <= 0,
    #  receivable_intensity >= 0, negative_cfo_flag >= 0]
    bounds = [
        (None, None),
        (None, 0.0),
        (0.05, None),
        (None, 0.0),
        (0.0, None),
        (0.0, None),
    ]
    res = minimize(loss_fn, np.zeros(n_features + 1), method="L-BFGS-B", bounds=bounds)
    return float(res.x[0]), res.x[1:].astype(float)


def train_solvency_model() -> dict[str, Any]:
    """Trains L2-regularized Logistic Solvency Classifier on audited BEI filings."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ticker, period_end_date, cash_coverage_ratio, sloan_ratio_ttm,
                   cfo_ttm_idr, revenue_ttm_idr, gross_contract_exposure_ratio,
                   debt_free_short_term, flag_acute_liquidity, flag_accrual_divergence
            FROM computed_metrics
            ORDER BY ticker, period_end_date
            """
        ).fetchall()

    X_raw: list[list[float]] = []
    y_list: list[int] = []

    for r in rows:
        debt_free = bool(r["debt_free_short_term"])
        cov = 8.0 if debt_free else float(r["cash_coverage_ratio"] or 0.0)
        cov = min(max(cov, 0.0), 10.0)
        log_cov = math.log1p(cov)

        sloan = min(max(float(r["sloan_ratio_ttm"] or 0.0), -1.0), 1.0)
        cfo = float(r["cfo_ttm_idr"] or 0.0)
        rev = float(r["revenue_ttm_idr"] or 0.0)
        cfo_margin = max(min(cfo / rev if rev > 0 else (0.0 if cfo >= 0 else -0.5), 2.0), -2.0)
        rec_int = min(max(float(r["gross_contract_exposure_ratio"] or 0.15), 0.0), 3.0)
        neg_cfo = 1.0 if cfo < 0 else 0.0

        # Ground-truth fundamental liquidity distress label from audited XBRL rules
        is_distress = int(
            bool(r["flag_acute_liquidity"])
            or (not debt_free and cov < 0.35 and cfo < 0)
            or (not debt_free and cov < 0.25)
        )

        X_raw.append([log_cov, sloan, cfo_margin, rec_int, neg_cfo])
        y_list.append(is_distress)

    X = np.array(X_raw, dtype=float)
    y = np.array(y_list, dtype=int)

    means = X.mean(axis=0)
    stds = np.where(X.std(axis=0) > 1e-6, X.std(axis=0), 1.0)
    X_std = (X - means) / stds

    # 5-fold stratified CV
    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    rng = np.random.default_rng(42)
    rng.shuffle(pos_idx)
    rng.shuffle(neg_idx)

    k = 5
    oof_probs = np.zeros(len(y), dtype=float)
    pos_folds = np.array_split(pos_idx, k)
    neg_folds = np.array_split(neg_idx, k)

    for fold in range(k):
        val_idx = np.concatenate([pos_folds[fold], neg_folds[fold]])
        train_mask = np.ones(len(y), dtype=bool)
        train_mask[val_idx] = False
        b0_f, w_f = _fit_l2_logistic(X_std[train_mask], y[train_mask], l2=1.2)
        oof_probs[val_idx] = _sigmoid(b0_f + X_std[val_idx] @ w_f)

    cv_auc = _roc_auc(y, oof_probs)
    cv_acc = float(np.mean((oof_probs >= 0.50).astype(int) == y))
    cv_brier = float(np.mean((oof_probs - y) ** 2))

    # Fit final model on all samples
    b0, w = _fit_l2_logistic(X_std, y, l2=1.2)

    artifact = {
        "model_name": "idx_solvency_l2_logit_v1",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_samples": int(len(y)),
        "positive_samples": int(np.sum(y)),
        "negative_samples": int(np.sum(y == 0)),
        "cv_folds": k,
        "cv_roc_auc": round(cv_auc, 4),
        "cv_accuracy": round(cv_acc, 4),
        "cv_brier_score": round(cv_brier, 4),
        "feature_names": FEATURE_NAMES,
        "feature_means": [round(float(m), 6) for m in means],
        "feature_stds": [round(float(s), 6) for s in stds],
        "intercept": round(b0, 6),
        "weights": {name: round(float(val), 6) for name, val in zip(FEATURE_NAMES, w)},
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    SOLVENCY_OUT.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def _tokenize_id(text: str) -> list[str]:
    clean = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    words = [w for w in clean.split() if len(w) >= 2]
    bigrams = [f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)]
    return words + bigrams


ANCHOR_NEWS_CORPUS: list[tuple[str, str]] = [
    ("suspensi perdagangan saham oleh bursa efek indonesia gagal bayar kupon sukuk", "PERHATIAN"),
    ("penundaan pembayaran pokok dan kupon obligasi sukuk mudharabah rups rupslb", "PERHATIAN"),
    ("gugatan pkpu pailit restrukturisasi utang bank macet gagal bayar", "PERHATIAN"),
    ("rugi bersih membengkak arus kas operasi negatif tekanan likuiditas", "PERHATIAN"),
    ("kredit macet penurunan peringkat utang default covenant breach", "PERHATIAN"),
    ("pembagian dividen tunai interim rekor laba bersih tumbuh positif", "POSITIF"),
    ("arus kas operasi menguat kas melimpah bebas utang jangka pendek", "POSITIF"),
    ("ekspansi pabrik baru kenaikan pendapatan penjualan tumbuh signifikan", "POSITIF"),
    ("peringkat kredit naik stabil prospek pertumbuhan kinerja keuangan solid", "POSITIF"),
    ("laporan hasil public expose tahunan penyampaian laporan keuangan", "NETRAL"),
    ("perubahan susunan direksi komisaris jadwal rapat umum pemegang saham", "NETRAL"),
    ("klarifikasi volatilitas transaksi bursa penjelasan keterbukaan informasi", "NETRAL"),
]


def train_news_nb_model() -> dict[str, Any]:
    """Trains Multinomial Naive Bayes on IDX daily news + curated BEI disclosure anchors."""
    docs: list[tuple[str, str]] = list(ANCHOR_NEWS_CORPUS)

    if NEWS_PATH.exists():
        raw = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
        by_ticker = raw.get("news") or raw.get("by_ticker") or {}
        for _, items in by_ticker.items():
            for item in items:
                hl = (item.get("headline") or "").strip()
                sent = (item.get("sentiment") or "NETRAL").strip().upper()
                if hl and sent in ("POSITIF", "NETRAL", "PERHATIAN"):
                    docs.append((hl, sent))

    classes = ["POSITIF", "NETRAL", "PERHATIAN"]
    vocab_counts: Counter[str] = Counter()
    tokenized = [(_tokenize_id(txt), lbl) for txt, lbl in docs]
    for toks, _ in tokenized:
        vocab_counts.update(toks)

    vocab = sorted([tok for tok, cnt in vocab_counts.items() if cnt >= 1])
    vocab_set = set(vocab)
    v_size = len(vocab)

    def fit_nb(train_docs: list[tuple[list[str], str]]) -> tuple[dict[str, float], dict[str, dict[str, float]], dict[str, float]]:
        cls_doc_cnt: Counter[str] = Counter()
        cls_tok_cnt: dict[str, Counter[str]] = {c: Counter() for c in classes}
        cls_total_toks: Counter[str] = Counter()
        for toks, lbl in train_docs:
            cls_doc_cnt[lbl] += 1
            for t in toks:
                if t in vocab_set:
                    cls_tok_cnt[lbl][t] += 1
                    cls_total_toks[lbl] += 1

        total_docs = max(len(train_docs), 1)
        log_priors = {c: math.log((cls_doc_cnt[c] + 0.5) / (total_docs + 1.5)) for c in classes}
        alpha = 1.0
        default_log = {}
        log_lik: dict[str, dict[str, float]] = {c: {} for c in classes}
        for c in classes:
            denom = cls_total_toks[c] + alpha * v_size
            default_log[c] = math.log(alpha / max(denom, 1.0))
            for t, cnt in cls_tok_cnt[c].items():
                log_lik[c][t] = math.log((cnt + alpha) / max(denom, 1.0))
        return log_priors, log_lik, default_log

    # 5-fold CV accuracy
    rng = np.random.default_rng(42)
    indices = np.arange(len(tokenized))
    rng.shuffle(indices)
    folds = np.array_split(indices, 5)
    correct = 0
    for fold in folds:
        val_set = set(fold.tolist())
        tr = [tokenized[i] for i in range(len(tokenized)) if i not in val_set]
        va = [tokenized[i] for i in fold]
        lp, ll, dl = fit_nb(tr)
        for toks, true_lbl in va:
            scores = {
                c: lp[c] + sum(ll[c].get(t, dl[c]) for t in toks if t in vocab_set)
                for c in classes
            }
            pred = max(classes, key=lambda c: scores[c])
            if pred == true_lbl:
                correct += 1

    cv_acc = correct / max(len(tokenized), 1)
    log_priors, log_lik, default_log = fit_nb(tokenized)

    artifact = {
        "model_name": "idx_news_multinomial_nb_v1",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_samples": len(tokenized),
        "vocab_size": v_size,
        "cv_accuracy": round(cv_acc, 4),
        "classes": classes,
        "log_priors": {c: round(v, 6) for c, v in log_priors.items()},
        "default_log_likelihood": {c: round(v, 6) for c, v in default_log.items()},
        "log_likelihoods": {
            c: {t: round(v, 6) for t, v in ll_map.items()}
            for c, ll_map in log_lik.items()
        },
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_NB_OUT.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def _fit_mlp_adam(
    X: np.ndarray,
    y: np.ndarray,
    epochs: int = 350,
    lr: float = 0.02,
    l2: float = 0.01,
    seed: int = 42,
) -> dict[str, Any]:
    """Trains a 3-layer Neural Network (5 -> 16 ReLU -> 8 ReLU -> 1 Sigmoid) with Adam."""
    rng = np.random.default_rng(seed)
    n, d_in = X.shape
    h1, h2 = 16, 8

    W1 = rng.normal(0.0, math.sqrt(2.0 / d_in), size=(d_in, h1))
    b1 = np.zeros(h1)
    W2 = rng.normal(0.0, math.sqrt(2.0 / h1), size=(h1, h2))
    b2 = np.zeros(h2)
    W3 = rng.normal(0.0, math.sqrt(2.0 / h2), size=(h2, 1))
    b3 = np.zeros(1)

    params = [W1, b1, W2, b2, W3, b3]
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    y_col = y.reshape(-1, 1)

    for t in range(1, epochs + 1):
        z1 = X @ W1 + b1
        a1 = np.maximum(0.0, z1)
        z2 = a1 @ W2 + b2
        a2 = np.maximum(0.0, z2)
        z3 = a2 @ W3 + b3
        p = _sigmoid(z3)

        dz3 = (p - y_col) / n
        dW3 = a2.T @ dz3 + (l2 / n) * W3
        db3 = np.sum(dz3, axis=0)

        da2 = dz3 @ W3.T
        dz2 = da2 * (z2 > 0.0)
        dW2 = a1.T @ dz2 + (l2 / n) * W2
        db2 = np.sum(dz2, axis=0)

        da1 = dz2 @ W2.T
        dz1 = da1 * (z1 > 0.0)
        dW1 = X.T @ dz1 + (l2 / n) * W1
        db1 = np.sum(dz1, axis=0)

        grads = [dW1, db1, dW2, db2, dW3, db3]
        for idx, (param, grad) in enumerate(zip(params, grads)):
            m[idx] = 0.9 * m[idx] + 0.1 * grad
            v[idx] = 0.999 * v[idx] + 0.001 * (grad ** 2)
            m_hat = m[idx] / (1.0 - 0.9 ** t)
            v_hat = v[idx] / (1.0 - 0.999 ** t)
            param -= lr * m_hat / (np.sqrt(v_hat) + 1e-8)

    return {
        "W1": W1.tolist(),
        "b1": b1.tolist(),
        "W2": W2.tolist(),
        "b2": b2.tolist(),
        "W3": W3.tolist(),
        "b3": b3.tolist(),
    }


def _mlp_predict(weights: dict[str, Any], X: np.ndarray) -> np.ndarray:
    W1 = np.array(weights["W1"], dtype=float)
    b1 = np.array(weights["b1"], dtype=float)
    W2 = np.array(weights["W2"], dtype=float)
    b2 = np.array(weights["b2"], dtype=float)
    W3 = np.array(weights["W3"], dtype=float)
    b3 = np.array(weights["b3"], dtype=float)

    a1 = np.maximum(0.0, X @ W1 + b1)
    a2 = np.maximum(0.0, a1 @ W2 + b2)
    return _sigmoid(a2 @ W3 + b3).ravel()


def train_neural_mlp_model() -> dict[str, Any]:
    """Trains the 3-layer Deep Learning MLP (5 -> 16 -> 8 -> 1) on audited BEI filings."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ticker, period_end_date, cash_coverage_ratio, sloan_ratio_ttm,
                   cfo_ttm_idr, revenue_ttm_idr, gross_contract_exposure_ratio,
                   debt_free_short_term, flag_acute_liquidity
            FROM computed_metrics
            ORDER BY ticker, period_end_date
            """
        ).fetchall()

    X_raw: list[list[float]] = []
    y_list: list[int] = []
    for r in rows:
        debt_free = bool(r["debt_free_short_term"])
        cov = 8.0 if debt_free else min(max(float(r["cash_coverage_ratio"] or 0.0), 0.0), 10.0)
        sloan = min(max(float(r["sloan_ratio_ttm"] or 0.0), -1.0), 1.0)
        cfo = float(r["cfo_ttm_idr"] or 0.0)
        rev = float(r["revenue_ttm_idr"] or 0.0)
        cfo_margin = max(min(cfo / rev if rev > 0 else (0.0 if cfo >= 0 else -0.5), 2.0), -2.0)
        rec_int = min(max(float(r["gross_contract_exposure_ratio"] or 0.15), 0.0), 3.0)
        neg_cfo = 1.0 if cfo < 0 else 0.0

        is_distress = int(
            bool(r["flag_acute_liquidity"])
            or (not debt_free and cov < 0.35 and cfo < 0)
            or (not debt_free and cov < 0.25)
        )
        X_raw.append([math.log1p(cov), sloan, cfo_margin, rec_int, neg_cfo])
        y_list.append(is_distress)

    X = np.array(X_raw, dtype=float)
    y = np.array(y_list, dtype=int)
    means = X.mean(axis=0)
    stds = np.where(X.std(axis=0) > 1e-6, X.std(axis=0), 1.0)
    X_std = (X - means) / stds

    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    rng = np.random.default_rng(42)
    rng.shuffle(pos_idx)
    rng.shuffle(neg_idx)

    k = 5
    oof_probs = np.zeros(len(y), dtype=float)
    pos_folds = np.array_split(pos_idx, k)
    neg_folds = np.array_split(neg_idx, k)
    for fold in range(k):
        val_idx = np.concatenate([pos_folds[fold], neg_folds[fold]])
        tr_mask = np.ones(len(y), dtype=bool)
        tr_mask[val_idx] = False
        wf = _fit_mlp_adam(X_std[tr_mask], y[tr_mask], seed=42 + fold)
        oof_probs[val_idx] = _mlp_predict(wf, X_std[val_idx])

    cv_auc = _roc_auc(y, oof_probs)
    cv_acc = float(np.mean((oof_probs >= 0.50).astype(int) == y))
    cv_brier = float(np.mean((oof_probs - y) ** 2))

    final_weights = _fit_mlp_adam(X_std, y, seed=42)
    artifact = {
        "model_name": "idx_solvency_mlp_5_16_8_1_v1",
        "architecture": [5, 16, 8, 1],
        "activations": ["relu", "relu", "sigmoid"],
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_samples": int(len(y)),
        "positive_samples": int(np.sum(y)),
        "cv_folds": k,
        "cv_roc_auc": round(cv_auc, 4),
        "cv_accuracy": round(cv_acc, 4),
        "cv_brier_score": round(cv_brier, 4),
        "feature_names": FEATURE_NAMES,
        "feature_means": [round(float(m), 6) for m in means],
        "feature_stds": [round(float(s), 6) for s in stds],
        "weights": final_weights,
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    MLP_OUT.write_text(json.dumps(artifact), encoding="utf-8")
    return artifact


def main() -> int:
    solv = train_solvency_model()
    print(
        f"[Model 1] {solv['model_name']} | samples={solv['training_samples']} "
        f"(pos={solv['positive_samples']}) | CV ROC-AUC={solv['cv_roc_auc']} | "
        f"CV Acc={solv['cv_accuracy']} | Brier={solv['cv_brier_score']}"
    )
    print(f"          weights={solv['weights']}")

    nb = train_news_nb_model()
    print(
        f"[Model 2] {nb['model_name']} | samples={nb['training_samples']} | "
        f"vocab={nb['vocab_size']} | CV Acc={nb['cv_accuracy']}"
    )

    mlp = train_neural_mlp_model()
    print(
        f"[Model 3] {mlp['model_name']} | arch={mlp['architecture']} | samples={mlp['training_samples']} | "
        f"CV ROC-AUC={mlp['cv_roc_auc']} | CV Acc={mlp['cv_accuracy']} | Brier={mlp['cv_brier_score']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
