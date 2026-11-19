"""Google News RSS fetcher (when:30d, newest-first) with deterministic sentiment scoring."""

from __future__ import annotations

import email.utils
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from lxml import etree

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


def fetch_latest_news(ticker: str, max_items: int = 3, timeout: float = 6.0) -> list[dict[str, Any]]:
    """Fetches newest Google News RSS articles (when:30d) sorted newest-first."""
    clean_t = ticker.strip().upper().replace(".JK", "")
    for query in (f"{clean_t} saham BEI when:30d", f"{clean_t} saham BEI"):
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

        parsed: list[tuple[datetime, dict[str, Any]]] = []
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

            dt = _parse_pub_dt(pub_date)
            parsed.append((
                dt,
                {
                    "date": pub_date[:16] if pub_date else dt.strftime("%d %b %Y"),
                    "headline": title,
                    "source": src,
                    "sentiment": score_headline_sentiment(title),
                    "url": link or None,
                },
            ))
        if parsed:
            parsed.sort(key=lambda pair: pair[0], reverse=True)
            return [item for _, item in parsed[:max_items]]

    return []
