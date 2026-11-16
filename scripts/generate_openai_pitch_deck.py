"""
Generates an investor-grade 12-slide 16:9 OpenAI-style Pitch Deck PDF
for IDX Cash & Accrual Radar.
Features Swiss/OpenAI editorial typography, zero pill bubbles, full-bleed
readable single-screenshot demos, verified FY 2022-2025 historical validation,
business model & pricing tiers, legal/ToS safeguards, and concrete roadmap.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "idx_cash_radar.db"
OUT_PDF = ROOT_DIR / "docs" / "IDX_Cash_Accrual_Radar_Pitch_Deck.pdf"


def load_verified_stats() -> dict[str, int]:
    """Reads live verified counts from SQLite."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        issuers = conn.execute("SELECT COUNT(*) FROM issuers").fetchone()[0]
        filings = conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
        facts = conn.execute("SELECT COUNT(*) FROM canonical_facts").fetchone()[0]
    return {"issuers": issuers, "filings": filings, "facts": facts}


def build_deck_html(stats: dict[str, int]) -> str:
    """Constructs the 12-slide 16:9 OpenAI-style investor pitch deck HTML."""
    n_issuers = stats["issuers"]
    n_filings = stats["filings"]
    n_facts = stats["facts"]

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <title>IDX Cash &amp; Accrual Radar | Investor Pitch Deck</title>
  <style>
    @page {{
      size: 13.333in 7.5in;
      margin: 0;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
      background: #0d0d0f;
    }}
    .slide {{
      width: 13.333in;
      height: 7.5in;
      padding: 0.56in 0.78in;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      position: relative;
      overflow: hidden;
      page-break-after: always;
    }}
    .slide:last-child {{
      page-break-after: auto;
    }}
    .dark {{
      background: #0d0d0f;
      color: #f4f4f5;
    }}
    .light {{
      background: #ffffff;
      color: #09090b;
    }}
    .eyebrow {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #10a37f;
    }}
    .slide-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 12px;
      border-bottom: 1px solid;
    }}
    .dark .slide-header {{ border-color: #26262b; }}
    .light .slide-header {{ border-color: #e4e4e7; }}

    .brand-mark {{
      font-size: 12px;
      font-weight: 500;
      letter-spacing: -0.01em;
    }}
    .dark .brand-mark {{ color: #a1a1aa; }}
    .light .brand-mark {{ color: #71717a; }}

    h1 {{
      font-size: 54px;
      font-weight: 600;
      line-height: 1.07;
      letter-spacing: -0.035em;
      max-width: 980px;
    }}
    h2 {{
      font-size: 34px;
      font-weight: 600;
      line-height: 1.15;
      letter-spacing: -0.03em;
      max-width: 960px;
    }}
    .subtitle {{
      font-size: 17.5px;
      line-height: 1.5;
      font-weight: 400;
      max-width: 820px;
    }}
    .dark .subtitle {{ color: #d4d4d8; }}
    .light .subtitle {{ color: #3f3f46; }}

    .cols-2 {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 36px;
    }}
    .cols-3 {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 30px;
    }}
    .cols-4 {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 26px;
    }}

    .rule-block {{
      border-top: 1px solid;
      padding-top: 15px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .dark .rule-block {{ border-color: #2e2e34; }}
    .light .rule-block {{ border-color: #d4d4d8; }}
    .rule-accent {{ border-top: 2px solid #10a37f !important; }}
    .rule-danger {{ border-top: 2px solid #e11d48 !important; }}
    .rule-warn {{ border-top: 2px solid #d97706 !important; }}

    .kicker {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }}
    .dark .kicker {{ color: #a1a1aa; }}
    .light .kicker {{ color: #52525b; }}

    .block-title {{
      font-size: 19px;
      font-weight: 600;
      letter-spacing: -0.015em;
    }}
    .block-body {{
      font-size: 14.5px;
      line-height: 1.55;
    }}
    .dark .block-body {{ color: #d4d4d8; }}
    .light .block-body {{ color: #27272a; }}

    .kv-list {{
      display: flex;
      flex-direction: column;
      margin-top: 4px;
    }}
    .kv-row {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 7px 0;
      border-bottom: 1px solid;
      font-size: 14px;
    }}
    .light .kv-row {{ border-color: #e4e4e7; }}
    .dark .kv-row {{ border-color: #242429; }}
    .light .kv-label {{ color: #52525b; font-weight: 500; }}
    .dark .kv-label {{ color: #a1a1aa; font-weight: 500; }}
    .kv-val {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-weight: 600;
    }}
    .light .kv-val {{ color: #09090b; }}
    .dark .kv-val {{ color: #f4f4f5; }}

    .metric-big {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 38px;
      font-weight: 600;
      letter-spacing: -0.03em;
      line-height: 1.05;
    }}

    .accent {{ color: #10a37f !important; }}
    .danger {{ color: #e11d48 !important; }}
    .warn {{ color: #d97706 !important; }}

    table.clean {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13.5px;
    }}
    table.clean th {{
      text-align: left;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 9px 12px 9px 0;
      border-bottom: 1px solid;
    }}
    table.clean td {{
      padding: 11px 12px 11px 0;
      border-bottom: 1px solid;
      line-height: 1.45;
      vertical-align: top;
    }}
    .light table.clean th {{ color: #52525b; border-color: #d4d4d8; }}
    .light table.clean td {{ color: #f4f4f5; border-color: #e4e4e7; }}
    .dark table.clean th {{ color: #a1a1aa; border-color: #2e2e34; }}
    .dark table.clean td {{ color: #e4e4e7; border-color: #242429; }}

    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .slide-footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 10px;
      border-top: 1px solid;
      font-size: 11px;
    }}
    .dark .slide-footer {{ border-color: #242429; color: #71717a; }}
    .light .slide-footer {{ border-color: #e4e4e7; color: #71717a; }}

    .shot-wrap {{
      border: 1px solid;
      border-radius: 4px;
      overflow: hidden;
      background: #0b0f19;
    }}
    .dark .shot-wrap {{ border-color: #27272a; }}
    .light .shot-wrap {{ border-color: #d4d4d8; }}
    .shot-caption-bar {{
      display: flex;
      justify-content: space-between;
      padding: 6px 12px;
      background: #141418;
      border-bottom: 1px solid #27272a;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 10.5px;
      color: #a1a1aa;
    }}
    .shot-img {{
      width: 100%;
      height: auto;
      display: block;
      object-fit: contain;
      background: #0b0f19;
    }}
  </style>
</head>
<body>

  <!-- SLIDE 01: HERO (OBSIDIAN) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">IDX CASH &amp; ACCRUAL RADAR / V2.0</span>
      <span class="brand-mark">Bursa Efek Indonesia Financial Intelligence</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 18px;">
      <span class="kicker accent">DETERMINISTIC XBRL ACCOUNTING + GEMINI NARRATIVE LAYER</span>
      <h1>Membaca kejujuran kas di balik angka laba pasar modal Indonesia.</h1>
      <p class="subtitle">
        Platform intelijen fundamental yang membedah laporan XBRL periodik BEI (FY 2022-2025)
        secara deterministik, menguji ketahanan kas terhadap utang jatuh tempo, dan
        membandingkannya secara real-time dengan sentimen berita pasar.
      </p>
    </div>
    <div class="cols-4">
      <div class="rule-block rule-accent">
        <div class="kicker">Semesta Terpantau</div>
        <div class="metric-big accent">{n_issuers}</div>
        <div class="block-body">Emiten BEI lintas 5 sektor makro</div>
      </div>
      <div class="rule-block">
        <div class="kicker">Laporan Periodik</div>
        <div class="metric-big">{n_filings}</div>
        <div class="block-body">Filing XBRL audited FY 2022-2025</div>
      </div>
      <div class="rule-block">
        <div class="kicker">Fakta Kanonikal</div>
        <div class="metric-big">{n_facts:,}</div>
        <div class="block-body">Lolos 4-Way Accounting Sanity Check</div>
      </div>
      <div class="rule-block">
        <div class="kicker">Latensi Kueri</div>
        <div class="metric-big accent">3.51 ms</div>
        <div class="block-body">SQLite berindeks, Python Decimal</div>
      </div>
    </div>
  </section>

  <!-- SLIDE 02: FIRST-PRINCIPLES PROBLEM (LIGHT) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">01 / MASALAH MENDASAR</span>
      <span class="brand-mark">First-Principles Thesis</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 12px;">
      <h2>Laba akuntansi bisa positif di atas kertas sementara kas di bank terus menyusut.</h2>
      <p class="subtitle">
        Investor ritel dan analis sering terjebak oleh rasio permukaan atau euforia kontrak baru
        tanpa memeriksa apakah pendapatan benar-benar cair menjadi arus kas operasi (CFO).
      </p>
    </div>
    <div class="cols-3">
      <div class="rule-block">
        <span class="kicker">01 / AKRUAL PSAK 72</span>
        <div class="block-title">Laba Tertahan di Piutang</div>
        <div class="block-body">
          Pendapatan proyek diakui berdasarkan persentase fisik, namun uang tunai tertahan di
          Aset Kontrak dan Piutang Usaha hingga bertahun-tahun.
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">02 / LIKUIDITAS JATUH TEMPO</span>
        <div class="block-title">Ilusi Berita Positif</div>
        <div class="block-body">
          Pengumuman kontrak bernilai triliunan sering menutupi fakta bahwa kas riil perusahaan
          tidak cukup menutup utang bank dan obligasi jangka pendek.
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">03 / KELEMAHAN LLM UMUM</span>
        <div class="block-title">AI Generatif Tanpa Audit</div>
        <div class="block-body">
          Chatbot AI generik rentan salah hitung saat membaca PDF laporan keuangan karena tidak
          memiliki mesin akuntansi deterministik maupun jejak tag XBRL.
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>IDX Cash &amp; Accrual Radar</span>
      <span class="mono">02 / 14</span>
    </div>
  </section>

  <!-- SLIDE 03: EMPIRICAL CASE STUDY (LIGHT) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">02 / STUDI KASUS EMPIRIS BEI</span>
      <span class="brand-mark">Berita Pasar Real-Time vs Neraca Audited FY 2025</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <h2>Satu mesin yang memisahkan katalis berita dari ketahanan kas nyata.</h2>
      <p class="subtitle">
        Perbandingan langsung dari database terverifikasi pada tiga emiten konstruksi Indonesia.
      </p>
    </div>
    <div class="cols-3">
      <div class="rule-block rule-danger">
        <span class="kicker danger">TEKANAN KAS</span>
        <div class="block-title" style="font-size: 24px;">WSKT</div>
        <div class="block-body" style="font-size: 14px;">
          <strong>Berita:</strong> Kontrak baru Rp 5,6 T (pembayaran bulanan).
        </div>
        <div class="kv-list">
          <div class="kv-row">
            <span class="kv-label">Cash Coverage</span>
            <span class="kv-val danger">0.23x</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Kas / Utang JP</span>
            <span class="kv-val">4,41 T / 19,47 T</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">CFO TTM</span>
            <span class="kv-val danger">-Rp 559,7 M</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Laba Bersih</span>
            <span class="kv-val danger">-Rp 4,48 T</span>
          </div>
        </div>
        <div style="font-size: 13.5px; font-weight: 600; color: #f4f4f5; margin-top: 4px;">
          Berita positif tidak menghapus tekanan neraca.
        </div>
      </div>

      <div class="rule-block rule-warn">
        <span class="kicker warn">PEMULIHAN BERSYARAT</span>
        <div class="block-title" style="font-size: 24px;">WIKA</div>
        <div class="block-body" style="font-size: 14px;">
          <strong>Berita:</strong> Beban utang Whoosh, dukungan Danantara.
        </div>
        <div class="kv-list">
          <div class="kv-row">
            <span class="kv-label">Cash Coverage (XBRL)</span>
            <span class="kv-val warn">0.95x</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Kas / Utang JP (inc. sewa)</span>
            <span class="kv-val">2,75 T / 2,89 T</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">CFO TTM</span>
            <span class="kv-val danger">-Rp 348,0 M</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Laba Bersih</span>
            <span class="kv-val danger">-Rp 10,14 T</span>
          </div>
        </div>
        <div style="font-size: 13.5px; font-weight: 600; color: #f4f4f5; margin-top: 4px;">
          Butuh restrukturisasi agar CFO kembali positif.
        </div>
      </div>

      <div class="rule-block rule-accent">
        <span class="kicker accent">BENCHMARK SOLVEN</span>
        <div class="block-title" style="font-size: 24px;">TOTL</div>
        <div class="block-body" style="font-size: 14px;">
          <strong>Neraca:</strong> Kontraktor swasta bebas utang jangka pendek.
        </div>
        <div class="kv-list">
          <div class="kv-row">
            <span class="kv-label">Utang JP Berbunga</span>
            <span class="kv-val accent">Rp 0 (Bebas)</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Uang Kas</span>
            <span class="kv-val accent">Rp 1,10 T</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">CFO TTM</span>
            <span class="kv-val accent">+Rp 434,9 M</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Sloan Accrual</span>
            <span class="kv-val accent">-0.5%</span>
          </div>
        </div>
        <div style="font-size: 13.5px; font-weight: 600; color: #10a37f; margin-top: 4px;">
          Laba pembukuan didukung penuh kas masuk riil.
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>
        Contextual Isolation: Sentimen berita tidak pernah mengubah flag kas deterministik
      </span>
      <span class="mono">03 / 14</span>
    </div>
  </section>

  <!-- SLIDE 04: DEMO 1 - FULL SCREENER & 5-SECTOR HEATMAP (OBSIDIAN) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">03A / DEMO PRODUK: SCREENER &amp; HEATMAP</span>
      <span class="brand-mark">Live Web Terminal (1440px Full View)</span>
    </div>
    <div style="display: grid; grid-template-columns: 2.25fr 1fr; gap: 24px; align-items: start;">
      <div class="shot-wrap">
        <div class="shot-caption-bar">
          <span>IDX Cash Radar / Screener Fundamental &amp; Heatmap 5 Sektor</span>
          <span class="accent">LIVE DATA</span>
        </div>
        <img src="screenshots/01_screener_heatmap.png"
             class="shot-img" style="max-height: 455px;">
      </div>
      <div style="display: flex; flex-direction: column; gap: 18px;">
        <div class="rule-block rule-accent">
          <span class="kicker accent">HEATMAP 5 SEKTOR BEI</span>
          <div class="block-title" style="font-size: 16px;">Agregasi CFO+ Realistis</div>
          <div class="block-body" style="font-size: 13px;">
            Menampilkan persentase emiten dengan arus kas operasi positif pada Konstruksi, FMCG,
            Perbankan, Energi, dan Telekomunikasi.
          </div>
        </div>
        <div class="rule-block">
          <span class="kicker">SELF-GROWING DATABASE</span>
          <div class="block-title" style="font-size: 16px;">Tambah Saham &amp; Upload XBRL</div>
          <div class="block-body" style="font-size: 13px;">
            Pengguna dapat menambah emiten baru via form laporan keuangan atau unggah berkas XBRL
            (.xml/.zip) langsung dari tombol toolbar.
          </div>
        </div>
        <div class="rule-block">
          <span class="kicker">DUAL-MODE UX</span>
          <div class="block-title" style="font-size: 16px;">Mode Pemula &amp; Expert</div>
          <div class="block-body" style="font-size: 13px;">
            Satu klik mengubah istilah teknis menjadi bahasa awam yang mudah dipahami pemula.
          </div>
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>Data keuangan bersumber dari filing periodik XBRL BEI (FY 2022-2025 Audited)</span>
      <span class="mono">04 / 14</span>
    </div>
  </section>

  <!-- SLIDE 05: DEMO 2 - REAL-TIME NEWS CROSS-CHECK & FORECAST (LIGHT) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">03B / DEMO PRODUK: ANALISIS BERITA REAL-TIME</span>
      <span class="brand-mark">Live News Link + Periodic Financial Cross-Check</span>
    </div>
    <div style="display: grid; grid-template-columns: 2.25fr 1fr; gap: 24px; align-items: start;">
      <div class="shot-wrap">
        <div class="shot-caption-bar">
          <span>IDX Cash Radar / Analisis Link Berita &amp; Proyeksi Kas</span>
          <span class="accent">WSKT CROSS-CHECK</span>
        </div>
        <img src="screenshots/02_news_forecast_wskt.png"
             class="shot-img" style="max-height: 455px;">
      </div>
      <div style="display: flex; flex-direction: column; gap: 18px;">
        <div class="rule-block rule-accent">
          <span class="kicker accent">REAL-TIME VS PERIODIK</span>
          <div class="block-title" style="font-size: 16px;">Uji Berita ke Neraca</div>
          <div class="block-body" style="font-size: 13px;">
            Artikel berita diambil secara real-time, lalu diuji terhadap laporan keuangan periodik
            audited emiten di SQLite.
          </div>
        </div>
        <div class="rule-block">
          <span class="kicker">PROYEKSI 12-24 BULAN</span>
          <div class="block-title" style="font-size: 16px;">Cash Trajectory &amp; Watchpoints</div>
          <div class="block-body" style="font-size: 13px;">
            Menampilkan skenario bisnis ke depan, estimasi regresi CFO FY 2026-2027, dan 3
            indikator kuartalan wajib pantau.
          </div>
        </div>
        <div class="rule-block">
          <span class="kicker">KEPATUHAN HAK CIPTA</span>
          <div class="block-title" style="font-size: 16px;">On-Demand Extraction</div>
          <div class="block-body" style="font-size: 13px;">
            Tidak menyimpan atau menerbitkan ulang artikel penuh; hanya mengekstrak fakta kunci
            dengan atribusi sumber atau input teks manual.
          </div>
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>Contextual Isolation menjaga flag likuiditas kebal terhadap headline optimistis</span>
      <span class="mono">05 / 14</span>
    </div>
  </section>

  <!-- SLIDE 06: DEMO 3 - UNIFIED GEMINI-STYLE AI WORKSPACE (OBSIDIAN) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">03C / DEMO PRODUK: ASISTEN AI TERPADU</span>
      <span class="brand-mark">Unified Grounded Chatbot (Sidebar + Multi-Session)</span>
    </div>
    <div style="display: grid; grid-template-columns: 2.25fr 1fr; gap: 24px; align-items: start;">
      <div class="shot-wrap">
        <div class="shot-caption-bar">
          <span>IDX Cash Radar / Asisten Tanya Saham (Sidebar + History)</span>
          <span class="accent">GEMINI WORKSPACE</span>
        </div>
        <img src="screenshots/03_gemini_chatbot.png"
             class="shot-img" style="max-height: 455px;">
      </div>
      <div style="display: flex; flex-direction: column; gap: 18px;">
        <div class="rule-block rule-accent">
          <span class="kicker accent">GROUNDING KETAT</span>
          <div class="block-title" style="font-size: 16px;">Angka 100% Deterministik</div>
          <div class="block-body" style="font-size: 13px;">
            Narasi AI dibatasi ketat oleh fakta terverifikasi SQLite BEI sehingga tidak mengarang
            angka rasio keuangan.
          </div>
        </div>
        <div class="rule-block">
          <span class="kicker">MULTI-SESSION WORKSPACE</span>
          <div class="block-title" style="font-size: 16px;">Sidebar &amp; Audit Cepat</div>
          <div class="block-body" style="font-size: 13px;">
            Riwayat percakapan tersimpan lokal per sesi, tombol Chat Baru, dan pintasan cepat
            emiten utama maupun saham baru unggahan user.
          </div>
        </div>
        <div class="rule-block">
          <span class="kicker">KETAHANAN OFFLINE</span>
          <div class="block-title" style="font-size: 16px;">Fallback &lt;10 ms</div>
          <div class="block-body" style="font-size: 13px;">
            Jika kuota API Gemini penuh atau jaringan lambat, mesin aturan Python langsung
            menjawab terstruktur tanpa error.
          </div>
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>Satu chatbot terpadu menggantikan widget ganda dengan kepatuhan bahasa OJK</span>
      <span class="mono">06 / 14</span>
    </div>
  </section>

  <!-- SLIDE 07: ARCHITECTURE & STATISTICAL DISCLAIMER (LIGHT) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">04 / CARA KERJA &amp; KEPATUHAN</span>
      <span class="brand-mark">4-Layer Deterministic Architecture</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <h2>Python menghitung, LLM hanya menerjemahkan menjadi bahasa manusia.</h2>
    </div>
    <div class="cols-4">
      <div class="rule-block">
        <span class="kicker">LAYER 01</span>
        <div class="block-title">XBRL Ingestion</div>
        <div class="block-body" style="font-size: 13.5px;">
          Parser <span class="mono">lxml</span> nol-dimensi, hash SHA-256, dan 4-Way Sanity Check
          (Aset = Liabilitas + Ekuitas).
        </div>
      </div>
      <div class="rule-block rule-accent">
        <span class="kicker accent">LAYER 02</span>
        <div class="block-title">Deterministic Math</div>
        <div class="block-body" style="font-size: 13.5px;">
          Aritmatika <span class="mono">Decimal</span>: de-kumulasi YTD ke TTM, Cash Coverage,
          Sloan Accrual, dan boolean Safeguards.
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">LAYER 03</span>
        <div class="block-title">Statistical Model</div>
        <div class="block-body" style="font-size: 13.5px;">
          Regresi OLS (<span class="mono">scipy</span>), proyeksi CFO FY 2026-2027 (CI 90%), serta
          indikator statistik internal P(Distress).
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">LAYER 04</span>
        <div class="block-title">Gemini Translator</div>
        <div class="block-body" style="font-size: 13.5px;">
          Model <span class="mono">gemini-3.8-flash</span> menerjemahkan fakta SQLite; output
          dipindai linter terhadap 10 kata terlarang.
        </div>
      </div>
    </div>
    <div class="rule-block rule-warn">
      <span class="kicker warn">BATASAN REGULASI &amp; STATISTIK</span>
      <div class="block-body" style="font-size: 13.5px;">
        <strong>Disclaimer Model:</strong> Skor P(Distress) dan Rating Sintetis adalah keluaran
        model kuantitatif statistik internal untuk riset fundamental deskriptif, <strong>bukan
        pemeringkatan kredit resmi</strong> maupun ajakan atau instruksi transaksi efek.
      </div>
    </div>
    <div class="slide-footer">
      <span>Setiap angka membawa metadata XML XBRL: localname, contextRef, unitRef, SHA-256</span>
      <span class="mono">07 / 14</span>
    </div>
  </section>

  <!-- SLIDE 08: RETROSPECTIVE CASE DETECTION (OBSIDIAN) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">05 / STUDI RETROSPEKTIF &amp; CONTOH DETEKSI</span>
      <span class="brand-mark">120 Filings Audited (FY 2022-2025)</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <h2>Contoh deteksi historis tekanan kas &amp; laba akrual pada sampel BEI.</h2>
      <p class="subtitle">
        Observasi retrospektif pada data historis FY 2022-2025 (studi kasus deteksi, sebelum
        backtest statistik skala penuh lintas bursa).
      </p>
    </div>
    <table class="clean">
      <thead>
        <tr>
          <th style="width: 15%;">Emiten</th>
          <th style="width: 24%;">Sinyal Terdeteksi Sistem</th>
          <th style="width: 34%;">Lintasan Data Historis (FY 2022-2025)</th>
          <th style="width: 27%;">Observasi Kasus</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong class="danger">WIKA (2023)</strong></td>
          <td><span class="mono danger">FLAG_ACUTE_LIQUIDITY</span></td>
          <td>
            Cash Coverage anjlok ke <span class="mono">0.15x</span> (CFO -Rp 2,93 T),
            berlanjut ke rugi -Rp 10,14 T (2025).
          </td>
          <td>Deteksi dini tekanan likuiditas akut sebelum restrukturisasi utang.</td>
        </tr>
        <tr>
          <td><strong class="danger">WSKT (2022-2025)</strong></td>
          <td><span class="mono warn">Coverage &lt; 0.27x (2023-2025)</span></td>
          <td>
            Cash Coverage turun dari <span class="mono">1.37x</span> (2022) ke
            <span class="mono">0.20x</span> (2023) dan <span class="mono">0.23x</span> (2025).
          </td>
          <td>Akumulasi rugi bersih 4 tahun mencapai -Rp 14,09 T.</td>
        </tr>
        <tr>
          <td><strong class="warn">WEGE / DGIK / PBSA</strong></td>
          <td><span class="mono warn">FLAG_ACCRUAL_DIVERGENCE</span></td>
          <td>
            Laba bersih positif namun CFO negatif dan Sloan Accrual &gt; +10% (hingga +23,1%).
          </td>
          <td>Mengisolasi laba akuntansi kertas sebelum kas operasional masuk.</td>
        </tr>
        <tr>
          <td><strong class="accent">TOTL (22-25)</strong></td>
          <td><span class="mono accent">NORMAL / BEBAS UTANG</span></td>
          <td>Utang JP Rp 0 dan CFO positif 4 tahun beruntun (+Rp 280 M s.d. +Rp 650 M/thn).</td>
          <td>Ketahanan neraca terjaga penuh oleh arus kas operasi riil.</td>
        </tr>
      </tbody>
    </table>
    <div class="slide-footer">
      <span>Didukung 126/126 automated unit &amp; API tests lulus serta latensi kueri 3.51 ms</span>
      <span class="mono">08 / 14</span>
    </div>
  </section>

  <!-- SLIDE 09: TARGET USERS & BUSINESS MODEL (LIGHT) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">06 / TARGET PENGGUNA &amp; MODEL BISNIS</span>
      <span class="brand-mark">Who Pays and Why</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 10px;">
      <h2>Monetisasi berjenjang dari investor ritel hingga meja riset institusi.</h2>
      <p class="subtitle">
        Menjawab kebutuhan verifikasi cepat antara narasi berita dan laporan keuangan BEI.
      </p>
    </div>
    <div class="cols-3">
      <div class="rule-block">
        <span class="kicker">TIER 1 / RITEL AKTIF</span>
        <div class="block-title">Akses Ritel (Freemium &amp; Berbayar)</div>
        <div class="kv-list">
          <div class="kv-row">
            <span class="kv-label">Target</span>
            <span class="kv-val">Investor Ritel BEI</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Nilai Jual</span>
            <span class="kv-val">Anti Jebakan Laba Semu</span>
          </div>
        </div>
        <div class="block-body" style="font-size: 13.5px; margin-top: 6px;">
          Akses Screener Mode Pemula, peringatan watchlist Telegram, dan kuota harian Analisis
          Link Berita Real-Time + Chatbot.
        </div>
      </div>

      <div class="rule-block rule-accent">
        <span class="kicker accent">TIER 2 / ANALIS &amp; KOMUNITAS</span>
        <div class="block-title">Pro Workspace (Langganan Analis)</div>
        <div class="kv-list">
          <div class="kv-row">
            <span class="kv-label">Target</span>
            <span class="kv-val">Analis, Edukator, Trader</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Nilai Jual</span>
            <span class="kv-val">Riset Cepat + Audit XBRL</span>
          </div>
        </div>
        <div class="block-body" style="font-size: 13.5px; margin-top: 6px;">
          Mode Expert penuh (Sloan, OLS, CI 90%), upload XBRL tak terbatas (Self-Growing DB),
          ekspor CSV, dan audit catatan CALK verbatim.
        </div>
      </div>

      <div class="rule-block">
        <span class="kicker">TIER 3 / B2B &amp; INSTITUSI</span>
        <div class="block-title">Enterprise Data &amp; API (Lisensi B2B)</div>
        <div class="kv-list">
          <div class="kv-row">
            <span class="kv-label">Target</span>
            <span class="kv-val">Sekuritas, MI, Perbankan</span>
          </div>
          <div class="kv-row">
            <span class="kv-label">Nilai Jual</span>
            <span class="kv-val">Credit Early Warning</span>
          </div>
        </div>
        <div class="block-body" style="font-size: 13.5px; margin-top: 6px;">
          Integrasi REST API skor likuiditas korporasi, pipeline XBRL otomatis terdedikasi, dan
          jejak audit SHA-256 untuk tim risiko kredit.
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>Revenue Drivers: SaaS Langganan Bulanan &amp; Lisensi Data API B2B</span>
      <span class="mono">09 / 14</span>
    </div>
  </section>

  <!-- SLIDE 10: COMPETITIVE MOAT & DEFENSIBILITY (LIGHT) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">07 / KEUNGGULAN KOMPETITIF</span>
      <span class="brand-mark">Structural Moat</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 10px;">
      <h2>Mengapa sistem ini sulit ditiru oleh screener maupun chatbot generik.</h2>
    </div>
    <table class="clean">
      <thead>
        <tr>
          <th style="width: 24%;">Dimensi</th>
          <th style="width: 38%;">Chatbot AI / Screener Konvensional</th>
          <th style="width: 38%;">IDX Cash &amp; Accrual Radar</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Akurasi Angka</strong></td>
          <td>Rentan salah hitung saat membaca PDF atau memproses rasio dengan LLM.</td>
          <td>
            <strong class="accent">100% Deterministik:</strong> dihitung Python
            <span class="mono">Decimal</span> dari tag XML XBRL primer.
          </td>
        </tr>
        <tr>
          <td><strong>Jejak Audit</strong></td>
          <td>Angka agregat tanpa sumber tag akuntansi maupun hash dokumen.</td>
          <td>
            Menyimpan <span class="mono">localname</span>, <span class="mono">contextRef</span>,
            <span class="mono">unitRef</span>, dan SHA-256.
          </td>
        </tr>
        <tr>
          <td><strong>Kontras Berita</strong></td>
          <td>Headline positif sering menenggelamkan sinyal risiko likuiditas.</td>
          <td>
            <strong>Contextual Isolation:</strong> berita positif tidak bisa menimpa bendera kas
            kritis.
          </td>
        </tr>
        <tr>
          <td><strong>Ketahanan Offline</strong></td>
          <td>Berhenti bekerja ketika kuota API LLM habis atau jaringan melambat.</td>
          <td>Auto-fallback ke mesin aturan deterministik dalam &lt; 10 ms.</td>
        </tr>
        <tr>
          <td><strong>Pertumbuhan Data</strong></td>
          <td>Database statis, bergantung pada rilis manual pengembang.</td>
          <td>
            <strong>Self-Growing:</strong> pengguna dapat menambah emiten atau unggah XBRL di UI.
          </td>
        </tr>
      </tbody>
    </table>
    <div class="slide-footer">
      <span>Defensible Financial Data Engineering</span>
      <span class="mono">10 / 14</span>
    </div>
  </section>

  <!-- SLIDE 11: CONCRETE ROADMAP & AUTOMATION SCALE (LIGHT) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">08 / PETA JALAN EKSPANSI TERUKUR</span>
      <span class="brand-mark">From 48 to 800+ IDX Issuers</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 10px;">
      <h2>Skalabilitas berbasis pipeline otomatis, bukan input manual.</h2>
    </div>
    <div class="cols-3">
      <div class="rule-block rule-accent">
        <span class="kicker accent">SAAT INI : V2.0 SIAP PAKAI</span>
        <div class="block-title">48 Emiten &amp; Dockerized</div>
        <div class="block-body">
          FastAPI Web Terminal, Bot Telegram (<span class="mono">aiogram 3.x</span>), Real-Time
          News Cross-Check, Unified Gemini Chat, serta Self-Growing XBRL Ingestor sudah berjalan
          di Docker/VPS.
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">Q1-Q2 : EKSPANSI 200+ EMITEN</span>
        <div class="block-title">Skrip Unduh &amp; Normalisasi Otomatis</div>
        <div class="block-body">
          Menggunakan skrip otomatis unduh filing BEI dan batch normalizer (parsing lokal
          terukur ~9 ms per berkas XBRL uji) dengan verifikasi SHA-256 &amp; sanity check per
          kuartal.
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">JANGKA PANJANG : 800+ EMITEN</span>
        <div class="block-title">Cakupan Penuh BEI &amp; B2B API</div>
        <div class="block-body">
          Kamus taksonomi multi-sektor (termasuk asuransi &amp; properti), pemeringkatan kuartil
          Q1-Q4 per sub-industri, serta integrasi API institusional dan riset sekuritas.
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>Pipeline otomasi menghilangkan bottleneck penambahan emiten per kuartal</span>
      <span class="mono">11 / 14</span>
    </div>
  </section>

  <!-- SLIDE 12: COLLABORATION ASK (DARK OBSIDIAN) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">09 / YANG GUA CARI (KOLABORASI)</span>
      <span class="brand-mark">Building Together from MVP to Scale</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 10px;">
      <h2>Engine inti sudah jalan; ini 4 area yang butuh partner untuk scale.</h2>
      <p class="subtitle">
        Fokus kolaborasi spesifik agar produk ini bertransformasi dari MVP fungsional menjadi
        platform riset pasar modal yang tervalidasi penuh.
      </p>
    </div>
    <div class="cols-2" style="row-gap: 26px;">
      <div class="rule-block rule-accent">
        <span class="kicker accent">01 / ENGINEERING &amp; INFRA</span>
        <div class="block-title">Scaling 48 -> 800+ Emiten</div>
        <div class="block-body">
          Otomasi penjadwalan ingestion kuartalan dari portal BEI, perluasan kamus taksonomi
          lintas sektor, serta deployment cloud/VPS yang tangguh.
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">02 / DATA &amp; RISET KUANTITATIF</span>
        <div class="block-title">Backtest Prediktif Harga &amp; Gagal Bayar</div>
        <div class="block-body">
          Menguji historis emiten Cash Coverage rendah + Sloan tinggi terhadap kinerja saham dan
          risiko gagal bayar 1-2 tahun ke depan untuk membuktikan edge sinyal.
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">03 / BISNIS &amp; PRODUK</span>
        <div class="block-title">Validasi User &amp; Monetisasi</div>
        <div class="block-body">
          Menentukan segmen paling siap bayar (ritel aktif, analis riset, atau B2B sekuritas)
          serta merancang paket produk dan distribusi yang tepat.
        </div>
      </div>
      <div class="rule-block rule-warn">
        <span class="kicker warn">04 / LEGAL &amp; COMPLIANCE</span>
        <div class="block-title">Regulasi OJK &amp; Lisensi Data BEI</div>
        <div class="block-body">
          Memastikan penggunaan komersial data XBRL BEI serta batas aman publikasi skor
          statistik internal P(Distress) dan Rating Sintetis ke publik.
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>Open for Technical, Research, Product, and Regulatory Collaboration</span>
      <span class="mono">12 / 14</span>
    </div>
  </section>

  <!-- SLIDE 13: DUE DILIGENCE & KEY FAQ (DARK OBSIDIAN) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">10 / DUE DILIGENCE &amp; PERTANYAAN KRITIS</span>
      <span class="brand-mark">Technical, Data &amp; Regulatory Readiness</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <h2>Jawaban jujur atas 4 pertanyaan kunci sebelum melangkah bersama.</h2>
    </div>
    <div class="cols-2" style="row-gap: 24px;">
      <div class="rule-block">
        <span class="kicker">Q1 / LISENSI DATA XBRL BEI</span>
        <div class="block-title" style="font-size: 16px;">Boleh dipakai komersial?</div>
        <div class="block-body" style="font-size: 13.5px;">
          Berkas XBRL publik BEI terbuka untuk riset dan analisis internal. Namun untuk
          redistribusi data mentah dalam layanan berbayar, verifikasi lisensi data IDX/OJK menjadi
          agenda legal bersama sebelum rilis komersial.
        </div>
      </div>
      <div class="rule-block rule-warn">
        <span class="kicker warn">Q2 / REGULASI &amp; OJK</span>
        <div class="block-title" style="font-size: 16px;">
          P(Distress) &amp; Rating Sintetis aman?
        </div>
        <div class="block-body" style="font-size: 13.5px;">
          Keduanya berlabel eksplisit sebagai keluaran model statistik internal deskriptif, bukan
          pemeringkatan kredit resmi maupun ajakan transaksi, serta dijaga compliance linter. Tetap
          disiapkan review konsultan OJK sebelum skala publik.
        </div>
      </div>
      <div class="rule-block rule-accent">
        <span class="kicker accent">Q3 / OTOMASI EMITEN</span>
        <div class="block-title" style="font-size: 16px;">Seberapa otomatis nambah emiten?</div>
        <div class="block-body" style="font-size: 13.5px;">
          Tag standar sudah otomatis lewat skrip unduh filing + batch normalizer (terukur ~9 ms
          per berkas XBRL uji) serta upload UI. Kerja manual hanya saat memetakan taksonomi sektor
          khusus baru.
        </div>
      </div>
      <div class="rule-block">
        <span class="kicker">Q4 / BUKTI SINYAL</span>
        <div class="block-title" style="font-size: 16px;">
          Sudah terbukti works atau baru akurat?
        </div>
        <div class="block-body" style="font-size: 13.5px;">
          Retrospektif 120 filing FY 2022-2025 sudah mengonfirmasi deteksi WIKA 2023 (0.15x),
          erosi WSKT, serta laba akrual WEGE/DGIK/PBSA. Tahap selanjutnya adalah backtest lintas
          800+ emiten terhadap return harga saham &amp; gagal bayar.
        </div>
      </div>
    </div>
    <div class="slide-footer">
      <span>Transparent Technical &amp; Regulatory Assessment</span>
      <span class="mono">13 / 14</span>
    </div>
  </section>

  <!-- SLIDE 14: CLOSING & CONTACT (OBSIDIAN) -->
  <section class="slide dark">
    <div class="slide-header">
      <span class="eyebrow">IDX CASH &amp; ACCRUAL RADAR</span>
      <span class="brand-mark">Closing &amp; Live Demo</span>
    </div>
    <div style="display: flex; flex-direction: column; gap: 20px; max-width: 920px;">
      <h1>Kejujuran arus kas, diverifikasi dari dokumen primer bursa.</h1>
      <p class="subtitle">
        Menggabungkan presisi akuntansi deterministik, validasi empiris historis, dan narasi AI
        yang patuh regulasi untuk membantu investor Indonesia melihat melampaui laba di permukaan.
      </p>
    </div>
    <div class="cols-2" style="border-top: 1px solid #242429; padding-top: 20px;">
      <div>
        <div class="kicker accent" style="margin-bottom: 6px;">FOUNDER &amp; LEAD ARCHITECT</div>
        <div style="font-size: 16px; font-weight: 600; color: #ffffff;">
          Yehezkiel David Setiawan, S.Kom, M.Kom
        </div>
        <div style="font-size: 13px; color: #a1a1aa; margin-top: 4px;">
          Financial Systems Architect &amp; Data Engineer
        </div>
      </div>
      <div style="text-align: right;">
        <div class="kicker" style="margin-bottom: 6px;">DEMO &amp; REPOSITORY</div>
        <div class="mono" style="font-size: 13px; color: #10a37f;">
          Live Demo via Call / Screen Share | GitHub Private Repo (akses by request)
        </div>
        <div class="mono" style="font-size: 12px; color: #a1a1aa; margin-top: 4px;">
          {n_issuers} Issuers | {n_filings} Filings | {n_facts:,} Facts | 14 / 14
        </div>
      </div>
    </div>
  </section>

</body>
</html>
"""


def generate_pdf() -> Path:
    stats = load_verified_stats()
    html_content = build_deck_html(stats)

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    tmp_html = OUT_PDF.with_suffix(".html")
    tmp_html.write_text(html_content, encoding="utf-8")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(tmp_html.resolve().as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(OUT_PDF),
                width="13.333in",
                height="7.5in",
                print_background=True,
                margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"},
            )
            browser.close()
    finally:
        tmp_html.unlink(missing_ok=True)

    return OUT_PDF


if __name__ == "__main__":
    out = generate_pdf()
    print(f"Generated OpenAI-style Pitch Deck PDF: {out} ({out.stat().st_size} bytes)")
