# PRE-REGISTRATION PROTOCOL & EVALUATION DESIGN
**Project:** IDX Cash & Accrual Radar (MVP v1.2)
**Author:** Yehezkiel David Setiawan, S.Kom., M.Kom.
**Document Status:** LOCKED PRE-EVALUATION SPECIFICATION
**Lock Date:** 11 November 2026

---

## 1. TUJUAN PRE-REGISTRASI METODOLOGI
Pada populasi sektoral yang berukuran kecil seperti sub-industri Konstruksi Bangunan di Bursa Efek Indonesia ($N \approx 15\text{--}25$ emiten aktif dan $\approx 3\text{--}8$ insiden gagal bayar/suspensi/restatement terdokumentasi pada rentang 2020–2025), mengubah rumus atau menggeser ambang batas (*threshold*) setelah melihat data historis akan menyebabkan *overfitting* dan *hindsight bias*.

Dokumen ini mengunci secara permanen sebelum eksekusi *backtest*:
1. Kriteria inklusi populasi emiten (*Point-in-Time Universe*) dan aturan versi berkas laporan keuangan.
2. Definisi matematis eksak dari ketiga metrik inti, komponen akun penyusunnya, dan aturan pelindung penyebut nol (*zero-denominator guards*).
3. Konstanta ambang batas (*thresholds*) untuk kedua bendera perhatian (*Safeguard Flags*).
4. Definisi peristiwa *Ground Truth* dan matriks evaluasi studi kasus tiga kelompok.
5. Kriteria keberhasilan teknis dan syarat *pivot* jujur (*Honest Engineering Pivot Criteria*).

---

## 2. POPULASI UJI (POINT-IN-TIME UNIVERSE) & JENDELA WAKTU

### 2.1 Cakupan Sub-Industri & Pencegahan Survivorship Bias
- **Target Populasi:** Seluruh emiten yang terdaftar dalam klasifikasi **IDX-IC Sub-Industri Konstruksi Bangunan & Rekayasa Sipil** (termasuk BUMN Karya dan kontraktor swasta) pada setiap titik kuartal evaluasi antara **Q1 2020 hingga Q4 2025**.
- **Aturan Point-in-Time (Anti Survivorship Bias):**
  - Emiten yang saat ini berstatus disuspensi panjang, dalam proses PKPU/pailit, atau telah *delisting* setelah 1 Januari 2020 WAJIB tetap dimasukkan ke dalam distribusi *peer group* pada seluruh kuartal di mana emiten tersebut masih menerbitkan laporan keuangan.
  - Emiten yang baru tercatat (IPO) setelah 1 Januari 2020 baru dimasukkan ke dalam distribusi *peer group* mulai kuartal di mana laporan keuangannya memiliki riwayat 4 kuartal penuh (TTM).

### 2.2 Jendela Evaluasi (2020–2025) & Buffer Pra-PSAK 72 (2019)
- **Periode Evaluasi Utama:** Q1 2020 s.d. Q4 2025 (24 kuartal evaluasi, selaras dengan masa berlaku efektif PSAK 72).
- **Aturan Buffer Data 2019:**
  - Data laporan keuangan tahun 2019 (Q1–FY 2019) ditarik khusus sebagai **buffer perhitungan penyebut dan arus kas 12 bulan (TTM)** untuk akun `Pendapatan`, `Laba Bersih`, `Arus Kas Operasi (CFO)`, dan `Total Aset` sehingga `Sloan Ratio TTM` dan `Cash Coverage` dapat dievaluasi penuh sejak Q1 2020.
  - Untuk `Gross/Net Contract Exposure Divergence YoY`, evaluasi perubahan YoY pada tahun 2020 hanya dilakukan apabila berkas XBRL 2020 menyertakan saldo komparatif 2019 yang telah disesuaikan dengan PSAK 72; jika tidak tersedia, maka perubahan YoY poin persentase dievaluasi mulai Q1 2021.

