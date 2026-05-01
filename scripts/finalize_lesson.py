"""
Finalize a draft lesson: generate audio, write pairs to resources, update manifest.

Step 2 of 2 in the lesson creation workflow.

Usage:
    uv run scripts/finalize_lesson.py --date 2026-04-28
    uv run scripts/finalize_lesson.py --date 2026-04-28 --dry-run

Prerequisites:
    - Run generate_daily_lesson.py first to create the draft lesson.
    - Review and correct data/lessons/{date}.json.
    - Then run this script to generate audio and publish to resources/manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from indic_transliteration import sanscript
from indic_transliteration.detect import detect
from indic_transliteration.sanscript import transliterate
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yml"
LANGUAGE_PROPERTIES_PATH = _SCRIPTS_DIR / "schema" / "language_properties.yml"
sys.path.insert(0, str(_SCRIPTS_DIR))

from lesson_builder import iter_sentence_objects
from providers.resource_writer import append_sentence_pairs, append_word_pairs
from providers.speech_generator import get_speech_generator
from schema.lesson_schema import validate_lesson, validate_manifest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("finalize_lesson")

DATA_DIR = REPO_ROOT / "data"
LESSONS_DIR = DATA_DIR / "lessons"
MANIFEST_PATH = DATA_DIR / "manifest.json"
DEFAULT_RESOURCE_DIR = REPO_ROOT / "resources"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
    return data


def _resolve_path(path_str: str) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute():
        return candidate
    repo_relative = REPO_ROOT / candidate
    if repo_relative.exists():
        return repo_relative
    return candidate


def _audio_hash(text: str, pace: float) -> str:
    """Return a 16-char hex hash identifying this (text, voice) combination."""
    key = f"{text}|{pace}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _audio_rel_path(hash_key: str) -> str:
    return f"resources/audio/{hash_key}.mp3"


def _transliterate_text(text: str) -> str:
    return transliterate(text, detect(text), sanscript.IAST)


def _fill_transliterations(
    lesson: dict[str, Any],
    language_props: dict[str, dict[str, bool]],
) -> int:
    """Fill transliteration fields in-place for languages that require transliteration.

    Returns number of sentence objects updated.
    """
    updated = 0
    for item in lesson.get("items", []):
        for sentence in iter_sentence_objects(item):
            language = sentence.get("language", "")
            if not language_props.get(language, {}).get("transliteration"):
                continue
            text = sentence.get("text", "").strip()
            if not text:
                continue
            sentence["transliteration"] = _transliterate_text(text)
            updated += 1
    return updated


def _fill_audio_paths(
    lesson: dict[str, Any],
    language_props: dict[str, dict[str, bool]],
    pace: float,
) -> list[tuple[str, str, str]]:
    """Fill in null audio_path fields in-place and return audio jobs.

    Returns list of (text, hash_key, rel_path) for sentences that need audio.
    """
    jobs: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for item in lesson.get("items", []):
        for sentence in iter_sentence_objects(item):
            language = sentence.get("language", "")
            if not language_props.get(language, {}).get("audio"):
                continue  # language has audio disabled

            text = sentence.get("text", "").strip()
            if not text:
                continue

            hash_key = _audio_hash(text, pace)
            rel_path = _audio_rel_path(hash_key)
            sentence["audio_path"] = rel_path

            if hash_key not in seen:
                seen.add(hash_key)
                jobs.append((text, hash_key, rel_path))

    return jobs


def _extract_sentence_pairs(
    lesson: dict[str, Any],
    reference_lang: str,
    target_lang: str,
) -> list[dict[str, Any]]:
    """Extract sentence pairs (reference + target) from MCQ and fill_blank items."""
    pairs: list[dict[str, Any]] = []
    for item in lesson.get("items", []):
        item_type = item.get("type")
        if item_type == "mcq_bimodal":
            q = item.get("question_sentence", {})
            correct_id = item.get("correct_option_id")
            correct_opt = next(
                (o for o in item.get("options", []) if o.get("id") == correct_id), None
            )
            if q.get("text") and correct_opt:
                pairs.append({
                    reference_lang: q["text"],
                    target_lang: correct_opt["text"],
                    "transliteration": correct_opt.get("transliteration") or "",
                })
        elif item_type == "fill_blank_audio":
            q = item.get("question_sentence", {})
            r = item.get("reference_sentence", {})
            if q.get("text") and r.get("text"):
                pairs.append({
                    reference_lang: q["text"],
                    target_lang: r["text"],
                    "transliteration": r.get("transliteration") or "",
                })
    return pairs


def _extract_word_pairs(
    lesson: dict[str, Any],
    reference_lang: str,
    target_lang: str,
) -> list[dict[str, Any]]:
    """Extract word pairs (reference + target) from match items."""
    pairs: list[dict[str, Any]] = []
    for item in lesson.get("items", []):
        if item.get("type") != "match_audio_text":
            continue
        for prompt in item.get("prompts", []):
            answer = prompt.get("answer_sentence", {})
            p_sent = prompt.get("prompt_sentence", {})
            if answer.get("text") and p_sent.get("text"):
                pairs.append({
                    reference_lang: answer["text"],
                    target_lang: p_sent["text"],
                    "transliteration": p_sent.get("transliteration") or "",
                })
    return pairs


def load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"updated_at": "", "lessons": []}


def save_manifest(manifest: dict[str, Any]) -> None:
    validate_manifest(manifest)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def update_manifest(manifest: dict[str, Any], lesson: dict[str, Any]) -> dict[str, Any]:
    new_entry = {
        "date": lesson["date"],
        "difficulty": lesson["difficulty"],
        "status": lesson.get("status", "draft"),
        "item_count": len(lesson["items"]),
        "path": f"data/lessons/{lesson['date']}.json",
    }
    existing = [e for e in manifest.get("lessons", []) if e["date"] != lesson["date"]]
    existing.append(new_entry)
    existing.sort(key=lambda e: e["date"], reverse=True)
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "lessons": existing,
    }


def load_language_properties(path: Path) -> dict[str, dict[str, bool]]:
    raw = _load_yaml_file(path)
    result: dict[str, dict[str, bool]] = {}
    for language, props in raw.items():
        result[language] = {
            "transliteration": bool(props.get("transliteration")),
            "audio": bool(props.get("audio")),
        }
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate audio for a draft lesson and publish to resources/manifest."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Lesson date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config.yml (used for speech settings and resource_dir).",
    )
    parser.add_argument(
        "--resource-dir",
        dest="resource_dir",
        default=None,
        help="Path to resource files directory. Overrides config.yml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing any files.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()
    args = _parse_args()

    config_path = _resolve_path(args.config)
    config = _load_yaml_file(config_path)

    speech_opts: dict[str, Any] = config.get("speech_opts") or {}
    speech_provider = str(config.get("speech_provider", "sarvam"))
    speaker = str(speech_opts.get("speaker", "anushka"))
    model = str(speech_opts.get("model", "bulbul:v2"))
    pace = float(speech_opts.get("pace", 1.0))

    resource_dir_str = args.resource_dir or config.get("resource_dir", str(DEFAULT_RESOURCE_DIR))
    resource_dir = _resolve_path(str(resource_dir_str))

    language_props = load_language_properties(LANGUAGE_PROPERTIES_PATH)

    lesson_date = args.date
    lesson_path = LESSONS_DIR / f"{lesson_date}.json"
    if not lesson_path.exists():
        raise FileNotFoundError(
            f"Draft lesson not found: {lesson_path}\n"
            f"Run generate_daily_lesson.py --date {lesson_date} first."
        )

    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    difficulty = lesson.get("difficulty", "A1")
    reference_lang = str(lesson.get("reference_lang") or config.get("reference_lang", "english"))
    target_lang = str(lesson.get("target_lang") or config.get("target_lang", "telugu"))
    lesson["status"] = "active"

    logger.info(
        "Finalizing lesson %s (difficulty=%s, %d items)",
        lesson_date,
        difficulty,
        len(lesson.get("items", [])),
    )

    translit_count = _fill_transliterations(lesson, language_props)
    logger.info("Transliteration filled for %d sentence objects", translit_count)

    # Fill in audio_path for every sentence that needs it
    audio_jobs = _fill_audio_paths(lesson, language_props, pace)
    logger.info("Audio jobs: %d unique files to generate", len(audio_jobs))

    # Validate lesson with full (non-text-only) schema now that audio_path is filled
    validate_lesson(lesson)
    logger.info("Lesson schema validation passed")

    if args.dry_run:
        logger.info("Dry run — audio jobs that would be generated:")
        for text, hash_key, rel_path in audio_jobs:
            exists = (REPO_ROOT / rel_path).exists()
            logger.info("  [%s] %s  <- '%s...'", "EXISTS" if exists else "NEW   ", rel_path, text[:50])
        logger.info("Sentence pairs that would be written to resources/%s.md: %d",
                    difficulty, len(_extract_sentence_pairs(lesson, reference_lang, target_lang)))
        logger.info("Word pairs that would be written to resources/%s.md: %d",
                    difficulty, len(_extract_word_pairs(lesson, reference_lang, target_lang)))
        logger.info("Dry run complete — no files written")
        return

    # Generate audio files
    speech_gen = get_speech_generator(
        provider=speech_provider,
        voice=speaker,
        model=model,
        pace=pace,
    )

    generated_count = 0
    skipped_count = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        for text, hash_key, rel_path in audio_jobs:
            final_path = REPO_ROOT / rel_path
            if final_path.exists():
                skipped_count += 1
                logger.debug("Audio exists, skipping: %s", rel_path)
                continue
            tmp_path = tmp_root / f"{hash_key}.mp3"
            speech_gen.generate(text, tmp_path)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp_path, final_path)
            generated_count += 1

    logger.info("Audio: %d generated, %d already existed", generated_count, skipped_count)

    # Write updated lesson JSON (now with audio_path values)
    lesson_path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Lesson updated with audio paths: %s", lesson_path.relative_to(REPO_ROOT))

    # Write pairs to resource files
    sentence_pairs = _extract_sentence_pairs(lesson, reference_lang, target_lang)
    word_pairs = _extract_word_pairs(lesson, reference_lang, target_lang)
    s_added = append_sentence_pairs(
        difficulty, sentence_pairs, resource_dir,
        reference_lang=reference_lang, target_lang=target_lang,
    )
    w_added = append_word_pairs(
        difficulty, word_pairs, resource_dir,
        reference_lang=reference_lang, target_lang=target_lang,
    )
    logger.info(
        "Resources: +%d sentence pairs, +%d word pairs written to resources/%s.md",
        s_added, w_added, difficulty,
    )

    # Update manifest
    manifest = load_manifest()
    updated_manifest = update_manifest(manifest, lesson)
    save_manifest(updated_manifest)
    logger.info("Manifest updated: %s", MANIFEST_PATH.relative_to(REPO_ROOT))

    logger.info(
        "Done — lesson %s finalized and published (status=active): %s",
        lesson_date,
        lesson_path.relative_to(REPO_ROOT),
    )


if __name__ == "__main__":
    main()
