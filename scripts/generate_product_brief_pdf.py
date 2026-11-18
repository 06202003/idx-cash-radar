"""
Generates a comprehensive Indonesian Product Discussion Brief (HTML + A4 PDF via Playwright)
covering the entire IDX Cash & Accrual Radar platform, including the latest News & Catalyst
Radar (Hype vs Cash Reality), XBRL Audit Engine, Self-Trained ML/MLP, Portfolio X-Ray,
AI Analyst, and Strategic Positioning for co-founder/peer discussion.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.generate_cofounder_pitch_deck import launch_browser  # noqa: E402

OUT_HTML = ROOT_DIR / "docs" / "IDX_Cash_Radar_Product_Brief_ID.html"
OUT_PDF = ROOT_DIR / "docs" / "IDX_Cash_Radar_Product_Brief_ID.pdf"


def build_brief_html() -> str:
    return """<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8" />
  <title>IDX Cash &amp; Accrual Radar — Product Discussion Brief (Lengkap)</title>
  <style>
    @page {
      size: A4 portrait;
      margin: 14mm 14mm 16mm 14mm;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
      color: #0f172a;
      background: #ffffff;
      font-size: 10.2pt;
      line-height: 1.5;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .page-break { page-break-before: always; }
    .avoid-break { break-inside: avoid; }

    /* Cover Banner */
    .hero {
      background: linear-gradient(135deg, #0b1120 0%, #172554 60%, #0f172a 100%);
      color: #f8fafc;
      border-radius: 12px;
      padding: 24px 26px;
      margin-bottom: 18px;
      border: 1px solid #1e3a8a;
    }
    .hero-tag {
      display: inline-block;
      background: rgba(56, 189, 248, 0.16);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.4);
      font-size: 8.5pt;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 999px;
      letter-spacing: 0.4px;
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .hero h1 {
      font-size: 21pt;
      font-weight: 800;
      letter-spacing: -0.4px;
      line-height: 1.2;
      margin-bottom: 8px;
      color: #ffffff;
    }
    .hero p {
      font-size: 10.5pt;
      color: #cbd5e1;
      max-width: 96%;
    }
    .hero-meta {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid rgba(148, 163, 184, 0.25);
      font-size: 8.8pt;
      color: #94a3b8;
    }
    .hero-meta strong { color: #f1f5f9; }

    /* Section Headings */
    h2 {
      font-size: 13pt;
      font-weight: 800;
      color: #0f172a;
      border-left: 4px solid #0284c7;
      padding-left: 10px;
      margin: 18px 0 10px 0;
    }
    h3 {
      font-size: 10.5pt;
      font-weight: 700;
      color: #1e293b;
      margin-bottom: 5px;
    }
    p { margin-bottom: 8px; color: #334155; }
    ul { margin: 4px 0 10px 18px; color: #334155; }
    li { margin-bottom: 4px; }

    /* Grid & Cards */
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 12px;
    }
    .grid-3 {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-bottom: 12px;
    }
    .card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 12px 14px;
    }
    .card-dark {
      background: #0f172a;
      color: #e2e8f0;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 12px 14px;
    }
    .card-dark h3 { color: #38bdf8; }
    .card-dark p, .card-dark li { color: #cbd5e1; }
    .card-amber {
      background: #fffbeb;
      border: 1px solid #fcd34d;
      border-radius: 8px;
      padding: 12px 14px;
    }
    .card-emerald {
      background: #ecfdf5;
      border: 1px solid #6ee7b7;
      border-radius: 8px;
      padding: 12px 14px;
    }
    .card-rose {
      background: #fff1f2;
      border: 1px solid #fda4af;
      border-radius: 8px;
      padding: 12px 14px;
    }

    /* Stat pills */
    .stat-num {
      font-size: 16pt;
      font-weight: 800;
      color: #0284c7;
      line-height: 1.1;
      margin-bottom: 3px;
    }
    .stat-label {
      font-size: 8.5pt;
      color: #475569;
      font-weight: 600;
    }

    /* Tables */
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 8px 0 12px 0;
      font-size: 9.2pt;
    }
    th {
      background: #0f172a;
      color: #f8fafc;
      text-align: left;
      padding: 7px 9px;
      font-weight: 700;
      font-size: 8.6pt;
    }
    td {
      border-bottom: 1px solid #e2e8f0;
      padding: 6.5px 9px;
      vertical-align: top;
      color: #334155;
    }
    tr:nth-child(even) td { background: #f8fafc; }

    .badge {
      display: inline-block;
      font-size: 7.8pt;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 4px;
      text-transform: uppercase;
    }
    .b-blue { background: #e0f2fe; color: #0369a1; }
    .b-amber { background: #fef3c7; color: #b45309; }
    .b-green { background: #d1fae5; color: #047857; }
    .b-red { background: #ffe4e6; color: #be123c; }

    .footer {
      margin-top: 14px;
      padding-top: 8px;
      border-top: 1px solid #cbd5e1;
      font-size: 8.2pt;
      color: #64748b;
      display: flex;
      justify-content: space-between;
    }
    code {
      background: #e2e8f0;
      padding: 1px 4px;
      border-radius: 3px;
      font-family: Consolas, monospace;
      font-size: 8.6pt;
    }
  </style>
</head>
<body>

  <!-- PAGE 1: COVER, CONTEXT & POSITIONING -->
  <div class="hero">
    <div class="hero-tag">Product Discussion Brief &bull; November 2026</div>
    <h1>IDX Cash &amp; Accrual Radar</h1>
    <p>
      <strong>Radar Fakta Berita, Katalis Pasar &amp; Audit Kas Riil BEI</strong> — Platform intelijen
      deterministik untuk membedah <em>hype</em> berita dan pergerakan saham liar dengan data kas
      auditan XBRL resmi Bursa Efek Indonesia (tanpa halusinasi, tanpa rekomendasi beli/jual).
    </p>
    <div class="hero-meta">
      <div><strong>Live App:</strong> idx-cash-radar.vercel.app</div>
      <div><strong>Universe:</strong> 49 Emiten (5 Sektor Inti BEI)</div>
      <div><strong>Rezim Data:</strong> XBRL BEI 2020&ndash;2025 (PSAK 72)</div>
      <div><strong>Status QA:</strong> 131 Automated Tests Pass</div>
    </div>
  </div>

  <div class="grid-3 avoid-break">
    <div class="card">
      <div class="stat-num">49 Emiten</div>
      <div class="stat-label">Konstruksi, Perbankan, Consumer/FMCG, Tambang &amp; Energi, Telco/Infra</div>
    </div>
    <div class="card">
      <div class="stat-num">100% Terlacak</div>
      <div class="stat-label">Setiap angka akuntansi dapat ditelusuri ke tag XML XBRL resmi BEI (<code>canonical_facts</code>)</div>
    </div>
    <div class="card">
      <div class="stat-num">Aturan Deterministik</div>
      <div class="stat-label">Skor utama berbasis <code>cash_coverage</code> &amp; <em>safeguard flags</em> terbuka di <code>/metodologi</code></div>
    </div>
  </div>

  <h2>1. Kenapa Produk Ini Ada? (Menjawab Realita Pasar BEI)</h2>
  <p>
    Investor dan trader ritel di BEI saat ini menghadapi dua masalah sekaligus: <strong>kelelahan fundamental
    (<em>fundamental fatigue</em>)</strong> saat saham <em>blue chip</em> pun bisa terkoreksi dalam dan katalis
    tahunan terasa jauh, serta <strong>banjirnya rumor &amp; pergerakan saham liar</strong> (aksi korporasi,
    isu <em>index exclusion</em> dari IHSG/MSCI, hingga status UMA/FCA).
  </p>

  <div class="grid-2 avoid-break">
    <div class="card-amber">
      <h3>Masalah di Lapangan</h3>
      <ul>
        <li>Berita saham sering bernada euforia (kontrak baru, akuisisi, rumor pengendali) padahal arus kas operasional emiten sebenarnya negatif.</li>
        <li>Katalis volatilitas seperti keluar dari indeks IHSG/LQ45, suspensi, atau masuk Papan Pemantauan Khusus (FCA) memicu pergerakan ekstrem.</li>
        <li>Ritel malas membaca laporan keuangan PDF ratusan halaman &amp; tag XBRL mentah.</li>
      </ul>
    </div>
    <div class="card-emerald">
      <h3>Posisi Produk Kita (Bukan "Guru Saham")</h3>
      <ul>
        <li><strong>Bukan pemberi sinyal cuan / target harga.</strong> Kita tidak memposisikan diri sebagai pihak yang "paling jago cuan di pasar".</li>
        <li><strong>Alat Forensik &amp; Fact-Checker:</strong> Seperti alat telemetri atau <em>lie detector</em> antara narasi berita vs kas riil di bank.</li>
        <li>Membantu trader/investor cepat sadar: apakah berita panas ini didukung kas nyata, atau murni volatilitas katalis?</li>
      </ul>
    </div>
  </div>

  <h2>2. Fitur Utama Terbaru: News &amp; Catalyst Radar ("Hype vs Cash")</h2>
  <p>
    Menanggapi masukan bahwa sisi <strong>News</strong> adalah daya tarik utama untuk menghadapi dinamika
    saham liar di BEI, modul <code>news_radar.py</code> dan <code>realtime_news_analyzer.py</code> kini
    dilengkapi detektor katalis pasar dan <em>cross-check</em> otomatis ke laporan XBRL:
  </p>

  <table>
    <thead>
      <tr>
        <th style="width: 24%;">Komponen News Radar</th>
        <th style="width: 44%;">Cara Kerja Deterministik</th>
        <th style="width: 32%;">Output untuk Pengguna</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>1. Detektor 3 Katalis Saham Liar</strong></td>
        <td>Memindai berita secara deterministik (dengan proteksi <em>word-boundary</em> agar bebas false-positive) untuk 3 kategori penggerak volatilitas.</td>
        <td>
          <span class="badge b-amber">Rebalancing / Eksklusi Indeks</span><br/>
          <span class="badge b-red">UMA / Suspensi / Papan FCA</span><br/>
          <span class="badge b-blue">Aksi Korporasi &amp; Pengendali</span>
        </td>
      </tr>
      <tr>
        <td><strong>2. Hype vs Cash Reality Check</strong></td>
        <td>Membandingkan nada sentimen + katalis berita terhadap CFO TTM, Cash Coverage, dan <em>Safeguard Flags</em> XBRL emiten terkait.</td>
        <td>
          Label status otomatis: <em>Berita Positif vs Kas Tertekan (Divergensi)</em>, <em>Katalis Volatilitas + Kas Tertekan</em>, atau <em>Selaras Kas Riil</em>.
        </td>
      </tr>
      <tr>
        <td><strong>3. URL &amp; Raw Text Analyzer</strong></td>
        <td>Tempel tautan berita media (atau teks mentah), otomatis mendeteksi ticker BEI (single/multi-emiten) &amp; menyusun ringkasan 2 mode.</td>
        <td>Mode <strong>Simple (Awam)</strong> &amp; Mode <strong>Expert (Pro)</strong> + proyeksi kas 2 tahun ke depan.</td>
      </tr>
      <tr>
        <td><strong>4. Contextual Isolation Rule</strong></td>
        <td>Aturan keras sistem: berita positif sebesar apa pun <strong>dilarang</strong> menghapus atau menurunkan bendera bahaya kas deterministik.</td>
        <td>Menjaga objektivitas audit agar tidak bias oleh berita promosi.</td>
      </tr>
    </tbody>
  </table>

  <div class="footer">
    <span>IDX Cash &amp; Accrual Radar &bull; Product Discussion Brief</span>
    <span>Halaman 1 dari 3</span>
  </div>

  <!-- PAGE 2: FULL PLATFORM ARCHITECTURE & 5 PILLARS -->
  <div class="page-break"></div>

  <h2>3. Peta Lengkap Seluruh Fitur Platform (5 Pilar Terintegrasi)</h2>
  <p>
    Selain News &amp; Catalyst Radar, di balik layar sudah terbangun infrastruktur data keuangan, machine
    learning mandiri, simulasi portofolio, hingga asisten AI dan bot Telegram. Berikut seluruh modul yang aktif:
  </p>

  <div class="grid-2 avoid-break">
    <div class="card">
      <h3>Pilar A &mdash; XBRL Audit Pipeline &amp; Screener (49 Emiten)</h3>
      <ul>
        <li><strong>Parser XBRL Primer (<code>lxml</code>):</strong> Membaca langsung berkas XML/XBRL resmi BEI (bukan scraping angka sekunder yang rawan salah).</li>
        <li><strong>De-kumulasi YTD &rarr; TTM:</strong> Mengonversi laporan kumulatif 3M, 6M, 9M, 12M menjadi kuartal tunggal &amp; <em>Trailing Twelve Months</em>.</li>
        <li><strong>3 Metrik Inti:</strong> Eksposur Kontrak PSAK 72, <em>Sloan Accrual Ratio</em> (mendeteksi laba kertas vs kas), dan <em>Cash-to-ST Debt Coverage</em>.</li>
        <li><strong>2 Safeguard Flags:</strong> <code>FLAG_ACCRUAL_DIVERGENCE</code> &amp; <code>FLAG_ACUTE_LIQUIDITY</code> dengan toleransi rekonsiliasi 4-arah Rp 0.</li>
        <li><strong>Bedah CALK:</strong> Ekstraksi rincian catatan kaki piutang, bank, dan utang berbunga.</li>
      </ul>
    </div>
    <div class="card">
      <h3>Pilar B &mdash; Aturan Deterministik &amp; Simulator What-If (Pro)</h3>
      <ul>
        <li><strong>Skor Utama Deterministik:</strong> Menggunakan rasio <em>Cash Coverage</em> (&lt; 1.0x / &lt; 0.20x) dan <em>Safeguard Flags</em> yang terbuka di <code>/metodologi</code> (klaim AUC model lama dicabut karena <em>label leakage</em> pada audit Fase 1).</li>
        <li><strong>Simulator Stres What-If (Pro/Lanjutan):</strong> Model MLP <code>5 &rarr; 16 &rarr; 8 &rarr; 1</code> hanya digunakan sebagai simulasi sensitivitas skenario kas/utang (<em>simulasi, bukan prediksi</em>).</li>
        <li><strong>Naive Bayes Berita Indonesia:</strong> Klasifikasi teks finansial lokal (129 dokumen latih, 1.627 kosakata) dalam artefak JSON ringan di bagian lanjutan.</li>
        <li><strong>Money-First Metrics:</strong> Menghitung surplus/defisit kas riil (Rp), <em>cash runway</em> (bulan), dan kebutuhan kas untuk menutup utang 1.0x.</li>
      </ul>
    </div>
  </div>

  <div class="grid-2 avoid-break">
    <div class="card">
      <h3>Pilar C &mdash; Portfolio Cash-Safety X-Ray &amp; Market Quotes</h3>
      <ul>
        <li><strong>Portfolio X-Ray:</strong> Pengguna memasukkan alokasi modal (Rp) per saham; sistem menghitung berapa rupiah modal yang benar-benar didukung kas vs utang jangka pendek berdasarkan <em>Book Equity Cash Backing</em>.</li>
        <li><strong>Benchmark Rekomendasi Sektor:</strong> Menunjukkan selisih <em>Capital-at-Risk</em> jika posisi terlemah dibandingkan dengan emiten se-subsektor yang lebih sehat kasnya.</li>
        <li><strong>Live Market Quotes &amp; Intraday WIB:</strong> Grafik harga dan kutipan pasar real-time disesuaikan ke jam bursa BEI (09:00&ndash;16:00 WIB).</li>
      </ul>
    </div>
    <div class="card">
      <h3>Pilar D &mdash; AI Analyst (RAG + BYOK) &amp; Telegram Bot</h3>
      <ul>
        <li><strong>AI Narrative Translator:</strong> Menggunakan Google Gemini (<code>google-genai</code>) hanya sebagai penerjemah angka Python menjadi bahasa awam maks 3 kalimat, dengan <em>fallback</em> deterministik jika kuota habis/offline.</li>
        <li><strong>Bring Your Own Key (BYOK):</strong> Di web Vercel, pengguna bisa memasukkan API Key Gemini sendiri (tersimpan lokal di browser) untuk AI chat berbasis data XBRL &amp; CALK.</li>
        <li><strong>Telegram Bot (<code>aiogram 3.x</code>):</strong> Kartu diagnostik instan per ticker via Jinja2 template, siap jalan 24/7 via Docker/VPS.</li>
      </ul>
    </div>
  </div>

  <h2>4. Pagar Kepatuhan Hukum &amp; Anti-Halusinasi (Guardrails)</h2>
  <div class="card-dark avoid-break">
    <h3>Kenapa Sistem Ini Aman untuk Dipublikasikan ke Publik Ritel?</h3>
    <p>
      Seluruh output web, AI, template Jinja2, hingga judul berita disaring otomatis oleh
      <code>tests/test_language_compliance.py</code> sebelum tampil ke pengguna:
    </p>
    <ul>
      <li><strong>Blacklist Kata Terlarang:</strong> Sistem memblokir keras kata tuduhan atau ajakan ilegal seperti <em>"Manipulasi", "Window Dressing", "Saham Gorengan", "Penipuan", "Fraud", "Bangkrut", "Rekomendasi Beli", "Rekomendasi Jual"</em>.</li>
      <li><strong>Bahasa Deskriptif Faktual:</strong> Diganti dengan frasa objektif yang bisa diaudit, misal: <em>"Arus kas operasi bernilai negatif", "Divergensi antara sentimen berita positif dan arus kas riil", "Katalis volatilitas tinggi (UMA/FCA/Indeks)"</em>.</li>
      <li><strong>Pemisahan Tegas Matematika vs LLM:</strong> AI tidak pernah menghitung rasio atau skor risiko; semua angka berasal dari Python deterministik.</li>
    </ul>
  </div>

  <div class="footer">
    <span>IDX Cash &amp; Accrual Radar &bull; Product Discussion Brief</span>
    <span>Halaman 2 dari 3</span>
  </div>

  <!-- PAGE 3: TECH STACK, CREDIBILITY & DISCUSSION ROADMAP -->
  <div class="page-break"></div>

  <h2>5. Ringkasan Teknis &amp; Kesiapan Produksi</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 26%;">Lapisan Sistem</th>
        <th style="width: 44%;">Teknologi &amp; Modul Utama</th>
        <th style="width: 30%;">Status Saat Ini</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Backend &amp; API</strong></td>
        <td>FastAPI (<code>src/web/app.py</code>), Python 3.11+, Pydantic v2, SQLite3 / PostgreSQL (Supabase)</td>
        <td><span class="badge b-green">Aktif &amp; Deployed (Vercel)</span></td>
      </tr>
      <tr>
        <td><strong>XBRL &amp; CALK Engine</strong></td>
        <td><code>lxml</code> parser, <code>decumulator.py</code>, <code>calculator.py</code>, <code>safeguards.py</code>, <code>calk_extractor.py</code></td>
        <td><span class="badge b-green">Teruji (131 Pytest Pass)</span></td>
      </tr>
      <tr>
        <td><strong>News &amp; Catalyst Radar</strong></td>
        <td><code>news_radar.py</code>, <code>realtime_news_analyzer.py</code>, <code>daily_news_cron.py</code></td>
        <td><span class="badge b-green">Baru Di-upgrade</span></td>
      </tr>
      <tr>
        <td><strong>ML &amp; AI Layer</strong></td>
        <td>L2 Logit, MLP <code>5-16-8-1</code>, Multinomial NB, <code>google-genai</code> (BYOK + Fallback)</td>
        <td><span class="badge b-green">Aktif (JSON Artifact)</span></td>
      </tr>
      <tr>
        <td><strong>Frontend, Kartu &amp; Analytics</strong></td>
        <td>Dashboard (<code>index.html</code>), Kartu PNG 1:1 &amp; 9:16 (<code>/api/card/{ticker}.png</code>), <code>/metodologi</code>, <code>/analytics</code>, Bot Telegram</td>
        <td><span class="badge b-green">Live &amp; Teruji (135 Pytest)</span></td>
      </tr>
    </tbody>
  </table>

  <h2>6. Poin Diskusi Bersama Teman / Co-Founder</h2>
  <p>
    Dokumen ini disiapkan sebagai bahan diskusi terbuka. Pertanyaan utama yang paling relevan untuk
    menentukan arah produk berikutnya:
  </p>

  <div class="grid-2 avoid-break">
    <div class="card-rose">
      <h3>1. Menjawab Isu Kredibilitas &amp; Positioning</h3>
      <ul>
        <li>Jika targetnya trader yang sudah skeptis terhadap "fundamental", <em>hook</em> awal terbaik adalah <strong>News &amp; Catalyst Fact-Checker</strong>, bukan screener laporan tahunan.</li>
        <li>Kita tidak perlu mengklaim "ahli cuan" — cukup posisikan produk sebagai <strong>alat cek fakta cepat</strong> (seperti <em>Carfax / CekFakta</em> untuk berita emiten BEI).</li>
      </ul>
    </div>
    <div class="card">
      <h3>2. Ide Pengembangan Fase Berikutnya</h3>
      <ul>
        <li><strong>Status Hook "Berita vs Kas":</strong> <em>Belum teruji, bukan terbantah</em> &mdash; backtest Fase 5 hanya menemukan 1 kejadian uji &amp; 1 kontrol (N=0 di horizon 5/20/60 hari); butuh arsip Keterbukaan Informasi BEI 2022&ndash;2025 untuk pengujian lanjut.</li>
        <li><strong>Kandidat Universe Baru (Fase 6):</strong> 28 emiten UMA/FCA/suspensi terverifikasi sudah dipetakan di <code>reports/universe_candidates.csv</code> (belum dimasukkan ke produksi sebelum berkas XBRL-nya diverifikasi).</li>
        <li><strong>Validasi Pasar:</strong> Uji coba ke 5&ndash;10 trader aktif dan pantau <code>/analytics</code> (prioritas <code>ticker_dicek</code> &amp; <code>kartu_dibagikan</code>).</li>
      </ul>
    </div>
  </div>

  <div class="card-dark avoid-break" style="margin-top: 10px;">
    <h3>Kesimpulan Singkat untuk Bahan Obrolan</h3>
    <p style="margin-bottom: 0;">
      Fondasi teknisnya sudah jadi dan berjalan (49 emiten, XBRL audit, ML/MLP, Portfolio X-Ray, hingga
      News &amp; Catalyst Radar terbaru). Tantangan sekarang bukan lagi di kode dasar, melainkan
      <strong>mengemas sudut pandang produk</strong> agar langsung menjawab kebutuhan nyata pelaku pasar
      di Indonesia: cepat membaca arah berita/katalis saham liar sambil tetap punya pegangan fakta kas riil.
    </p>
  </div>

  <div class="footer">
    <span>IDX Cash &amp; Accrual Radar &bull; Product Discussion Brief (Nov 2026)</span>
    <span>Halaman 3 dari 3</span>
  </div>

</body>
</html>
"""


def main() -> int:
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    html = build_brief_html()
    OUT_HTML.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        page.goto(OUT_HTML.resolve().as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            margin={"top": "14mm", "right": "14mm", "bottom": "16mm", "left": "14mm"},
        )
        browser.close()

    print(f"Generated HTML: {OUT_HTML}")
    print(f"Generated PDF : {OUT_PDF} ({OUT_PDF.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
