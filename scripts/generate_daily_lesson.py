"""
Daily English-Telugu lesson generator — main orchestration script.

Usage (local):
    uv run scripts/generate_daily_lesson.py
    uv run scripts/generate_daily_lesson.py --date 2026-04-25 --difficulty A2 --count 10
    uv run scripts/generate_daily_lesson.py --dry-run   # validate only, no files written

The script:
  1. Loads config from .env / environment variables.
  2. Reads the existing manifest to gather used Telugu phrases.
  3. Calls the text provider (OpenRouter) to generate sentence pairs.
  4. Validates the pairs and assembles the lesson dict.
  5. Calls the speech provider (Sarvam) to generate per-item audio,
     staging output in a temp directory first.
  6. Atomically copies staged files to data/lessons/ and data/audio/.
  7. Updates data/manifest.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import shutil
import sys
import tempfile
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Resolve paths and make sibling packages importable
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from providers.speech_generator import get_speech_generator, item_audio_filename
from providers.text_generator import get_text_generator
from schema.lesson_schema import validate_lesson, validate_manifest

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("generate_daily_lesson")

# ---------------------------------------------------------------------------
# Stable config
# ---------------------------------------------------------------------------

PROMPT_VERSION = "1.0"

QUESTION_TYPE_WEIGHTS: dict[str, float] = {
    "mcq_bimodal": 0.55,
    "fill_blank_audio": 0.30,
    "match_audio_text": 0.15,
}

DATA_DIR = REPO_ROOT / "data"
LESSONS_DIR = DATA_DIR / "lessons"
AUDIO_DIR = DATA_DIR / "audio"
MANIFEST_PATH = DATA_DIR / "manifest.json"


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"updated_at": "", "lessons": []}


def _load_existing_english(manifest: dict) -> list[str]:
    """Return all English sentences from previously committed lessons.

    Silently skips lesson files that are missing (e.g. fresh clone without data/).
    """
    result: list[str] = []
    for entry in manifest.get("lessons", []):
        lesson_path = REPO_ROOT / entry["path"]
        if not lesson_path.exists():
            logger.debug("Lesson file not found on disk, skipping: %s", lesson_path)
            continue
        try:
            lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
            result.extend(item["english"] for item in lesson.get("items", []))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Could not read existing lesson %s: %s", lesson_path, exc)
    return result


def _load_existing_telugu(manifest: dict) -> list[str]:
    """Return all Telugu sentences from previously committed lessons.

    Silently skips lesson files that are missing (e.g. fresh clone without data/).
    """
    result: list[str] = []
    for entry in manifest.get("lessons", []):
        lesson_path = REPO_ROOT / entry["path"]
        if not lesson_path.exists():
            logger.debug("Lesson file not found on disk, skipping: %s", lesson_path)
            continue
        try:
            lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
            result.extend(item["telugu"] for item in lesson.get("items", []))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Could not read existing lesson %s: %s", lesson_path, exc)
    return result


def save_manifest(manifest: dict, dest: Path) -> None:
    validate_manifest(manifest)
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def update_manifest(manifest: dict, lesson: dict) -> dict:
    """Insert or replace the manifest entry for the lesson's date (sorted desc)."""
    new_entry = {
        "date": lesson["date"],
        "difficulty": lesson["difficulty"],
        "item_count": len(lesson["items"]),
        "path": f"data/lessons/{lesson['date']}.json",
    }
    # Replace existing entry for the same date if present
    existing = [e for e in manifest.get("lessons", []) if e["date"] != lesson["date"]]
    existing.append(new_entry)
    existing.sort(key=lambda e: e["date"], reverse=True)
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "lessons": existing,
    }


# ---------------------------------------------------------------------------
# Lesson assembly
# ---------------------------------------------------------------------------


