"""
PDF Reader and CALK Footnote Section Finder.
Reads Indonesian financial PDFs and locates footnotes for Trade Receivables & Contract Assets.
Uses PyMuPDF (fitz) or pypdf with fallback support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FootnotePageCandidate:
    page_number: int
    title_found: str
    text_content: str
    footnote_number: str | None = None


class PDFCALKReader:
    """PDF Reader and CALK section locator."""

    RECEIVABLE_KEYWORDS = [
        "piutang usaha",
        "trade receivables",
        "piutang proyek",
        "piutang retensi",
    ]

    CONTRACT_ASSET_KEYWORDS = [
        "aset kontrak",
        "contract assets",
        "tagihan bruto kepada pemberi kerja",
        "gross amount due from customers",
    ]

    RELATED_PARTY_KEYWORDS = [
        "pihak berelasi",
        "related parties",
        "pihak ketiga",
        "third parties",
    ]

    def extract_text_from_pdf(self, pdf_path: str | Path) -> list[tuple[int, str]]:
        """
        Extracts all pages from PDF file.
        Returns list of (page_number_1_indexed, text).
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        pages: list[tuple[int, str]] = []

        # Try PyMuPDF (fitz) first (very fast and preserves layout)
        try:
            import fitz

            doc = fitz.open(str(path))
            for i, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                pages.append((i, text))
            doc.close()
            return pages
        except Exception:
            pass

        # Try pypdf fallback
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            for i, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                pages.append((i, text))
            return pages
        except Exception as exc:
            raise RuntimeError(f"Could not extract text from PDF {path}: {exc}") from exc

    def find_footnote_candidates(
        self,
        pages: list[tuple[int, str]],
        target_type: str = "receivables",  # "receivables" | "contract_assets"
    ) -> list[FootnotePageCandidate]:
        """
        Finds pages containing relevant footnote disclosures.
        """
        candidates: list[FootnotePageCandidate] = []
        target_keywords = (
            self.RECEIVABLE_KEYWORDS
            if target_type == "receivables"
            else self.CONTRACT_ASSET_KEYWORDS
        )

        footnote_num_pattern = re.compile(
            r"(?:catatan|note)\s*(\d+[a-z]?)\s*[:\.]\s*([^\n\r]+)",
            re.IGNORECASE,
        )

        for page_num, text in pages:
            text_lower = text.lower()

            # Must have at least one target keyword
            has_target = any(kw in text_lower for kw in target_keywords)
            if not has_target:
                continue

            # Must also discuss related parties or third parties to have the breakdown
            has_breakdown = any(kw in text_lower for kw in self.RELATED_PARTY_KEYWORDS)
            if not has_breakdown:
                continue

            # Check if there is an explicit footnote header
            fn_match = footnote_num_pattern.search(text)
            fn_number = f"Catatan {fn_match.group(1)}" if fn_match else None
            fn_title = (
                fn_match.group(2).strip()
                if fn_match
                else target_type.replace("_", " ").title()
            )

            candidates.append(
                FootnotePageCandidate(
                    page_number=page_num,
                    title_found=fn_title,
                    text_content=text,
                    footnote_number=fn_number,
                )
            )

        return candidates
