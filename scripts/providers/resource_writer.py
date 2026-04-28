"""Append new sentence and word pairs to per-level Markdown resource files.

Creates the file and section if they don't exist yet.
Deduplicates by the reference language value before appending.

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

logger = logging.getLogger(__name__)

_SECTION_SENTENCE = "Sentence Pairs"
_SECTION_WORD = "Word Pairs"


def _table_header(reference_lang: str, target_lang: str) -> str:
    ref_sep = "-" * max(len(reference_lang), 7)
    tgt_sep = "-" * max(len(target_lang), 6)
    return (
        f"| {reference_lang} | {target_lang} | transliteration |\n"
        f"|{ref_sep}|{tgt_sep}|-----------------|"
    )


def _existing_reference_keys(text: str, section_title: str, reference_lang: str) -> set[str]:
    """Return the lowercased reference-language values already stored in *section_title*."""
    pattern = rf"##\s+{re.escape(section_title)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return set()

    keys: set[str] = set()
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or not line.startswith("|") or all(c in "-|: " for c in line):
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        if cells and cells[0] and cells[0].lower() != reference_lang.lower():
            keys.add(cells[0].lower())
    return keys


def _append_rows_to_section(
    path: Path,
    section_title: str,
    rows: list[tuple[str, str, str]],
    reference_lang: str,
    target_lang: str,
) -> int:
    """Append *rows* to the given section, creating file/section as needed.

    Returns the number of rows actually written (after deduplication).
    """
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    existing_keys = _existing_reference_keys(text, section_title, reference_lang)
    new_rows = [r for r in rows if r[0].lower() not in existing_keys]
    if not new_rows:
        return 0

    new_lines = "\n".join(f"| {e} | {t} | {tr} |" for e, t, tr in new_rows)

    section_pattern = rf"(##\s+{re.escape(section_title)}\s*\n)(.*?)(?=\n##\s|\Z)"
    section_match = re.search(section_pattern, text, re.DOTALL)

    if section_match:
        # Append to the existing section body
        before = text[: section_match.end()].rstrip()
        after = text[section_match.end():]
        text = before + "\n" + new_lines + "\n" + after
    else:
        # Create a brand-new section at the end of the file
        if text and not text.endswith("\n"):
            text += "\n"
        header = _table_header(reference_lang, target_lang)
        text += f"\n## {section_title}\n\n{header}\n{new_lines}\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return len(new_rows)


def append_sentence_pairs(
    level: str,
    pairs: list[dict[str, Any]],
    resource_dir: str | Path,
    reference_lang: str = "english",
    target_lang: str = "telugu",
) -> int:
    """Append sentence pairs to resources/{level}.md.

    Skips pairs whose reference-language text already exists in the file.
    Returns the number of new rows written.
    """
    path = Path(resource_dir) / f"{level}.md"
    rows = [
        (p[reference_lang], p[target_lang], p.get("transliteration") or "")
        for p in pairs
        if p.get(reference_lang) and p.get(target_lang)
    ]
    count = _append_rows_to_section(path, _SECTION_SENTENCE, rows, reference_lang, target_lang)
    logger.info("Appended %d/%d sentence pairs to %s", count, len(pairs), path.name)
    return count


def append_word_pairs(
    level: str,
    pairs: list[dict[str, Any]],
    resource_dir: str | Path,
    reference_lang: str = "english",
    target_lang: str = "telugu",
) -> int:
    """Append word pairs to resources/{level}.md.

    Skips pairs whose reference-language text already exists in the file.
    Returns the number of new rows written.
    """
    path = Path(resource_dir) / f"{level}.md"
    rows = [
        (p[reference_lang], p[target_lang], p.get("transliteration") or "")
        for p in pairs
        if p.get(reference_lang) and p.get(target_lang)
    ]
    count = _append_rows_to_section(path, _SECTION_WORD, rows, reference_lang, target_lang)
    logger.info("Appended %d/%d word pairs to %s", count, len(pairs), path.name)
    return count
