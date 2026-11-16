"""
Helper script to embed precomputed 48-issuer financial dataset directly into index.html.
Ensures zero-latency instant rendering and 100% offline/outdated-process resilience.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.web.app import (  # noqa: E402
    get_ml_distress_rankings,
    get_radar_matrix,
    get_regression_analytics,
    get_screener_data,
    news_radar,
    repo,
)

TEMPLATE_PATH = ROOT_DIR / "src" / "web" / "templates" / "index.html"

def main():
    screener = get_screener_data(2025)
    radar = get_radar_matrix(2025)

    distress_rankings = get_ml_distress_rankings(2025)
    distress_map = {r["ticker"]: r for r in distress_rankings}

    news_sentiment_map = {}
    for item in screener:
        t = item["ticker"]
        news_items = news_radar.get_news_for_ticker(t, max_items=4, use_live=False)
        news_sentiment_map[t] = [n.model_dump() for n in news_items]

    history_map: dict[str, list[dict]] = {}
    with repo.get_connection() as conn:
        h_rows = conn.execute(
            """
            SELECT cm.ticker, f.fiscal_year, cm.cash_coverage_ratio, cm.debt_free_short_term,
                   cm.cfo_ttm_idr, cm.net_income_ttm_idr, cm.sloan_ratio_ttm
            FROM computed_metrics cm
            JOIN filings f ON cm.filing_id = f.filing_id
            ORDER BY cm.ticker ASC, f.fiscal_year ASC;
            """
        ).fetchall()
    for hr in h_rows:
        t = hr["ticker"]
        history_map.setdefault(t, []).append({
            "fiscal_year": hr["fiscal_year"],
            "cash_coverage_ratio": hr["cash_coverage_ratio"],
            "debt_free_short_term": hr["debt_free_short_term"],
            "cfo_ttm_idr": hr["cfo_ttm_idr"],
            "net_income_ttm_idr": hr["net_income_ttm_idr"],
            "sloan_ratio_ttm": hr["sloan_ratio_ttm"],
        })

    sector_regressions = {
        "": get_regression_analytics(2025, None),
        "CONSTRUCTION": get_regression_analytics(2025, "CONSTRUCTION"),
        "FMCG": get_regression_analytics(2025, "FMCG"),
        "BANKING": get_regression_analytics(2025, "BANKING"),
        "ENERGY": get_regression_analytics(2025, "ENERGY"),
        "TELECOM": get_regression_analytics(2025, "TELECOM"),
    }

    screener_json = json.dumps(screener)
    radar_json = json.dumps(radar)
    sector_regs_json = json.dumps(sector_regressions)
    distress_map_json = json.dumps(distress_map)
    news_sentiment_json = json.dumps(news_sentiment_map)
    history_map_json = json.dumps(history_map)

    data_block = f"""
    // PRECOMPUTED DETERMINISTIC FINANCIAL DATA (Instant Hydration & Zero Latency)
    window.EMBEDDED_SCREENER = {screener_json};
    window.EMBEDDED_RADAR = {radar_json};
    window.EMBEDDED_SECTOR_REGRESSIONS = {sector_regs_json};
    window.EMBEDDED_REGRESSION = window.EMBEDDED_SECTOR_REGRESSIONS[""];
    window.EMBEDDED_DISTRESS_MAP = {distress_map_json};
    window.EMBEDDED_NEWS_SENTIMENT = {news_sentiment_json};
    window.EMBEDDED_HISTORY_MAP = {history_map_json};
    """

    content = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Find injection marker
    target_marker = "const APP_CACHE = {"
    if "window.EMBEDDED_SCREENER =" in content:
        # Already embedded, replace existing block
        import re
        content = re.sub(
            r"// PRECOMPUTED DETERMINISTIC FINANCIAL DATA.*?(?=const APP_CACHE = \{)",
            lambda _: data_block.strip() + "\n\n    ",
            content,
            flags=re.DOTALL,
        )
    else:
        content = content.replace(target_marker, data_block.strip() + "\n\n    " + target_marker)

    TEMPLATE_PATH.write_text(content, encoding="utf-8")
    print(f"Successfully embedded data into {TEMPLATE_PATH} (Length: {len(content)})")

    deploy_index = ROOT_DIR / "deploy_web" / "index.html"
    deploy_index.parent.mkdir(parents=True, exist_ok=True)
    deploy_index.write_text(content, encoding="utf-8")
    print(f"Successfully synced static deploy file to {deploy_index}")

if __name__ == "__main__":
    main()
