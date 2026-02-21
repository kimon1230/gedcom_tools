"""Fasttext wrapper for GEDCOM note language detection."""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path
from typing import Any

from fast_langdetect import (  # type: ignore[import-untyped]
    LangDetectConfig,
    LangDetector,
)

MIN_TEXT_LENGTH_DEFAULT = 10
CONFIDENCE_FLOOR = 0.4
MARGIN_THRESHOLD = 0.15

# fasttext returns "no" for Norwegian; we normalise to Bokmål.
FASTTEXT_CODE_MAP: dict[str, str] = {
    "no": "nb",
}

DEFAULT_LANGUAGES: set[str] = {
    "en",
    "el",
    "de",
    "fr",
    "it",
    "es",
    "pt",
    "nl",
    "pl",
    "sv",
    "nb",
    "nn",
    "da",
    "fi",
    "hu",
    "cs",
    "ro",
    "ru",
    "uk",
    "ar",
    "he",
    "tr",
    "zh",
    "ja",
    "ko",
    "la",
}

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "el": "Greek",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "es": "Spanish",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "sv": "Swedish",
    "nb": "Norwegian Bokmal",
    "nn": "Norwegian Nynorsk",
    "da": "Danish",
    "fi": "Finnish",
    "hu": "Hungarian",
    "cs": "Czech",
    "ro": "Romanian",
    "ru": "Russian",
    "uk": "Ukrainian",
    "ar": "Arabic",
    "he": "Hebrew",
    "tr": "Turkish",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "la": "Latin",
}


def _full_model_cache_dir() -> Path:
    """Return the cache directory that fast-langdetect actually uses."""
    return Path(LangDetectConfig().cache_dir)


def _full_model_available() -> bool:
    """Check if the full model (lid.176.bin) exists in the cache."""
    return (_full_model_cache_dir() / "lid.176.bin").exists()


def _ensure_full_model(stream: Any = None) -> None:
    """Download the full fasttext model if not already cached."""
    if _full_model_available():
        return
    out = stream or sys.stderr
    print(
        "Downloading language model (126 MB, one-time)...",
        file=out,
        flush=True,
    )
    config = LangDetectConfig(model="full", max_input_length=100)
    detector = LangDetector(config)
    detector.detect("test", k=1)  # triggers download
    print("Download complete.", file=out, flush=True)


class GedcomLanguageDetector:
    """Wraps fasttext for GEDCOM text detection."""

    def __init__(
        self,
        min_length: int = MIN_TEXT_LENGTH_DEFAULT,
        stream: Any = None,
    ) -> None:
        self.min_length = min_length
        _ensure_full_model(stream)
        config = LangDetectConfig(model="full", max_input_length=2000)
        self._detector = LangDetector(config)

    def detect(self, text: str | None) -> tuple[str, bool]:
        """Detect language of text.

        Returns (iso_code, was_skipped) where iso_code is a 2-letter
        ISO 639-1 code or 'unknown', and was_skipped is True if the
        text was below min_length or was None.
        """
        if text is None:
            return ("unknown", True)
        text = unicodedata.normalize("NFC", text).strip()
        if len(text) < self.min_length:
            return ("unknown", True)
        if not any(c.isalpha() for c in text):
            return ("unknown", False)
        try:
            result = self._detector.detect(text, k=2)
            if not result:
                return ("unknown", False)
            top_lang = result[0]["lang"]
            top_score: float = result[0]["score"]
            if top_score < CONFIDENCE_FLOOR:
                return ("unknown", False)
            second_score: float = result[1]["score"] if len(result) > 1 else 0.0
            if top_score - second_score < MARGIN_THRESHOLD:
                return ("unknown", False)
            top_lang = FASTTEXT_CODE_MAP.get(top_lang, top_lang)
            if top_lang not in DEFAULT_LANGUAGES:
                return ("unknown", False)
            return (top_lang, False)
        except (ValueError, RuntimeError, OSError):
            return ("unknown", False)
