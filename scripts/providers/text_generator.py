"""Provider-agnostic text generation interface and OpenRouter adapter."""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import openai
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

SENTENCE_PROMPT_VERSION = "sentence_pairs.v1"
MATCH_WORD_PROMPT_VERSION = "match_words.v1"

def _sentence_system_prompt(reference_lang: str, target_lang: str, count: int, difficulty: str) -> str:
    return (
        f"You are an expert {target_lang}-{reference_lang} bilingual educator creating daily language learning content.\n\n"
        f"Generate exactly {count} {target_lang}-{reference_lang} sentence pairs suitable for CEFR {difficulty}.\n"
        "For each pair provide:\n"
        f"1) natural {target_lang} sentence,\n"
        f"2) accurate {reference_lang} translation,\n"
        f"3) exactly 3 plausible but incorrect {target_lang} distractors, each with its {reference_lang} translation.\n\n"
        "Return ONLY JSON array:\n"
        "[\n"
        "  {\n"
        f'    "{target_lang}": "...",\n'
        f'    "{reference_lang}": "...",\n'
        f'    "distractors": [\n'
        f'      {{"{target_lang}": "...", "{reference_lang}": "..."}},\n'
        f'      {{"{target_lang}": "...", "{reference_lang}": "..."}},\n'
        f'      {{"{target_lang}": "...", "{reference_lang}": "..."}}\n'
        '    ]\n'
        "  }\n"
        "]\n\n"
        "Rules:\n"
        f"- {target_lang} text must use the correct script/characters for that language.\n"
        "- No duplicates.\n"
        "- Distractors must be distinct from the correct answer and each other.\n"
    )


def _sentence_must_include_block(
    reference_lang: str, target_lang: str, n: int, pairs_json: str
) -> str:
    return (
        f"\nYou MUST include the following {n} pairs exactly as given "
        f"(same {target_lang} and {reference_lang} text). "
        f"For each of them, add 3 appropriate {target_lang} distractors, each with its {reference_lang} translation:\n{pairs_json}\n"
    )


def _match_word_system_prompt(reference_lang: str, target_lang: str, count: int, difficulty: str) -> str:
    return (
        f"You are an expert {target_lang}-{reference_lang} bilingual educator creating match-game vocabulary items.\n\n"
        f"Generate exactly {count} {target_lang}-{reference_lang} lexical pairs "
        "(single words preferred; short phrases allowed only when a natural single word is not suitable) "
        f"for CEFR {difficulty}.\n"
        "Return ONLY JSON array:\n"
        "[\n"
        f'  {{"{target_lang}": "...", "{reference_lang}": "..."}}\n'
        "]\n\n"
        "Rules:\n"
        f"- {target_lang} text must use the correct script/characters for that language.\n"
        "- Avoid full sentences and punctuation-heavy outputs.\n"
        "- No duplicates in either language.\n"
        "- Keep items concise and easy to match quickly.\n"
    )


_TOPICS_BLOCK = "\n\nFocus on these topics or themes: {topics}."


