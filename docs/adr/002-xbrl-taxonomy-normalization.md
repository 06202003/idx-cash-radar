# ADR 002: XBRL Taxonomy Normalization, Dimension Filtering & Multi-Item Debt Mapping

**Status:** Accepted  
**Date:** 2026-11-11  
**Deciders:** Yehezkiel David Setiawan, S.Kom., M.Kom. (Lead Architect)  
**Target:** IDX Cash & Accrual Radar (MVP v1.2)

---

## 1. Context & Problem Statement
Laporan keuangan emiten Bursa Efek Indonesia (BEI) yang disajikan dalam format XBRL (`instance.xbrl`) menggunakan taksonomi lokal BEI (`http://www.idx.co.id/xbrl/cor/2020-01-01`). Pada proses Spike (Gate 0) dan Ingestion (Gate 1) terhadap emiten sektor konstruksi (`ADHI`, `PTPP`, `WIKA`), ditemukan beberapa karakteristik struktural yang membutuhkan normalisasi deterministik:

1. **Eksplosi Konteks Multidimensi:** Satu berkas XBRL rata-rata memuat lebih dari 4.500 tag `<xbrli:context>`. Sebagian besar konteks tersebut merupakan data segmen geografis, pihak berelasi, atau rincian mata uang (`<xbrli:segment>`, `<xbrli:scenario>`, `<xbrldi:explicitMember>`).
2. **Fragmentasi Pos Aset Kontrak (PSAK 72):** Pos aset kontrak sering kali tidak dilaporkan dalam satu tag tunggal, melainkan dipecah menjadi tag piutang retensi (`RetentionReceivables...`) dan tag piutang belum ditagih (`UnbilledReceivables...`).
3. **Fragmentasi Utang Jangka Pendek:** Utang berbunga jangka pendek tersebar dalam beberapa tranche (pinjaman bank jangka pendek, pinjaman bukan bank, bagian lancar utang jangka panjang bank, obligasi, sukuk, dan liabilitas sewa).
4. **Pembedaan Pos Kas Neraca vs Arus Kas:** BEI menggunakan tag `CashAndCashEquivalents` untuk neraca dan `CashAndCashEquivalentsCashFlows` untuk arus kas akhir periode.

---

## 2. Decision Drivers
- **Zero Hallucination:** Menghilangkan ambiguitas dalam kalkulasi metrik finansial.
- **Auditability:** Setiap nilai kanonikal harus dapat dilacak langsung ke tag XBRL sumbernya.
- **Performance:** Memfilter ribuan konteks dimensi berlebih agar proses ingestion selesai dalam hitungan detik.
- **Akurasi Neraca:** Memastikan rekonsiliasi akuntansi 4 arah (*4-Way Sanity Check*) terpenuhi dengan toleransi selisih $\le \text{Rp } 1.000.000$.

---

## 3. Considered Options
1. **Menggunakan Python XBRL Library Pihak Ketiga (seperti `Arelle`):**
   - *Ditolak:* Terlalu lambat, membawa dependensi besar, dan dilarang secara tegas dalam AGENTS.md.
2. **Parser `lxml` Kustom dengan Filter Konteks Nol-Dimensi:**
   - *Dipilih:* Mengisolasi tepat 7 konteks konsolidasi utama (`CurrentYearInstant`, `CurrentYearDuration`, dsb.) dan membuang seluruh dimensi segmental.

---

## 4. Normalization Architecture & Rules

### 4.1 Filter Konteks Nol-Dimensi (*Zero-Dimension Context Filter*)
Konteks yang diterima hanyalah konteks yang tidak memiliki anak elemen:
- `<xbrli:segment>`
- `<xbrli:scenario>`
- `<xbrldi:explicitMember>`
- `<xbrldi:typedMember>`

Konteks kemudian diklasifikasikan strictly berdasarkan tipenya:
- `instant`: Hanya untuk Laporan Posisi Keuangan (Neraca).
- `duration`: Hanya untuk Laba Rugi dan Laporan Arus Kas.

### 4.2 Multi-Item Aggregation Mapping
Untuk pos kanonikal yang memiliki beberapa komponen, normalizer melakukan penjumlahan deterministik:

1. **Aset Kontrak Bruto (PSAK 72):**
   $$\text{Aset Kontrak} = \text{UnbilledReceivablesThirdParties} + \text{UnbilledReceivablesRelatedParties} + \text{RetentionReceivablesThirdParties} + \text{CurrentContractAssets}$$
2. **Liabilitas Kontrak (Uang Muka Proyek):**
   $$\text{Liabilitas Kontrak} = \text{CurrentAdvancesFromCustomersThirdParties} + \text{CurrentContractLiabilities} + \text{CurrentUnearnedRevenue}$$
3. **Utang Berbunga Jangka Pendek ($\text{ST\_Debt}$):**
   $$\text{ST\_Debt} = \sum (\text{ShortTermBankLoans}, \text{ShortTermNonBankLoans}, \text{CurrentMaturitiesBankLoans}, \text{CurrentMaturitiesBonds}, \text{CurrentMaturitiesSukuk}, \text{CurrentMaturitiesLease})$$

### 4.3 4-Way Sanity Check Enforcement
Seluruh berkas XBRL yang diproses wajib lolos 4 pemeriksaan matematis sebelum masuk basis data SQLite:
1. $|\text{Total Aset} - (\text{Total Liabilitas} + \text{Total Ekuitas})| \le \text{Rp } 1.000.000$
2. $|\text{Total Aset} - (\text{Aset Lancar} + \text{Aset Tidak Lancar})| \le \text{Rp } 1.000.000$
3. $|\text{Total Liabilitas} - (\text{Liabilitas Jangka Pendek} + \text{Liabilitas Jangka Panjang})| \le \text{Rp } 1.000.000$
4. $|\text{Kas Neraca} - \text{Kas Arus Kas Akhir Periode}| \le \text{Rp } 1.000.000$

---

## 5. Consequences
- **Positif:** 100% berkas emiten uji (`ADHI`, `PTPP`, `WIKA`) tervalidasi dengan selisih $\text{Rp } 0$ (sempurna).
- **Positif:** Waktu kueri diagnostik bot Telegram terpelihara pada $\approx 3.5\text{ ms}$, jauh di bawah batas $50\text{ ms}$.
- **Kompromi:** Tag XBRL baru di masa depan harus dicocokkan dengan kamus `config/taxonomy_mapping.yaml`.

