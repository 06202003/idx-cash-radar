"""
Real-Time News Link Sentiment & Accrual Radar Cross-Check Engine.
Fetches a public news URL (or raw article text), detects the BEI issuer ticker,
classifies deterministic sentiment signals, and synthesizes a side-by-side
comparison against the issuer's audited XBRL Cash & Accrual Radar metrics.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from lxml import html as lxml_html

from src.engine.llm_explainer import (
    DEFAULT_GEMINI_MODEL,
    check_language_compliance,
)
from src.engine.news_radar import PERHATIAN_KEYWORDS, POSITIF_KEYWORDS

logger = logging.getLogger(__name__)
_GEMINI_BACKOFF_UNTIL: float = 0.0

# Extended article-body sentiment cues (deterministic & transparent)
ARTICLE_POSITIVE_CUES = list(
    dict.fromkeys(
        POSITIF_KEYWORDS
        + [
            "nilai kontrak baru",
            "pembayaran bulanan",
            "uang muka",
            "non-turnkey",
            "menghindari skema turnkey",
            "buyback",
            "arus kas positif",
            "surplus kas",
            "ekspansi",
            "proyek pemerintah",
            "investasi baru",
            "rekor laba",
            "tak akan dibiarkan",
            "suntikan modal",
            "penyelesaian utang",
            "dukungan pemerintah",
            "surplus operasional",
        ]
    )
)

ARTICLE_WARNING_CUES = list(
    dict.fromkeys(
        PERHATIAN_KEYWORDS
        + [
            "gagal bayar",
            "kredit macet",
            "tekanan likuiditas",
            "ekuitas negatif",
            "rugi bersih",
            "arus kas negatif",
            "kewajiban jatuh tempo",
            "gugatan",
            "penurunan pendapatan",
            "pembengkakan utang",
            "terbebani",
            "beban utang",
            "beban bunga",
            "kerugian",
            "mencatat rugi",
            "rugi rp",
            "membengkak",
            "tekanan utang",
            "merosot",
            "tertekan",
            "utang menumpuk",
            "piutang macet",
        ]
    )
)

CAPTCHA_MARKERS = (
    "verify you are human",
    "cf-turnstile",
    "g-recaptcha",
    "hcaptcha",
    "attention required! | cloudflare",
)

# Common issuer aliases for natural-language company detection
ISSUER_NAME_ALIASES: dict[str, list[str]] = {
    "WSKT": ["waskita karya", "waskita"],
    "WIKA": ["wijaya karya"],
    "ADHI": ["adhi karya"],
    "PTPP": ["pp (persero)", "pembangunan perumahan", "pt pp"],
    "TOTL": ["total bangun persada"],
    "ACST": ["acset indonusa"],
    "JKON": ["jaya konstruksi"],
    "NRCA": ["nusa raya cipta"],
    "WEGE": ["wijaya karya bangunan gedung", "wika gedung"],
    "PPRE": ["pp presisi"],
    "DGIK": ["nusa konstruksi enjiniring"],
    "PBSA": ["paramita bangun sarana"],
    "TOPS": ["totalindo eka persada"],
    "SSIA": ["surya semesta internusa"],
    "IDPR": ["indonesia pondasi raya"],
    "BBRI": ["bank rakyat indonesia", "bri "],
    "BMRI": ["bank mandiri"],
    "BBNI": ["bank negara indonesia", "bni "],
    "BRIS": ["bank syariah indonesia", "bsi "],
    "BBTN": ["bank tabungan negara", "btn "],
    "BDMN": ["bank danamon"],
    "BNGA": ["cimb niaga"],
    "MEGA": ["bank mega"],
    "ICBP": ["indofood cbp"],
    "INDF": ["indofood sukses makmur"],
    "UNVR": ["unilever indonesia"],
    "MYOR": ["mayora indah"],
    "AMRT": ["sumber alfaria trijaya", "alfamart"],
    "ACES": ["aspirasi hidup indonesia", "ace hardware"],
    "MAPI": ["mitra adiperkasa"],
    "KLBF": ["kalbe farma"],
    "SIDO": ["sido muncul"],
    "CMRY": ["cisarua mountain dairy", "cimory"],
    "GGRM": ["gudang garam"],
    "HMSP": ["hm sampoerna", "sampoerna"],
    "ADRO": ["adaro energy", "alamtri"],
    "PTBA": ["bukit asam"],
    "PGAS": ["perusahaan gas negara", "pgn "],
    "MEDC": ["medco energi"],
    "AKRA": ["akr corporindo"],
    "ANTM": ["aneka tambang", "antam"],
    "INCO": ["vale indonesia"],
    "ITMG": ["indo tambangraya megah"],
    "TLKM": ["telkom indonesia"],
    "ISAT": ["indosat ooredoo", "indosat"],
    "EXCL": ["xl axiata"],
    "TOWR": ["sarana menara nusantara"],
    "MTEL": ["dayamitra telekomunikasi", "mitratel"],
}


def validate_public_url(url: str) -> tuple[bool, str]:
    """Validates URL scheme and blocks SSRF access to private/loopback IP ranges."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return False, "Format URL tidak valid."

    if parsed.scheme not in ("http", "https"):
        return False, "URL wajib menggunakan protokol http:// atau https://."
    if not parsed.hostname:
        return False, "Hostname pada URL tidak ditemukan."

    host = parsed.hostname.lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Akses ke alamat lokal tidak diizinkan."

    try:
        addr_info = socket.getaddrinfo(host, None)
        for item in addr_info:
            ip_str = item[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
            ):
                return False, "Akses ke jaringan internal/privat tidak diizinkan."
    except socket.gaierror:
        return False, f"Domain '{host}' tidak dapat ditemukan (DNS error)."
    except Exception as exc:
        return False, f"Gagal memvalidasi alamat URL: {exc}"

    return True, ""


