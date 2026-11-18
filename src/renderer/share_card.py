"""
Shareable Fact Card Generator (Fase 7 Audit-Ledger Redesign).
Produces deterministic, compliance-checked retail fact cards (PNG 1:1 & 9:16)
in light-first audit-ledger style (#FAF8F5 paper, #FFFFFF sheet, #18181B ink).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from src.engine.llm_explainer import check_language_compliance


def _fmt_idr_id(val: float | int | None) -> str:
    """Formats IDR amounts in Indonesian convention (comma decimal, minus sign)."""
    if val is None:
        return "Tidak tersedia"
    v = float(val)
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e12:
        return f"{sign}Rp {av / 1e12:,.2f} T".replace(",", "X").replace(".", ",").replace("X", ".")
    if av >= 1e9:
        return f"{sign}Rp {av / 1e9:,.1f} M".replace(",", "X").replace(".", ",").replace("X", ".")
    if av >= 1e6:
        return f"{sign}Rp {av / 1e6:,.1f} Jt".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}Rp {av:,.0f}".replace(",", ".")


def _load_font(size: int, bold: bool = False) -> Any:
    from PIL import ImageFont

    candidates = (
        [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for fp in candidates:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def build_share_card_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Builds deterministic, retail-language fact card fields for a single ticker."""
    ticker = str(row.get("ticker", "")).upper()
    company_name = str(row.get("company_name") or ticker)
    period_end_date = str(row.get("period_end_date") or "2025-12-31")
    cfo_val = float(row.get("cfo_ttm_idr") or 0.0)
    is_free = bool(row.get("debt_free_short_term"))
    cov_val = float(row.get("cash_coverage_ratio") or 0.0)
    flag_liq = bool(row.get("flag_acute_liquidity"))
    flag_acc = bool(row.get("flag_accrual_divergence"))

    cfo_label = "Kas masuk dari operasional (12 bulan terakhir)"
    cfo_value = _fmt_idr_id(cfo_val)

    cov_label = "Kas dibanding utang jangka pendek"
    cov_value = "Bebas utang jangka pendek" if is_free else f"{cov_val:.2f}x".replace(".", ",")

    status_label = "Ringkasan kondisi kas"
    if is_free:
        status_value = f"Tidak ada utang jangka pendek berbunga (laporan {period_end_date})"
        status_tone = "neutral"
    else:
        pct = round(cov_val * 100)
        if flag_liq:
            status_value = (
                f"Kas menutup {pct}% utang jangka pendek, arus kas operasional negatif "
                f"(laporan {period_end_date})"
            )
            status_tone = "warm"
        elif flag_acc:
            status_value = (
                f"Laba tercatat positif, arus kas operasional negatif, kas menutup {pct}% "
                f"utang jangka pendek (laporan {period_end_date})"
            )
            status_tone = "warm"
        elif cov_val < 1.0:
            status_value = f"Kas menutup {pct}% utang jangka pendek (laporan {period_end_date})"
            status_tone = "warm"
        else:
            status_value = f"Kas menutup {pct}% utang jangka pendek (laporan {period_end_date})"
            status_tone = "neutral"

    xbrl_source = "Sumber: laporan XBRL resmi BEI (tabel canonical_facts)"
    disclaimer = (
        "Bukan rekomendasi investasi dan bukan saran transaksi saham. Data bersifat historis "
        "dan mengikuti tanggal laporan keuangan berkala BEI di atas."
    )

    all_text = " ".join([
        ticker, company_name, cfo_label, cfo_value, cov_label, cov_value,
        status_label, status_value, xbrl_source, disclaimer,
    ])
    if not check_language_compliance(all_text):
        raise ValueError("Share card text failed language compliance check.")

    return {
        "ticker": ticker,
        "company_name": company_name,
        "period_end_date": period_end_date,
        "metrics": [
            {"label": cfo_label, "value": cfo_value, "is_negative": cfo_val < 0},
            {"label": cov_label, "value": cov_value, "is_negative": False},
            {"label": status_label, "value": status_value, "tone": status_tone, "is_negative": False},
        ],
        "xbrl_source": xbrl_source,
        "disclaimer": disclaimer,
        "status_tone": status_tone,
    }


