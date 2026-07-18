"""
Enterprise RAG AI Assistant — Language Detection Helper
========================================================
Wraps ``langdetect`` with a safe fallback so callers never crash on short
or ambiguous text.

ISO 639-1 codes are stored (e.g. ``"en"``, ``"fr"``, ``"de"``).
Falls back to ``"und"`` (undetermined) when:
  - text is shorter than MIN_CHARS threshold
  - ``langdetect`` raises ``LangDetectException``
  - detection returns an unexpected format
"""

from __future__ import annotations

# Minimum character count required to attempt detection.
# Very short strings produce unreliable results.
_MIN_CHARS = 20
_FALLBACK = "und"


def detect_language(text: str) -> str:
    """
    Detect the primary language of ``text`` and return an ISO 639-1 code.

    Args:
        text: Clean, normalised text to analyse.

    Returns:
        Two-letter ISO 639-1 language code, or ``"und"`` on failure.
    """
    if not text or len(text.strip()) < _MIN_CHARS:
        return _FALLBACK

    try:
        from langdetect import detect  # type: ignore[import-untyped]
        from langdetect.lang_detect_exception import (
            LangDetectException,  # type: ignore[import-untyped]
        )

        try:
            code: str = detect(text)
            # langdetect returns codes like "zh-cn"; truncate to base lang
            return code.split("-")[0][:10]
        except LangDetectException:
            return _FALLBACK
    except ImportError:  # pragma: no cover
        return _FALLBACK
