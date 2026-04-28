from __future__ import annotations

import random
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


def sample_question_types(
    num_questions: int,
    question_type_weights: dict[str, float],
) -> list[str]:
    q_types = list(question_type_weights.keys())
    q_weights = list(question_type_weights.values())
    weight_sum = sum(q_weights)
    if weight_sum <= 0:
        raise ValueError("question_type_weights must sum to a positive value")
    normalized = [weight / weight_sum for weight in q_weights]
    return random.choices(population=q_types, weights=normalized, k=num_questions)


def iter_sentence_objects(item: dict[str, Any]) -> list[dict[str, Any]]:
    sentences: list[dict[str, Any]] = []

    for key in ("question_sentence", "reference_sentence", "display_correct_answer"):
        value = item.get(key)
        if isinstance(value, dict) and "text" in value and "language" in value:
            sentences.append(value)

    for answer in item.get("accepted_answers", []):
        if isinstance(answer, dict) and "text" in answer and "language" in answer:
            sentences.append(answer)

    for option in item.get("options", []):
        if isinstance(option, dict) and "text" in option and "language" in option:
            sentences.append(option)

    for prompt in item.get("prompts", []):
        if not isinstance(prompt, dict):
            continue
        for key in ("prompt_sentence", "answer_sentence"):
            value = prompt.get(key)
            if isinstance(value, dict) and "text" in value and "language" in value:
                sentences.append(value)

    return sentences


