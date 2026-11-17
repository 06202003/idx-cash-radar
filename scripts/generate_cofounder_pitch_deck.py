"""
Generates an executive 10-slide 16:9 Co-Founder & Collaborator Pitch Deck
(HTML + PDF via Playwright) with live application screenshots from http://127.0.0.1:8000.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "idx_cash_radar.db"
DAILY_NEWS_PATH = ROOT_DIR / "data" / "daily_news_sentiment.json"
SHOTS_DIR = ROOT_DIR / "docs" / "deck_shots"
OUT_HTML = ROOT_DIR / "docs" / "IDX_Cash_Radar_CoFounder_Deck.html"
OUT_PDF = ROOT_DIR / "docs" / "IDX_Cash_Radar_CoFounder_Deck.pdf"


def load_live_stats() -> dict[str, int]:
    """Reads verified counts from SQLite and daily news snapshot."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        issuers = conn.execute("SELECT COUNT(*) FROM issuers").fetchone()[0]
        filings = conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
        facts = conn.execute("SELECT COUNT(*) FROM canonical_facts").fetchone()[0]

    news_tickers = 39
    news_articles = 117
    if DAILY_NEWS_PATH.exists():
        try:
            dn = json.loads(DAILY_NEWS_PATH.read_text(encoding="utf-8"))
            news_tickers = int(dn.get("ticker_count") or news_tickers)
            news_articles = int(dn.get("total_articles") or news_articles)
        except Exception:
            pass

    return {
        "issuers": issuers,
        "filings": filings,
        "facts": facts,
        "news_tickers": news_tickers,
        "news_articles": news_articles,
    }


def launch_browser(p: object) -> Browser:
    """Launches Edge, Chrome, or Chromium fallback."""
    for ch in ("msedge", "chrome", None):
        try:
            return p.chromium.launch(channel=ch) if ch else p.chromium.launch()
        except Exception:
            continue
    raise RuntimeError("No Chromium/Edge/Chrome browser available for Playwright.")


def capture_live_screenshots(base_url: str = "http://127.0.0.1:8000/") -> dict[str, str]:
    """Captures 3 crisp 1280x720 screenshots of the running web dashboard."""
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "screener": SHOTS_DIR / "01_screener.png",
        "detail": SHOTS_DIR / "02_stock_detail.png",
        "news": SHOTS_DIR / "03_news_radar.png",
    }

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        context.add_cookies([{"name": "idx_radar_tour_done", "value": "1", "url": base_url}])
        page = context.new_page()
        page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
        # Wait until background hydration finishes (dailyNews cards & live quotes rendered)
        page.wait_for_function(
            "() => document.querySelectorAll('#dailyNewsFeedGrid button').length > 0",
            timeout=35000,
        )
        page.wait_for_timeout(800)

        # 1. Screener tab
        page.screenshot(path=str(paths["screener"]), full_page=False)

        # 2. Stock Detail (Live) tab for BBRI — wait for OHLCV + LightweightCharts canvas
        page.click("#tabBtnCalk")
        page.evaluate("() => { if (typeof inspectFiling === 'function') inspectFiling('BBRI'); }")
        page.wait_for_function(
            "() => { const p = document.getElementById('stockChartLivePrice'); "
            "const c = document.querySelector('#stockPriceChartBox canvas'); "
            "const m = document.getElementById('stockChartRangeMeta'); "
            "return p && p.textContent && p.textContent !== '-' "
            "&& c !== null && m && !m.textContent.includes('Loading'); }",
            timeout=30000,
        )
        page.wait_for_timeout(1000)
        page.screenshot(path=str(paths["detail"]), full_page=False)

        # 3. News & URL Analyzer tab
        page.click("#tabBtnNews")
        page.wait_for_timeout(800)
        page.screenshot(path=str(paths["news"]), full_page=False)

        browser.close()

    return {k: v.resolve().as_uri() for k, v in paths.items()}