### 2.3 Aturan Versi Laporan (`As-First-Reported` vs. `Restated`)
- Evaluasi kemampuan deteksi dini terhadap kasus penyajian kembali (*restatement*) HANYA valid apabila portal BEI menyediakan berkas laporan keuangan versi rilis pertama (*as-first-reported*) sebelum dikoreksi.
- Apabila pada suatu periode portal BEI hanya menyimpan berkas versi yang telah disajikan kembali (*overwritten by restated filing*), maka berkas tersebut diberi label `RESTATED_OVERWRITE` di database dan **tidak boleh diklaim** sebagai bukti prediksi *restatement* sebelum kejadian.

---

## 3. DEFINISI MATEMATIS & AMBANG BATAS YANG DIKUNCI (LOCKED THRESHOLDS)

### 3.1 Parameter Konstanta yang Dikunci
Seluruh konstanta di bawah ini ditetapkan sebelum pengujian dan dilarang diubah untuk mempercantik hasil evaluasi:

| Nama Parameter | Nilai Dikunci | Rasional Penetapan Awal |
| :--- | :--- | :--- |
| `MIN_PEER_COUNT` ($N_{\min}$) | `8 emiten` | Batas minimum sampel agar pembagian 4 kuartil memiliki minimal $\ge 2$ emiten per kuartil. |
| `REVENUE_DROP_GUARD_LIMIT` | `-50.0% YoY` (atau $\le 0$) | Mencegah ledakan rasio eksposur kontrak akibat keruntuhan penyebut omzet (misal: penghentian proyek saat pandemi). |
| `SLOAN_ACCRUAL_THRESHOLD` | `> +0.10` (+10% dari rata-rata Aset) | Ambang standar literatur akuntansi forensik (Sloan, 1996) di mana laba tahunan menyimpang signifikan dari kas operasi. |
| `CASH_COVERAGE_THRESHOLD` | `< 0.20x` (Kas $< 20\%$ utang berbunga lancar) | Menandakan kas bebas tidak cukup menutup seperlima kewajiban pokok pinjaman yang jatuh tempo dalam 12 bulan. |

### 3.2 Spesifikasi Eksak 3 Metrik Inti
1. **Intensitas Eksposur Kontrak Bruto & Neto (PSAK 72):**
   - $\text{Gross Exposure}_t = \text{Piutang Usaha Neto (Pihak Ketiga + Berelasi)}_t + \text{Aset Kontrak (Lancar + Tidak Lancar)}_t$
   - $\text{Net Exposure}_t = \text{Gross Exposure}_t - \text{Liabilitas Kontrak (Jangka Pendek + Panjang)}_t$
   - $\text{Gross Exposure Ratio}_t = \frac{\text{Gross Exposure}_t}{\text{Pendapatan}_{\text{TTM}, t}}$
   - $\text{Net Exposure Ratio}_t = \frac{\text{Net Exposure}_t}{\text{Pendapatan}_{\text{TTM}, t}}$
   - $\text{Divergence YoY (percentage points)}_t = (\text{Gross Exposure Ratio}_t - \text{Gross Exposure Ratio}_{t-4}) \times 100$

2. **Sloan Accrual Ratio (TTM):**
   - $\text{Sloan Ratio}_{\text{TTM}, t} = \frac{\text{Laba Bersih}_{\text{TTM}, t} - \text{CFO}_{\text{TTM}, t}}{0.5 \times (\text{Total Aset}_t + \text{Total Aset}_{t-4})}$

3. **Cash-to-Short-Term Interest-Bearing Debt Coverage:**
   - $\text{Cash Coverage}_t = \frac{\text{Kas dan Setara Kas Tidak Dibatasi}_t}{\text{Utang Bank JP} + \text{Bagian Lancar Utang Bank Jpj} + \text{Bagian Lancar Obligasi/Sukuk/MTN} + \text{Liabilitas Sewa JP}}$