def build_lesson(
    *,
    lesson_date: str,
    question_types: list[str],
    sentence_pairs: list[dict[str, Any]],
    match_pairs: list[dict[str, Any]],
    difficulty: str,
    model: str,
    provider: str,
    prompt_versions: dict[str, str],
    question_type_weights: dict[str, float],
    reference_lang: str,
    target_lang: str,
    language_props: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    def split_words(sentence: str) -> list[str]:
        return sentence.split()

    def sanitize_answer(word: str) -> str:
        return word.strip(".,!?;:'\"()[]{}")

    def normalize_fuzzy_answer(word: str) -> str:
        stripped = sanitize_answer(word)
        normalized = unicodedata.normalize("NFKD", stripped)
        without_diacritics = "".join(c for c in normalized if not unicodedata.combining(c))
        simplified = re.sub(r"[^a-zA-Z0-9\s]", " ", without_diacritics)
        return re.sub(r"\s+", " ", simplified).strip().lower()

    def pick_omit_loc(words: list[str]) -> int:
        candidate_indexes = [
            idx for idx, word in enumerate(words)
            if sanitize_answer(word) and len(sanitize_answer(word)) > 2
        ]
        if not candidate_indexes:
            candidate_indexes = [idx for idx, word in enumerate(words) if sanitize_answer(word)]
        if not candidate_indexes:
            raise ValueError("Cannot build fill-in-the-blank from an empty sentence")
        return random.choice(candidate_indexes) + 1

    def pair_text(pair: dict[str, Any], language: str) -> str:
        if language not in pair:
            raise KeyError(
                f"Language key '{language}' not found in pair. Available keys: {list(pair.keys())}"
            )
        return pair[language]

    def distractor_text(distractor: dict[str, Any], language: str) -> str:
        if language not in distractor:
            raise KeyError(
                f"Language key '{language}' not found in distractor. Available keys: {list(distractor.keys())}"
            )
        return distractor[language]

    def build_sentence_object(
        *,
        sentence_id: str,
        text: str,
        language: str,
    ) -> dict[str, Any]:
        return {
            "id": sentence_id,
            "text": text,
            "language": language,
            "audio_path": None,
            "transliteration": None,
        }

    def shuffle_languages():
        langs = [reference_lang, target_lang]
        random.shuffle(langs)
        return langs

    def build_mcq(item_id: str, pair: dict[str, Any]) -> dict[str, Any]:
        question_lang, options_lang = shuffle_languages()

        question_sentence = build_sentence_object(
            sentence_id=f"{item_id}_question",
            text=pair_text(pair, question_lang),
            language=question_lang,
        )

        options = [
            build_sentence_object(
                sentence_id=f"{item_id}_opt0",
                text=pair_text(pair, options_lang),
                language=options_lang,
            )
        ]
        for d_idx, distractor in enumerate(pair["distractors"], start=1):
            options.append(
                build_sentence_object(
                    sentence_id=f"{item_id}_opt{d_idx}",
                    text=distractor_text(distractor, options_lang),
                    language=options_lang,
                )
            )

        random.shuffle(options)
        correct_text = pair_text(pair, options_lang)
        correct_option_id = next(opt["id"] for opt in options if opt["text"] == correct_text)
        return {
            "id": item_id,
            "type": "mcq_bimodal",
            "question_sentence": question_sentence,
            "options": options,
            "correct_option_id": correct_option_id,
        }

    def build_fill_blank(item_id: str, pair: dict[str, Any]) -> dict[str, Any]:
        question_lang, hint_lang = shuffle_languages()

        question_text = pair_text(pair, question_lang)
        question_sentence = build_sentence_object(
            sentence_id=f"{item_id}_question",
            text=question_text,
            language=question_lang,
        )
        hint_sentence = build_sentence_object(
            sentence_id=f"{item_id}_reference",
            text=pair_text(pair, hint_lang),
            language=hint_lang,
        )

        words = split_words(question_text)
        omit_loc = pick_omit_loc(words)
        omitted_word = words[omit_loc - 1]
        sanitized_answer = sanitize_answer(omitted_word)

        answer_mode = "exact"
        _props = language_props or {}
        if _props.get(hint_lang, {}).get("unicode_range"):
            answer_mode = "fuzzy"

        answer_texts: list[str] = [omitted_word]
        if answer_mode == "fuzzy":
            normalized = normalize_fuzzy_answer(omitted_word)
            if normalized and normalized not in answer_texts:
                answer_texts.append(normalized)
        if sanitized_answer and sanitized_answer != omitted_word and sanitized_answer not in answer_texts:
            answer_texts.append(sanitized_answer)
        accepted_answers = [
            build_sentence_object(
                sentence_id=f"{item_id}_ans{idx}",
                text=text,
                language=question_lang,
            )
            for idx, text in enumerate(answer_texts)
        ]

        display_answer_sentence = build_sentence_object(
            sentence_id=f"{item_id}_display_answer",
            text=sanitized_answer or omitted_word,
            language=question_lang,
        )

        return {
            "id": item_id,
            "type": "fill_blank_audio",
            "question_sentence": question_sentence,
            "reference_sentence": hint_sentence,
            "answer_mode": answer_mode,
            "omit_loc": omit_loc,
            "accepted_answers": accepted_answers,
            "display_correct_answer": display_answer_sentence,
        }

    def build_match(item_id: str, chunk: list[dict[str, Any]]) -> dict[str, Any]:
        option_records: list[dict[str, Any]] = []
        prompts: list[dict[str, Any]] = []
        for idx, pair in enumerate(chunk, start=1):
            option_id = f"{item_id}_opt{idx}"
            option_sentence = build_sentence_object(
                sentence_id=option_id,
                text=pair_text(pair, reference_lang),
                language=reference_lang,
            )
            option_records.append(option_sentence)
            prompts.append(
                {
                    "id": f"{item_id}_p{idx}",
                    "prompt_sentence": build_sentence_object(
                        sentence_id=f"{item_id}_p{idx}_prompt",
                        text=pair_text(pair, target_lang),
                        language=target_lang,
                    ),
                    "answer_sentence": dict(option_sentence),
                }
            )

        random.shuffle(option_records)
        return {
            "id": item_id,
            "type": "match_audio_text",
            "prompts": prompts,
            "prompt_mode": "audio_text",
            "options": option_records,
        }

    sentence_idx = 0
    match_idx = 0
    items: list[dict[str, Any]] = []

    for index, qtype in enumerate(question_types):
        item_id = f"{lesson_date}_{index + 1:03d}"
        if qtype == "mcq_bimodal":
            if sentence_idx >= len(sentence_pairs):
                raise ValueError("Insufficient sentence pairs for mcq_bimodal")
            items.append(build_mcq(item_id, sentence_pairs[sentence_idx]))
            sentence_idx += 1
        elif qtype == "fill_blank_audio":
            if sentence_idx >= len(sentence_pairs):
                raise ValueError("Insufficient sentence pairs for fill_blank_audio")
            items.append(build_fill_blank(item_id, sentence_pairs[sentence_idx]))
            sentence_idx += 1
        elif qtype == "match_audio_text":
            if match_idx + 3 > len(match_pairs):
                raise ValueError("Insufficient match pairs for match_audio_text")
            chunk = match_pairs[match_idx:match_idx + 3]
            items.append(build_match(item_id, chunk))
            match_idx += 3
        else:
            raise ValueError(f"Unsupported question type in sequence: {qtype}")

    question_type_counts = {
        "mcq_bimodal": sum(1 for item in items if item["type"] == "mcq_bimodal"),
        "fill_blank_audio": sum(1 for item in items if item["type"] == "fill_blank_audio"),
        "match_audio_text": sum(1 for item in items if item["type"] == "match_audio_text"),
    }

    return {
        "lesson_id": lesson_date,
        "date": lesson_date,
        "status": "draft",
        "difficulty": difficulty,
        "reference_lang": reference_lang,
        "target_lang": target_lang,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_versions,
        "question_type_weights": question_type_weights,
        "question_type_counts": question_type_counts,
        "items": items,
    }
