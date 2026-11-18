"""
Phase 5: Reproducible Backtest of "Berita Positif + Kas Tertekan" vs Control ("Kas Sehat")
and IHSG (^JKSE) using frozen rules in docs/backtest_rules.md.
Uses Yahoo Finance adjusted close prices and verifiable dated news from
data/daily_news_sentiment.json + CURATED_DISCLOSURES.
Outputs reports/backtest.md and reports/backtest_events.csv.
"""

from __future__ import annotations

import csv
import email.utils
import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.engine.news_radar import CURATED_DISCLOSURES  # noqa: E402
from src.engine.realtime_news_analyzer import analyze_sentiment_deterministic  # noqa: E402

DB_PATH = ROOT_DIR / "idx_cash_radar.db"
DAILY_NEWS_PATH = ROOT_DIR / "data" / "daily_news_sentiment.json"
OUT_MD = ROOT_DIR / "reports" / "backtest.md"
OUT_CSV = ROOT_DIR / "reports" / "backtest_events.csv"

ID_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5,
    "jun": 6, "jul": 7, "agu": 8, "aug": 8, "sep": 9, "okt": 10, "oct": 10,
    "nov": 11, "des": 12, "dec": 12,
}


def _parse_verifiable_date(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    # RFC 2822 e.g. "Mon, 17 Nov 2026" or "Mon, 16 Nov 2026 07:00:00 GMT"
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    # "28 Des 2023" / "15 Des 2023"
    parts = s.split()
    if len(parts) == 3 and parts[0].isdigit() and parts[2].isdigit():
        m = ID_MONTHS.get(parts[1].lower()[:3])
        if m:
            return f"{int(parts[2]):04d}-{m:02d}-{int(parts[0]):02d}"
    # ISO YYYY-MM-DD
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def _load_latest_metrics() -> dict[str, list[dict[str, Any]]]:
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ticker, period_end_date, cfo_ttm_idr, cash_coverage_ratio,
                   debt_free_short_term, flag_acute_liquidity
            FROM computed_metrics
            ORDER BY ticker, period_end_date ASC
            """
        ).fetchall()
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_ticker.setdefault(r["ticker"], []).append(dict(r))
    return by_ticker


def _pick_fundamental_before(
    rows: list[dict[str, Any]], pub_date: str
) -> dict[str, Any] | None:
    if not rows:
        return None
    prior = [r for r in rows if str(r["period_end_date"]) <= pub_date]
    return prior[-1] if prior else rows[0]


def _classify_cash_group(fund: dict[str, Any] | None) -> str | None:
    if not fund:
        return None
    cfo = float(fund.get("cfo_ttm_idr") or 0.0)
    debt_free = bool(fund.get("debt_free_short_term"))
    cov = float(fund.get("cash_coverage_ratio") or 0.0)
    flag_liq = bool(fund.get("flag_acute_liquidity"))

    if cfo < 0 or flag_liq or (not debt_free and cov < 0.25):
        return "TREATMENT_KAS_TERTEKAN"
    if cfo > 0 and not flag_liq and (debt_free or cov >= 1.0):
        return "CONTROL_KAS_SEHAT"
    return None


def _fetch_yahoo_adjclose(symbol: str, start_date: str, end_date: str) -> list[tuple[str, float]]:
    dt1 = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())
    dt2 = int(
        (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=2))
        .replace(tzinfo=UTC)
        .timestamp()
    )
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
        f"?period1={dt1}&period2={dt2}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        res = data["chart"]["result"][0]
        ts = res.get("timestamp") or []
        adj = (res.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
        if not adj:
            adj = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        out: list[tuple[str, float]] = []
        for t, p in zip(ts, adj, strict=False):
            if p is not None:
                d_str = datetime.fromtimestamp(t, tz=UTC).strftime("%Y-%m-%d")
                out.append((d_str, float(p)))
        return out
    except Exception:
        return []


def _compute_forward_returns(
    series: list[tuple[str, float]], pub_date: str, horizons: tuple[int, ...] = (5, 20, 60)
) -> dict[int, float | None]:
    idx0 = next((i for i, (d, _) in enumerate(series) if d >= pub_date), None)
    if idx0 is None:
        return {h: None for h in horizons}
    p0 = series[idx0][1]
    if p0 <= 0:
        return {h: None for h in horizons}
    out: dict[int, float | None] = {}
    for h in horizons:
        if idx0 + h < len(series):
            out[h] = (series[idx0 + h][1] / p0) - 1.0
        else:
            out[h] = None
    return out


def main() -> int:
    metrics_map = _load_latest_metrics()
    candidates: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    # 1. Daily news snapshot
    if DAILY_NEWS_PATH.exists():
        snap = json.loads(DAILY_NEWS_PATH.read_text(encoding="utf-8"))
        for ticker, items in (snap.get("news_by_ticker") or {}).items():
            for it in items:
                dt = _parse_verifiable_date(it.get("date", ""))
                hl = (it.get("headline") or "").strip()
                if not dt or not hl:
                    continue
                key = (ticker.upper(), dt, hl[:60].lower())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                sent = analyze_sentiment_deterministic(hl, "")
                if sent["sentiment"] == "POSITIF":
                    candidates.append({
                        "ticker": ticker.upper(),
                        "pub_date": dt,
                        "headline": hl,
                        "source": it.get("source", "RSS"),
                    })

    # 2. Curated BEI disclosures
    for ticker, items in CURATED_DISCLOSURES.items():
        for it in items:
            dt = _parse_verifiable_date(it.get("date", ""))
            hl = (it.get("headline") or "").strip()
            if not dt or not hl:
                continue
            key = (ticker.upper(), dt, hl[:60].lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            sent = analyze_sentiment_deterministic(hl, it.get("detail", ""))
            if sent["sentiment"] == "POSITIF":
                candidates.append({
                    "ticker": ticker.upper(),
                    "pub_date": dt,
                    "headline": hl,
                    "source": it.get("source", "Keterbukaan BEI"),
                })

    # Filter into Treatment / Control
    events: list[dict[str, Any]] = []
    for c in candidates:
        fund = _pick_fundamental_before(metrics_map.get(c["ticker"], []), c["pub_date"])
        grp = _classify_cash_group(fund)
        if grp:
            events.append({
                **c,
                "group": grp,
                "period_end_date": fund["period_end_date"] if fund else None,
            })

    # Fetch Yahoo Finance prices if we have events
    price_cache: dict[str, list[tuple[str, float]]] = {}
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    if events:
        min_dt = min(e["pub_date"] for e in events)
        price_cache["^JKSE"] = _fetch_yahoo_adjclose("^JKSE", min_dt, today_str)
        for t in sorted({e["ticker"] for e in events}):
            price_cache[t] = _fetch_yahoo_adjclose(f"{t}.JK", min_dt, today_str)

    ihsg_series = price_cache.get("^JKSE", [])
    rows_out: list[dict[str, Any]] = []
    for e in events:
        t_series = price_cache.get(e["ticker"], [])
        r_stock = _compute_forward_returns(t_series, e["pub_date"])
        r_ihsg = _compute_forward_returns(ihsg_series, e["pub_date"])
        ex5 = (r_stock[5] - r_ihsg[5]) if (r_stock[5] is not None and r_ihsg[5] is not None) else None
        ex20 = (r_stock[20] - r_ihsg[20]) if (r_stock[20] is not None and r_ihsg[20] is not None) else None
        ex60 = (r_stock[60] - r_ihsg[60]) if (r_stock[60] is not None and r_ihsg[60] is not None) else None
        rows_out.append({
            "ticker": e["ticker"],
            "pub_date": e["pub_date"],
            "group": e["group"],
            "period_end_date": e["period_end_date"],
            "source": e["source"],
            "headline": e["headline"],
            "ret_5d": round(r_stock[5], 6) if r_stock[5] is not None else "",
            "ret_20d": round(r_stock[20], 6) if r_stock[20] is not None else "",
            "ret_60d": round(r_stock[60], 6) if r_stock[60] is not None else "",
            "excess_5d": round(ex5, 6) if ex5 is not None else "",
            "excess_20d": round(ex20, 6) if ex20 is not None else "",
            "excess_60d": round(ex60, 6) if ex60 is not None else "",
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ticker", "pub_date", "group", "period_end_date", "source", "headline",
        "ret_5d", "ret_20d", "ret_60d", "excess_5d", "excess_20d", "excess_60d",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    # Summarize per group & horizon
    def _stats(grp_name: str, col: str) -> dict[str, Any]:
        vals = [float(r[col]) for r in rows_out if r["group"] == grp_name and r[col] != ""]
        if not vals:
            return {"n": 0, "median": None, "mean": None, "hit_neg": None}
        return {
            "n": len(vals),
            "median": median(vals),
            "mean": mean(vals),
            "hit_neg": sum(1 for v in vals if v < 0) / len(vals),
        }

    tr_n_total = sum(1 for r in rows_out if r["group"] == "TREATMENT_KAS_TERTEKAN")
    ct_n_total = sum(1 for r in rows_out if r["group"] == "CONTROL_KAS_SEHAT")
    tr_60 = _stats("TREATMENT_KAS_TERTEKAN", "excess_60d")
    evidence_insufficient = (tr_n_total < 10) or (ct_n_total < 10) or (tr_60["n"] < 10)

    md_lines = [
        "# Laporan Backtest Kasus — Fase 5 (`reports/backtest.md`)\n",
        f"**Status Bukti:** **{'BUKTI TIDAK CUKUP' if evidence_insufficient else 'DIEVALUASI'}**\n",
        "Aturan terkunci di `docs/backtest_rules.md` diterapkan pada seluruh kejadian berita "
        "bertanggal terverifikasi di `data/daily_news_sentiment.json` dan `CURATED_DISCLOSURES` "
        "(tanpa cherry-picking, tanpa data sintetis).\n",
        "## 1. Ringkasan Jumlah Kejadian\n",
        f"- Total berita `POSITIF` bertanggal terverifikasi: **{len(candidates)}**",
        f"- Kelompok Uji (`TREATMENT_KAS_TERTEKAN`): **{tr_n_total}** kejadian",
        f"- Kelompok Kontrol (`CONTROL_KAS_SEHAT`): **{ct_n_total}** kejadian\n",
        "## 2. Hasil Excess Return vs IHSG (`^JKSE`, Adjusted Close)\n",
        "| Kelompok | Horizon | N Valid | Median Excess Return | Rata-rata Excess Return | Hit Rate (`Excess < 0`) |",
        "| :--- | :--- | ---: | ---: | ---: | ---: |",
    ]
    for grp in ("TREATMENT_KAS_TERTEKAN", "CONTROL_KAS_SEHAT"):
        for hz, col in (("5 Hari", "excess_5d"), ("20 Hari", "excess_20d"), ("60 Hari", "excess_60d")):
            st = _stats(grp, col)
            med_s = f"{st['median']*100:+.2f}%" if st["median"] is not None else "N/A"
            mean_s = f"{st['mean']*100:+.2f}%" if st["mean"] is not None else "N/A"
            hit_s = f"{st['hit_neg']*100:.1f}%" if st["hit_neg"] is not None else "N/A"
            md_lines.append(f"| `{grp}` | {hz} | {st['n']} | {med_s} | {mean_s} | {hit_s} |")

    md_lines.append("\n## 3. Kejadian Kontra & Keterbatasan\n")
    contras = [
        r for r in rows_out
        if r["group"] == "TREATMENT_KAS_TERTEKAN"
        and any(r[c] != "" and float(r[c]) > 0 for c in ("excess_5d", "excess_20d", "excess_60d"))
    ]
    if contras:
        md_lines.append("Kejadian kelompok uji yang justru mengungguli IHSG (kontra hipotesis):")
        for c in contras[:10]:
            md_lines.append(
                f"- `{c['ticker']}` ({c['pub_date']}): {c['headline']} "
                f"[5d={c['excess_5d']}, 20d={c['excess_20d']}, 60d={c['excess_60d']}]"
            )
    else:
        md_lines.append("- Tidak ada kejadian dengan horizon lengkap yang dapat dievaluasi sebagai kontra.")

    md_lines.append(
        "\n- **Survivorship Bias:** Universe 49 emiten hanya mencakup emiten yang masih tercatat/aktif; "
        "emiten yang delisting tidak masuk.\n"
        "- **Keterbatasan Berita Historis:** `data/daily_news_sentiment.json` hanya menyimpan snapshot "
        "berita RSS terbaru (mayoritas belum memiliki horizon 20–60 hari bursa ke depan), sementara "
        "arsip Keterbukaan Informasi BEI historis 2020–2025 belum tersedia di repositori.\n"
    )

    md_lines.append("## 4. Draft Thread (Maks 8 Poin)\n")
    if evidence_insufficient:
        md_lines.append(
            "*(Draft thread dikosongkan sesuai aturan Fase 5 karena status = **BUKTI TIDAK CUKUP**: "
            f"Treatment N={tr_n_total}, Control N={ct_n_total}, dan horizon 60 hari N={tr_60['n']} < 10.)*\n"
        )
    else:
        md_lines.append("1. (Draft tersedia jika bukti cukup.)\n")

    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print("\n".join(md_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