### 3.3 Tabel Kebenaran (Truth Table) Bendera Safeguard
Dua bendera dievaluasi secara terpisah untuk menghindari titik buta pada emiten yang sudah merugi:

| Nama Bendera | Syarat 1 | Syarat 2 | Syarat 3 | Syarat 4 | Tujuan Deteksi |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`FLAG_ACCRUAL_DIVERGENCE`** | $\text{NI}_{\text{TTM}, t} > 0$ | $\text{CFO}_{\text{TTM}, t} < 0$ | $\text{CFO}_{\text{single}, t} < 0$ | $\text{Sloan}_{\text{TTM}, t} > +0.10$ | Emiten melaporkan laba bersih positif, namun arus kas operasi 12M dan kuartal berjalan negatif disertai akrual $>10\%$ aset. |
| **`FLAG_ACUTE_LIQUIDITY`** | *(Berlaku untuk $\text{NI} > 0$ maupun $\text{NI} \le 0$)* | $\text{CFO}_{\text{TTM}, t} < 0$ | $\text{ST\_IB\_Debt}_t > 0$ | $\text{Cash Coverage}_t < 0.20\text{x}$ | Emiten membakar kas operasional 12M sementara kas bebas di neraca $< 20\%$ dari utang berbunga jatuh tempo $\le 1$ tahun. |

---

## 4. DEFINISI PERISTIWA GROUND TRUTH & MATRIKS EVALUASI KASUS

### 4.1 Kriteria Peristiwa Ground Truth Resmi ($T_0$)
Sebuah emiten konstruksi dikategorikan mengalami peristiwa *Distress / Restatement* pada kuartal $T_0$ hanya jika terdapat dokumen pengumuman resmi BEI atau OJK untuk salah satu dari kejadian berikut:
1. **Suspensi Gagal Bayar / PKPU:** Penghentian sementara perdagangan saham oleh BEI akibat gagal bayar bunga/pokok obligasi, sukuk, utang sindikasi, atau putusan PKPU/Pailit pengadilan niaga.
2. **Penyajian Kembali Material (*Restatement*):** Penerbitan kembali laporan keuangan tahunan/kuartalan yang mengubah nilai Laba Bersih, Ekuitas, atau Piutang/Aset Kontrak secara material akibat koreksi kesalahan akuntansi atau audit investigasi (bukan sekadar reklasifikasi adopsi standar baru).
3. **Sanksi Administratif Laporan Keuangan OJK:** Surat sanksi OJK terkait pelanggaran standar penyajian laporan keuangan.

*(Catatan: Notasi khusus administratif semata seperti keterlambatan penyampaian laporan [Notasi L] atau ekuitas negatif [Notasi E] TIDAK dijadikan target prediksi untuk mencegah label leakage, melainkan dicatat sebagai informasi kronologis).*

### 4.2 Struktur Tabel Evaluasi Tiga Kelompok (Wajib Dipublikasikan Utuh)
Hasil pengujian retrospektif 2020–2025 wajib disajikan tanpa penyaringan (*no cherry-picking*) dalam 3 tabel:

1. **Tabel A — Known Distress & Restatement Cases (Evaluasi Lead Time & False Negatives):**
   Untuk setiap kasus Ground Truth pada populasi konstruksi, laporkan:
   - Kode Emiten, Jenis Peristiwa Resmi, Nomor & Tanggal Pengumuman BEI/OJK ($T_0$).
   - Kuartal pertama sebelum $T_0$ di mana `FLAG_ACCRUAL_DIVERGENCE`, `FLAG_ACUTE_LIQUIDITY`, atau `Kuartil 4 Eksposur Kontrak` menyala.
   - **Lead Time (dalam jumlah kuartal):** $T_0 - T_{\text{first\_flag}}$.
   - Jika tidak ada bendera yang menyala sebelum $T_0$ (atau baru menyala setelah $T_0$), kasus tersebut wajib diberi label **`FALSE NEGATIVE (MISSED CASE)`** disertai analisis mengapa metrik gagal menangkapnya.

