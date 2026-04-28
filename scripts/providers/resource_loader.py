"""Load sentence and word pairs from per-level Markdown resource files.

Resource file format (resources/{LEVEL}.md):

    ## Sentence Pairs

    | english | telugu | transliteration |
    |---------|--------|-----------------|
    | The cat is on the mat. | పిల్లి చాపమీద ఉంది. | pillI cApamlda uMdi. |

    ## Word Pairs

    | english | telugu | transliteration |
    |---------|--------|-----------------|
    | water | నీరు | nIru |
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from indic_transliteration import sanscript
from indic_transliteration.detect import detect
from indic_transliteration.sanscript import transliterate

logger = logging.getLogger(__name__)


def _transliterate(text: str) -> str:
    try:
        return transliterate(text, detect(text), sanscript.IAST)
    except Exception:
        return text


def _parse_md_table(text: str, section_title: str) -> list[list[str]]:
    """Return data rows (excluding the header row) from a Markdown table under *section_title*."""
    pattern = rf"##\s+{re.escape(section_title)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return []

    rows: list[list[str]] = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        # Skip separator rows like |---|---|---|
        if all(c in "-|: " for c in line):
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        rows.append(cells)

    # First row is the header — drop it
    return rows[1:] if len(rows) > 1 else []


def _load_pairs(
    level: str,
    resource_dir: str | Path,
    section_title: str,
    reference_lang: str,
    target_lang: str,
) -> list[dict[str, Any]]:
    path = Path(resource_dir) / f"{level}.md"
    if not path.exists():
        logger.debug("Resource file not found, returning empty: %s", path)
        return []

    text = path.read_text(encoding="utf-8")
    rows = _parse_md_table(text, section_title)

    pairs: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < 2:
            continue
        reference = row[0].strip()
        target = row[1].strip()
        if not reference or not target:
            continue
        transliteration = row[2].strip() if len(row) > 2 and row[2].strip() else _transliterate(target)
        pairs.append({reference_lang: reference, target_lang: target, "transliteration": transliteration})

    return pairs


def load_sentence_pairs(
    level: str,
    resource_dir: str | Path,
    reference_lang: str = "english",
    target_lang: str = "telugu",
) -> list[dict[str, Any]]:
    """Load sentence pairs from resources/{level}.md.

    Returns a list of ``{reference_lang: ..., target_lang: ..., "transliteration": ...}`` dicts.
    Returns ``[]`` if the file or section is missing.
    """
    pairs = _load_pairs(level, resource_dir, "Sentence Pairs", reference_lang, target_lang)
    logger.info("Loaded %d sentence pairs for level %s from resources", len(pairs), level)
    return pairs


def load_word_pairs(
    level: str,
    resource_dir: str | Path,
    reference_lang: str = "english",
    target_lang: str = "telugu",
) -> list[dict[str, Any]]:
    """Load word pairs from resources/{level}.md.

    Returns a list of ``{reference_lang: ..., target_lang: ..., "transliteration": ...}`` dicts.
    Returns ``[]`` if the file or section is missing.
    """
    pairs = _load_pairs(level, resource_dir, "Word Pairs", reference_lang, target_lang)
    logger.info("Loaded %d word pairs for level %s from resources", len(pairs), level)
    return pairs