def _fmt_idr_short(val: float | int | None) -> str:
    if val is None:
        return "-"
    abs_v = abs(float(val))
    sign = "-" if float(val) < 0 else ""
    if abs_v >= 1e12:
        return f"{sign}Rp {abs_v / 1e12:.2f} T"
    if abs_v >= 1e9:
        return f"{sign}Rp {abs_v / 1e9:.1f} M"
    return f"{sign}Rp {int(abs_v):,}".replace(",", ".")


def extract_article_from_html(raw_html: bytes | str, url: str = "") -> dict[str, Any]:
    """Extracts headline, site source, body text, and key sentences from HTML."""
    if isinstance(raw_html, bytes):
        text_html = raw_html.decode("utf-8", errors="replace")
    else:
        text_html = raw_html

    lower_html = text_html.lower()
    for marker in CAPTCHA_MARKERS:
        if marker in lower_html and len(text_html) < 50000:
            return {
                "blocked": True,
                "reason": (
                    "Situs sumber dilindungi verifikasi anti-bot/CAPTCHA. "
                    "Silakan salin-tempel teks berita secara manual di kolom teks."
                ),
            }

    tree = lxml_html.fromstring(text_html)

    # 1. Clean Headline extraction priority: og:title -> h1 -> non-loading <title>
    og_title = tree.xpath("//meta[@property='og:title']/@content")
    h1_text = tree.xpath("//h1//text()")
    title_tags = [t.strip() for t in tree.xpath("//title/text()") if t.strip()]
    valid_titles = [t for t in title_tags if "loading" not in t.lower()]

    headline = ""
    if og_title and og_title[0].strip():
        headline = og_title[0].strip()
    elif h1_text:
        joined_h1 = " ".join(t.strip() for t in h1_text if t.strip())
        if len(joined_h1) > 10:
            headline = joined_h1
    if not headline and valid_titles:
        headline = max(valid_titles, key=len)

    # 2. Source / Publisher
    og_site = tree.xpath("//meta[@property='og:site_name']/@content")
    domain = urllib.parse.urlparse(url).netloc.replace("www.", "") if url else "Sumber Web"
    source = og_site[0].strip() if og_site and og_site[0].strip() else (domain or "Sumber Web")

    # 3. Paragraphs from <article> or <main> or general <p>
    para_nodes = tree.xpath("//article//p | //main//p")
    if len(para_nodes) < 2:
        para_nodes = tree.xpath("//p")

    paragraphs: list[str] = []
    seen_p: set[str] = set()
    for p in para_nodes:
        p_txt = re.sub(r"\s+", " ", p.text_content()).strip()
        if len(p_txt) < 35:
            continue
        p_lower = p_txt.lower()
        skip_cues = ("baca juga:", "copyright ©", "ikuti kami di", "cookie")
        if any(skip in p_lower for skip in skip_cues):
            continue
        if p_txt not in seen_p:
            seen_p.add(p_txt)
            paragraphs.append(p_txt)

    meta_desc = tree.xpath("//meta[@name='description']/@content")
    if not paragraphs and meta_desc and meta_desc[0].strip():
        paragraphs.append(meta_desc[0].strip())

    body_text = "\n".join(paragraphs)[:4000]
    highlights = extract_key_highlights(headline, paragraphs)

    return {
        "blocked": False,
        "headline": headline or (paragraphs[0][:120] if paragraphs else "Artikel Berita"),
        "source": source,
        "body_text": body_text,
        "highlights": highlights,
    }


