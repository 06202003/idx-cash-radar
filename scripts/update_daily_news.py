"""
Daily News Sentiment Cron CLI.
Run manually or via scheduler (cron / Task Scheduler / GitHub Actions) to refresh
data/daily_news_sentiment.json for all covered IDX issuers.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.engine.daily_news_cron import refresh_daily_news  # noqa: E402
from src.web.app import get_issuers  # noqa: E402


def main() -> int:
    issuers = get_issuers()
    print(f"[daily-news-cron] Fetching daily RSS news sentiment for {len(issuers)} issuers...")
    res = refresh_daily_news(issuers, max_per_ticker=3, max_workers=8)
    print(
        f"[daily-news-cron] Done! {res['ticker_count']} tickers updated, "
        f"{res['total_articles']} headlines scored at {res['updated_at_utc']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
