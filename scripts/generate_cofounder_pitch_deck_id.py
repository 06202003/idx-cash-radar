"""
Generates the Indonesian 13-slide 16:9 Co-Founder Pitch Deck
(HTML + PDF via Playwright) reusing the verified live screenshots in docs/deck_shots/.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.generate_cofounder_pitch_deck import (  # noqa: E402
    SHOTS_DIR,
    launch_browser,
    load_live_stats,
)

OUT_HTML_ID = ROOT_DIR / "docs" / "IDX_Cash_Radar_CoFounder_Deck_ID.html"
OUT_PDF_ID = ROOT_DIR / "docs" / "IDX_Cash_Radar_CoFounder_Deck_ID.pdf"


def load_existing_shots() -> dict[str, str]:
    """Loads existing live screenshots from docs/deck_shots."""
    mapping = {
        "screener": SHOTS_DIR / "01_screener.png",
        "quadrant": SHOTS_DIR / "02_quadrant_map.png",
        "tour": SHOTS_DIR / "03_live_tour.png",
        "detail": SHOTS_DIR / "04_stock_detail.png",
        "calk": SHOTS_DIR / "05_annual_calk.png",
        "news": SHOTS_DIR / "06_news_radar.png",
        "chat": SHOTS_DIR / "07_ai_analyst.png",
    }
    return {k: v.resolve().as_uri() for k, v in mapping.items()}


def build_html_id(s: dict[str, int], shots: dict[str, str]) -> str:
    """Constructs the 13-slide 16:9 Indonesian presentation HTML."""
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <title>IDX Cash &amp; Accrual Radar: Co-Founder Pitch Deck (Bahasa Indonesia)</title>
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
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .shot-frame img {{
      width: 100%;
      height: auto;
      max-height: 4.85in;
      object-fit: contain;
      display: block;
    }}
    .shot-stack {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .shot-stack .shot-frame img {{
      max-height: 2.32in;
      width: auto;
      max-width: 100%;
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
      <div class="eyebrow">PLATFORM INTELIJENSA SAHAM ANTI-HYPE UNTUK PASAR INDONESIA</div>
      <h1>Membantu Investor Ritel Membedakan Kas Riil vs. Laba Kertas.</h1>
      <p class="lead" style="margin-top: 16px;">
        Kami sudah membangun dan merilis platform aktif yang menggabungkan <strong>Laporan XBRL Resmi BEI</strong>,
        <strong>Grafik Saham OHLCV Live</strong>, dan <strong>Sentimen Berita Harian</strong> untuk
        <strong>{s['issuers']} emiten BEI</strong>. Mencari co-builder untuk menskalakan bersama.
      </p>
    </div>

    <div class="grid-4">
      <div class="card">
        <div class="kpi-num">{s['issuers']}</div>
        <div class="kpi-label">Emiten BEI Aktif</div>
        <div class="muted">Konstruksi, Perbankan, FMCG, Energi &amp; Telekomunikasi</div>
      </div>
      <div class="card">
        <div class="kpi-num">{s['facts']:,}</div>
        <div class="kpi-label">Fakta XBRL Teraudit</div>
        <div class="muted">Terverifikasi SHA-256 dari {s['filings']} laporan resmi</div>
      </div>
      <div class="card">
        <div class="kpi-num">{s['news_articles']}</div>
        <div class="kpi-label">Berita Harian Terskor</div>
        <div class="muted">Cron RSS otomatis lintas {s['news_tickers']} emiten</div>
      </div>
      <div class="card">
        <div class="kpi-num">0%</div>
        <div class="kpi-label">Halusinasi Hitungan AI</div>
        <div class="muted">100% kalkulasi Python Decimal + grafik bursa OHLCV</div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; &copy; Yehezkiel David Setiawan, S.Kom, M.Kom</span>
      <span>Slide 1 / 13</span>
    </div>
  </section>

  <!-- SLIDE 2: RINGKASAN EKSEKUTIF -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">01 / RINGKASAN EKSEKUTIF</div>
      <h2>Satu Radar yang Menghubungkan Harga Pasar, Berita Harian, &amp; Arus Kas Riil.</h2>
      <p class="lead">Dirancang untuk investor pemula dan trader ritel yang butuh verifikasi kas setara analis institusi tanpa harus membaca PDF 200 halaman.</p>
    </div>

    <div class="grid-2">
      <div class="card card-accent">
        <div style="font-weight: 800; font-size: 14px; color: #0369a1; margin-bottom: 10px;">YANG SUDAH DIBANGUN</div>
        <ul>
          <li><strong>Engine XBRL Primer:</strong> Membaca berkas mentah <code>instance.xbrl</code> BEI secara langsung, memisahkan arus kas masuk riil (CFO) dari laba akuntansi kertas (Sloan Accruals).</li>
          <li><strong>Grafik Pasar Live + Keuangan Tahunan:</strong> Candlestick OHLCV interaktif (1D-1Y + Volume) berdampingan dengan laporan keuangan FY 2022-2025.</li>
          <li><strong>Cron Sentimen Berita Harian:</strong> Menarik &amp; menilai berita emiten harian secara otomatis sambil menjaga flag bahaya kas tetap terisolasi dari euforia PR.</li>
        </ul>
      </div>

      <div class="card card-green">
        <div style="font-weight: 800; font-size: 14px; color: #047857; margin-bottom: 10px;">KEUNGGULAN STRUKTURAL (MOAT)</div>
        <ul>
          <li><strong>Auditabilitas Sumber Primer:</strong> Setiap metrik tertaut ke tag XML XBRL BEI persis (<code>localname</code>, <code>contextRef</code>) lengkap dengan hash SHA-256 laporan.</li>
          <li><strong>Pemisahan Ketat Matematika &amp; Narasi:</strong> Seluruh rasio dihitung deterministik di Python <code>Decimal</code>; AI hanya menerjemahkan hasil tanpa boleh mengarang angka.</li>
          <li><strong>Safeguard Kebal Sentimen:</strong> Berita positif sebesar apa pun tidak pernah bisa menghapus atau melunakkan peringatan bahaya kas di neraca.</li>
        </ul>
      </div>
    </div>

    <div class="card" style="background: #0f172a; color: #f8fafc; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center;">
      <span style="font-size: 13px; color: #cbd5e1;">Prototipe aktif berjalan untuk <strong style="color: #ffffff;">{s['issuers']} emiten BEI</strong> dengan data audit FY 2022-2025 &amp; kuotasi harga OHLCV live.</span>
      <a href="https://idx-cash-radar.vercel.app/" target="_blank" style="font-size: 12px; font-weight: 700; color: #38bdf8;">idx-cash-radar.vercel.app &#8599;</a>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Ringkasan Eksekutif</span>
      <span>Slide 2 / 13</span>
    </div>
  </section>

  <!-- SLIDE 3: MASALAH -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">02 / MASALAH DI PASAR</div>
      <h2>Mengapa Investor Awam &amp; Trader Pemula Sering Terjebak di BEI.</h2>
      <p class="lead">Lebih dari 12 juta investor ritel Indonesia punya aplikasi grafik, namun tetap sering terbakar kasus gagal bayar utang dan saham "laba kertas".</p>
    </div>

    <div class="grid-3">
      <div class="card card-red">
        <div style="font-weight: 800; font-size: 14px; color: #be123c; margin-bottom: 8px;">1. JEBAKAN "LABA KERTAS"</div>
        <div class="muted" style="font-size: 13px;">
          Emiten melaporkan Laba Bersih positif sehingga pemula mengira sehat, padahal Arus Kas Operasi (CFO) negatif dan uangnya tertahan di piutang tak tertagih.
        </div>
      </div>
      <div class="card card-amber">
        <div style="font-weight: 800; font-size: 14px; color: #b45309; margin-bottom: 8px;">2. BIAS HEADLINE BERITA</div>
        <div class="muted" style="font-size: 13px;">
          Berita kontrak baru (<em>"Menang Kontrak Rp 5,6 Triliun"</em>) memicu aksi beli FOMO, padahal kas di bank hanya menutup kurang dari <strong>20%</strong> utang jangka pendek jatuh tempo.
        </div>
      </div>
      <div class="card card-accent">
        <div style="font-weight: 800; font-size: 14px; color: #0369a1; margin-bottom: 8px;">3. PDF TEBAL &amp; AI NGARANG</div>
        <div class="muted" style="font-size: 13px;">
          Laporan keuangan BEI mencapai 150+ halaman, sementara chatbot AI generik sering berhalusinasi saat diminta menghitung atau merangkum angka keuangan.
        </div>
      </div>
    </div>

    <div class="card" style="padding: 14px 18px; border-left: 4px solid #0f172a;">
      <strong style="font-size: 13px;">Celah Pasar:</strong>
      <span style="font-size: 13px; color: #334155;">Trader pemula butuh satu tempat yang menerjemahkan kesehatan kas XBRL ke bahasa sederhana berdampingan dengan grafik harga &amp; berita harian.</span>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Rumusan Masalah</span>
      <span>Slide 3 / 13</span>
    </div>
  </section>

  <!-- SLIDE 4: TARGET PENGGUNA & ALUR KERJA HARIAN -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">03 / TARGET PENGGUNA &amp; ALUR PEMAKAIAN HARIAN</div>
      <h2>Bagaimana Orang Awam &amp; Trader Pemula Memakai Aplikasi Ini.</h2>
      <p class="lead">Dirancang sebagai pengecekan keamanan fundamental sebelum mengambil keputusan beli.</p>
    </div>

    <div class="grid-3">
      <div class="card card-green">
        <span class="tag tag-green" style="margin-bottom: 8px;">LANGKAH 1: SARING &amp; HINDARI JEBAKAN</span>
        <div style="font-weight: 800; font-size: 15px; margin-bottom: 6px;">Cek Stock Screener</div>
        <div class="muted" style="font-size: 13px;">
          Sebelum ikut membeli saham yang ramai di media sosial, buka <strong>Simple Mode</strong>: cek apakah statusnya <strong style="color:#047857;">CASH SAFE / DEBT-FREE</strong> atau <strong style="color:#be123c;">CRITICAL CASH</strong> beserta pergerakan harga hari ini.
        </div>
      </div>
      <div class="card card-accent">
        <span class="tag tag-blue" style="margin-bottom: 8px;">LANGKAH 2: GRAFIK + KAS TAHUNAN</span>
        <div style="font-weight: 800; font-size: 15px; margin-bottom: 6px;">Periksa Harga &amp; Laporan Kas</div>
        <div class="muted" style="font-size: 13px;">
          Klik <strong>Inspect</strong> untuk membuka grafik Candlestick live (1D-1Y), cek apakah Laba Bersih didukung Arus Kas Operasi riil (FY 2022-2025), dan baca Financial Health Summary.
        </div>
      </div>
      <div class="card card-amber">
        <span class="tag tag-amber" style="margin-bottom: 8px;">LANGKAH 3: CEK BERITA ANTI-FOMO</span>
        <div style="font-weight: 800; font-size: 15px; margin-bottom: 6px;">Uji Silang Link Berita</div>
        <div class="muted" style="font-size: 13px;">
          Menemukan link berita saham yang viral? Tempel ke <strong>News &amp; URL Analyzer</strong> (atau cek Daily News Feed) untuk melihat apakah judul positif sesuai dengan kas di bank.
        </div>
      </div>
    </div>

    <div class="grid-2">
      <div class="card" style="padding: 13px 18px;">
        <strong style="font-size: 13px; color: #0369a1;">Untuk Investor Pemula (Orang Awam):</strong>
        <span style="font-size: 12.5px; color: #475569;">Memilih perusahaan jangka panjang yang aman ("Cash Fortress" tanpa utang jangka pendek &amp; CFO positif) tanpa perlu gelar akuntansi.</span>
      </div>
      <div class="card" style="padding: 13px 18px;">
        <strong style="font-size: 13px; color: #047857;">Untuk Swing Trader Pemula:</strong>
        <span style="font-size: 12.5px; color: #475569;">Menggabungkan tren candlestick OHLCV live dengan sentimen berita RSS harian dan menghindari saham rawan suspensi atau gagal bayar.</span>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Alur Pengguna</span>
      <span>Slide 4 / 13</span>
    </div>
  </section>

  <!-- SLIDE 5: PENDALAMAN FITUR 1 -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">04 / PENDALAMAN FITUR 1: SCREENER &amp; PANDUAN INTERAKTIF</div>
      <h2>Mengapa Kami Membangun Screener Dua Mode + Tur Terbang Berbasis Cookie.</h2>
    </div>

    <div class="grid-2" style="align-items: center;">
      <div class="shot-stack">
        <div class="shot-frame">
          <img src="{shots['screener']}" alt="Tampilan Stock Screener">
        </div>
        <div class="shot-frame">
          <img src="{shots['tour']}" alt="Tutorial Terbang Berbasis Cookie">
        </div>
      </div>
      <div style="display: flex; flex-direction: column; gap: 12px;">
        <div class="card card-accent" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Alasan Desain</div>
          <div class="muted">Pengguna baru langsung keluar dalam 10 detik jika disambut tabel akuntansi mentah, sementara pengguna lama benci pop-up tutorial yang muncul berulang kali.</div>
        </div>
        <div class="card card-green" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Tur Terbang Per-Tab Berbasis Cookie (Tanpa Login)</div>
          <div class="muted">Saat kunjungan pertama ke tiap tab, spotlight terbang menyoroti card penting lalu menyimpan cookie (<code>idx_radar_tour_*</code>) agar kunjungan berikutnya tetap bersih, dengan tombol <strong>Guide</strong> di header.</div>
        </div>
        <div class="card card-amber" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Manfaat ke User: Simple Mode vs. Expert Mode</div>
          <div class="muted">Investor awam melihat vonis aman yang jelas (<em>"Cash Safe"</em> vs <em>"Critical Cash"</em>) + heatmap 5 sektor + kuotasi <code>.JK</code> live, sementara analis bisa menyalakan rasio Sloan &amp; XBRL penuh.</div>
        </div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Pendalaman Fitur: Screener &amp; Onboarding</span>
      <span>Slide 5 / 13</span>
    </div>
  </section>

  <!-- SLIDE 6: PENDALAMAN FITUR 2 -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">05 / PENDALAMAN FITUR 2: PETA KARTESIAN 4-KUADRAN</div>
      <h2>Mengubah Rasio Neraca Menjadi Peta Keamanan Visual Seketika.</h2>
    </div>

    <div class="grid-demo">
      <div class="shot-frame">
        <img src="{shots['quadrant']}" alt="Zoom Peta 4-Kuadran dengan Tooltip">
      </div>
      <div style="display: flex; flex-direction: column; gap: 10px;">
        <div class="card card-accent" style="padding: 12px 15px;">
          <div style="font-weight: 800; font-size: 13px; margin-bottom: 3px;">Mengapa Peta Spasial + Tooltip Hover?</div>
          <div class="muted">Angka seperti <code>0.23x</code> atau <code>Sloan +14%</code> abstrak bagi pemula. Memetakan <strong>Cash Coverage (X)</strong> vs <strong>Sloan Accruals (Y)</strong> lengkap dengan tooltip Q1-Q4 membuat siapa saja bisa membaca risiko dalam 3 detik.</div>
        </div>
        <div class="card card-green" style="padding: 11px 15px;">
          <div style="font-weight: 800; font-size: 12.5px; color: #047857;">Q4: Cash Fortress (Kanan Bawah)</div>
          <div class="muted">Kas &ge; 1.0x utang jangka pendek &amp; Akrual &le; 0%. Laba benar-benar didukung kas masuk riil.</div>
        </div>
        <div class="card card-amber" style="padding: 11px 15px;">
          <div style="font-weight: 800; font-size: 12.5px; color: #b45309;">Q1: High Accrual &amp; Q3: Cash Stress</div>
          <div class="muted"><strong>Q1:</strong> Kas &ge; 1.0x cukup, tapi laba tertahan di piutang. <strong>Q3:</strong> Cadangan kas tipis (&lt; 1.0x utang).</div>
        </div>
        <div class="card card-red" style="padding: 11px 15px;">
          <div style="font-weight: 800; font-size: 12.5px; color: #be123c;">Q2: Double Stress (Kiri Atas)</div>
          <div class="muted">Zona risiko tertinggi: Kas &lt; 1.0x utang jangka pendek DAN Akrual &gt; 0% (laba kertas + kas menipis).</div>
        </div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Pendalaman Fitur: Peta 4-Kuadran</span>
      <span>Slide 6 / 13</span>
    </div>
  </section>

  <!-- SLIDE 7: PENDALAMAN FITUR 3 -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">06 / PENDALAMAN FITUR 3: DETAIL SAHAM LIVE</div>
      <h2>Mengapa Grafik Candlestick Disandingkan dengan Triangulasi Kas Teraudit.</h2>
    </div>

    <div class="grid-demo">
      <div class="shot-frame">
        <img src="{shots['detail']}" alt="Screenshot Detail Saham BBRI.JK">
      </div>
      <div style="display: flex; flex-direction: column; gap: 11px;">
        <div class="card card-accent" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Mengapa Harga &amp; Kas Harus Berdampingan?</div>
          <div class="muted">Trader ritel terbiasa hidup di aplikasi grafik. Alat fundamental gagal dipakai jika memaksa user keluar dari chart ke spreadsheet statis, sehingga TradingView Lightweight Charts ditanam langsung.</div>
        </div>
        <div class="card card-green" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Candlestick OHLCV + Volume Live</div>
          <div class="muted">Mendukung rentang <strong>1D (15m), 1W (1h), 1M, 3M, &amp; 1Y</strong> dengan legend OHLCV interaktif dan data <code>.JK</code> langsung dari bursa.</div>
        </div>
        <div class="card card-amber" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Kartu Triangulasi 3-Arah</div>
          <div class="muted">Menyatukan <strong>Harga Live</strong> + <strong>Berita RSS Terbaru</strong> + <strong>Analisis Diagnostik Kas FY 2025</strong> agar divergensi terlihat sebelum entry.</div>
        </div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Pendalaman Fitur: Detail Saham (BBRI.JK)</span>
      <span>Slide 7 / 13</span>
    </div>
  </section>

  <!-- SLIDE 8: PENDALAMAN FITUR 4 -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">07 / PENDALAMAN FITUR 4: XBRL MULTI-TAHUN &amp; CALK</div>
      <h2>Membongkar Piutang Pihak Berelasi &amp; Jejak Tag XBRL Resmi BEI.</h2>
    </div>

    <div class="grid-demo">
      <div class="shot-frame">
        <img src="{shots['calk']}" alt="Zoom Laporan Tahunan dan CALK">
      </div>
      <div style="display: flex; flex-direction: column; gap: 11px;">
        <div class="card card-accent" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Mengapa Data Multi-Tahun &amp; CALK Penting?</div>
          <div class="muted">Rasio satu tahun sering menyembunyikan pembakaran kas bertahun-tahun. Selain itu, "laba kertas" sering bersembunyi di <em>Piutang Pihak Berelasi</em> pada catatan kaki laporan keuangan.</div>
        </div>
        <div class="card card-green" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Jejak Audit XBRL Lengkap</div>
          <div class="muted">Setiap angka merujuk ke tag XBRL BEI persis (<code>localname</code>, <code>contextRef</code>, <code>decimals</code>) beserta hash SHA-256 berkas, tanpa estimasi kotak hitam.</div>
        </div>
        <div class="card card-amber" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Proyeksi Runway Kas Deterministik</div>
          <div class="muted">Memproyeksikan ketahanan likuiditas jangka pendek dari tren arus kas operasi historis FY 2022-2025 terhadap kewajiban jatuh tempo.</div>
        </div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Pendalaman Fitur: XBRL Tahunan &amp; CALK</span>
      <span>Slide 8 / 13</span>
    </div>
  </section>

  <!-- SLIDE 9: PENDALAMAN FITUR 5 -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">08 / PENDALAMAN FITUR 5: RADAR BERITA &amp; AI BYOK</div>
      <h2>Cron Sentimen Berita Harian + Uji Silang URL + Analis AI BYOK.</h2>
    </div>

    <div class="grid-2" style="align-items: center;">
      <div class="shot-stack">
        <div class="shot-frame">
          <img src="{shots['news']}" alt="Radar Berita Harian dan URL Analyzer">
        </div>
        <div class="shot-frame">
          <img src="{shots['chat']}" alt="AI Financial Analyst">
        </div>
      </div>
      <div style="display: flex; flex-direction: column; gap: 12px;">
        <div class="card card-red" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Mengapa Isolasi Konteks Wajib Ada?</div>
          <div class="muted">Berita kontrak besar memicu beli FOMO. Engine menilai {s['news_articles']} berita harian ({s['news_tickers']} emiten) tiap <code>08:00 WIB</code>, tetapi <strong>berita positif tidak pernah menimpa flag bahaya kas</strong>.</div>
        </div>
        <div class="card card-accent" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Tempel URL Berita Apa Saja</div>
          <div class="muted">User cukup menempel link berita viral; sistem mendeteksi semua emiten yang disebut (termasuk berita multi-emiten seperti <em>PTPP &amp; ADHI</em>) lalu membandingkan narasi berita vs kas riil di bank.</div>
        </div>
        <div class="card card-green" style="padding: 13px 16px;">
          <div style="font-weight: 800; font-size: 13.5px; margin-bottom: 4px;">Analis AI BYOK = Penerjemah Saja (0% Hitung)</div>
          <div class="muted">User memakai Gemini API Key sendiri (<code>localStorage</code> BYOK, nol beban token server); Gemini hanya menerjemahkan fakta <code>Decimal</code> Python tanpa mengarang angka.</div>
        </div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Pendalaman Fitur: Berita &amp; Analis AI</span>
      <span>Slide 9 / 13</span>
    </div>
  </section>

  <!-- SLIDE 10: PEMBUKTIAN BACKTEST NYATA (2022-2025) -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">09 / PEMBUKTIAN BACKTEST NYATA (2022-2025)</div>
      <h2>Bagaimana Flag Kas 2022-2023 Memprediksi Distres Utang Nyata di 2025.</h2>
      <p class="lead">Angka XBRL teraudit dari database kami dibandingkan langsung dengan kejadian suspensi BEI, penundaan kupon, dan restrukturisasi.</p>
    </div>

    <div class="grid-3">
      <div class="card card-red" style="display: flex; flex-direction: column; justify-content: space-between; gap: 8px;">
        <div>
          <span class="tag tag-red" style="margin-bottom: 6px;">KASUS 1: WIKA (PENUNDAAN KUPON &amp; SUSPENSI)</span>
          <div style="font-weight: 800; font-size: 14px; margin-bottom: 6px;">Peringatan Dini Sejak FY 2022-2023</div>
          <ul style="font-size: 12px; color: #334155;">
            <li><strong>FY 2022:</strong> Masih mencatat laba bersih <strong>+Rp 13 M</strong>, padahal Arus Kas Operasi (CFO) sudah <strong>-Rp 2,88 T</strong> dan Cash Coverage turun ke <strong>0,38x</strong>.</li>
            <li><strong>FY 2023:</strong> Engine memicu <strong style="color:#be123c;">ACUTE LIQUIDITY FLAG</strong>: Cash Coverage jatuh ke <strong>0,15x</strong>, CFO <strong>-Rp 2,93 T</strong>, Rugi Bersih <strong>-Rp 7,83 T</strong>.</li>
            <li><strong>Realita 2025:</strong> Penundaan pembayaran kupon sukuk/obligasi, restrukturisasi utang (RUPO), suspensi perdagangan BEI, dan rugi FY 2025 melebar ke <strong>-Rp 10,14 T</strong>.</li>
          </ul>
        </div>
      </div>

      <div class="card card-amber" style="display: flex; flex-direction: column; justify-content: space-between; gap: 8px;">
        <div>
          <span class="tag tag-amber" style="margin-bottom: 6px;">KASUS 2: WSKT (EUFORIA KONTRAK VS KAS)</span>
          <div style="font-weight: 800; font-size: 14px; margin-bottom: 6px;">Tekanan 2023 &amp; Kas Kritis Berlanjut</div>
          <ul style="font-size: 12px; color: #334155;">
            <li><strong>FY 2022 -> FY 2023:</strong> Cash Coverage anjlok dari <strong>1,37x</strong> menjadi <strong>0,20x</strong> dengan rugi bersih <strong>-Rp 4,02 T</strong>.</li>
            <li><strong>FY 2024 -> FY 2025:</strong> Coverage tetap kritis di <strong>0,26x</strong> (2024) dan <strong>0,23x</strong> (2025), CFO <strong>-Rp 2,38 T</strong> -> <strong>-Rp 560 M</strong>, Rugi Bersih <strong>-Rp 4,48 T</strong>.</li>
            <li><strong>Realita 2025:</strong> Meski berita ramai menyoroti <em>"Kontrak Baru Rp 5,6 T"</em>, WSKT tetap berada dalam suspensi BEI &amp; restrukturisasi utang.</li>
          </ul>
        </div>
      </div>

      <div class="card card-green" style="display: flex; flex-direction: column; justify-content: space-between; gap: 8px;">
        <div>
          <span class="tag tag-green" style="margin-bottom: 6px;">KONTROL: TOTL (SEKTOR SAMA, SEHAT)</span>
          <div style="font-weight: 800; font-size: 14px; margin-bottom: 6px;">Disiplin Kas Melindungi Investor</div>
          <ul style="font-size: 12px; color: #334155;">
            <li><strong>FY 2022-2025:</strong> Konsisten menjaga <strong>Nol Utang Berbunga Jangka Pendek (Debt-Free)</strong> selama 4 tahun penuh.</li>
            <li><strong>Kas Masuk Riil:</strong> CFO positif setiap tahun: <strong>+0,28 T</strong> (2022) -> <strong>+0,65 T</strong> (2024) -> <strong>+0,44 T</strong> (2025).</li>
            <li><strong>Realita 2025:</strong> Laba bersih tumbuh <strong>4,5x</strong> (dari +92 M di 2022 menjadi <strong>+415 M</strong> di 2025) tanpa tekanan likuiditas dan rutin membagikan dividen.</li>
          </ul>
        </div>
      </div>
    </div>

    <div class="card" style="background: #0f172a; color: #f8fafc; padding: 12px 18px; font-size: 12.5px;">
      <strong style="color: #38bdf8;">Kesimpulan:</strong> Investor ritel yang memeriksa <strong>Cash Coverage (&lt;0,20x)</strong> dan <strong>CFO Negatif</strong> pada laporan XBRL 2023 dapat menghindari dana tersangkut bertahun-tahun di 2025.
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Pembuktian Backtest Nyata (2022-2025)</span>
      <span>Slide 10 / 13</span>
    </div>
  </section>

  <!-- SLIDE 11: DATA EMPIRIS & ARSITEKTUR -->
  <section class="slide slide-light">
    <div>
      <div class="eyebrow">10 / DATA EMPIRIS &amp; ARSITEKTUR</div>
      <h2>Angka Terverifikasi FY 2025 di Atas Arsitektur Serverless Ringan.</h2>
    </div>

    <table>
      <thead>
        <tr>
          <th>Emiten</th>
          <th>Sektor</th>
          <th>Cash Coverage</th>
          <th>CFO TTM</th>
          <th>Sloan Accrual</th>
          <th>Realita Triangulasi</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>WSKT</strong></td>
          <td>Konstruksi</td>
          <td><strong>0.23x</strong></td>
          <td style="color: #be123c; font-weight: 700;">-IDR 559.7 B</td>
          <td>-5.5%</td>
          <td><span class="tag tag-red">GAP KATALIS VS KAS</span> (Berita Kontrak 5,6T vs Kas Tipis)</td>
        </tr>
        <tr>
          <td><strong>TOTL</strong></td>
          <td>Konstruksi</td>
          <td><strong>Debt-Free</strong></td>
          <td style="color: #047857; font-weight: 700;">+IDR 388.4 B</td>
          <td>-0.5%</td>
          <td><span class="tag tag-green">CASH FORTRESS</span> (Nol Utang JP + Dividen Interim)</td>
        </tr>
        <tr>
          <td><strong>BBRI</strong></td>
          <td>Perbankan</td>
          <td><strong>Debt-Free</strong></td>
          <td style="color: #047857; font-weight: 700;">+IDR 14.62 T</td>
          <td>+1.7%</td>
          <td><span class="tag tag-green">SEHAT SELARAS</span> (Arus Kas Operasi Kuat &amp; Dividen)</td>
        </tr>
        <tr>
          <td><strong>ADRO</strong></td>
          <td>Energi (USD->IDR)</td>
          <td><strong>7.52x</strong></td>
          <td style="color: #047857; font-weight: 700;">+IDR 9.62 T</td>
          <td>-5.9%</td>
          <td><span class="tag tag-green">FUNDAMENTAL TANGGUH</span> (Cadangan Kas 7,52x)</td>
        </tr>
      </tbody>
    </table>

    <div class="grid-3">
      <div class="card" style="padding: 13px 16px;">
        <strong style="font-size: 12.5px; color: #0369a1;">BACKEND &amp; DATABASE</strong>
        <div class="muted" style="margin-top: 4px;">Python 3.12, FastAPI, parser XBRL <code>lxml</code>, Supabase PostgreSQL, Vercel Serverless.</div>
      </div>
      <div class="card" style="padding: 13px 16px;">
        <strong style="font-size: 12.5px; color: #047857;">PASAR &amp; BERITA</strong>
        <div class="muted" style="margin-top: 4px;">Kuotasi paralel Yahoo Finance <code>.JK</code>, TradingView Lightweight Charts, Cron RSS Google News.</div>
      </div>
      <div class="card" style="padding: 13px 16px;">
        <strong style="font-size: 12.5px; color: #b45309;">AI BYOK &amp; BOT</strong>
        <div class="muted" style="margin-top: 4px;">Gemini AI (penerjemah narasi saja via BYOK user, 0% hitung), Bot Telegram <code>aiogram 3.x</code>.</div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Data Empiris &amp; Arsitektur</span>
      <span>Slide 11 / 13</span>
    </div>
  </section>

  <!-- SLIDE 12: ROADMAP 90 HARI & PERAN CO-BUILDER -->
  <section class="slide slide-dark">
    <div>
      <div class="eyebrow">11 / ROADMAP 90 HARI &amp; MENGAPA BERGABUNG SEKARANG</div>
      <h2>Yang Akan Kita Bangun Bersama dalam 90 Hari ke Depan.</h2>
      <p class="lead">Mesin inti sudah berjalan live. Bergabunglah sebagai co-builder untuk memperluas cakupan emiten, retensi pengguna, dan peluncuran komunitas.</p>
    </div>

    <div class="grid-3">
      <div class="card">
        <div style="color: #38bdf8; font-weight: 800; font-size: 13.5px; margin-bottom: 8px;">FASE 1 (HARI 1-30)</div>
        <ul>
          <li>Ingesti laporan kuartalan (<code>TW1-TW3</code>) untuk TTM live</li>
          <li>Aktifkan watchlist pribadi &amp; peringatan flag via Telegram</li>
          <li>Tambahkan konteks valuasi Cash/Market-Cap &amp; Price/CFO</li>
        </ul>
      </div>
      <div class="card">
        <div style="color: #34d399; font-weight: 800; font-size: 13.5px; margin-bottom: 8px;">FASE 2 (HARI 31-60)</div>
        <ul>
          <li>Perluas pipeline XBRL dari {s['issuers']} menjadi 200+ saham likuid BEI</li>
          <li>Optimasi tampilan mobile-first &amp; kartu diagnostik siap bagikan</li>
          <li>Akun pengguna &amp; penyimpanan screener (Supabase Auth)</li>
        </ul>
      </div>
      <div class="card">
        <div style="color: #fbbf24; font-weight: 800; font-size: 13.5px; margin-bottom: 8px;">FASE 3 (HARI 61-90)</div>
        <ul>
          <li>Peluncuran beta ke komunitas ritel &amp; value-investing Indonesia</li>
          <li>Iterasi langsung berdasarkan masukan trader pemula</li>
          <li>Merancang monetisasi berkelanjutan setelah retensi terbukti</li>
        </ul>
      </div>
    </div>

    <div class="card" style="padding: 14px 20px; border-left: 4px solid #38bdf8;">
      <strong style="color: #38bdf8; font-size: 13.5px;">Peran yang Tersedia:</strong>
      <span style="font-size: 13px; color: #cbd5e1; margin-left: 6px;">Kepemilikan penuh co-builder di bidang Frontend/UX, Scaling Data XBRL, atau Growth &amp; Komunitas dengan pembagian ekuitas/bagi hasil yang adil sejak hari pertama.</span>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; Roadmap &amp; Peran Co-Builder</span>
      <span>Slide 12 / 13</span>
    </div>
  </section>

  <!-- SLIDE 13: KREDIT FOUNDER & LANGKAH SELANJUTNYA -->
  <section class="slide slide-dark" style="justify-content: space-between;">
    <div>
      <div class="eyebrow">12 / KREDIT FOUNDER &amp; LANGKAH SELANJUTNYA</div>
      <h1 style="font-size: 42px;">Coba Aplikasinya Hari Ini. Mari Bangun v3 Bersama.</h1>
      <p class="lead" style="margin-top: 10px;">
        Uji screener live, cek tooltip 4-kuadran, inspeksi candlestick <code>BBRI.JK</code>, dan mari diskusikan langkah pembangunan fase berikutnya bersama.
      </p>
    </div>

    <div class="card" style="padding: 16px 20px; border-left: 4px solid #38bdf8; display: flex; justify-content: space-between; align-items: center; gap: 20px;">
      <div>
        <div class="kpi-label" style="color: #38bdf8; margin-bottom: 3px;">FOUNDER &amp; LEAD ARCHITECT</div>
        <div style="font-size: 18px; font-weight: 800; color: #ffffff; margin-bottom: 4px;">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
        <div class="muted" style="font-size: 12.5px; color: #cbd5e1; max-width: 780px;">
          AI Engineer, LLM Researcher &amp; Lead Engineer / System Analyst di PT. Royal Medicalink Pharmalab (alumni Universitas Kristen Maranatha). Berfokus pada arsitektur Retrieval-Augmented Generation (RAG), Sustainable AI, semantic vector caching, dan sistem enterprise.
        </div>
      </div>
      <a href="https://yehezkiel.netlify.app/" target="_blank" style="white-space: nowrap; font-size: 12px; font-weight: 700; color: #38bdf8; border: 1px solid #0284c7; background: rgba(2, 132, 199, 0.15); padding: 8px 14px; border-radius: 8px;">yehezkiel.netlify.app &#8599;</a>
    </div>

    <div class="grid-3">
      <div class="card">
        <div class="kpi-label" style="color: #38bdf8;">APLIKASI WEB (VERCEL)</div>
        <div style="font-size: 14px; font-weight: 700; margin-top: 4px;">
          <a href="https://idx-cash-radar.vercel.app/" target="_blank" style="color: #38bdf8; text-decoration: underline;">https://idx-cash-radar.vercel.app/</a>
        </div>
        <div class="muted" style="margin-top: 4px;">{s['issuers']} Emiten BEI &bull; {s['facts']:,} Fakta XBRL Teraudit &bull; Grafik Live</div>
      </div>
      <div class="card">
        <div class="kpi-label" style="color: #34d399;">REPOSITORI GITHUB</div>
        <div style="font-size: 14px; font-weight: 700; margin-top: 4px;">github.com/06202003/idx-cash-radar</div>
        <div class="muted" style="margin-top: 4px;">FastAPI + Supabase + BYOK Gemini + Cron Berita Harian</div>
      </div>
      <div class="card">
        <div class="kpi-label" style="color: #fbbf24;">LANGKAH SELANJUTNYA</div>
        <div style="font-size: 14px; font-weight: 700; margin-top: 4px;">Demo Live 30 Menit &amp; Diskusi</div>
        <div class="muted" style="margin-top: 4px;">Menyelaraskan visi produk, pembagian peran, dan sprint 30 hari pertama.</div>
      </div>
    </div>

    <div class="watermark">Yehezkiel David Setiawan, S.Kom, M.Kom</div>
    <div class="footer">
      <span>IDX Cash &amp; Accrual Radar &bull; &copy; Yehezkiel David Setiawan, S.Kom, M.Kom &bull; yehezkiel.netlify.app</span>
      <span>Slide 13 / 13</span>
    </div>
  </section>

</body>
</html>
"""


def main() -> int:
    stats = load_live_stats()
    shots = load_existing_shots()
    html = build_html_id(stats, shots)
    OUT_HTML_ID.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML_ID.write_text(html, encoding="utf-8")
    print(f"Wrote Indonesian HTML deck: {OUT_HTML_ID}")

    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        page.goto(OUT_HTML_ID.resolve().as_uri(), wait_until="load")
        page.wait_for_timeout(400)
        page.pdf(
            path=str(OUT_PDF_ID),
            width="13.333in",
            height="7.5in",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()
    print(f"Wrote Indonesian PDF deck : {OUT_PDF_ID} ({OUT_PDF_ID.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