def extract_key_highlights(headline: str, paragraphs: list[str], max_items: int = 3) -> list[str]:
    """Selects top fact-dense sentences (with numbers, currency, or cash terms)."""
    fact_cues = (
        "triliun",
        "miliar",
        "persen",
        "%",
        "rp",
        "kontrak",
        "uang muka",
        "turnkey",
        "pembayaran",
        "laba",
        "rugi",
        "utang",
        "obligasi",
        "dividen",
        "kas",
    )
    candidates: list[tuple[int, str]] = []
    for p in paragraphs[:15]:
        sentences = re.split(r"(?<=[.!?])\s+", p)
        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) < 30 or s_clean == headline:
                continue
            s_low = s_clean.lower()
            score = sum(2 for cue in fact_cues if cue in s_low)
            if re.search(r"\d", s_clean):
                score += 1
            if score > 0 and check_language_compliance(s_clean):
                candidates.append((score, s_clean))

    candidates.sort(key=lambda x: x[0], reverse=True)
    selected: list[str] = []
    for _, s in candidates:
        if s not in selected:
            selected.append(s)
        if len(selected) >= max_items:
            break

    if not selected and paragraphs:
        for p in paragraphs[:max_items]:
            if check_language_compliance(p):
                selected.append(p[:260])

    return selected


