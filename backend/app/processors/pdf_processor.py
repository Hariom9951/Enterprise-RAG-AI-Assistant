"""
Enterprise RAG AI Assistant — PDF Processor
============================================
Extracts text and metadata from PDF files using PyMuPDF (``fitz``).

Extraction strategy
-------------------
- Iterate over pages in document order.
- Use ``page.get_text("text")`` for plain-text extraction.
- Concatenate pages with double-newline paragraph boundaries.
- Capture document metadata (title, author, subject, creator, keywords).

Dependencies: PyMuPDF (``fitz``)
"""

from __future__ import annotations

from pathlib import Path

from app.processors import normalizer
from app.processors.base_processor import BaseProcessor, ProcessingResult
from app.processors.language_detector import detect_language


class PDFProcessor(BaseProcessor):
    """Extracts text and metadata from PDF files via PyMuPDF."""

    def _extract(self, path: Path) -> ProcessingResult:
        """
        Open the PDF, iterate pages, extract text, normalise, detect language.

        Args:
            path: Path to the PDF file.

        Returns:
            ``ProcessingResult`` with all fields populated.

        Raises:
            RuntimeError: If the file cannot be opened as a valid PDF.
        """
        import fitz  # type: ignore[import-untyped]  # PyMuPDF

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            raise RuntimeError(f"Failed to open PDF at {path}: {exc}") from exc

        page_count = doc.page_count
        page_texts: list[str] = []

        for page in doc:
            text = page.get_text("text")  # type: ignore[attr-defined]
            if text and text.strip():
                page_texts.append(text)

        raw_text = "\n\n".join(page_texts)

        # Extract document metadata safely
        meta: dict[str, str] = {}
        try:
            pdf_meta = doc.metadata or {}  # type: ignore[attr-defined]
            for key in ("title", "author", "subject", "creator", "keywords"):
                value = pdf_meta.get(key, "")
                if value and isinstance(value, str) and value.strip():
                    meta[key] = value.strip()
        except Exception:
            pass  # metadata extraction is best-effort

        doc.close()

        clean_text = normalizer.normalize(raw_text)
        language = detect_language(clean_text)

        return ProcessingResult(
            raw_text=raw_text,
            clean_text=clean_text,
            language=language,
            page_count=page_count,
            word_count=normalizer.word_count(clean_text),
            character_count=normalizer.character_count(clean_text),
            processing_time=0.0,  # overwritten by BaseProcessor.extract()
            metadata=meta,
        )
