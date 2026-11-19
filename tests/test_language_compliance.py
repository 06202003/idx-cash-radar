"""
Language Linter & Legal Compliance Automated Test.
Strictly enforces Section 10 of AGENTS.md:
Scans all templates, bot messages, and renderers to ensure zero blacklisted accusatory terms.
"""

from __future__ import annotations

from pathlib import Path

# Blacklist of prohibited words mandated in Section 10 of AGENTS.md
BLACKLISTED_WORDS = [
    "manipulasi",
    "window dressing",
    "laporan palsu",
    "saham gorengan",
    "penipuan",
    "fraud",
    "bangkrut",
    "rekayasa laba",
    "rekomendasi beli",
    "rekomendasi jual",
    "rawan kejar",
    "momentum sehat",
    "kas prima",
    "layak",
    "skor kelayakan",
    "hindari",
    "peluang",
]

TARGET_DIRS = [
    Path("src/renderer/templates"),
    Path("src/renderer"),
    Path("src/bot"),
]


def test_no_blacklisted_words_in_ui_and_templates() -> None:
    """Verifies that no template or bot string contains any prohibited accusatory words."""
    violations = []

    for target_dir in TARGET_DIRS:
        if not target_dir.exists():
            continue
        for file_path in target_dir.rglob("*"):
            if not file_path.is_file() or file_path.suffix not in (".j2", ".py", ".md", ".txt"):
                continue

            content = file_path.read_text(encoding="utf-8").lower()
            for word in BLACKLISTED_WORDS:
                if word in content:
                    violations.append(
                        f"File: {file_path.name} contains blacklisted word: '{word}'"
                    )

    assert not violations, "Legal compliance violations found:\n" + "\n".join(violations)


def test_external_deck_and_brief_compliance() -> None:
    """Task 7: Verifies rendered deck & brief HTML pass language compliance & revoked-claim checks."""
    import re
    from pathlib import Path
    from src.engine.llm_explainer import check_language_compliance

    root_dir = Path(__file__).resolve().parents[1]
    revoked_phrases = [
        "96.7%",
        "cv acc",
        "self-trained",
        "lie detector",
        "benchmark rekomendasi sektor",
        "100% terlacak",
        "arah berita",
    ]
    targets = [
        root_dir / "docs" / "IDX_Cash_Radar_CoFounder_Deck_ID.html",
        root_dir / "docs" / "IDX_Cash_Radar_Product_Brief_ID.html",
    ]
    for path in targets:
        assert path.exists(), f"Missing generated HTML: {path}"
        raw = path.read_text(encoding="utf-8")
        # Strip HTML tags/styles so we check visible text
        text = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        assert check_language_compliance(text) is True, f"Blacklist hit in {path.name}"
        low = text.lower()
        for phrase in revoked_phrases:
            assert phrase not in low, f"Revoked phrase '{phrase}' still present in {path.name}"