def _build_ssl_context() -> ssl.SSLContext:
    """Builds a standard verified TLS context using certifi CA bundle on Windows/Linux."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_article_from_url(url: str, timeout: int = 10) -> dict[str, Any]:
    """Safely fetches a public news URL and extracts clean article content."""
    is_valid, err_msg = validate_public_url(url)
    if not is_valid:
        return {"status": "error", "message": err_msg}

    req = urllib.request.Request(
        url.strip(),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        },
    )

    try:
        ssl_ctx = _build_ssl_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as resp:
            raw = resp.read(1_500_000)  # cap 1.5 MB
            extracted = extract_article_from_html(raw, url=url)
            if extracted.get("blocked"):
                return {"status": "blocked", "message": extracted["reason"]}
            return {"status": "success", **extracted}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 429):
            return {
                "status": "blocked",
                "message": (
                    f"Situs menolak akses otomatis (HTTP {exc.code}). "
                    "Gunakan kolom 'Teks Berita Manual' untuk menganalisis isi artikel."
                ),
            }
        return {"status": "error", "message": f"Gagal mengambil halaman (HTTP {exc.code})."}
    except urllib.error.URLError as exc:
        return {"status": "error", "message": f"Gagal mengakses URL berita: {exc.reason}"}
    except Exception as exc:
        return {"status": "error", "message": f"Gagal mengakses URL berita: {exc}"}


def _find_best_alias_match(
    haystack: str,
    issuers: list[dict[str, Any]],
    known_tickers: set[str],
    prefer_earliest: bool = True,
) -> str | None:
    """Finds the best matching ticker in haystack by position or frequency."""
    lowered = haystack.lower()
    candidates: list[tuple[int, int, str]] = []  # (first_pos, -count, ticker)

    for ticker, aliases in ISSUER_NAME_ALIASES.items():
        if ticker not in known_tickers:
            continue
        best_pos: int | None = None
        total_hits = 0
        for alias in aliases:
            pos = lowered.find(alias)
            if pos != -1:
                if best_pos is None or pos < best_pos:
                    best_pos = pos
                total_hits += lowered.count(alias)
        if best_pos is not None:
            candidates.append((best_pos, -total_hits, ticker))

    if not candidates:
        for item in issuers:
            t = item["ticker"].upper()
            comp_clean = (
                item.get("company_name", "")
                .lower()
                .replace("tbk.", "")
                .replace("(persero)", "")
                .strip()
            )
            first_two = " ".join(comp_clean.split()[:2])
            if len(first_two) >= 5:
                pos = lowered.find(first_two)
                if pos != -1:
                    candidates.append((pos, -lowered.count(first_two), t))

    if not candidates:
        return None
    if prefer_earliest:
        candidates.sort(key=lambda x: (x[0], x[1]))
    else:
        candidates.sort(key=lambda x: (x[1], x[0]))
    return candidates[0][2]


def detect_ticker_in_article(
    text: str,
    issuers: list[dict[str, Any]],
    url: str = "",
) -> str | None:
    """Detects which covered BEI ticker is referenced, prioritizing headline and URL."""
    known_tickers = {i["ticker"].upper() for i in issuers}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    headline = lines[0] if lines else ""
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    url_norm = url.replace("-", " ").replace("_", " ")

    # 1. Priority: Headline & URL (explicit ticker -> alias/company name earliest in headline)
    head_and_url = f"{headline}\n{url_norm}"
    for t in re.findall(r"\(([A-Z]{4})\)", head_and_url):
        if t in known_tickers:
            return t
    for t in re.findall(r"\b([A-Z]{4})\b", headline):
        if t in known_tickers:
            return t
    head_match = _find_best_alias_match(
        head_and_url, issuers, known_tickers, prefer_earliest=True
    )
    if head_match:
        return head_match

    # 2. Fallback: Article body (explicit ticker -> most frequent / earliest alias)
    for t in re.findall(r"\(([A-Z]{4})\)", body):
        if t in known_tickers:
            return t
    for t in re.findall(r"\b([A-Z]{4})\b", body):
        if t in known_tickers:
            return t
    return _find_best_alias_match(
        body, issuers, known_tickers, prefer_earliest=False
    )


def detect_all_tickers_in_article(
    text: str,
    issuers: list[dict[str, Any]],
    url: str = "",
    max_tickers: int = 5,
) -> list[str]:
    """Returns ordered unique list of covered BEI tickers mentioned in headline/URL/body."""
    known_tickers = {i["ticker"].upper() for i in issuers}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    headline = lines[0] if lines else ""
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    url_norm = url.replace("-", " ").replace("_", " ")
    head_and_url = f"{headline}\n{url_norm}".lower()
    body_low = body.lower()

    found: list[tuple[int, int, str]] = []  # (section_rank, pos, ticker)
    seen: set[str] = set()

    def _scan(haystack_raw: str, haystack_low: str, sec_rank: int) -> None:
        for m in re.finditer(r"\(([A-Z]{4})\)|\b([A-Z]{4})\b", haystack_raw):
            t = m.group(1) or m.group(2)
            if t in known_tickers and t not in seen:
                seen.add(t)
                found.append((sec_rank, m.start(), t))
        for ticker, aliases in ISSUER_NAME_ALIASES.items():
            if ticker not in known_tickers or ticker in seen:
                continue
            positions = [haystack_low.find(a) for a in aliases if haystack_low.find(a) != -1]
            if positions:
                seen.add(ticker)
                found.append((sec_rank, min(positions), ticker))

    _scan(f"{headline}\n{url_norm}", head_and_url, 0)
    _scan(body, body_low, 1)
    found.sort(key=lambda x: (x[0], x[1]))
    return [t for _, _, t in found[:max_tickers]]


def analyze_sentiment_deterministic(headline: str, body_text: str) -> dict[str, Any]:
    """Classifies news article sentiment deterministically and extracts keyword evidence."""
    full_text = f"{headline} {body_text}".lower()
    head_low = headline.lower()

    matched_pos = [kw for kw in ARTICLE_POSITIVE_CUES if kw in full_text]
    matched_warn = [kw for kw in ARTICLE_WARNING_CUES if kw in full_text]

    # Headline carries higher structural weight than passing mentions in the body
    head_pos = sum(2 for kw in ARTICLE_POSITIVE_CUES if kw in head_low)
    head_warn = sum(2 for kw in ARTICLE_WARNING_CUES if kw in head_low)

    pos_score = len(matched_pos) + head_pos
    warn_score = len(matched_warn) + head_warn

    if warn_score > pos_score and warn_score > 0:
        sentiment = "PERHATIAN"
    elif pos_score > warn_score and pos_score > 0:
        sentiment = "POSITIF"
    elif pos_score > 0 and warn_score > 0:
        sentiment = "POSITIF" if head_pos >= head_warn else "PERHATIAN"
    else:
        sentiment = "NETRAL"

    return {
        "sentiment": sentiment,
        "positive_score": pos_score,
        "warning_score": warn_score,
        "matched_positive": matched_pos[:6],
        "matched_warning": matched_warn[:6],
    }


def _build_forward_forecast_block(
    ticker: str,
    fundamentals: dict[str, Any],
    sentiment_res: dict[str, Any],
    headline: str,
    highlights: list[str],
    ml_forecast: dict[str, Any] | None,
) -> dict[str, Any]:
    """Computes deterministic forward-looking business & cash-flow outlook."""
    combined_news = f"{headline} {' '.join(highlights)}".lower()
    sentiment = sentiment_res["sentiment"]
    is_free = bool(fundamentals.get("debt_free_short_term"))
    cov = float(fundamentals.get("cash_coverage_ratio") or 0.0)
    cfo = float(fundamentals.get("cfo_ttm_idr") or 0.0)
    net_inc = float(fundamentals.get("net_income_ttm_idr") or 0.0)
    sloan_pct = float(fundamentals.get("sloan_ratio_pct") or 0.0)

    is_cash_tight = (not is_free and cov < 1.0 and cfo < 0) or (not is_free and cov < 0.30)
    has_rescue_cue = any(
        w in combined_news
        for w in ("danantara", "tak akan dibiarkan", "pmn", "suntikan", "restrukturisasi", "bumn")
    )
    has_debt_loss_cue = any(
        w in combined_news
        for w in ("terbebani", "kerugian", "rugi", "utang", "whoosh", "kcic", "psbi", "bunga")
    )
    has_contract_cue = any(
        w in combined_news for w in ("kontrak baru", "nilai kontrak", "proyek", "ikn", "uang muka")
    )

    projs = (ml_forecast or {}).get("projections") or []
    trend_cfo = float((ml_forecast or {}).get("cfo_annual_trend_idr") or 0.0)
    p26 = projs[0] if len(projs) >= 1 else None
    p27 = projs[1] if len(projs) >= 2 else None

    if p26 and p27:
        cfo26 = _fmt_idr_short(p26.get("projected_cfo_idr"))
        cfo26_low = _fmt_idr_short(p26.get("projected_cfo_lower_90"))
        cfo26_high = _fmt_idr_short(p26.get("projected_cfo_upper_90"))
        cov26 = p26.get("projected_cash_coverage")
        cov27 = p27.get("projected_cash_coverage")
        cfo27 = _fmt_idr_short(p27.get("projected_cfo_idr"))
        trend_txt = (
            f"+{_fmt_idr_short(trend_cfo)}/thn (membaik)"
            if trend_cfo >= 0
            else f"{_fmt_idr_short(trend_cfo)}/thn (tertekan)"
        )
        cov_proj_txt = (
            f"{cov26:.2f}x (2026) -> {cov27:.2f}x (2027)"
            if cov26 is not None and cov27 is not None
            else "Bebas Utang JP"
        )
        ml_line_expert = (
            f"Proyeksi regresi arus kas FY 2026–2027 menunjukkan slope CFO {trend_txt}: "
            f"estimasi tengah CFO FY 2026 {cfo26} (CI 90%: {cfo26_low} s.d. {cfo26_high}) "
            f"dan FY 2027 {cfo27}, dengan proyeksi Cash Coverage {cov_proj_txt}."
        )
    else:
        ml_line_expert = (
            "Data historis multi-tahun masih terakumulasi sehingga proyeksi lintas tahun "
            "berfokus pada rasio likuiditas dan kualitas akrual periode berjalan."
        )

    if is_cash_tight and has_debt_loss_cue:
        if has_rescue_cue:
            stance = "VOLATILITAS JANGKA PENDEK: PEMULIHAN BERSYARAT DUKUNGAN HOLDING"
            f_awam = (
                f"Proyeksi 12-24 bulan ke depan untuk {ticker}: jangka pendek masih berat "
                f"karena kerugian berjalan dan beban utang/konsorsium menahan arus kas. "
                f"Namun, sinyal penyelamatan negara/holding menjaga peluang bertahan tetap terbuka "
                f"bila restrukturisasi atau suntikan ekuitas terealisasi tanpa menambah beban kas."
            )
            f_expert = (
                f"{ml_line_expert} Kendati arah regresi CFO historis membaik, tekanan rugi "
                "berjalan dan kewajiban asosiasi menciptakan risiko deviasi ke batas bawah CI 90%."
                " Katalis re-rating fundamental baru terjadi apabila dukungan holding "
                "mengonversi/merestrukturisasi porsi beban utang dan memulihkan CFO > Rp 0."
            )
        else:
            stance = "TEKANAN LIKUIDITAS BERKELANJUTAN: PRIORITAS EFISIENSI KAS"
            f_awam = (
                f"Proyeksi ke depan untuk {ticker}: kinerja operasional masih menghadapi ujian "
                f"ketat karena uang kas belum cukup lebar untuk menutup utang jatuh tempo "
                f"sementara arus kas usaha masih keluar negatif."
            )
            f_expert = (
                f"{ml_line_expert} Tanpa konversi piutang cepat atau penjadwalan ulang utang JP, "
                f"risiko pengetatan modal kerja dan erosi ekuitas tetap dominan 4 kuartal ke depan."
            )
    elif is_cash_tight and has_contract_cue:
        stance = "PEMULIHAN BERSYARAT: MENUNGGU KONVERSI KONTRAK JADI KAS"
        f_awam = (
            f"Proyeksi 12-24 bulan {ticker}: perolehan/progres proyek memberi bahan bakar "
            f"pendapatan ke depan, tetapi pemulihan fundamental baru sah jika termin proyek "
            f"dibayar tunai dan kas operasional berbalik positif secara konsisten."
        )
        f_expert = (
            f"{ml_line_expert} Katalis orderbook/progres proyek bersifat positif terhadap "
            f"utilisasi aset, namun konversi piutang menjadi CFO riil menentukan apakah "
            f"Cash Coverage dapat melewati ambang aman > 1.00x."
        )
    elif (is_free or cov >= 1.2) and cfo > 0 and net_inc > 0 and sloan_pct <= 10.0:
        stance = "PROSPEK FUNDAMENTAL SOLVEN & TANGGUH"
        f_awam = (
            f"Proyeksi ke depan {ticker} berada di jalur sehat: kas tebal serta arus kas masuk "
            f"yang nyata memberi ruang aman untuk membiayai ekspansi atau menjaga ketahanan "
            f"saat kondisi pasar berfluktuasi."
        )
        f_expert = (
            f"{ml_line_expert} Profil neraca berdaya serap risiko tinggi mendukung stabilitas "
            f"margin serta kapasitas pemenuhan kewajiban tanpa kebutuhan utang berbunga baru."
        )
    elif net_inc > 0 and cfo < 0 and sloan_pct > 10.0:
        stance = "WASPADA KUALITAS LABA AKRUAL"
        f_awam = (
            f"Proyeksi ke depan {ticker}: pertumbuhan penjualan/laba pembukuan perlu diwaspadai "
            f"apabila tagihan pelanggan menumpuk terlalu lama dan tidak segera cair jadi kas."
        )
        f_expert = (
            f"{ml_line_expert} Divergensi laba akuntansi vs CFO meningkatkan sensitivitas risiko "
            f"penurunan nilai piutang (CKPN) dalam 2-4 kuartal mendatang."
        )
    else:
        stance = "NETRAL TERKENDALI: PANTAU REALISASI KAS KUARTALAN"
        f_awam = (
            f"Proyeksi ke depan {ticker} tergolong stabil bersyarat: likuiditas saat ini masih "
            f"terjaga, namun arah perbaikan jangka menengah bergantung pada konsistensi kas "
            f"masuk operasional di laporan kuartal berikutnya."
        )
        f_expert = (
            f"{ml_line_expert} Kinerja kuartalan berikutnya akan menjadi penentu apakah "
            f"momentum berita ({sentiment}) berkonversi menjadi perbaikan CFO dan margin kas."
        )

    watchpoints: list[str] = []
    if has_rescue_cue or has_debt_loss_cue:
        watchpoints.append(
            "Skema riil restrukturisasi/penyelesaian utang & beban asosiasi (apakah menurunkan "
            "beban bunga dan menahan rugi bersih di kuartal mendatang)."
        )
    if has_contract_cue:
        watchpoints.append(
            "Realisasi uang muka & pembayaran termin bulanan pada pos Arus Kas Operasi (CFO)."
        )
    if cfo < 0:
        watchpoints.append(
            f"Titik balik CFO TTM {ticker} menuju zona positif (> Rp 0) guna memutus "
            "ketergantungan pendanaan eksternal."
        )
    else:
        watchpoints.append(
            "Konsistensi rasio konversi CFO terhadap laba bersih serta Sloan Accrual (< 10%)."
        )
    if not is_free:
        watchpoints.append(
            f"Pergerakan Cash Coverage Ratio (saat ini {cov:.2f}x) menuju bantalan aman >= 1.20x."
        )

    return {
        "outlook_stance": stance,
        "forecast_awam": f_awam,
        "forecast_expert": f_expert,
        "watchpoints": watchpoints[:3],
    }


def _build_deterministic_synthesis(
    ticker: str,
    company_name: str,
    fundamentals: dict[str, Any],
    sentiment_res: dict[str, Any],
    headline: str,
    highlights: list[str],
    ml_forecast: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds strict zero-hallucination dual-mode synthesis (Awam & Expert) + forward forecast."""
    sentiment = sentiment_res["sentiment"]
    is_free = bool(fundamentals.get("debt_free_short_term"))
    cov = float(fundamentals.get("cash_coverage_ratio") or 0.0)
    cfo = float(fundamentals.get("cfo_ttm_idr") or 0.0)
    net_inc = float(fundamentals.get("net_income_ttm_idr") or 0.0)
    sloan_pct = float(fundamentals.get("sloan_ratio_pct") or 0.0)
    cash_str = _fmt_idr_short(fundamentals.get("cash_idr"))
    debt_str = _fmt_idr_short(fundamentals.get("st_debt_idr"))
    cfo_str = _fmt_idr_short(cfo)
    net_str = _fmt_idr_short(net_inc)
    p_distress = float(fundamentals.get("distress_probability_pct") or 0.0)
    rating = fundamentals.get("synthetic_rating") or "N/A"

    is_cash_tight = (not is_free and cov < 0.30) or (cfo < 0 and net_inc < 0)
    is_paper_profit = net_inc > 0 and cfo < 0 and sloan_pct > 10.0

    hl_summary = highlights[0] if highlights else headline
    combined_low = f"{headline} {hl_summary}".lower()
    has_rescue_cue = any(
        w in combined_low for w in ("danantara", "tak akan dibiarkan", "pmn", "suntikan")
    )

    if is_cash_tight and sentiment == "POSITIF":
        awam = (
            f"Berita '{headline}' bernada POSITIF sebagai katalis bisnis {ticker} ke depan "
            f"({hl_summary}). Namun, Accrual Radar BEI mencatat kas saat ini masih ketat: "
            f"uang kas {cash_str} berbanding utang jatuh tempo {debt_str} ({cov:.2f}x), "
            f"dengan arus kas usaha {cfo_str} dan laba {net_str}. "
            f"Kesimpulan: berita kontrak/ekspansi ini perlu dibuktikan dengan masuknya "
            f"uang tunai nyata pada laporan CFO kuartal mendatang."
        )
        expert = (
            f"Katalis berita POSITIF ({headline}) berpotensi memperbaiki modal kerja "
            f"prospektif {ticker}, namun sesuai prinsip Contextual Isolation tidak "
            f"menghapus tekanan likuiditas neraca berjalan (Cash Coverage {cov:.2f}x, "
            f"CFO TTM {cfo_str}, Net Income {net_str}, Sloan {sloan_pct:+.1f}%, "
            f"P(Distress) {p_distress:.1f}% / Rating {rating}). Pantau realisasi termin "
            f"kas dari katalis tersebut terhadap pemulihan CFO kuartalan."
        )
    elif is_cash_tight and sentiment == "PERHATIAN":
        rescue_note_awam = (
            " Adanya sinyal dukungan pemegang saham/holding memberi bantalan harapan, namun belum "
            "mengubah fakta utang dan rugi pada neraca saat ini."
            if has_rescue_cue
            else ""
        )
        rescue_note_expert = (
            " Sinyal jangkar holding/negara hanya meredam tail-risk gagal bayar bila segera "
            "ditindaklanjuti injeksi ekuitas atau restrukturisasi mengikat."
            if has_rescue_cue
            else ""
        )
        awam = (
            f"Berita peringatan ('{headline}') mengonfirmasi tekanan fundamental pada {ticker}: "
            f"kas di bank {cash_str} berbanding utang jatuh tempo {debt_str} (daya tahan "
            f"{cov:.2f}x), dengan arus kas usaha {cfo_str} dan rugi bersih {net_str}."
            f"{rescue_note_awam}"
        )
        expert = (
            f"Sentimen berita PERHATIAN sejalan dengan kerentanan laporan keuangan {ticker} "
            f"(Cash {cash_str} vs Utang JP {debt_str}, Coverage {cov:.2f}x, CFO {cfo_str}, "
            f"Net Income {net_str}).{rescue_note_expert}"
        )
    elif is_paper_profit:
        awam = (
            f"Berita berstatus {sentiment} ('{headline}'). Meski pembukuan {ticker} "
            f"mencatat laba {net_str}, Accrual Radar mendeteksi kas usaha riil masih "
            f"{cfo_str} (Sloan Accrual {sloan_pct:+.1f}%). Pastikan piutang pelanggan "
            f"benar-benar tertagih menjadi uang kas di bank."
        )
        expert = (
            f"Terlepas dari sentimen berita {sentiment}, Accrual Radar mendeteksi "
            f"divergensi akrual tinggi pada {ticker} (Net Income {net_str}, CFO {cfo_str}, "
            f"Sloan {sloan_pct:+.1f}%). Verifikasi kolektibilitas piutang dan kecukupan "
            f"cadangan CKPN tetap menjadi prioritas di atas narasi berita."
        )
    elif (is_free or cov >= 1.0) and sentiment == "POSITIF":
        awam = (
            f"Sinergi sehat pada {ticker}: berita POSITIF ('{headline}') didukung penuh "
            f"oleh kas tebal ({'Bebas Utang Tahun Ini' if is_free else f'{cov:.2f}x utang'}) "
            f"dan kas masuk usaha nyata {cfo_str}. Ekspansi berjalan di atas modal kas riil."
        )
        expert = (
            f"Alignment fundamental & sentimen pada {ticker}: katalis POSITIF sejalan "
            f"dengan neraca solven ({'Debt-Free JP' if is_free else f'Coverage {cov:.2f}x'}, "
            f"CFO TTM {cfo_str}, Sloan {sloan_pct:+.1f}%, Rating {rating})."
        )
    else:
        cov_txt = "Bebas Utang JP" if is_free else f"{cov:.2f}x"
        awam = (
            f"Berita '{headline}' berstatus {sentiment}. Secara fundamental BEI, {ticker} "
            f"memiliki kas {cash_str} ({cov_txt}), arus kas usaha {cfo_str}, dan laba "
            f"bersih {net_str}."
        )
        expert = (
            f"Berita berstatus {sentiment} ({headline}) disandingkan dengan profil deterministik "
            f"{ticker}: Cash {cash_str}, {cov_txt}, CFO TTM {cfo_str}, Net Income {net_str}, "
            f"Sloan {sloan_pct:+.1f}% (P(Distress) {p_distress:.1f}%, Rating {rating})."
        )

    fwd = _build_forward_forecast_block(
        ticker=ticker,
        fundamentals=fundamentals,
        sentiment_res=sentiment_res,
        headline=headline,
        highlights=highlights,
        ml_forecast=ml_forecast,
    )

    return {
        "analysis_awam": awam,
        "analysis_expert": expert,
        "engine_source": "Deterministic Cross-Check & Cash Trajectory Engine",
        **fwd,
    }


