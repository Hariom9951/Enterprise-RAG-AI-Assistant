"""
Enterprise RAG AI Assistant — Text Normalisation Pipeline
==========================================================
Shared, stateless text cleaning functions used by every processor.

Pipeline order
--------------
1. NFC Unicode normalisation   — canonical composed form
2. Line-ending normalisation   — CRLF/CR → LF
3. Control character stripping — remove C0/C1 chars except \\t and \\n
4. Whitespace collapsing       — collapse multiple spaces/tabs on a single line
5. Paragraph boundary cleanup  — reduce >2 consecutive blank lines to 2
6. Edge trimming               — strip leading/trailing whitespace

Statistics helpers
------------------
``word_count``      — whitespace-delimited token count
``character_count`` — ``len`` of cleaned text
"""

from __future__ import annotations

import re
import unicodedata

# Pre-compiled patterns for performance
_CRLF = re.compile(r"\r\n|\r")
_CONTROL_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f"  # C0 excluding \t(\x09) \n(\x0a)
    r"\x80-\x9f]"  # C1 control block
)
_MULTI_SPACES = re.compile(r"[^\S\n]+")  # Multiple spaces/tabs on a line
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")  # More than two consecutive newlines


def normalize(text: str) -> str:
    """
    Apply the full normalisation pipeline and return a clean string.

    Args:
        text: Raw extracted text.

    Returns:
        Normalised string suitable for storage and downstream processing.
    """
    if not text:
        return ""

    # 1. Unicode NFC normalisation
    text = unicodedata.normalize("NFC", text)

    # 2. Normalise line endings
    text = _CRLF.sub("\n", text)

    # 3. Strip invalid control characters
    text = _CONTROL_CHARS.sub("", text)

    # 4. Collapse repeated spaces/tabs within each line
    text = _MULTI_SPACES.sub(" ", text)

    # 5. Reduce excessive blank lines (≤ 2 consecutive newlines)
    text = _EXCESS_BLANK_LINES.sub("\n\n", text)

    # 6. Strip leading/trailing whitespace
    return text.strip()


def word_count(text: str) -> int:
    """Return the number of whitespace-delimited tokens in ``text``."""
    return len(text.split()) if text.strip() else 0


def character_count(text: str) -> int:
    """Return ``len(text)`` — character count including spaces."""
    return len(text)
