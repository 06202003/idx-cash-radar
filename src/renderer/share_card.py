"""
Shareable Fact Card Generator (Fase 3).
Produces deterministic, compliance-checked retail fact cards (PNG 1:1 & 9:16)
using only audited XBRL data (cash_coverage, CFO TTM, deterministic safeguard flags).
Zero ML probabilities, zero price predictions.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from src.engine.llm_explainer import check_language_compliance


def _fmt_idr_compact(val: float | int | None) -> str:
    if val is None:
        return "N/A"
    v = float(val)
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e12:
        return f"{sign}Rp {av / 1e12:,.2f} T"
    if av >= 1e9:
        return f"{sign}Rp {av / 1e9:,.1f} M"
    if av >= 1e6:
        return f"{sign}Rp {av / 1e6:,.1f} Jt"
    return f"{sign}Rp {av:,.0f}"


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

    cfo_label = "Kas masuk dari operasional (12 bln)"
    cfo_value = _fmt_idr_compact(cfo_val)

    cov_label = "Kas dibanding utang jangka pendek"
    cov_value = "Bebas Utang JP" if is_free else f"{cov_val:.2f}x"

    status_label = "Status divergensi deterministik"
    if flag_liq:
        status_value = "Tekanan Likuiditas Kas (< 0.20x & CFO Negatif)"
        status_tone = "red"
    elif flag_acc:
        status_value = "Laba Kertas, Kas Operasi Negatif (Sloan > 10%)"
        status_tone = "amber"
    elif not is_free and cov_val < 1.0:
        status_value = "Kas di Bawah 1.0x Utang Jangka Pendek"
        status_tone = "amber"
    else:
        status_value = "Kas >= 1.0x Utang Jangka Pendek / Bebas Utang"
        status_tone = "green"

    xbrl_source = "Sumber: Laporan XBRL Resmi BEI (canonical_facts)"
    disclaimer = (
        "Bukan rekomendasi investasi atau ajakan beli/jual. Data bersifat historis "
        "dan tertinggal (laporan berkala BEI per tanggal laporan di atas)."
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
            {"label": cfo_label, "value": cfo_value},
            {"label": cov_label, "value": cov_value},
            {"label": status_label, "value": status_value, "tone": status_tone},
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
    """Renders the deterministic fact card into PNG bytes (1:1 or 9:16)."""
    from PIL import Image, ImageDraw

    is_vertical = ratio.strip() == "9:16"
    width, height = (1080, 1920) if is_vertical else (1080, 1080)

    img = Image.new("RGB", (width, height), color=(11, 15, 25))
    draw = ImageDraw.Draw(img)

    # Outer border & header bar
    pad = 64
    draw.rounded_rectangle(
        [(32, 32), (width - 32, height - 32)],
        radius=28,
        fill=(17, 24, 39),
        outline=(30, 58, 138),
        width=3,
    )

    f_brand = _load_font(28, bold=True)
    f_ticker = _load_font(84 if is_vertical else 72, bold=True)
    f_comp = _load_font(34 if is_vertical else 30, bold=False)
    f_date = _load_font(26, bold=True)
    f_lbl = _load_font(28, bold=False)
    f_val = _load_font(44 if is_vertical else 40, bold=True)
    f_stat = _load_font(32 if is_vertical else 29, bold=True)
    f_foot = _load_font(23, bold=False)

    y = 72
    draw.text((pad, y), "IDX CASH & ACCRUAL RADAR  |  KARTU AUDIT FAKTA", fill=(56, 189, 248), font=f_brand)
    y += 56
    draw.line([(pad, y), (width - pad, y)], fill=(31, 41, 55), width=2)
    y += 34

    draw.text((pad, y), payload["ticker"], fill=(255, 255, 255), font=f_ticker)
    y += (104 if is_vertical else 90)
    for line in _wrap_text(draw, payload["company_name"], f_comp, width - 2 * pad):
        draw.text((pad, y), line, fill=(203, 213, 225), font=f_comp)
        y += 40
    y += 14
    draw.text(
        (pad, y),
        f"Tanggal Laporan Keuangan: {payload['period_end_date']}",
        fill=(251, 191, 36),
        font=f_date,
    )
    y += (64 if is_vertical else 48)

    tone_colors = {
        "green": (52, 211, 153),
        "amber": (251, 191, 36),
        "red": (251, 113, 133),
    }

    card_h = 220 if is_vertical else 156
    gap = 34 if is_vertical else 24
    for idx, m in enumerate(payload["metrics"]):
        box_top = y
        box_bot = y + card_h
        draw.rounded_rectangle(
            [(pad, box_top), (width - pad, box_bot)],
            radius=18,
            fill=(11, 19, 41),
            outline=(30, 64, 175),
            width=2,
        )
        draw.text((pad + 28, box_top + 24), m["label"], fill=(148, 163, 184), font=f_lbl)
        val_color = tone_colors.get(m.get("tone", ""), (255, 255, 255))
        if idx == 2:
            vy = box_top + 74
            for ln in _wrap_text(draw, m["value"], f_stat, width - 2 * pad - 56):
                draw.text((pad + 28, vy), ln, fill=val_color, font=f_stat)
                vy += 42
        else:
            draw.text((pad + 28, box_top + 74), m["value"], fill=val_color, font=f_val)
        y = box_bot + gap

    # Footer: XBRL source + disclaimer
    foot_y = height - (230 if is_vertical else 165)
    draw.line([(pad, foot_y - 20), (width - pad, foot_y - 20)], fill=(31, 41, 55), width=2)
    draw.text((pad, foot_y), payload["xbrl_source"], fill=(56, 189, 248), font=f_foot)
    dy = foot_y + 36
    for ln in _wrap_text(draw, payload["disclaimer"], f_foot, width - 2 * pad):
        draw.text((pad, dy), ln, fill=(148, 163, 184), font=f_foot)
        dy += 30

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