def _wrap_text(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        bbox = draw.textbbox((0, 0), cand, font=font)
        if (bbox[2] - bbox[0]) <= max_width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_share_card_png(payload: dict[str, Any], ratio: str = "1:1") -> bytes:
    """Renders the deterministic fact card into light-first ledger PNG bytes (1:1 or 9:16)."""
    from PIL import Image, ImageDraw

    is_vertical = ratio.strip() == "9:16"
    width, height = (1080, 1920) if is_vertical else (1080, 1080)

    paper = (250, 248, 245)      # #FAF8F5
    sheet = (255, 255, 255)      # #FFFFFF
    ink = (24, 24, 27)           # #18181B
    muted = (82, 82, 91)         # #52525B
    rule = (228, 224, 216)       # #E4E0D8
    neg_red = (185, 28, 28)      # #B91C1C
    warm_bg = (254, 243, 199)    # #FEF3C7
    warm_ink = (120, 53, 15)     # #78350F
    neu_bg = (244, 244, 240)

    img = Image.new("RGB", (width, height), color=paper)
    draw = ImageDraw.Draw(img)

    margin = 48
    pad = 84
    draw.rectangle(
        [(margin, margin), (width - margin, height - margin)],
        fill=sheet,
        outline=rule,
        width=2,
    )

    f_brand = _load_font(26, bold=True)
    f_ticker = _load_font(82 if is_vertical else 72, bold=True)
    f_comp = _load_font(34 if is_vertical else 30, bold=False)
    f_date = _load_font(26, bold=False)
    f_lbl = _load_font(27, bold=False)
    f_val = _load_font(44 if is_vertical else 40, bold=True)
    f_stat = _load_font(30 if is_vertical else 28, bold=True)
    f_foot = _load_font(23, bold=False)

    y = 92
    draw.text((pad, y), "IDX Cash Radar, catatan fakta kas", fill=muted, font=f_brand)
    y += 48
    draw.line([(pad, y), (width - pad, y)], fill=rule, width=2)
    y += 32

    draw.text((pad, y), payload["ticker"], fill=ink, font=f_ticker)
    y += (102 if is_vertical else 88)
    for line in _wrap_text(draw, payload["company_name"], f_comp, width - 2 * pad):
        draw.text((pad, y), line, fill=ink, font=f_comp)
        y += 40
    y += 10
    draw.text(
        (pad, y),
        f"Tanggal laporan keuangan: {payload['period_end_date']}",
        fill=muted,
        font=f_date,
    )
    y += (54 if is_vertical else 40)
    draw.line([(pad, y), (width - pad, y)], fill=rule, width=2)
    y += (36 if is_vertical else 24)

    for idx, m in enumerate(payload["metrics"]):
        draw.text((pad, y), m["label"], fill=muted, font=f_lbl)
        y += 40
        if idx == 2:
            bg = warm_bg if m.get("tone") == "warm" else neu_bg
            fg = warm_ink if m.get("tone") == "warm" else ink
            lines = _wrap_text(draw, m["value"], f_stat, width - 2 * pad - 36)
            box_h = 32 + len(lines) * 40
            draw.rectangle([(pad, y), (width - pad, y + box_h)], fill=bg, outline=rule, width=1)
            ty = y + 16
            for ln in lines:
                draw.text((pad + 18, ty), ln, fill=fg, font=f_stat)
                ty += 40
            y += box_h + (42 if is_vertical else 28)
        else:
            val_col = neg_red if m.get("is_negative") else ink
            draw.text((pad, y), m["value"], fill=val_col, font=f_val)
            y += (64 if is_vertical else 56)
            draw.line([(pad, y), (width - pad, y)], fill=rule, width=1)
            y += (34 if is_vertical else 22)

    foot_y = height - (230 if is_vertical else 165)
    draw.line([(pad, foot_y - 20), (width - pad, foot_y - 20)], fill=rule, width=2)
    draw.text((pad, foot_y), payload["xbrl_source"], fill=ink, font=f_foot)
    dy = foot_y + 34
    for ln in _wrap_text(draw, payload["disclaimer"], f_foot, width - 2 * pad):
        draw.text((pad, dy), ln, fill=muted, font=f_foot)
        dy += 30

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