def synthesize_news_vs_accrual(
    ticker: str,
    company_name: str,
    fundamentals: dict[str, Any],
    sentiment_res: dict[str, Any],
    headline: str,
    highlights: list[str],
    api_key: str | None = None,
    ml_forecast: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Combines news sentiment & highlights with audited XBRL fundamentals and forward forecast.
    Uses Gemini strictly as narrative translator if configured, with safe deterministic fallback.
    """
    det = _build_deterministic_synthesis(
        ticker=ticker,
        company_name=company_name,
        fundamentals=fundamentals,
        sentiment_res=sentiment_res,
        headline=headline,
        highlights=highlights,
        ml_forecast=ml_forecast,
    )

    global _GEMINI_BACKOFF_UNTIL
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key or os.getenv("PYTEST_CURRENT_TEST") or time.time() < _GEMINI_BACKOFF_UNTIL:
        return det

    try:
        from google import genai

        client = genai.Client(api_key=key)
        is_free = bool(fundamentals.get("debt_free_short_term"))
        cov = float(fundamentals.get("cash_coverage_ratio") or 0.0)
        cov_str = "Bebas Utang JP" if is_free else f"{cov:.2f}x"
        prompt = (
            "Kamu adalah analis komunikasi keuangan BEI. Tugasmu HANYA membandingkan berita "
            "dan angka audit Python di bawah ini menjadi 2 versi singkat (masing-masing maks 3 "
            "kalimat): [AWAM] untuk orang awam tanpa istilah rumit, dan [EXPERT] untuk analis "
            "profesional. Jelaskan implikasi prospek bisnis & arus kas ke depan secara netral. "
            "DILARANG menghitung angka baru, DILARANG memberi rekomendasi beli/jual/target harga, "
            "dan DILARANG memakai kata tuduhan.\n\n"
            f"Emiten: {ticker} ({company_name})\n"
            f"Berita ({sentiment_res['sentiment']}): {headline}\n"
            f"Fakta Artikel: {' | '.join(highlights[:2])}\n"
            f"Angka Audit BEI FY2025: Kas={_fmt_idr_short(fundamentals.get('cash_idr'))}, "
            f"Utang JP={_fmt_idr_short(fundamentals.get('st_debt_idr'))}, Coverage={cov_str}, "
            f"CFO TTM={_fmt_idr_short(fundamentals.get('cfo_ttm_idr'))}, "
            f"Laba TTM={_fmt_idr_short(fundamentals.get('net_income_ttm_idr'))}, "
            f"Sloan={float(fundamentals.get('sloan_ratio_pct') or 0.0):+.1f}%, "
            f"P(Distress)={float(fundamentals.get('distress_probability_pct') or 0.0):.1f}% "
            f"(Rating {fundamentals.get('synthetic_rating', 'N/A')}).\n"
            f"Proyeksi Kuantitatif Python: {det['forecast_expert']}\n\n"
            "Format output persis:\nAWAM: <teks>\nEXPERT: <teks>"
        )

        res_holder: list[Any] = []

        def _worker() -> None:
            try:
                resp = client.models.generate_content(model=DEFAULT_GEMINI_MODEL, contents=prompt)
                res_holder.append((getattr(resp, "text", "") or "").strip())
            except Exception as exc:
                res_holder.append(exc)

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        th.join(timeout=2.5)

        if not res_holder or isinstance(res_holder[0], Exception):
            _GEMINI_BACKOFF_UNTIL = time.time() + 600
            return det

        txt = str(res_holder[0])
        if txt and check_language_compliance(txt) and "AWAM:" in txt and "EXPERT:" in txt:
            parts = txt.split("EXPERT:", 1)
            awam_txt = parts[0].replace("AWAM:", "").strip()
            expert_txt = parts[1].strip()
            if awam_txt and expert_txt:
                return {
                    **det,
                    "analysis_awam": awam_txt,
                    "analysis_expert": expert_txt,
                    "engine_source": "Gemini AI + Deterministic Cash Trajectory",
                }
    except Exception as exc:
        _GEMINI_BACKOFF_UNTIL = time.time() + 600
        logger.debug("Gemini synthesis fallback triggered: %s", exc)

    return det
