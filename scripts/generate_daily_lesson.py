"""
Daily lesson generator — main orchestration script.

Usage (local):
    uv run scripts/generate_daily_lesson.py
    uv run scripts/generate_daily_lesson.py --config config.yml --date 2026-04-25
    uv run scripts/generate_daily_lesson.py --dry-run

Step 1 of 2: generates text content only.  No audio is produced here.
After human review, run finalize_lesson.py to generate audio and publish.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import yaml

# ---------------------------------------------------------------------------
# Resolve paths and make sibling packages importable
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yml"
LANGUAGE_PROPERTIES_PATH = _SCRIPTS_DIR / "schema" / "language_properties.yml"
sys.path.insert(0, str(_SCRIPTS_DIR))

from lesson_builder import (
    build_lesson,
    sample_question_types,
)
from providers.resource_loader import load_sentence_pairs, load_word_pairs
from providers.text_generator import (
    MATCH_WORD_PROMPT_VERSION,
    SENTENCE_PROMPT_VERSION,
    get_text_generator,
)
from schema.lesson_schema import validate_lesson

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("generate_daily_lesson")

PROMPT_VERSIONS = {
    "mcq_bimodal": SENTENCE_PROMPT_VERSION,
    "fill_blank_audio": SENTENCE_PROMPT_VERSION,
    "match_audio_text": MATCH_WORD_PROMPT_VERSION,
}

DEFAULT_QUESTION_TYPE_WEIGHTS: dict[str, float] = {
    "mcq_bimodal": 0.55,
    "fill_blank_audio": 0.30,
    "match_audio_text": 0.15,
}

DATA_DIR = REPO_ROOT / "data"
LESSONS_DIR = DATA_DIR / "lessons"
DEFAULT_RESOURCE_DIR = REPO_ROOT / "resources"
DEFAULT_RESOURCE_REUSE_PCT = 0.20


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _resolve_path(path_str: str) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute():
        return candidate
    repo_relative = REPO_ROOT / candidate
    if repo_relative.exists():
        return repo_relative
    return candidate


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}, got {type(data).__name__}")
    return data


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a draft daily lesson (JSON only).")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to a YML config file with generation parameters.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Lesson date in YYYY-MM-DD format. Overrides config.yml.",
    )
    parser.add_argument(
        "--reference-lang",
        dest="reference_lang",
        default=None,
        help="Language used as the reference side for generation.",
    )
    parser.add_argument(
        "--target-lang",
        dest="target_lang",
        default=None,
        help="Language the learner is studying.",
    )
    parser.add_argument(
        "--difficulty",
        default=None,
        choices=["A1", "A2", "B1", "B2", "C1", "C2"],
        help="CEFR difficulty level. Overrides config.yml.",
    )
    parser.add_argument(
        "--num-questions",
        dest="num_questions",
        type=int,
        default=None,
        help="Number of questions in the lesson. Overrides config.yml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate content but do not write any files.",
    )
    parser.add_argument(
        "--resource-dir",
        dest="resource_dir",
        default=None,
        help="Path to resource files directory. Overrides config.yml.",
    )
    parser.add_argument(
        "--resource-reuse-pct",
        dest="resource_reuse_pct",
        type=float,
        default=None,
        help="Fraction of pairs to reuse from resources (0.0–1.0). Overrides config.yml.",
    )
    return parser.parse_args()


def _validate_question_type_weights(weights: dict[str, Any]) -> dict[str, float]:
    required_keys = {"mcq_bimodal", "fill_blank_audio", "match_audio_text"}
    if set(weights.keys()) != required_keys:
        raise ValueError(
            "question_type_weights must contain exactly these keys: "
            "mcq_bimodal, fill_blank_audio, match_audio_text"
        )

    normalized: dict[str, float] = {}
    for q_type, value in weights.items():
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"question_type_weights.{q_type} must be numeric") from exc
        if numeric < 0:
            raise ValueError(f"question_type_weights.{q_type} must be >= 0")
        normalized[q_type] = numeric

    if sum(normalized.values()) <= 0:
        raise ValueError("question_type_weights must sum to a positive value")

    return normalized


def load_effective_config(args: argparse.Namespace) -> dict[str, Any]:
    config_path = _resolve_path(args.config)
    config = _load_yaml_file(config_path)

    overrides = {
        key: value
        for key, value in vars(args).items()
        if key in {"date", "reference_lang", "target_lang", "difficulty", "num_questions",
                   "resource_dir", "resource_reuse_pct"}
        and value is not None
    }

    effective = {**config, **overrides}
    effective["config_path"] = str(config_path)
    effective["dry_run"] = args.dry_run
    if effective.get("date") is None:
        raise ValueError("Lesson date must be specified via --date or config.yml")
    effective.setdefault("reference_lang", "english")
    effective.setdefault("target_lang", "telugu")
    effective.setdefault("difficulty", "A1")
    effective.setdefault("num_questions", 10)
    effective.setdefault("text_provider", "openrouter")
    effective.setdefault(
        "LLM_model",
        os.environ.get("OPENROUTER_MODEL", "google/gemini-3-flash-preview"),
    )
    effective.setdefault("question_type_weights", DEFAULT_QUESTION_TYPE_WEIGHTS)
    effective.setdefault("resource_dir", str(DEFAULT_RESOURCE_DIR))
    effective.setdefault("resource_reuse_pct", DEFAULT_RESOURCE_REUSE_PCT)
    effective.setdefault("topics", [])

    if int(effective["num_questions"]) < 1:
        raise ValueError("num_questions must be at least 1")
    reuse_pct = float(effective["resource_reuse_pct"])
    if not (0.0 <= reuse_pct <= 1.0):
        raise ValueError("resource_reuse_pct must be between 0.0 and 1.0")
    effective["resource_reuse_pct"] = reuse_pct
    if not isinstance(effective.get("topics"), list):
        raise ValueError("topics in config.yml must be a list of strings")

    effective["question_type_weights"] = _validate_question_type_weights(
        effective["question_type_weights"]
    )
    return effective


def load_language_properties(path: Path) -> dict[str, dict[str, bool]]:
    raw = _load_yaml_file(path)
    language_props: dict[str, dict[str, bool]] = {}
    for language, props in raw.items():
        if not isinstance(props, dict):
            raise ValueError(f"Language properties for '{language}' must be a mapping")
        transliteration = props.get("transliteration")
        audio = props.get("audio")
        if not isinstance(transliteration, bool) or not isinstance(audio, bool):
            raise ValueError(
                f"Language '{language}' must define boolean transliteration/audio flags"
            )
        language_props[language] = {
            "transliteration": transliteration,
            "audio": audio,
        }
    return language_props


def validate_effective_config(
    config: dict[str, Any],
    language_props: dict[str, dict[str, bool]],
) -> None:
    reference_lang = config["reference_lang"]
    target_lang = config["target_lang"]
    for language in (reference_lang, target_lang):
        if language not in language_props:
            raise ValueError(
                f"Language '{language}' is not defined in {LANGUAGE_PROPERTIES_PATH}"
            )

    if (
        config["question_type_weights"].get("match_audio_text", 0) > 0
        and not language_props[target_lang]["audio"]
    ):
        raise ValueError(
            "match_audio_text requires audio-enabled prompt sentences, "
            f"but target language '{target_lang}' has audio disabled."
        )


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def _sample_reuse(pairs: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Return a random sample of up to *n* items from *pairs*."""
    import random
    if n <= 0 or not pairs:
        return []
    return random.sample(pairs, min(n, len(pairs)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()
    args = _parse_args()
    config = load_effective_config(args)
    language_props = load_language_properties(LANGUAGE_PROPERTIES_PATH)
    validate_effective_config(config, language_props)

    lesson_date = str(config["date"])
    difficulty = str(config["difficulty"])
    count = int(config["num_questions"])
    dry_run = bool(config["dry_run"])
    text_provider = str(config["text_provider"])
    llm_model = str(config["LLM_model"])
    reference_lang = str(config["reference_lang"])
    target_lang = str(config["target_lang"])
    question_type_weights = config["question_type_weights"]
    resource_dir = _resolve_path(str(config["resource_dir"]))
    reuse_pct = float(config["resource_reuse_pct"])
    topics: list[str] = list(config.get("topics") or [])

    logger.info(
        "Starting generation: date=%s difficulty=%s count=%d dry_run=%s config=%s",
        lesson_date,
        difficulty,
        count,
        dry_run,
        config["config_path"],
    )

    question_sequence = sample_question_types(count, question_type_weights)
    sentence_needed = sum(1 for qtype in question_sequence if qtype in {"mcq_bimodal", "fill_blank_audio"})
    match_questions = sum(1 for qtype in question_sequence if qtype == "match_audio_text")
    match_pairs_needed = match_questions * 3

    text_gen = get_text_generator(
        provider=text_provider,
        model=llm_model,
        reference_lang=reference_lang,
        target_lang=target_lang,
        language_props=language_props,
    )

    # --- Load resource pairs for the current CEFR level ---
    resource_sentence_pairs = load_sentence_pairs(
        difficulty, resource_dir, reference_lang=reference_lang, target_lang=target_lang
    )
    resource_word_pairs = load_word_pairs(
        difficulty, resource_dir, reference_lang=reference_lang, target_lang=target_lang
    )

    # Existing texts used to ask the LLM to avoid duplicates
    existing_target_texts = [p[target_lang] for p in resource_sentence_pairs]
    existing_reference_texts = [p[reference_lang] for p in resource_word_pairs]

    # --- reuse N pairs, generate the rest ---
    n_reuse_s = round(sentence_needed * reuse_pct)
    n_new_s = sentence_needed - n_reuse_s

    must_include_pairs = _sample_reuse(resource_sentence_pairs, n_reuse_s)
    if len(must_include_pairs) < n_reuse_s:
        logger.warning(
            "Requested to reuse %d sentence pairs, but only %d available in resources",
            n_reuse_s,
            len(must_include_pairs),
        )
        n_new_s = sentence_needed - len(must_include_pairs)

    logger.info(
        "Sentence pairs: %d reused from resources, %d new from LLM (total %d)",
        len(must_include_pairs), n_new_s, sentence_needed,
    )

    n_reuse_w = round(match_pairs_needed * reuse_pct)
    n_new_w = match_pairs_needed - n_reuse_w

    reused_word_pairs = _sample_reuse(resource_word_pairs, n_reuse_w)
    if len(reused_word_pairs) < n_reuse_w:
        logger.warning(
            "Requested to reuse %d word pairs, but only %d available in resources",
            n_reuse_w,
            len(reused_word_pairs),
        )
        n_new_w = match_pairs_needed - len(reused_word_pairs)
    logger.info(
        "Word pairs: %d reused from resources, %d new from LLM (total %d)",
        len(reused_word_pairs), n_new_w, match_pairs_needed,
    )

    sentence_pairs: list[dict[str, Any]] = []
    if sentence_needed > 0:
        sentence_pairs = text_gen.generate_sentence_pairs(
            count=sentence_needed,
            difficulty=difficulty,
            existing_sentences=existing_target_texts or None,
            must_include_pairs=must_include_pairs or None,
            topics=topics or None,
        )

    match_pairs: list[dict[str, Any]] = []
    if n_new_w > 0:
        match_pairs = text_gen.generate_match_word_pairs(
            count=n_new_w,
            difficulty=difficulty,
            existing_sentences=existing_reference_texts or None,
            topics=topics or None,
        )
    match_pairs = reused_word_pairs + match_pairs

    lesson = build_lesson(
        lesson_date=lesson_date,
        question_types=question_sequence,
        sentence_pairs=sentence_pairs,
        match_pairs=match_pairs,
        difficulty=difficulty,
        model=llm_model,
        provider=text_provider,
        prompt_versions=PROMPT_VERSIONS,
        question_type_weights=question_type_weights,
        reference_lang=reference_lang,
        target_lang=target_lang,
        language_props=language_props,
    )
    validate_lesson(lesson, text_only=True)
    logger.info("Lesson schema validation passed (%d items)", len(lesson["items"]))
    logger.info("Question type counts: %s", lesson.get("question_type_counts", {}))

    if dry_run:
        print(json.dumps(lesson, ensure_ascii=False, indent=2))
        logger.info("Dry run complete — no files written")
        return

    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    final_lesson_path = LESSONS_DIR / f"{lesson_date}.json"
    final_lesson_path.write_text(
        json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Draft lesson written: %s", final_lesson_path.relative_to(REPO_ROOT))
    logger.info(
        "Done — review and correct %s, then run: "
        "uv run scripts/finalize_lesson.py --date %s",
        final_lesson_path.relative_to(REPO_ROOT),
        lesson_date,
    )


if __name__ == "__main__":
    main()