class TextGenerator(ABC):
    """Abstract interface for LLM-based bilingual generation."""

    def __init__(
        self,
        reference_lang: str,
        target_lang: str,
        language_props: dict[str, dict[str, Any]],
    ) -> None:
        self.reference_lang = reference_lang
        self.target_lang = target_lang
        self.language_props = language_props

    @abstractmethod
    def generate_sentence_pairs(
        self,
        count: int,
        difficulty: str,
        existing_sentences: list[str] | None = None,
        must_include_pairs: list[dict[str, Any]] | None = None,
        topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return sentence pairs with distractors for MCQ/fill questions."""

    @abstractmethod
    def generate_match_word_pairs(
        self,
        count: int,
        difficulty: str,
        existing_sentences: list[str] | None = None,
        topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return lexical pairs for match questions."""


class OpenRouterTextGenerator(TextGenerator):
    """Calls OpenRouter API using OpenAI-compatible SDK."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        reference_lang: str,
        target_lang: str,
        language_props: dict[str, dict[str, Any]],
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(reference_lang, target_lang, language_props)
        self._api_key = api_key or os.environ["OPENROUTER_API_KEY"]
        self._model = model or os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash")
        self._client = openai.OpenAI(api_key=self._api_key, base_url=self.BASE_URL)

    @retry(
        retry=retry_if_exception_type(
            (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _request_json(self, prompt: str) -> Any:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4096,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model returned non-JSON content: {raw[:200]}") from exc

    def generate_sentence_pairs(
        self,
        count: int,
        difficulty: str,
        existing_sentences: list[str] | None = None,
        must_include_pairs: list[dict[str, Any]] | None = None,
        topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        reference_lang = self.reference_lang
        target_lang = self.target_lang
        prompt = _sentence_system_prompt(reference_lang, target_lang, count, difficulty)
        if must_include_pairs:
            prompt += _sentence_must_include_block(
                reference_lang=reference_lang,
                target_lang=target_lang,
                n=len(must_include_pairs),
                pairs_json=json.dumps(
                    [{reference_lang: p[reference_lang], target_lang: p[target_lang]}
                     for p in must_include_pairs],
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        if topics:
            prompt += _TOPICS_BLOCK.format(topics=", ".join(topics))
        if existing_sentences:
            prompt += (
                f"\n\nAvoid these existing {target_lang} phrases:\n"
                + json.dumps(existing_sentences, ensure_ascii=False)
            )

        logger.info(
            "Requesting %d sentence pairs from OpenRouter model=%s difficulty=%s",
            count,
            self._model,
            difficulty,
        )
        pairs = self._request_json(prompt)
        _validate_sentence_pairs(pairs, count, reference_lang, target_lang, self.language_props)

        return pairs

    def generate_match_word_pairs(
        self,
        count: int,
        difficulty: str,
        existing_sentences: list[str] | None = None,
        topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        reference_lang = self.reference_lang
        target_lang = self.target_lang
        prompt = _match_word_system_prompt(reference_lang, target_lang, count, difficulty)
        if topics:
            prompt += _TOPICS_BLOCK.format(topics=", ".join(topics))
        if existing_sentences:
            prompt += (
                f"\n\nAvoid these existing {reference_lang} items:\n"
                + json.dumps(existing_sentences, ensure_ascii=False)
            )

        logger.info(
            "Requesting %d match lexical pairs from OpenRouter model=%s difficulty=%s",
            count,
            self._model,
            difficulty,
        )
        pairs = self._request_json(prompt)
        _validate_match_word_pairs(pairs, count, reference_lang, target_lang, self.language_props)

        return pairs


def _check_unicode_range(
    text: str,
    language: str,
    language_props: dict[str, dict[str, Any]],
) -> bool:
    """Return False if a unicode_range is defined for *language* and *text* contains no chars in it."""
    unicode_range = language_props.get(language, {}).get("unicode_range")
    if not unicode_range:
        return True  # no range defined — skip check
    lo, hi = int(unicode_range[0]), int(unicode_range[1])
    return any(lo <= ord(c) <= hi for c in text)


def _validate_sentence_pairs(
    pairs: Any,
    expected_count: int,
    reference_lang: str,
    target_lang: str,
    language_props: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(pairs, list):
        raise ValueError(f"Expected a JSON array from the model, got {type(pairs).__name__}")
    if len(pairs) != expected_count:
        raise ValueError(f"Expected {expected_count} pairs but got {len(pairs)}")

    seen_target: set[str] = set()
    seen_reference: set[str] = set()
    for i, pair in enumerate(pairs):
        for key in (target_lang, reference_lang, "distractors"):
            if key not in pair:
                raise ValueError(f"Pair {i}: missing key '{key}'")

        target = pair[target_lang].strip()
        reference = pair[reference_lang].strip()
        if not target or not reference:
            raise ValueError(f"Pair {i}: {target_lang}/{reference_lang} must be non-empty")
        if not _check_unicode_range(target, target_lang, language_props):
            raise ValueError(
                f"Pair {i}: {target_lang} text must contain expected script characters"
            )

        if target in seen_target:
            raise ValueError(f"Pair {i}: duplicate {target_lang} text '{target}'")
        if reference.lower() in seen_reference:
            raise ValueError(f"Pair {i}: duplicate {reference_lang} text '{reference}'")
        seen_target.add(target)
        seen_reference.add(reference.lower())

        distractors = pair["distractors"]
        if not isinstance(distractors, list) or len(distractors) != 3:
            raise ValueError(f"Pair {i}: must have exactly 3 distractors")

        seen_distractors: set[str] = set()
        for j, distractor in enumerate(distractors):
            if not isinstance(distractor, dict) or target_lang not in distractor:
                raise ValueError(
                    f"Pair {i}: distractor {j} must be an object with '{target_lang}'"
                )
            if reference_lang not in distractor:
                raise ValueError(
                    f"Pair {i}: distractor {j} must include a '{reference_lang}' translation"
                )
            d_target = distractor[target_lang].strip()
            if not d_target:
                raise ValueError(f"Pair {i}: distractor {j} must be non-empty")
            if d_target == target:
                raise ValueError(f"Pair {i}: distractor {j} matches correct {target_lang}")
            if d_target in seen_distractors:
                raise ValueError(f"Pair {i}: duplicate distractor '{d_target}'")
            if not _check_unicode_range(d_target, target_lang, language_props):
                raise ValueError(
                    f"Pair {i}: distractor {j} must contain expected {target_lang} script characters"
                )
            seen_distractors.add(d_target)


def _validate_match_word_pairs(
    pairs: Any,
    expected_count: int,
    reference_lang: str,
    target_lang: str,
    language_props: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(pairs, list):
        raise ValueError(f"Expected a JSON array from the model, got {type(pairs).__name__}")
    if len(pairs) != expected_count:
        raise ValueError(f"Expected {expected_count} pairs but got {len(pairs)}")

    seen_target: set[str] = set()
    seen_reference: set[str] = set()

    for i, pair in enumerate(pairs):
        for key in (target_lang, reference_lang):
            if key not in pair:
                raise ValueError(f"Match pair {i}: missing key '{key}'")

        target = str(pair[target_lang]).strip()
        reference = str(pair[reference_lang]).strip()
        if not target or not reference:
            raise ValueError(f"Match pair {i}: {target_lang}/{reference_lang} must be non-empty")
        if not _check_unicode_range(target, target_lang, language_props):
            raise ValueError(
                f"Match pair {i}: {target_lang} text must contain expected script characters"
            )

        # Word-focused: keep lexical items compact.
        if len(reference.split()) > 3 or len(target.split()) > 3:
            raise ValueError(
                f"Match pair {i}: lexical items should be a word or short phrase (<= 3 words)"
            )

        if target in seen_target:
            raise ValueError(f"Match pair {i}: duplicate {target_lang} text '{target}'")
        if reference.lower() in seen_reference:
            raise ValueError(f"Match pair {i}: duplicate {reference_lang} text '{reference}'")

        seen_target.add(target)
        seen_reference.add(reference.lower())


def get_text_generator(
    provider: str | None = None,
    *,
    reference_lang: str,
    target_lang: str,
    language_props: dict[str, dict[str, Any]],
    model: str | None = None,
    api_key: str | None = None,
) -> TextGenerator:
    provider = provider or "openrouter"
    if provider == "openrouter":
        return OpenRouterTextGenerator(
            reference_lang=reference_lang,
            target_lang=target_lang,
            language_props=language_props,
            api_key=api_key,
            model=model,
        )
    raise NotImplementedError(
        f"Text provider '{provider}' is not implemented. Supported providers: openrouter"
    )
