"""Lesson and manifest schema definitions and validation helpers.

The lesson JSON file is the integration contract between the Python pipeline and
the SurveyJS-first frontend. Item payloads are type-based so new quiz formats
can be added without changing top-level lesson shape.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

import jsonschema

# ---------------------------------------------------------------------------
# JSON Schema definitions
# ---------------------------------------------------------------------------

_SENTENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "text", "language", "audio_path", "transliteration"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "text": {"type": "string", "minLength": 1},
        "language": {"type": "string", "minLength": 1},
        "audio_path": {"type": ["string", "null"], "minLength": 1},
        "transliteration": {"type": ["string", "null"], "minLength": 1},
    },
}


def set_audio_required(sentence_schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the given schema with all audio_path fields made required."""
    new_schema = copy.deepcopy(sentence_schema)
    if "audio_path" in new_schema["properties"]:
        new_schema["properties"]["audio_path"]["type"] = "string"
    return new_schema


_QUES_MCQ_BIMODAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "id",
        "type",
        "question_sentence",
        "options",
        "correct_option_id",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "mcq_bimodal"},
        "question_sentence": _SENTENCE_SCHEMA,
        "options": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": _SENTENCE_SCHEMA,
        },
        "correct_option_id": {"type": "string", "minLength": 1},
    },
}

_QUES_FILL_BLANK_AUDIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "id",
        "type",
        "question_sentence",
        "reference_sentence",
        "answer_mode",
        "omit_loc",
        "accepted_answers",
        "display_correct_answer",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {"const": "fill_blank_audio"},
        "question_sentence": _SENTENCE_SCHEMA,
        "reference_sentence": _SENTENCE_SCHEMA,
        "answer_mode": {
            "type": "string",
            "enum": ["exact", "fuzzy"],
        },
        "omit_loc": {
            "type": "integer", "minimum": 1, "description": "1-based index of the word to omit in the question sentence"
        },
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
        "prompt_sentence",
        "answer_sentence",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "prompt_sentence": set_audio_required(_SENTENCE_SCHEMA),
        "answer_sentence": _SENTENCE_SCHEMA,
    },
}

_QUES_MATCH_AUDIO_TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "type", "prompts", "prompt_mode", "options"],
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
        "prompt_mode": {
            "type": "string",
            "enum": ["audio", "text", "audio_text"],
        },
        "options": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": _SENTENCE_SCHEMA,
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
        "prompt_version": {
            "type": "object",
            "required": ["mcq_bimodal", "fill_blank_audio", "match_audio_text"],
            "additionalProperties": False,
            "properties": {
                "mcq_bimodal": {"type": "string", "minLength": 1},
                "fill_blank_audio": {"type": "string", "minLength": 1},
                "match_audio_text": {"type": "string", "minLength": 1},
            },
        },
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
                    _QUES_MCQ_BIMODAL_SCHEMA,
                    _QUES_FILL_BLANK_AUDIO_SCHEMA,
                    _QUES_MATCH_AUDIO_TEXT_SCHEMA,
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


def _normalize_exact_answer(text: str) -> str:
    stripped = text.strip()
    normalized_edges = re.sub(r"^\W+|\W+$", "", stripped, flags=re.UNICODE)
    return normalized_edges.casefold()


def _normalize_fuzzy_answer(text: str) -> str:
    stripped = text.strip(".,!?;:'\"()[]{}").strip()
    normalized = unicodedata.normalize("NFKD", stripped)
    without_diacritics = "".join(c for c in normalized if not unicodedata.combining(c))
    simplified = re.sub(r"[^\w\s]", " ", without_diacritics, flags=re.UNICODE)
    return re.sub(r"\s+", " ", simplified).strip().casefold()


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

            question_sentence = item.get("question_sentence") or {}
            question_language = question_sentence.get("language")
            option_languages = {opt.get("language") for opt in options}

            if len(option_languages) > 1:
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': all options must share the same language"
                )

            option_language = next(iter(option_languages), None)
            if question_language and option_language and question_language == option_language:
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': question_language and option_language should differ"
                )

        if item_type == "fill_blank_audio":
            question_sentence = item["question_sentence"]
            question_text = question_sentence["text"]
            words = question_text.split()
            omit_loc = item["omit_loc"]
            if omit_loc > len(words):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': omit_loc must point to a word in question_sentence"
                )
            omitted_word = words[omit_loc - 1]

            if item["answer_mode"] == "fuzzy":
                normalize = _normalize_fuzzy_answer
            else:
                normalize = _normalize_exact_answer

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
            options = item.get("options", [])
            option_ids = [option["id"] for option in options]
            if len(option_ids) != len(set(option_ids)):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': option ids must be unique: {option_ids}"
                )

            option_languages = {option["language"] for option in options}
            if len(option_languages) > 1:
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': all options must share the same language"
                )

            option_by_id = {option["id"]: option for option in options}
            prompt_ids = [p["id"] for p in prompts]
            if len(prompt_ids) != len(set(prompt_ids)):
                raise jsonschema.ValidationError(
                    f"Item '{item_id}': prompt ids must be unique: {prompt_ids}"
                )
            for prompt in prompts:
                prompt_sentence = prompt["prompt_sentence"]
                answer_sentence = prompt["answer_sentence"]
                matching_option = option_by_id.get(answer_sentence["id"])

                if matching_option is None:
                    raise jsonschema.ValidationError(
                        f"Item '{item_id}': prompt '{prompt['id']}' answer_sentence.id "
                        "not present in options"
                    )

                if answer_sentence["text"] != matching_option["text"]:
                    raise jsonschema.ValidationError(
                        f"Item '{item_id}': prompt '{prompt['id']}' answer_sentence.text must "
                        "match the option text for the same id"
                    )

                if answer_sentence["language"] != matching_option["language"]:
                    raise jsonschema.ValidationError(
                        f"Item '{item_id}': prompt '{prompt['id']}' answer_sentence.language must "
                        "match the option language for the same id"
                    )

                if prompt_sentence["language"] == answer_sentence["language"]:
                    raise jsonschema.ValidationError(
                        f"Item '{item_id}': prompt '{prompt['id']}' prompt and answer languages should differ"
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
