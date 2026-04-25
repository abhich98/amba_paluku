"""
Provider-agnostic speech generation interface and Sarvam AI adapter.

Adding a new provider
---------------------
1. Subclass SpeechGenerator and implement generate().
2. Register it in get_speech_generator() with a new provider key.
3. Add the SDK/HTTP dependency to pyproject.toml.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sarvam AI constants
# ---------------------------------------------------------------------------

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

# Telugu voice options on Sarvam (as of 2026-04).
# See https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert for the full list.
DEFAULT_SARVAM_VOICE = "anushka"


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class SpeechGenerator(ABC):
    """Abstract interface for TTS audio generation."""

    @abstractmethod
    def generate(self, text: str, output_path: Path) -> Path:
        """Generate speech audio for `text` and write MP3 to `output_path`.

        Creates parent directories as needed.
        Returns the output path on success.
        """
        ...


# ---------------------------------------------------------------------------
# Sarvam AI adapter
# ---------------------------------------------------------------------------


class SarvamSpeechGenerator(SpeechGenerator):
    """Calls the Sarvam AI TTS REST API to generate Telugu audio.

    Environment variables
    ---------------------
    SARVAM_API_KEY  (required)
    SARVAM_VOICE    (optional, default: anushka)
    """

    def __init__(
        self,
        api_key: str | None = None,
        voice: str | None = None,
        language_code: str = "te-IN",
    ) -> None:
        self._api_key = api_key or os.environ["SARVAM_API_KEY"]
        self._voice = voice or os.environ.get("SARVAM_VOICE", DEFAULT_SARVAM_VOICE)
        self._language_code = language_code
        self._client = httpx.Client(timeout=30.0)

    @retry(
        retry=retry_if_exception_type(httpx.TimeoutException),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def generate(self, text: str, output_path: Path) -> Path:
        logger.info(
            "Sarvam TTS: '%s...' -> %s (voice=%s)",
            text[:40],
            output_path.name,
            self._voice,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        response = self._client.post(
            SARVAM_TTS_URL,
            headers={
                "api-subscription-key": self._api_key,
                "Content-Type": "application/json",
            },
            json={
                "inputs": [text],
                "target_language_code": self._language_code,
                "speaker": self._voice,
                "pace": 0.8,
                "speech_sample_rate": 22050,
                "enable_preprocessing": True,
                "model": "bulbul:v2",
            },
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Sarvam TTS returned HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        data = response.json()
        # Sarvam returns a list of base64-encoded WAV/MP3 strings in data["audios"]
        audio_b64: str = data["audios"][0]
        audio_bytes = base64.b64decode(audio_b64)
        output_path.write_bytes(audio_bytes)
        logger.info("Audio saved (%d bytes): %s", len(audio_bytes), output_path)
        return output_path

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SarvamSpeechGenerator":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def item_audio_filename(item_id: str) -> str:
    """Return the canonical MP3 filename for a lesson item ID.

    Example: '2026-04-25_003' -> '2026-04-25_003.mp3'
    """
    return f"{item_id}.mp3"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_speech_generator(provider: str | None = None) -> SpeechGenerator:
    """Return a configured SpeechGenerator for the given provider name.

    Reads SPEECH_PROVIDER env var when provider is None.
    Currently supported: 'sarvam'
    """
    provider = provider or os.environ.get("SPEECH_PROVIDER", "sarvam")
    if provider == "sarvam":
        return SarvamSpeechGenerator()
    raise NotImplementedError(
        f"Speech provider '{provider}' is not implemented. "
        "Supported providers: sarvam"
    )