2. **Tabel B — Flagged Non-Distress Cases (Inspeksi False Alarms):**
   Daftar seluruh emiten konstruksi yang **tidak** mengalami suspensi gagal bayar/restatement sepanjang 2020–2025, namun pernah menyalakan `FLAG_ACCRUAL_DIVERGENCE` atau `FLAG_ACUTE_LIQUIDITY`:
   - Kode Emiten & Kuartal menyalanya bendera.
   - Nilai ketiga metrik pada kuartal tersebut.
   - Penjelasan akuntansi objektif (misal: arus kas negatif sementara akibat dimulainya proyek baru yang didanai kas internal/ekuitas, lalu pulih pada Q4).

3. **Tabel C — Unflagged Control Peers:**
   Ringkasan statistik (median dan rentang antarkuartil) dari emiten konstruksi sehat yang tidak pernah menyalakan bendera safeguard sepanjang periode uji.

---

## 5. KRITERIA KEBERHASILAN TEKNIS & ATURAN PIVOT JUJUR

### 5.1 Gerbang Validasi Rekayasa (Engineering Acceptance Gates)
1. **Gate Persamaan Akuntansi:** 100% berkas `instance.xbrl` yang masuk ke dalam evaluasi lulus *4-Way Accounting Sanity Check* secara otomatis.
2. **Gate Audit Manual terhadap PDF Asli:**
   - **Minggu 1 (Tahap Parser):** 100% angka kanonikal pada 5 emiten pertama diverifikasi manual terhadap baris tabel PDF laporan keuangan resmi BEI dengan tingkat kesesuaian 100%.
   - **Minggu 4 (Tahap Rilis):** Minimal 20% sampel acaknya (terstratifikasi per tahun dan per emiten) diverifikasi manual terhadap dokumen PDF asli.

### 5.2 Kriteria Pivot Metodologi (Honest Pivot Rule)
Apabila setelah seluruh tahapan de-kumulasi YTD dan perhitungan 3 metrik selesai dijalankan pada populasi konstruksi 2020–2025 ditemukan bahwa:
- Indikator `FLAG_ACCRUAL_DIVERGENCE` dan `FLAG_ACUTE_LIQUIDITY` gagal menyala minimal **2 kuartal sebelum $T_0$** pada mayoritas kasus gagal bayar konstruksi utama (seperti kasus BUMN Karya periode 2020–2024), **ATAU**
- Indikator menyala hampir di seluruh emiten sehat pada setiap kuartal sehingga tidak memberikan daya pisah (*discriminative power*) yang bermakna,

Maka proyek **dilarang mengubah ambang batas secara diam-diam**. Proyek akan mempublikasikan hasil negatif tersebut secara transparan di dalam repositori dan melakukan *pivot* posisi produk menjadi **Open-Source IDX XBRL Parser, YTD De-cumulator & Cash Flow Visualizer**.

---

## 6. KEBIJAKAN LOG PERUBAHAN PASCA-SPIKE (AMENDMENT LOG)
Jika selama pelaksanaan **Spike Minggu 0 (Hari 1–3)** ditemukan fakta teknis pada struktur XBRL BEI yang mengharuskan penyesuaian rumus komponen akun, perubahan tersebut wajib dicatat pada tabel di bawah ini lengkap dengan *commit hash* dan alasan teknisnya sebelum *backtest* dijalankan:

| Tanggal | Commit Hash | Bagian yang Diubah | Alasan Empiris dari Temuan Spike XBRL |
| :--- | :--- | :--- | :--- |
| 11 Nov 2026 | `INITIAL` | Penguncian dokumen awal v1.2 | Penetapan protokol pra-spike. |