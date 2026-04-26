"""Lesson and manifest schema definitions and validation helpers.

The lesson JSON file is the integration contract between the Python pipeline and
the SurveyJS-first frontend. Item payloads are type-based so new quiz formats
can be added without changing top-level lesson shape.
"""
from __future__ import annotations

import re
import unicodedata
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
    "required": ["id", "type", "sentence_english", "options", "correct_option_id"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "mcq_bimodal"},
        "sentence_english": {"type": "string", "minLength": 1},
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
        "question_language",
        "question_sentence",
        "reference_sentence",
        "answer_mode",
        "reference_transliteration",
        "reference_telugu",
        "omit_loc",
        "audio_path",
        "accepted_answers",
        "display_correct_answer",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "fill_blank_audio"},
        "question_language": {
            "type": "string",
            "enum": ["english", "telugu_transliteration"],
        },
        "question_sentence": {"type": "string", "minLength": 1},
        "reference_sentence": {"type": "string", "minLength": 1},
        "answer_mode": {
            "type": "string",
            "enum": ["english", "transliteration"],
        },
        "reference_transliteration": {"type": "string", "minLength": 1},
        "reference_telugu": {"type": "string", "minLength": 1},
        "omit_loc": {
            "type": "integer", "minimum": 1, "description": "1-based index of the word to omit in the question sentence"
        },
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
        "question_type_weights",
        "question_type_counts",
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
        "question_type_counts": {
            "type": "object",
            "required": ["mcq_bimodal", "fill_blank_audio", "match_audio_text"],
            "additionalProperties": False,
            "properties": {
                "mcq_bimodal": {"type": "integer", "minimum": 0},
                "fill_blank_audio": {"type": "integer", "minimum": 0},
                "match_audio_text": {"type": "integer", "minimum": 0},
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


def _normalize_english_answer(text: str) -> str:
    return text.strip(".,!?;:'\"()[]{}").strip().lower()


def _normalize_transliteration_answer(text: str) -> str:
    stripped = text.strip(".,!?;:'\"()[]{}").strip()
    normalized = unicodedata.normalize("NFKD", stripped)
    without_diacritics = "".join(c for c in normalized if not unicodedata.combining(c))
    simplified = re.sub(r"[^a-zA-Z0-9\s]", " ", without_diacritics)
    return re.sub(r"\s+", " ", simplified).strip().lower()


def validate_lesson(lesson: dict[str, Any]) -> None:
    """Validate a lesson dict against LESSON_SCHEMA.

    Raises jsonschema.ValidationError with a human-readable message on failure.
    """
    jsonschema.validate(instance=lesson, schema=LESSON_SCHEMA)

    # Cross-validate type-specific invariants.
    actual_counts = {
        "mcq_bimodal": 0,
        "fill_blank_audio": 0,
        "match_audio_text": 0,
    }

    for item in lesson.get("items", []):
        item_type = item.get("type")
        item_id = item.get("id")

        if item_type in actual_counts:
            actual_counts[item_type] += 1

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
            words = item["question_sentence"].split()
            omit_loc = item["omit_loc"]
            if omit_loc > len(words):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': omit_loc must point to a word in question_sentence"
                )
            omitted_word = words[omit_loc - 1]
            if item["question_language"] == "english" and item["answer_mode"] != "english":
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': answer_mode must be 'english' when question_language is 'english'"
                )
            if item["question_language"] == "telugu_transliteration" and item["answer_mode"] != "transliteration":
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': answer_mode must be 'transliteration' when question_language is 'telugu_transliteration'"
                )

            if item["answer_mode"] == "transliteration":
                normalize = _normalize_transliteration_answer
            else:
                normalize = _normalize_english_answer

            normalized_accepted_answers = {
                normalize(answer)
                for answer in item["accepted_answers"]
                if normalize(answer)
            }
            normalized_omitted_word = normalize(omitted_word)
            if normalized_omitted_word not in normalized_accepted_answers:
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': accepted_answers must include the omitted word "
                    "from question_sentence"
                )
            if normalize(item["display_correct_answer"]) != normalized_omitted_word:
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': display_correct_answer must match the omitted word"
                )

        if item_type == "match_audio_text":
            prompts = item.get("prompts", [])
            english_options = item.get("english_options", [])
            if len(english_options) != len(set(english_options)):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': english_options must be unique: {english_options}"
                )
            prompt_ids = [p["id"] for p in prompts]
            if len(prompt_ids) != len(set(prompt_ids)):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': prompt ids must be unique: {prompt_ids}"
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

    declared_counts = lesson.get("question_type_counts", {})
    if declared_counts != actual_counts:
        raise jsonschema.ValidationError(
            "question_type_counts must match actual item type counts: "
            f"declared={declared_counts} actual={actual_counts}"
        )


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate a manifest dict against MANIFEST_SCHEMA.

    Raises jsonschema.ValidationError on failure.
    """
    jsonschema.validate(instance=manifest, schema=MANIFEST_SCHEMA)
