"""
Enterprise RAG AI Assistant — TXT Processor
============================================
Extracts text from plain-text files with automatic encoding detection.

Encoding detection strategy
----------------------------
1. Attempt UTF-8 (strict) — fastest, handles the majority of modern files.
2. Attempt UTF-16 — handles BOM-prefixed Windows/Unicode exports.
3. Fall back to ``charset-normalizer`` best-guess detection.
4. Final fallback: decode as Latin-1 with ``errors="replace"`` — Latin-1
   is a superset of ASCII and maps all 256 byte values, so it never raises.

Page count for plain-text is fixed at 1 (no pagination information).

Dependencies: charset-normalizer
"""

from __future__ import annotations

from pathlib import Path

from app.processors import normalizer
from app.processors.base_processor import BaseProcessor, ProcessingResult
from app.processors.language_detector import detect_language


class TXTProcessor(BaseProcessor):
    """Extracts text from plain-text files with automatic encoding detection."""

    # Encodings tried in order before falling back to charset-normalizer
    _FAST_ENCODINGS = ("utf-8", "utf-16")

    def _extract(self, path: Path) -> ProcessingResult:
        """
        Read the file, detect encoding, decode text, normalise.

        Args:
            path: Path to the text file.

        Returns:
            ``ProcessingResult`` with page_count always set to 1.

        Raises:
            RuntimeError: If the file cannot be read at all.
        """
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"Cannot read TXT file at {path}: {exc}") from exc

        raw_text = self._decode(raw_bytes)
        clean_text = normalizer.normalize(raw_text)
        language = detect_language(clean_text)

        return ProcessingResult(
            raw_text=raw_text,
            clean_text=clean_text,
            language=language,
            page_count=1,
            word_count=normalizer.word_count(clean_text),
            character_count=normalizer.character_count(clean_text),
            processing_time=0.0,
            metadata={"encoding": self._detect_encoding_label(raw_bytes)},
        )

    def _decode(self, data: bytes) -> str:
        """Attempt to decode ``data`` using the encoding detection strategy."""
        # 1. Try common encodings first (fast path)
        for enc in self._FAST_ENCODINGS:
            try:
                return data.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue

        # 2. charset-normalizer best-guess
        try:
            from charset_normalizer import from_bytes  # type: ignore[import-untyped]

            result = from_bytes(data).best()
            if result is not None:
                return str(result)
        except Exception:
            pass

        # 3. Latin-1 fallback — always succeeds
        return data.decode("latin-1", errors="replace")

    def _detect_encoding_label(self, data: bytes) -> str:
        """Return a human-readable encoding label for metadata storage."""
        for enc in self._FAST_ENCODINGS:
            try:
                data.decode(enc)
                return enc
            except (UnicodeDecodeError, LookupError):
                continue

        try:
            from charset_normalizer import from_bytes  # type: ignore[import-untyped]

            result = from_bytes(data).best()
            if result is not None:
                return result.encoding or "unknown"
        except Exception:
            pass

        return "latin-1"