def build_lesson(
    lesson_date: str,
    num_questions: int,
    difficulty: str,
    pairs: list[dict],
    model: str,
    provider: str,
) -> dict:
    """Assemble a weighted multi-type lesson dict from raw LLM pairs."""

    def split_english_words(sentence: str) -> list[str]:
        return sentence.split()

    def sanitize_english_answer(word: str) -> str:
        return word.strip(".,!?;:'\"()[]{}")

    def sanitize_translit_answer(word: str) -> str:
        return word.strip(".,!?;:'\"()[]{}")

    def normalize_translit_answer(word: str) -> str:
        stripped = sanitize_translit_answer(word)
        normalized = unicodedata.normalize("NFKD", stripped)
        without_diacritics = "".join(c for c in normalized if not unicodedata.combining(c))
        simplified = re.sub(r"[^a-zA-Z0-9\s]", " ", without_diacritics)
        return re.sub(r"\s+", " ", simplified).strip().lower()

    def pick_omit_loc(words: list[str]) -> int:
        candidate_indexes = [
            idx for idx, word in enumerate(words)
            if sanitize_english_answer(word) and len(sanitize_english_answer(word)) > 2
        ]
        if not candidate_indexes:
            candidate_indexes = [idx for idx, word in enumerate(words) if sanitize_english_answer(word)]
        if not candidate_indexes:
            raise ValueError("Cannot build fill-in-the-blank from an empty English sentence")
        return random.choice(candidate_indexes) + 1

    def audio_rel_path(stem: str) -> str:
        return f"data/audio/{lesson_date}/{item_audio_filename(stem)}"

    def build_mcq(item_id: str, pair: dict) -> dict:
        options = [
            {
                "id": f"{item_id}_opt0",
                "transliteration": pair["transliteration"],
                "telugu": pair["telugu"],
                "audio_path": audio_rel_path(f"{item_id}_opt0"),
            }
        ]
        for d_idx, distractor in enumerate(pair["distractors"], start=1):
            options.append(
                {
                    "id": f"{item_id}_opt{d_idx}",
                    "transliteration": distractor["transliteration"],
                    "telugu": distractor["telugu"],
                    "audio_path": audio_rel_path(f"{item_id}_opt{d_idx}"),
                }
            )

        random.shuffle(options)
        correct_option_id = next(opt["id"] for opt in options if opt["telugu"] == pair["telugu"])
        return {
            "id": item_id,
            "type": "mcq_bimodal",
            "sentence_english": pair["english"],
            "options": options,
            "correct_option_id": correct_option_id,
        }

    def build_fill_blank(item_id: str, pair: dict) -> dict:
        reference_transliteration = pair["transliteration"].strip()
        telugu_mode = random.random() < 0.5

        if telugu_mode:
            question_language = "telugu_transliteration"
            question_sentence = reference_transliteration
            reference_sentence = pair["english"]
            words = question_sentence.split()
            omit_loc = pick_omit_loc(words)
            omitted_word = words[omit_loc - 1]
            sanitized_answer = sanitize_translit_answer(omitted_word)
            normalized_answer = normalize_translit_answer(omitted_word)
            answer_mode = "transliteration"
            accepted_answers = [omitted_word]
            for extra in [sanitized_answer, normalized_answer]:
                if extra and extra not in accepted_answers:
                    accepted_answers.append(extra)
            display_correct_answer = sanitized_answer or omitted_word
        else:
            question_language = "english"
            question_sentence = pair["english"]
            reference_sentence = pair["telugu"]
            words = split_english_words(question_sentence)
            omit_loc = pick_omit_loc(words)
            omitted_word = words[omit_loc - 1]
            sanitized_answer = sanitize_english_answer(omitted_word)
            answer_mode = "english"
            accepted_answers = [omitted_word]
            if sanitized_answer and sanitized_answer != omitted_word:
                accepted_answers.append(sanitized_answer)
            display_correct_answer = sanitized_answer or omitted_word

        return {
            "id": item_id,
            "type": "fill_blank_audio",
            "question_language": question_language,
            "question_sentence": question_sentence,
            "reference_sentence": reference_sentence,
            "answer_mode": answer_mode,
            "reference_transliteration": reference_transliteration,
            "reference_telugu": pair["telugu"],
            "omit_loc": omit_loc,
            "audio_path": audio_rel_path(item_id),
            "accepted_answers": accepted_answers,
            "display_correct_answer": display_correct_answer,
        }

    def build_match(item_id: str, chunk: list[dict]) -> dict:
        prompts = []
        for m_idx, pair in enumerate(chunk, start=1):
            prompts.append(
                {
                    "id": f"{item_id}_p{m_idx}",
                    "reference_transliteration": pair["transliteration"],
                    "reference_telugu": pair["telugu"],
                    "audio_path": audio_rel_path(f"{item_id}_p{m_idx}"),
                    "correct_english": pair["english"],
                }
            )
        english_options = [p["correct_english"] for p in prompts]
        random.shuffle(english_options)
        return {
            "id": item_id,
            "type": "match_audio_text",
            "prompts": prompts,
            "english_options": english_options,
        }

    items: list[dict] = []
    q_types = list(QUESTION_TYPE_WEIGHTS.keys())
    q_probs = list(QUESTION_TYPE_WEIGHTS.values())
    q_probs = [w / sum(q_probs) for w in q_probs]
    lesson_q_types = random.choices(population=q_types, weights=q_probs, k=num_questions)

    for i in range(num_questions):
        qtype = lesson_q_types[i]
        if qtype == "match_audio_text":
            chunk = [pairs[i] for i in random.sample(range(len(pairs)), k=3)]
            items.append(build_match(f"{lesson_date}_{i+1:03d}", chunk))

        elif qtype == "fill_blank_audio":
            items.append(build_fill_blank(f"{lesson_date}_{i+1:03d}", pairs[i]))

        else:
            items.append(build_mcq(f"{lesson_date}_{i+1:03d}", pairs[i]))

    question_type_counts = {
        "mcq_bimodal": sum(1 for item in items if item["type"] == "mcq_bimodal"),
        "fill_blank_audio": sum(1 for item in items if item["type"] == "fill_blank_audio"),
        "match_audio_text": sum(1 for item in items if item["type"] == "match_audio_text"),
    }

    return {
        "lesson_id": lesson_date,
        "date": lesson_date,
        "difficulty": difficulty,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "question_type_weights": QUESTION_TYPE_WEIGHTS,
        "question_type_counts": question_type_counts,
        "items": items,
    }


