"""Google News RSS fetcher (when:30d, newest-first) with deterministic sentiment scoring."""

from __future__ import annotations

import email.utils
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from lxml import etree

WIB = ZoneInfo("Asia/Jakarta")

POSITIVE_KEYWORDS = (
    "dividen", "laba naik", "laba tumbuh", "kontrak baru", "ekspansi",
    "buyback", "rekor", "pendapatan naik", "pertumbuhan", "melampaui",
    "proyek baru", "surplus", "investasi baru", "akuisisi", "rebalancing",
)
WARNING_KEYWORDS = (
    "suspensi", "uma", "unusual market activity", "fca", "pkpu", "gagal bayar",
    "penundaan", "restrukturisasi", "rugi", "anjlok", "koreksi tajam",
    "gugatan", "pailit", "pemantauan khusus", "penurunan laba",
)


def score_headline_sentiment(headline: str) -> str:
    """Deterministically classifies headline into POSITIF, PERHATIAN, or NETRAL."""
    low = (headline or "").lower()
    pos_hits = sum(1 for kw in POSITIVE_KEYWORDS if kw in low)
    warn_hits = sum(1 for kw in WARNING_KEYWORDS if kw in low)
    if warn_hits > 0 and warn_hits >= pos_hits:
        return "PERHATIAN"
    if pos_hits > warn_hits:
        return "POSITIF"
    return "NETRAL"


def _parse_pub_dt(pub_date: str) -> datetime:
    if not pub_date:
        return datetime.min.replace(tzinfo=UTC)
    try:
        dt = email.utils.parsedate_to_datetime(pub_date)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    except Exception:
        return datetime.min.replace(tzinfo=UTC)


def _format_pub_wib(dt: datetime, raw_pub_date: str) -> str:
    if dt > datetime.min.replace(tzinfo=UTC):
        return dt.astimezone(WIB).strftime("%d %b %Y %H:%M WIB")
    return raw_pub_date[:16] if raw_pub_date else "-"


def fetch_latest_news(ticker: str, max_items: int = 3, timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetches newest Google News RSS articles (WIB timestamps, newest-first)."""
    clean_t = ticker.strip().upper().replace(".JK", "")
    queries = (
        f"{clean_t} saham when:2d",
        f"{clean_t} saham BEI when:30d",
        f"{clean_t} saham",
    )
    seen_titles: set[str] = set()
    parsed: list[tuple[datetime, dict[str, Any]]] = []

    for query in queries:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=id&gl=ID&ceid=ID:id"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; IDXAlertBot/1.0)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_xml = resp.read()
            root = etree.fromstring(raw_xml)
        except Exception:
            continue

        for el in root.xpath("//channel/item"):
            title = (el.findtext("title") or "").strip()
            link = (el.findtext("link") or "").strip()
            pub_date = (el.findtext("pubDate") or "").strip()
            src_el = el.find("source")
            src = src_el.text.strip() if src_el is not None and src_el.text else "Google News"
            if not title:
                continue
            if " - " in title and src != "Google News":
                title = title.rsplit(" - ", 1)[0].strip()

            norm_key = title.lower()
            if norm_key in seen_titles:
                continue
            seen_titles.add(norm_key)

            dt = _parse_pub_dt(pub_date)
            parsed.append((
                dt,
                {
                    "date": _format_pub_wib(dt, pub_date),
                    "headline": title,
                    "source": src,
                    "sentiment": score_headline_sentiment(title),
                    "url": link or None,
                },
            ))

        # Stop early once we already have recent items from the fresher query
        if len(parsed) >= max_items:
            break

    if parsed:
        parsed.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in parsed[:max_items]]

    return []
