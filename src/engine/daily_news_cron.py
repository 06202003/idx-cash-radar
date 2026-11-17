"""
Daily News Sentiment Cron Engine.
Fetches latest public IDX/business news headlines via Google News RSS per ticker,
scores sentiment deterministically (POSITIF / NETRAL / PERHATIAN), and persists
daily snapshots to data/daily_news_sentiment.json (with in-memory fallback).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lxml import etree

from src.engine.realtime_news_analyzer import analyze_sentiment_deterministic

ROOT_DIR = Path(__file__).resolve().parents[2]
DAILY_NEWS_PATH = ROOT_DIR / "data" / "daily_news_sentiment.json"

_DAILY_LOCK = threading.Lock()
_DAILY_MEMORY_CACHE: dict[str, Any] = {}


def fetch_ticker_rss_news(
    ticker: str,
    company_name: str = "",
    max_items: int = 3,
    timeout: float = 6.0,
) -> list[dict[str, Any]]:
    """Fetches and deterministically scores latest Google News RSS headlines for an IDX ticker."""
    clean_t = ticker.strip().upper()
    short_comp = " ".join(
        company_name.replace("Tbk.", "").replace("(Persero)", "").split()[:2]
    ).strip()
    query = f"{clean_t} {short_comp} saham".strip() if short_comp else f"{clean_t} saham BEI"
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=id&gl=ID&ceid=ID:id"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; IDXCashRadarBot/2.0)"},
    )

    items: list[dict[str, Any]] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_xml = resp.read()
        root = etree.fromstring(raw_xml)
        for item_el in root.xpath("//channel/item")[:max_items]:
            title = (item_el.findtext("title") or "").strip()
            link = (item_el.findtext("link") or "").strip()
            pub_date = (item_el.findtext("pubDate") or "").strip()
            source_el = item_el.find("source")
            source_name = (
                source_el.text.strip()
                if source_el is not None and source_el.text
                else "Google News RSS"
            )
            if not title:
                continue

            # Clean trailing " - Publisher" from Google News titles
            if " - " in title and source_name != "Google News RSS":
                title = title.rsplit(" - ", 1)[0].strip()

            sent_res = analyze_sentiment_deterministic(title, "")
            fallback_dt = datetime.now(UTC).strftime("%d %b %Y")
            items.append({
                "date": pub_date[:16] if pub_date else fallback_dt,
                "sentiment": sent_res["sentiment"],
                "headline": title,
                "source": source_name,
                "url": link or None,
                "matched_positive": sent_res["matched_positive"],
                "matched_warning": sent_res["matched_warning"],
            })
    except Exception:
        return []

    return items


def refresh_daily_news(
    issuers: list[dict[str, Any]],
    max_per_ticker: int = 3,
    max_workers: int = 8,
) -> dict[str, Any]:
    """Runs daily RSS news sentiment refresh across all covered issuers."""
    news_map: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(
                fetch_ticker_rss_news,
                row["ticker"],
                row.get("company_name", ""),
                max_per_ticker,
            ): row["ticker"].upper()
            for row in issuers
        }
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                res = fut.result()
                if res:
                    news_map[t] = res
            except Exception:
                continue

    payload = {
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "updated_timestamp": int(time.time()),
        "ticker_count": len(news_map),
        "total_articles": sum(len(v) for v in news_map.values()),
        "news": news_map,
    }

    with _DAILY_LOCK:
        _DAILY_MEMORY_CACHE.clear()
        _DAILY_MEMORY_CACHE.update(payload)

    try:
        DAILY_NEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DAILY_NEWS_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        # Read-only filesystem (e.g. Vercel serverless) — keep in memory
        pass

    return payload


def load_daily_news() -> dict[str, Any]:
    """Loads latest daily news sentiment snapshot from memory or disk."""
    with _DAILY_LOCK:
        if _DAILY_MEMORY_CACHE:
            return dict(_DAILY_MEMORY_CACHE)

    if DAILY_NEWS_PATH.exists():
        try:
            data = json.loads(DAILY_NEWS_PATH.read_text(encoding="utf-8"))
            with _DAILY_LOCK:
                _DAILY_MEMORY_CACHE.clear()
                _DAILY_MEMORY_CACHE.update(data)
            return data
        except Exception:
            pass

    return {
        "updated_at_utc": None,
        "updated_timestamp": 0,
        "ticker_count": 0,
        "total_articles": 0,
        "news": {},
    }
