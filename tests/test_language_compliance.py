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
