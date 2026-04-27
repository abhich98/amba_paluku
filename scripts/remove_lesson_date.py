"""Remove all generated lesson artifacts for a specific date.

Usage:
    uv run scripts/remove_lesson_date.py --date 2026-04-28
    uv run scripts/remove_lesson_date.py --date 2026-04-28 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schema.lesson_schema import validate_manifest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("remove_lesson_date")

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
LESSONS_DIR = DATA_DIR / "lessons"
AUDIO_DIR = DATA_DIR / "audio"
MANIFEST_PATH = DATA_DIR / "manifest.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove lesson JSON, audio assets, and manifest entry for a date."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Date to remove in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without writing changes.",
    )
    return parser.parse_args()


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"updated_at": "", "lessons": []}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _save_manifest(manifest: dict[str, Any]) -> None:
    validate_manifest(manifest)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _remove_for_date(date_str: str, dry_run: bool) -> None:
    lesson_file = LESSONS_DIR / f"{date_str}.json"
    audio_dir = AUDIO_DIR / date_str

    manifest = _load_manifest()
    lessons = manifest.get("lessons", [])
    remaining = [entry for entry in lessons if entry.get("date") != date_str]
    removed_entries = len(lessons) - len(remaining)

    if lesson_file.exists():
        if dry_run:
            logger.info("[dry-run] Would delete lesson file: %s", lesson_file)
        else:
            lesson_file.unlink()
            logger.info("Deleted lesson file: %s", lesson_file)
    else:
        logger.info("Lesson file not found (skipping): %s", lesson_file)

    if audio_dir.exists():
        if dry_run:
            logger.info("[dry-run] Would delete audio directory: %s", audio_dir)
        else:
            shutil.rmtree(audio_dir)
            logger.info("Deleted audio directory: %s", audio_dir)
    else:
        logger.info("Audio directory not found (skipping): %s", audio_dir)

    if removed_entries > 0:
        if dry_run:
            logger.info("[dry-run] Would remove %d manifest entr(y/ies)", removed_entries)
        else:
            manifest["lessons"] = remaining
            manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_manifest(manifest)
            logger.info("Removed %d manifest entr(y/ies)", removed_entries)
    else:
        logger.info("No manifest entries found for date %s", date_str)


def main() -> None:
    args = _parse_args()
    _remove_for_date(args.date, args.dry_run)


if __name__ == "__main__":
    main()