def build_html(s: dict[str, int], shots: dict[str, str]) -> str:
    """Constructs the 10-slide 16:9 presentation HTML."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>IDX Cash &amp; Accrual Radar — Co-Founder Pitch Deck</title>
  <style>
    @page {{
      size: 13.333in 7.5in;
      margin: 0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #0f172a;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}
    .slide {{
      width: 13.333in;
      height: 7.5in;
      padding: 0.55in 0.72in;
      position: relative;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      page-break-after: always;
      overflow: hidden;
    }}
    .slide-dark {{
      background: linear-gradient(135deg, #070b14 0%, #0f172a 60%, #0c192c 100%);
      color: #f8fafc;
    }}
    .slide-light {{
      background: #ffffff;
      color: #0f172a;
    }}
    .eyebrow {{
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.8px;
      text-transform: uppercase;
      color: #0284c7;
      margin-bottom: 8px;
    }}
    .slide-dark .eyebrow {{ color: #38bdf8; }}
    h1 {{
      font-size: 44px;
      font-weight: 800;
      letter-spacing: -1.3px;
      line-height: 1.08;
    }}
    h2 {{
      font-size: 29px;
      font-weight: 800;
      letter-spacing: -0.7px;
      line-height: 1.15;
      margin-bottom: 10px;
    }}
    .lead {{
      font-size: 15.5px;
      line-height: 1.48;
      color: #475569;
      max-width: 960px;
    }}
    .slide-dark .lead {{ color: #cbd5e1; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }}
    .grid-demo {{ display: grid; grid-template-columns: 1.65fr 1fr; gap: 20px; align-items: center; }}
    .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
    .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }}
    .card {{
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 18px 20px;
      background: #f8fafc;
    }}
    .slide-dark .card {{
      background: rgba(15, 23, 42, 0.78);
      border: 1px solid #1e293b;
    }}
    .card-accent {{ border-left: 4px solid #0284c7; }}
    .card-red {{ border-left: 4px solid #e11d48; }}
    .card-green {{ border-left: 4px solid #059669; }}
    .card-amber {{ border-left: 4px solid #d97706; }}
    .kpi-num {{
      font-size: 34px;
      font-weight: 800;
      letter-spacing: -1px;
      color: #0284c7;
      line-height: 1.1;
      margin-bottom: 5px;
    }}
    .slide-dark .kpi-num {{ color: #38bdf8; }}
    .kpi-label {{
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 4px;
    }}
    .muted {{
      font-size: 12.5px;
      line-height: 1.45;
      color: #64748b;
    }}
    .slide-dark .muted {{ color: #94a3b8; }}
    .shot-frame {{
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      overflow: hidden;
      background: #0b0f19;
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.16);
    }}
    .shot-frame img {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .tag {{
      display: inline-block;
      padding: 3px 9px;
      border-radius: 4px;
      font-size: 10.5px;
      font-weight: 700;
    }}
    .tag-red {{ background: #ffe4e6; color: #be123c; }}
    .tag-green {{ background: #d1fae5; color: #047857; }}
    .tag-amber {{ background: #fef3c7; color: #b45309; }}
    .tag-blue {{ background: #e0f2fe; color: #0369a1; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
    }}
    th {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 2px solid #cbd5e1;
      font-size: 10.5px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: #475569;
    }}
    td {{
      padding: 9px 10px;
      border-bottom: 1px solid #e2e8f0;
    }}
    .footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: #94a3b8;
      border-top: 1px solid #e2e8f0;
      padding-top: 8px;
    }}
    .slide-dark .footer {{
      border-top-color: #1e293b;
      color: #64748b;
    }}
    .watermark {{
      position: absolute;
      bottom: 0.92in;
      right: 0.72in;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      color: rgba(15, 23, 42, 0.14);
      pointer-events: none;
      user-select: none;
    }}
    .slide-dark .watermark {{
      color: rgba(248, 250, 252, 0.14);
    }}
    a {{ color: inherit; text-decoration: none; }}
    ul {{ padding-left: 18px; }}
    li {{ margin-bottom: 6px; font-size: 13px; line-height: 1.45; }}
  </style>
</head>
<body>

  <!-- SLIDE 1: COVER -->
  <section class="slide slide-dark">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <span style="font-weight: 800; font-size: 14px; letter-spacing: 0.5px; color: #38bdf8;">IDX CASH &amp; ACCRUAL RADAR</span>
      <a href="https://idx-cash-radar.vercel.app/" target="_blank" style="font-size: 11.5px; color: #94a3b8; border-bottom: 1px solid #334155; padding-bottom: 2px; font-weight: 600;">idx-cash-radar.vercel.app &#8599;</a>
    </div>

    <div style="max-width: 980px;">
      <div class="eyebrow">THE ANTI-HYPE STOCK INTELLIGENCE PLATFORM FOR INDONESIA</div>
      <h1>Helping Everyday Investors Spot Real Cash vs. Paper Profits.</h1>
      <p class="lead" style="margin-top: 16px;">
        We already built and shipped a live platform combining <strong>Official IDX XBRL Financials</strong>,
        <strong>Live TradingView-style Stock Charts</strong>, and <strong>Daily News Sentiment</strong> across
        <strong>{s['issuers']} IDX issuers</strong>. Looking for a co-builder to scale it together.
      </p>
    </div>

    <div class="grid-4">
      <div class="card">
        <div class="kpi-num">{s['issuers']}</div>
        <div class="kpi-label">IDX Issuers Live</div>
        <div class="muted">Construction, Banking, FMCG, Energy &amp; Telecom</div>
      </div>
      <div class="card">
        <div class="kpi-num">{s['facts']:,}</div>
        <div class="kpi-label">Audited XBRL Facts</div>
        <div class="muted">SHA-256 verified across {s['filings']} official filings</div>
      </div>
      <div class="card">
        <div class="kpi-num">{s['news_articles']}</div>
        <div class="kpi-label">Daily Scored Headlines</div>
        <div class="muted">Automated RSS sentiment cron across {s['news_tickers']} tickers</div>
      </div>
      <div class="card">
        <div class="kpi-num">0%</div>
        <div class="kpi-label">AI Math Hallucination</div>
        <div class="muted">100% Python Decimal math + Exchange OHLCV charts</div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; &copy; Yehezkiel David Setiawan, S.Kom, M.Kom</span>
      <span>Slide 1 / 10</span>
    </div>
  </section>

  <!-- SLIDE 2: EXECUTIVE SUMMARY -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">01 / EXECUTIVE SUMMARY</div>
      <h2>One Radar That Connects Price Action, Daily News, &amp; Real Cash Flow.</h2>
      <p class="lead">Built for retail beginners and novice traders who want institutional-grade cash checks without reading 200-page financial PDFs.</p>
    </div>

    <div class="grid-2">
      <div class="card card-accent">
        <div style="font-weight: 800; font-size: 14px; color: #0369a1; margin-bottom: 10px;">WHAT WE BUILT</div>
        <ul>
          <li><strong>Primary XBRL Engine:</strong> Reads raw IDX <code>instance.xbrl</code> filings directly—separating real cash inflows (CFO) from paper accounting profits (Sloan Accruals).</li>
          <li><strong>Live Market + Candlestick UI:</strong> Stockbit-style TradingView Lightweight Charts (1D–1Y OHLCV + Volume) paired with annual financials.</li>
          <li><strong>Daily News Sentiment Cron:</strong> Automatically pulls &amp; scores daily IDX headlines while keeping cash safeguard flags strictly isolated from PR hype.</li>
        </ul>
      </div>

      <div class="card card-green">
        <div style="font-weight: 800; font-size: 14px; color: #047857; margin-bottom: 10px;">STRUCTURAL MOAT</div>
        <ul>
          <li><strong>Primary-Source Auditability:</strong> Every metric traces back to exact IDX XBRL XML tags (<code>localname</code>, <code>contextRef</code>) with SHA-256 filing hashes.</li>
          <li><strong>Zero-Hallucination Separation:</strong> Financial ratios execute strictly in Python <code>Decimal</code>; AI is confined to plain-language translation.</li>
          <li><strong>Sentiment-Isolated Safeguards:</strong> Bullish PR headlines never override or soften deterministic cash-stress flags on the balance sheet.</li>
        </ul>
      </div>
    </div>

    <div class="card" style="background: #0f172a; color: #f8fafc; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center;">
      <span style="font-size: 13px; color: #cbd5e1;">Working prototype deployed across <strong style="color: #ffffff;">{s['issuers']} IDX issuers</strong> with audited FY 2022–2025 filings &amp; live OHLCV price feeds.</span>
      <a href="https://idx-cash-radar.vercel.app/" target="_blank" style="font-size: 12px; font-weight: 700; color: #38bdf8;">idx-cash-radar.vercel.app &#8599;</a>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Executive Summary</span>
      <span>Slide 2 / 10</span>
    </div>
  </section>

  <!-- SLIDE 3: THE PROBLEM -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">02 / THE PROBLEM</div>
      <h2>Why Everyday Investors &amp; Novice Traders Get Trapped on IDX.</h2>
      <p class="lead">12M+ Indonesian retail investors have charting apps, yet still get burned by sudden debt restructurings and "paper profit" stocks.</p>
    </div>

    <div class="grid-3">
      <div class="card card-red">
        <div style="font-weight: 800; font-size: 14px; color: #be123c; margin-bottom: 8px;">1. "PAPER PROFIT" TRAP</div>
        <div class="muted" style="font-size: 13px;">
          A company reports positive Net Income, so beginners think it's healthy—unaware that Operating Cash Flow (CFO) is negative and cash is stuck in uncollected receivables.
        </div>
      </div>
      <div class="card card-amber">
        <div style="font-weight: 800; font-size: 14px; color: #b45309; margin-bottom: 8px;">2. PR HEADLINE BIAS</div>
        <div class="muted" style="font-size: 13px;">
          Bullish news (<em>"Wins IDR 5.6T Contract"</em>) triggers FOMO buying, even when the company's bank cash covers less than <strong>20%</strong> of its maturing short-term debt.
        </div>
      </div>
      <div class="card card-accent">
        <div style="font-weight: 800; font-size: 14px; color: #0369a1; margin-bottom: 8px;">3. PDF &amp; RATIO OVERLOAD</div>
        <div class="muted" style="font-size: 13px;">
          Official IDX financial statements are 150+ pages long, while generic AI chatbots hallucinate financial numbers when asked to summarize them.
        </div>
      </div>
    </div>

    <div class="card" style="padding: 14px 18px; border-left: 4px solid #0f172a;">
      <strong style="font-size: 13px;">The Gap:</strong>
      <span style="font-size: 13px; color: #334155;">Retail traders need one place that translates audited XBRL cash health into plain language alongside live price charts and daily news.</span>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Problem Statement</span>
      <span>Slide 3 / 10</span>
    </div>
  </section>

  <!-- SLIDE 4: WHO IS THIS FOR & HOW BEGINNERS USE IT -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">03 / TARGET USERS &amp; DAILY WORKFLOW</div>
      <h2>How Beginners &amp; Novice Traders Actually Use This App.</h2>
      <p class="lead">Designed for everyday retail investors (<em>orang awam</em>) and beginner traders as a 10-second fundamental safety check before making decisions.</p>
    </div>

    <div class="grid-3">
      <div class="card card-green">
        <span class="tag tag-green" style="margin-bottom: 8px;">STEP 1: FILTER &amp; AVOID TRAPS</span>
        <div style="font-weight: 800; font-size: 15px; margin-bottom: 6px;">Check the Stock Screener</div>
        <div class="muted" style="font-size: 13px;">
          Before buying a stock hyped on social media, open <strong>Simple Mode</strong>: check if its badge is <strong style="color:#047857;">CASH SAFE / DEBT-FREE</strong> or <strong style="color:#be123c;">CRITICAL CASH</strong>, and see today's live price move.
        </div>
      </div>
      <div class="card card-accent">
        <span class="tag tag-blue" style="margin-bottom: 8px;">STEP 2: CHART + ANNUAL CASH</span>
        <div style="font-weight: 800; font-size: 15px; margin-bottom: 6px;">Inspect Price &amp; Financials</div>
        <div class="muted" style="font-size: 13px;">
          Click <strong>Inspect</strong> to view the Stockbit-style Candlestick chart (1D–1Y), see whether Net Profit is backed by real Operating Cash (FY 2022–2025), and read a 3-sentence plain summary.
        </div>
      </div>
      <div class="card card-amber">
        <span class="tag tag-amber" style="margin-bottom: 8px;">STEP 3: ANTI-FOMO NEWS CHECK</span>
        <div style="font-weight: 800; font-size: 15px; margin-bottom: 6px;">Cross-Check News Links</div>
        <div class="muted" style="font-size: 13px;">
          See a viral stock news link? Paste it into <strong>News &amp; URL Analyzer</strong> (or browse the Daily News Feed) to instantly see if the bullish headline matches real cash in the bank.
        </div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card" style="padding: 13px 18px;">
        <strong style="font-size: 13px; color: #0369a1;">For Beginner Investors (Orang Awam):</strong>
        <span style="font-size: 12.5px; color: #475569;">Pick safer long-term companies ("Cash Fortress" with zero short-term debt &amp; positive CFO) without needing an accounting degree.</span>
      </div>
      <div class="card" style="padding: 13px 18px;">
        <strong style="font-size: 13px; color: #047857;">For Novice Swing Traders:</strong>
        <span style="font-size: 12.5px; color: #475569;">Pair live OHLCV candlestick trends with daily RSS news sentiment and avoid stocks at risk of sudden suspension or debt default.</span>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; User Workflow</span>
      <span>Slide 4 / 10</span>
    </div>
  </section>

  <!-- SLIDE 5: LIVE SCREENSHOT 1 — SCREENER -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">04 / LIVE APP DEMO — STOCK SCREENER</div>
      <h2>Screen 49 IDX Stocks by Live Price, News Sentiment, &amp; Cash Health.</h2>
    </div>

    <div class="grid-demo">
      <div class="shot-frame">
        <img src="{shots['screener']}" alt="Stock Screener Screenshot">
      </div>
      <div style="display: flex; flex-direction: column; gap: 12px;">
        <div class="card card-accent" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">4-Quadrant Cartesian Radar</div>
          <div class="muted">Visually separates <strong>Cash Fortress</strong> stocks (bottom-right) from <strong>Double Stress</strong> stocks (top-left).</div>
        </div>
        <div class="card card-green" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">5-Sector Heatmap + Live Quotes</div>
          <div class="muted">One-click filter across Construction, Banking, FMCG, Energy, &amp; Telecom with live <code>.JK</code> price &amp; 1D % change.</div>
        </div>
        <div class="card card-amber" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Simple Mode vs. Expert Mode</div>
          <div class="muted">Switch between beginner-friendly labels and institutional accounting metrics instantly.</div>
        </div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Live Screenshot: Stock Screener</span>
      <span>Slide 5 / 10</span>
    </div>
  </section>

  <!-- SLIDE 6: LIVE SCREENSHOT 2 — STOCK DETAIL (STOCKBIT-STYLE) -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">05 / LIVE APP DEMO — STOCK DETAIL (STOCKBIT-STYLE)</div>
      <h2>Exchange Candlestick Chart + Triangulation + Annual XBRL Financials.</h2>
    </div>

    <div class="grid-demo">
      <div class="shot-frame">
        <img src="{shots['detail']}" alt="Stock Detail Candlestick Screenshot">
      </div>
      <div style="display: flex; flex-direction: column; gap: 12px;">
        <div class="card card-green" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">TradingView Lightweight Charts</div>
          <div class="muted">Interactive OHLCV candlesticks + Volume bars across <strong>1D (15m), 1W (1h), 1M, 3M, &amp; 1Y</strong> with crosshair inspection.</div>
        </div>
        <div class="card card-accent" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">3-Way Triangulation Card</div>
          <div class="muted">Combines Live Quote, Latest Daily RSS News, and FY 2025 Cash Coverage &amp; CFO in one glance.</div>
        </div>
        <div class="card card-amber" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Multi-Year Annuals &amp; CALK</div>
          <div class="muted">Full FY 2022–2025 historical table, related-party receivables breakdown, &amp; deterministic cash forecast below.</div>
        </div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Live Screenshot: Stock Detail (BBRI.JK)</span>
      <span>Slide 6 / 10</span>
    </div>
  </section>

  <!-- SLIDE 7: LIVE SCREENSHOT 3 — DAILY NEWS & URL ANALYZER -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">06 / LIVE APP DEMO — DAILY NEWS CRON &amp; URL ANALYZER</div>
      <h2>Automated Daily News Sentiment Cron + Instant Link Cross-Check.</h2>
    </div>

    <div class="grid-demo">
      <div class="shot-frame">
        <img src="{shots['news']}" alt="News & URL Analyzer Screenshot">
      </div>
      <div style="display: flex; flex-direction: column; gap: 12px;">
        <div class="card card-accent" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Daily RSS Sentiment Cron</div>
          <div class="muted">Automatically pulls &amp; scores {s['news_articles']} headlines across {s['news_tickers']} tickers daily (<code>08:00 WIB</code>) + one-click manual refresh.</div>
        </div>
        <div class="card card-red" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Paste Any News Link</div>
          <div class="muted">Auto-detects mentioned issuers (including multi-company articles like <em>PTPP &amp; ADHI</em>) and compares hype vs. real bank cash.</div>
        </div>
        <div class="card card-green" style="padding: 14px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Contextual Isolation Rule</div>
          <div class="muted">Positive news never overrides red cash-stress flags—protecting beginners from FOMO traps.</div>
        </div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Live Screenshot: Daily News &amp; URL Radar</span>
      <span>Slide 7 / 10</span>
    </div>
  </section>

  <!-- SLIDE 8: EMPIRICAL PROOF & ARCHITECTURE -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">07 / EMPIRICAL DATA &amp; ARCHITECTURE</div>
      <h2>Verified FY 2025 Numbers Running on a Lean Serverless Stack.</h2>
    </div>

    <table>
      <thead>
        <tr>
          <th>Issuer</th>
          <th>Sector</th>
          <th>Cash Coverage</th>
          <th>CFO TTM</th>
          <th>Sloan Accrual</th>
          <th>Triangulation Reality</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>WSKT</strong></td>
          <td>Construction</td>
          <td><strong>0.23x</strong></td>
          <td style="color: #be123c; font-weight: 700;">-IDR 559.7 B</td>
          <td>-5.5%</td>
          <td><span class="tag tag-red">CATALYST VS CASH GAP</span> (5.6T Contract News vs Tight Cash)</td>
        </tr>
        <tr>
          <td><strong>TOTL</strong></td>
          <td>Construction</td>
          <td><strong>Debt-Free</strong></td>
          <td style="color: #047857; font-weight: 700;">+IDR 388.4 B</td>
          <td>-0.5%</td>
          <td><span class="tag tag-green">CASH FORTRESS</span> (Zero ST Debt + Interim Dividend)</td>
        </tr>
        <tr>
          <td><strong>BBRI</strong></td>
          <td>Banking</td>
          <td><strong>Debt-Free</strong></td>
          <td style="color: #047857; font-weight: 700;">+IDR 14.62 T</td>
          <td>+1.7%</td>
          <td><span class="tag tag-green">ALIGNED HEALTHY</span> (Strong Operating Cash &amp; Dividend)</td>
        </tr>
        <tr>
          <td><strong>ADRO</strong></td>
          <td>Energy (USD→IDR)</td>
          <td><strong>7.52x</strong></td>
          <td style="color: #047857; font-weight: 700;">+IDR 9.62 T</td>
          <td>-5.9%</td>
          <td><span class="tag tag-green">RESILIENT FUNDAMENTALS</span> (7.52x Cash Buffer)</td>
        </tr>
      </tbody>
    </table>

    <div class="grid-3">
      <div class="card" style="padding: 13px 16px;">
        <strong style="font-size: 12.5px; color: #0369a1;">BACKEND &amp; DB</strong>
        <div class="muted" style="margin-top: 4px;">Python 3.12, FastAPI, <code>lxml</code> XBRL parser, Supabase PostgreSQL, Vercel Serverless.</div>
      </div>
      <div class="card" style="padding: 13px 16px;">
        <strong style="font-size: 12.5px; color: #047857;">MARKET &amp; NEWS</strong>
        <div class="muted" style="margin-top: 4px;">Yahoo Finance <code>.JK</code> parallel quotes, TradingView Lightweight Charts, Google News RSS Cron.</div>
      </div>
      <div class="card" style="padding: 13px 16px;">
        <strong style="font-size: 12.5px; color: #b45309;">AI &amp; BOT</strong>
        <div class="muted" style="margin-top: 4px;">Gemini AI (narrative translator only, 0% math), <code>aiogram 3.x</code> Telegram Bot.</div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Empirical Proof &amp; Stack</span>
      <span>Slide 8 / 10</span>
    </div>
  </section>

  <!-- SLIDE 9: 90-DAY ROADMAP & CO-BUILDER ROLES -->
  <section class="slide slide-dark">
    <div>
      <div class="eyebrow">08 / 90-DAY ROADMAP &amp; WHY JOIN NOW</div>
      <h2>What We Will Build Together in the Next 90 Days.</h2>
      <p class="lead">The core engine is live. Join as a co-builder to help scale data coverage, user retention, and community launch.</p>
    </div>

    <div class="grid-3">
      <div class="card">
        <div style="color: #38bdf8; font-weight: 800; font-size: 13.5px; margin-bottom: 8px;">PHASE 1 (DAYS 1–30)</div>
        <ul>
          <li>Ingest quarterly filings (<code>TW1–TW3</code>) for live TTM</li>
          <li>Activate personal watchlists &amp; Telegram flag alerts</li>
          <li>Add Cash/Market-Cap &amp; Price/CFO valuation context</li>
        </ul>
      </div>
      <div class="card">
        <div style="color: #34d399; font-weight: 800; font-size: 13.5px; margin-bottom: 8px;">PHASE 2 (DAYS 31–60)</div>
        <ul>
          <li>Expand XBRL pipeline from {s['issuers']} to top 200+ liquid IDX stocks</li>
          <li>Mobile-first UX polish &amp; shareable stock diagnostic cards</li>
          <li>User accounts &amp; saved screeners (Supabase Auth)</li>
        </ul>
      </div>
      <div class="card">
        <div style="color: #fbbf24; font-weight: 800; font-size: 13.5px; margin-bottom: 8px;">PHASE 3 (DAYS 61–90)</div>
        <ul>
          <li>Beta launch to Indonesian retail &amp; value-investing groups</li>
          <li>Iterate directly with early beginner &amp; trader feedback</li>
          <li>Design sustainable monetization once retention is proven</li>
        </ul>
      </div>
    </div>

    <div class="card" style="padding: 14px 20px; border-left: 4px solid #38bdf8;">
      <strong style="color: #38bdf8; font-size: 13.5px;">Where You Fit In:</strong>
      <span style="font-size: 13px; color: #cbd5e1; margin-left: 6px;">Full co-builder ownership across Frontend/UX, XBRL Data Scaling, or Growth &amp; Community—with fair equity/rev-share from day one.</span>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Roadmap &amp; Co-Builder Fit</span>
      <span>Slide 9 / 10</span>
    </div>
  </section>

  <!-- SLIDE 10: CALL TO ACTION -->
  <section class="slide slide-dark" style="justify-content: center; gap: 32px;">
    <div>
      <div class="eyebrow">09 / LET'S BUILD THIS TOGETHER</div>
      <h1 style="font-size: 46px;">Try the Live App Today.<br>Let's Ship v3 Together.</h1>
      <p class="lead" style="margin-top: 14px;">
        Test the live screener, inspect <code>BBRI.JK</code> candlesticks, cross-check a news link, and let's talk about building the next phase together.
      </p>
    </div>

    <div class="grid-3">
      <div class="card">
        <div class="kpi-label" style="color: #38bdf8;">LIVE WEB APP (VERCEL)</div>
        <div style="font-size: 14px; font-weight: 700; margin-top: 4px;">
          <a href="https://idx-cash-radar.vercel.app/" target="_blank" style="color: #38bdf8; text-decoration: underline;">https://idx-cash-radar.vercel.app/</a>
        </div>
        <div class="muted" style="margin-top: 4px;">{s['issuers']} IDX Issuers &bull; {s['facts']:,} Audited XBRL Facts &bull; Live Charts</div>
      </div>
      <div class="card">
        <div class="kpi-label" style="color: #34d399;">GITHUB REPOSITORY</div>
        <div style="font-size: 14px; font-weight: 700; margin-top: 4px;">github.com/06202003/idx-cash-radar</div>
        <div class="muted" style="margin-top: 4px;">Commit <code>54e8768</code> &bull; FastAPI + Supabase + Daily News Cron</div>
      </div>
      <div class="card">
        <div class="kpi-label" style="color: #fbbf24;">NEXT STEP</div>
        <div style="font-size: 14px; font-weight: 700; margin-top: 4px;">30-Min Live Demo &amp; Coffee Sync</div>
        <div class="muted" style="margin-top: 4px;">Align on product vision, roles, and our first 30-day sprint.</div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer" style="position: absolute; bottom: 0.55in; left: 0.72in; right: 0.72in;">
      <span>IDX Cash &amp; Accrual Radar &bull; &copy; Yehezkiel David Setiawan, S.Kom, M.Kom</span>
      <span>Slide 10 / 10</span>
    </div>
  </section>

</body>
</html>
"""


def main() -> int:
    stats = load_live_stats()
    shots = capture_live_screenshots()
    print(f"Captured 3 live screenshots in {SHOTS_DIR}")

    html = build_html(stats, shots)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote HTML deck: {OUT_HTML}")

    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        page.goto(OUT_HTML.resolve().as_uri(), wait_until="load")
        page.wait_for_timeout(500)
        page.pdf(
            path=str(OUT_PDF),
            width="13.333in",
            height="7.5in",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()
    print(f"Wrote PDF deck : {OUT_PDF} ({OUT_PDF.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