def collect_audio_jobs(lesson: dict, repo_root: Path) -> list[tuple[str, Path]]:
    """Collect unique (text, path) audio jobs from lesson items.

    Audio remains optional for many fields. Only non-null audio paths are emitted.
    """
    jobs: dict[Path, str] = {}
    for item in lesson["items"]:
        if item["type"] == "mcq_bimodal":
            for option in item["options"]:
                audio_path = option.get("audio_path")
                if audio_path:
                    jobs[repo_root / audio_path] = option["telugu"]
        elif item["type"] == "fill_blank_audio":
            audio_path = item.get("audio_path")
            if audio_path:
                jobs[repo_root / audio_path] = item["reference_telugu"]
        elif item["type"] == "match_audio_text":
            for prompt in item["prompts"]:
                audio_path = prompt.get("audio_path")
                if audio_path:
                    jobs[repo_root / audio_path] = prompt["reference_telugu"]

    return [(text, path) for path, text in jobs.items()]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Generate a daily English-Telugu lesson (JSON + MP3)."
    )
    parser.add_argument(
        "--date",
        default=str(date.today()),
        help="Lesson date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--difficulty",
        default="A1",
        choices=["A1", "A2", "B1", "B2", "C1", "C2"],
        help="CEFR difficulty level (default: A1)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of questions in the lesson (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate content but do not write any files",
    )
    args = parser.parse_args()

    lesson_date: str = args.date
    difficulty: str = args.difficulty
    count: int = args.count
    dry_run: bool = args.dry_run

    logger.info(
        "Starting generation: date=%s difficulty=%s count=%d dry_run=%s",
        lesson_date,
        difficulty,
        count,
        dry_run,
    )

    # ------------------------------------------------------------------
    # Phase A: Text generation
    # ------------------------------------------------------------------
    text_gen = get_text_generator()
    manifest = load_manifest()
    existing_sentences = _load_existing_telugu(manifest)

    if existing_sentences:
        logger.info(
            "Loaded %d existing Telugu phrases to avoid duplicates", len(existing_sentences)
        )

    pairs = text_gen.generate_pairs(
        count=count,
        difficulty=difficulty,
        existing_sentences=existing_sentences or None,
    )

    # ------------------------------------------------------------------
    # Phase B: Build and validate lesson
    # ------------------------------------------------------------------
    model = os.environ.get("OPENROUTER_MODEL", "google/gemini-3-flash-preview")
    lesson = build_lesson(
        lesson_date=lesson_date,
        num_questions=count,
        difficulty=difficulty,
        pairs=pairs,
        model=model,
        provider="openrouter",
    )
    validate_lesson(lesson)
    logger.info("Lesson schema validation passed (%d items)", len(lesson["items"]))
    logger.info("Question type counts: %s", lesson.get("question_type_counts", {}))

    if dry_run:
        print(json.dumps(lesson, ensure_ascii=False, indent=2))
        logger.info("Dry run complete — no files written")
        return

    # ------------------------------------------------------------------
    # Phase C: Audio generation (staged to a temp dir)
    # ------------------------------------------------------------------
    speech_gen = get_speech_generator()
    generated_count = 0
    skipped_count = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        tmp_lesson_file = tmp_root / f"{lesson_date}.json"

        audio_jobs = collect_audio_jobs(lesson, REPO_ROOT)
        for telugu_text, final_audio_path in audio_jobs:
            if final_audio_path.exists():
                skipped_count += 1
                logger.debug("Audio exists, skipping: %s", final_audio_path.name)
                continue

            tmp_audio_path = tmp_root / final_audio_path.relative_to(REPO_ROOT)
            tmp_audio_path.parent.mkdir(parents=True, exist_ok=True)
            speech_gen.generate(telugu_text, tmp_audio_path)
            generated_count += 1

        # Write lesson JSON into staging area
        tmp_lesson_file.write_text(
            json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ------------------------------------------------------------------
        # Phase D: Atomic publish — copy from temp to final destinations
        # ------------------------------------------------------------------
        LESSONS_DIR.mkdir(parents=True, exist_ok=True)
        final_lesson_path = LESSONS_DIR / f"{lesson_date}.json"
        shutil.copy2(tmp_lesson_file, final_lesson_path)
        logger.info("Lesson written: %s", final_lesson_path.relative_to(REPO_ROOT))

        if generated_count > 0:
            staged_day_dir = tmp_root / "data" / "audio" / lesson_date
            if staged_day_dir.exists():
                final_audio_day_dir = AUDIO_DIR / lesson_date
                final_audio_day_dir.mkdir(parents=True, exist_ok=True)
                for audio_file in staged_day_dir.iterdir():
                    shutil.copy2(audio_file, final_audio_day_dir / audio_file.name)
            logger.info(
                "Audio written: %d new, %d skipped", generated_count, skipped_count
            )
        else:
            logger.info("Audio: all %d files already existed", skipped_count)

    # ------------------------------------------------------------------
    # Phase E: Update manifest
    # ------------------------------------------------------------------
    updated_manifest = update_manifest(manifest, lesson)
    save_manifest(updated_manifest, MANIFEST_PATH)
    logger.info("Manifest updated: %s", MANIFEST_PATH.relative_to(REPO_ROOT))

    logger.info(
        "Done — lesson %s: %d items, %d new audio files, %d skipped",
        lesson_date,
        count,
        generated_count,
        skipped_count,
    )


if __name__ == "__main__":
    main()
