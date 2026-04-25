"""Lesson and manifest schema definitions and validation helpers.

The lesson JSON file is the integration contract between the Python pipeline and
the SurveyJS-first frontend. Item payloads are type-based so new quiz formats
can be added without changing top-level lesson shape.
"""
from __future__ import annotations

from typing import Any

import jsonschema

# ---------------------------------------------------------------------------
# JSON Schema definitions
# ---------------------------------------------------------------------------

_OPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "transliteration", "telugu"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "transliteration": {"type": "string", "minLength": 1},
        "telugu": {"type": "string", "minLength": 1},
        "audio_path": {"type": ["string", "null"], "minLength": 1},
    },
}

_MCQ_BIMODAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "type", "prompt_english", "options", "correct_option_id"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "mcq_bimodal"},
        "prompt_english": {"type": "string", "minLength": 1},
        "options": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": _OPTION_SCHEMA,
        },
        "correct_option_id": {"type": "string", "minLength": 1},
    },
}

_FILL_BLANK_AUDIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "id",
        "type",
        "prompt_english",
        "reference_transliteration",
        "reference_telugu",
        "audio_path",
        "accepted_answers",
        "display_correct_answer",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "fill_blank_audio"},
        "prompt_english": {"type": "string", "minLength": 1},
        "reference_transliteration": {"type": "string", "minLength": 1},
        "reference_telugu": {"type": "string", "minLength": 1},
        "audio_path": {"type": ["string", "null"], "minLength": 1},
        "accepted_answers": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "display_correct_answer": {"type": "string", "minLength": 1},
    },
}

_MATCH_PROMPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "id",
        "reference_transliteration",
        "reference_telugu",
        "audio_path",
        "correct_english",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "reference_transliteration": {"type": "string", "minLength": 1},
        "reference_telugu": {"type": "string", "minLength": 1},
        "audio_path": {"type": ["string", "null"], "minLength": 1},
        "correct_english": {"type": "string", "minLength": 1},
    },
}

_MATCH_AUDIO_TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "type", "prompts", "english_options"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "match_audio_text"},
        "prompts": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": _MATCH_PROMPT_SCHEMA,
        },
        "english_options": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {"type": "string", "minLength": 1},
        },
    },
}


LESSON_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": [
        "lesson_id",
        "date",
        "difficulty",
        "generated_at",
        "provider",
        "model",
        "prompt_version",
        "items",
    ],
    "additionalProperties": False,
    "properties": {
        "lesson_id": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "difficulty": {
            "type": "string",
            "enum": ["A1", "A2", "B1", "B2", "C1", "C2"],
        },
        "generated_at": {"type": "string", "minLength": 1},
        "provider": {"type": "string", "minLength": 1},
        "model": {"type": "string", "minLength": 1},
        "prompt_version": {"type": "string", "minLength": 1},
        "question_type_weights": {
            "type": "object",
            "required": ["mcq_bimodal", "fill_blank_audio", "match_audio_text"],
            "additionalProperties": False,
            "properties": {
                "mcq_bimodal": {"type": "number", "minimum": 0},
                "fill_blank_audio": {"type": "number", "minimum": 0},
                "match_audio_text": {"type": "number", "minimum": 0},
            },
        },
        "items": {
            "type": "array",
            "minItems": 1,
            "items": {
                "oneOf": [
                    _MCQ_BIMODAL_SCHEMA,
                    _FILL_BLANK_AUDIO_SCHEMA,
                    _MATCH_AUDIO_TEXT_SCHEMA,
                ]
            },
        },
    },
}

MANIFEST_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["updated_at", "lessons"],
    "additionalProperties": False,
    "properties": {
        "updated_at": {"type": "string"},
        "lessons": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["date", "difficulty", "item_count", "path"],
                "additionalProperties": False,
                "properties": {
                    "date": {
                        "type": "string",
                        "pattern": r"^\d{4}-\d{2}-\d{2}$",
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["A1", "A2", "B1", "B2", "C1", "C2"],
                    },
                    "item_count": {"type": "integer", "minimum": 1},
                    "path": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _contains_telugu_script(text: str) -> bool:
    return any("\u0C00" <= c <= "\u0C7F" for c in text)


def validate_lesson(lesson: dict[str, Any]) -> None:
    """Validate a lesson dict against LESSON_SCHEMA.

    Raises jsonschema.ValidationError with a human-readable message on failure.
    """
    jsonschema.validate(instance=lesson, schema=LESSON_SCHEMA)

    # Cross-validate type-specific invariants.
    for item in lesson.get("items", []):
        item_type = item.get("type")
        item_id = item.get("id")

        if item_type == "mcq_bimodal":
            options = item.get("options", [])
            option_ids = [opt["id"] for opt in options]
            if len(option_ids) != len(set(option_ids)):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': option ids must be unique"
                )
            if item.get("correct_option_id") not in option_ids:
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': correct_option_id must match one option id"
                )
            for opt in options:
                if not _contains_telugu_script(opt["telugu"]):
                    raise jsonschema.ValidationError(
                        f"Item '{item_id}': option '{opt['id']}' telugu must contain "
                        "Telugu script characters"
                    )

        if item_type == "fill_blank_audio":
            if not _contains_telugu_script(item["reference_telugu"]):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': reference_telugu must contain Telugu script "
                    "characters"
                )

        if item_type == "match_audio_text":
            prompts = item.get("prompts", [])
            english_options = item.get("english_options", [])
            if len(english_options) != len(set(english_options)):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': english_options must be unique"
                )
            prompt_ids = [p["id"] for p in prompts]
            if len(prompt_ids) != len(set(prompt_ids)):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': prompt ids must be unique"
                )
            for prompt in prompts:
                if prompt["correct_english"] not in english_options:
                    raise jsonschema.ValidationError(
                        f"Item '{item_id}': prompt '{prompt['id']}' has correct_english "
                        "not present in english_options"
                    )
                if not _contains_telugu_script(prompt["reference_telugu"]):
                    raise jsonschema.ValidationError(
                        f"Item '{item_id}': prompt '{prompt['id']}' reference_telugu "
                        "must contain Telugu script characters"
                    )


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate a manifest dict against MANIFEST_SCHEMA.

    Raises jsonschema.ValidationError on failure.
    """
    jsonschema.validate(instance=manifest, schema=MANIFEST_SCHEMA)
