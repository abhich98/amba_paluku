"""
Provider-agnostic text generation interface and OpenRouter adapter.

Adding a new provider
---------------------
1. Subclass TextGenerator and implement generate_pairs().
2. Register it in get_text_generator() with a new provider key.
3. Add the SDK dependency to pyproject.toml.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from indic_transliteration import sanscript
from indic_transliteration.detect import detect
from indic_transliteration.sanscript import transliterate
import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template  (prompt_version = "1.0")
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert Telugu-English bilingual educator creating daily language \
learning content for the Amba Paluku app.

Generate exactly {count} Telugu-English sentence pairs suitable for a CEFR \
{difficulty} learner. If topics are provided, generate some of the sentences on the following topics: {topics}.

For each pair provide:
1. A natural Telugu sentence or common phrase.
2. Its accurate English translation.
3. Exactly 3 plausible but incorrect Telugu alternatives \
("distractors") for a multiple-choice question.

Return ONLY a valid JSON array — no markdown fences, no extra commentary:
[
  {{
    "telugu":          "...",
    "english":         "...",
        "distractors":     [
            {{
                "telugu": "..."
            }},
            {{
                "telugu": "..."
            }},
            {{
                "telugu": "..."
            }}
        ]
  }}
]

Hard rules:
- Telugu must use proper Unicode Telugu script (U+0C00–U+0C7F).
- Distractors must be in Telugu script, plausible but clearly wrong.
- Distractors must be distinct from the correct answer and from each other.
- No duplicate English/Telugu sentences within the set.
- Difficulty vocabulary guide:
    A1 → basic greetings, numbers, colours, family terms
    A2 → everyday objects, simple actions, time expressions
    B1 → opinions, comparisons, short narratives
    B2 → abstract topics, idiomatic phrases, formal register
    C1/C2 → nuanced expression, literature-register phrases
"""


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class TextGenerator(ABC):
    """Abstract interface for LLM-based English-Telugu pair generation."""

    @abstractmethod
    def generate_pairs(
        self,
        count: int,
        difficulty: str,
        topics: list[str] | None = None,
        existing_sentences: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return `count` sentence pairs as a list of dicts.

        Each dict has keys: telugu, english, transliteration, distractors.
        Each distractor has keys: telugu, transliteration.
        existing_sentences is a list of Telugu strings to avoid duplicating.
        """
        ...


# ---------------------------------------------------------------------------
# OpenRouter adapter  (OpenAI-compatible endpoint)
# ---------------------------------------------------------------------------


class OpenRouterTextGenerator(TextGenerator):
    """Calls the OpenRouter API using the OpenAI SDK.

    Environment variables
    ---------------------
    OPENROUTER_API_KEY  (required)
    OPENROUTER_MODEL    (optional, default: google/gemini-2.0-flash)
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ["OPENROUTER_API_KEY"]
        self._model = model or os.environ.get(
            "OPENROUTER_MODEL", "google/gemini-2.0-flash"
        )
        self._client = openai.OpenAI(
            api_key=self._api_key,
            base_url=self.BASE_URL,
        )

    @retry(
        retry=retry_if_exception_type(
            (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def generate_pairs(
        self,
        count: int,
        difficulty: str,
        topics: list[str] | None = None,
        existing_sentences: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        prompt = _SYSTEM_PROMPT.format(count=count, difficulty=difficulty, topics=topics)
        if existing_sentences:
            prompt += (
                "\n\nAvoid these Telugu phrases already used in previous lessons:\n"
                + json.dumps(existing_sentences, ensure_ascii=False)
            )

        logger.info(
            "Requesting %d pairs from OpenRouter model=%s difficulty=%s",
            count,
            self._model,
            difficulty,
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4096,
        )

        raw: str = response.choices[0].message.content.strip()

        # Strip markdown code fences if the model wraps the JSON
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            pairs: list[dict[str, Any]] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Model returned non-JSON content: {raw[:200]}"
            ) from exc

        _validate_raw_pairs(pairs, count)

        # Enrich transliteration after raw schema validation.
        for pair in pairs:
            pair["transliteration"] = _transliterate_tool(pair["telugu"])
            for distractor in pair["distractors"]:
                distractor["transliteration"] = _transliterate_tool(
                    distractor["telugu"]
                )
        logger.info("Received and validated %d pairs", len(pairs))
        return pairs


# ---------------------------------------------------------------------------
# Shared validation for raw LLM output
# ---------------------------------------------------------------------------


def _validate_raw_pairs(pairs: list[dict[str, Any]], expected_count: int) -> None:
    """Structural validation before the pairs reach the main pipeline."""
    if not isinstance(pairs, list):
        raise ValueError(
            f"Expected a JSON array from the model, got {type(pairs).__name__}"
        )
    if len(pairs) != expected_count:
        raise ValueError(
            f"Expected {expected_count} pairs but the model returned {len(pairs)}"
        )

    required_keys = {"english", "telugu", "distractors"}
    seen_sentences: set[str] = set()

    for i, pair in enumerate(pairs):
        missing = required_keys - pair.keys()
        if missing:
            raise ValueError(f"Pair {i}: missing keys {missing}")

        # Telugu script presence check (U+0C00–U+0C7F)
        if not any("\u0C00" <= c <= "\u0C7F" for c in pair["telugu"]):
            raise ValueError(
                f"Pair {i}: 'telugu' field does not contain Telugu script characters"
            )

        if not isinstance(pair["distractors"], list) or len(pair["distractors"]) != 3:
            raise ValueError(f"Pair {i}: must have exactly 3 distractors")

        for j, distractor in enumerate(pair["distractors"]):
            if not isinstance(distractor, dict):
                raise ValueError(f"Pair {i}: distractor {j} must be an object")
            distractor_text = distractor.get("telugu")
            if not isinstance(distractor_text, str) or not distractor_text.strip():
                raise ValueError(
                    f"Pair {i}: distractor {j} telugu must be a non-empty Telugu string"
                )
            if not any("\u0C00" <= c <= "\u0C7F" for c in distractor_text):
                raise ValueError(
                    f"Pair {i}: distractor {j} telugu must contain Telugu script"
                )

        tel = pair["telugu"].strip()
        if tel in seen_sentences:
            raise ValueError(f"Pair {i}: duplicate Telugu sentence '{pair['telugu']}'")
        seen_sentences.add(tel)


# Transliteration helper

def _transliterate_tool(text: str) -> str:
    """
    Transliterates indian language script to Roman script (IAST format).
    
    This tool helps in providing the English pronunciation (transliteration) 
    for Indian language words and sentences.
    
    Args:
        text: A single string in Indian language to be transliterated.
        
    Returns:
        A single transliterated string.
    """
    if isinstance(text, str):
        # Transliterate from Indian language script to IAST (Romanized)
        return transliterate(text, detect(text), sanscript.IAST)
    else:
        # Graceful handling of unexpected types
        return str(text)

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_text_generator(provider: str | None = None) -> TextGenerator:
    """Return a configured TextGenerator for the given provider name.

    Reads TEXT_PROVIDER env var when provider is None.
    Currently supported: 'openrouter'
    """
    provider = provider or os.environ.get("TEXT_PROVIDER", "openrouter")
    if provider == "openrouter":
        return OpenRouterTextGenerator()
    raise NotImplementedError(
        f"Text provider '{provider}' is not implemented. "
        "Supported providers: openrouter"
    )
