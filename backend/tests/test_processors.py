"""
Enterprise RAG AI Assistant — Phase 5 Processor Unit Tests
===========================================================
Tests for:
  - PDF extraction via PyMuPDF
  - DOCX extraction via python-docx
  - TXT extraction with automatic encoding detection
  - Unicode normalisation pipeline
  - Language detection
  - Processor factory routing
  - UnsupportedFormatError
  - Statistics (word_count, character_count)
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest

# =============================================================================
# Helpers — create minimal valid in-memory files
# =============================================================================

def make_txt_file(content: str, encoding: str = "utf-8") -> bytes:
    return content.encode(encoding)


def make_minimal_docx(paragraphs: list[str]) -> bytes:
    """
    Create a minimal valid DOCX (zip-based) in memory using python-docx.
    python-docx writes the full structure into a BytesIO buffer.
    """
    from docx import Document  # type: ignore[import-untyped]

    buf = io.BytesIO()
    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def make_minimal_pdf(text_pages: list[str]) -> bytes:
    """
    Build a minimal valid PDF in memory using PyMuPDF (fitz).
    """
    import fitz  # type: ignore[import-untyped]

    pdf = fitz.open()
    for page_text in text_pages:
        page = pdf.new_page()
        page.insert_text((72, 100), page_text, fontsize=11)
    buf = io.BytesIO()
    pdf.save(buf)
    pdf.close()
    buf.seek(0)
    return buf.read()


# =============================================================================
# Normaliser Tests
# =============================================================================

class TestNormalizer:
    def test_nfc_normalisation(self) -> None:
        """Combining characters should be composed to NFC form."""
        import unicodedata

        from app.processors.normalizer import normalize

        # "é" as decomposed (NFD): e + combining accent
        nfd = "e\u0301"
        result = normalize(nfd)
        assert unicodedata.is_normalized("NFC", result)
        assert result == "é"

    def test_control_char_removal(self) -> None:
        """C0/C1 control characters except \\t and \\n should be stripped."""
        from app.processors.normalizer import normalize

        text = "hello\x00world\x01\x1fend"
        result = normalize(text)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x1f" not in result
        assert "helloworld" in result.replace(" ", "")

    def test_preserves_newlines(self) -> None:
        """Newline characters must be preserved as paragraph boundaries."""
        from app.processors.normalizer import normalize

        text = "paragraph one\n\nparagraph two"
        result = normalize(text)
        assert "\n\n" in result
        assert "paragraph one" in result
        assert "paragraph two" in result

    def test_collapses_repeated_spaces(self) -> None:
        """Multiple spaces on a line should become a single space."""
        from app.processors.normalizer import normalize

        result = normalize("hello   world   foo")
        assert result == "hello world foo"

    def test_crlf_to_lf(self) -> None:
        """Windows line endings (CRLF) should be converted to LF."""
        from app.processors.normalizer import normalize

        result = normalize("line one\r\nline two\r\nline three")
        assert "\r" not in result
        assert "line one\nline two\nline three" == result

    def test_excess_blank_lines_reduced(self) -> None:
        """More than 2 consecutive blank lines should become exactly 2."""
        from app.processors.normalizer import normalize

        text = "a\n\n\n\n\nb"
        result = normalize(text)
        assert result == "a\n\nb"

    def test_strips_leading_trailing(self) -> None:
        from app.processors.normalizer import normalize

        assert normalize("  hello  ") == "hello"

    def test_empty_string(self) -> None:
        from app.processors.normalizer import normalize

        assert normalize("") == ""

    def test_word_count(self) -> None:
        from app.processors.normalizer import word_count

        assert word_count("hello world foo bar") == 4
        assert word_count("") == 0
        assert word_count("   ") == 0

    def test_character_count(self) -> None:
        from app.processors.normalizer import character_count

        assert character_count("hello") == 5
        assert character_count("") == 0


# =============================================================================
# Language Detection Tests
# =============================================================================

class TestLanguageDetector:
    def test_english_detection(self) -> None:
        from app.processors.language_detector import detect_language

        text = "The quick brown fox jumps over the lazy dog. This is a simple English sentence."
        assert detect_language(text) == "en"

    def test_short_text_fallback(self) -> None:
        """Text under the minimum threshold should return 'und'."""
        from app.processors.language_detector import detect_language

        assert detect_language("hi") == "und"
        assert detect_language("") == "und"

    def test_none_like_input(self) -> None:
        from app.processors.language_detector import detect_language

        assert detect_language("") == "und"


# =============================================================================
# TXT Processor Tests
# =============================================================================

class TestTXTProcessor:
    def _write_temp(self, data: bytes, suffix: str = ".txt") -> Path:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return Path(tmp.name)

    def test_utf8_extraction(self) -> None:
        from app.processors.txt_processor import TXTProcessor

        content = "Hello, world! This is a UTF-8 encoded plain text file with enough words."
        path = self._write_temp(content.encode("utf-8"))
        try:
            result = TXTProcessor().extract(path)
            assert "Hello" in result.clean_text
            assert result.page_count == 1
            assert result.word_count > 0
            assert result.character_count > 0
        finally:
            path.unlink(missing_ok=True)

    def test_latin1_encoding_detection(self) -> None:
        """Latin-1 encoded bytes should be decoded without UnicodeDecodeError."""
        from app.processors.txt_processor import TXTProcessor

        # Latin-1 specific characters: é, ü, ñ
        content = "Héllo wörld! This text uses Latin-1 encoding with accented characters."
        path = self._write_temp(content.encode("latin-1"))
        try:
            result = TXTProcessor().extract(path)
            assert result.page_count == 1
            assert result.character_count > 0
        finally:
            path.unlink(missing_ok=True)

    def test_utf16_encoding(self) -> None:
        from app.processors.txt_processor import TXTProcessor

        content = "UTF-16 encoded document with enough words to pass language detection threshold."
        path = self._write_temp(content.encode("utf-16"))
        try:
            result = TXTProcessor().extract(path)
            assert result.page_count == 1
            assert result.word_count > 0
        finally:
            path.unlink(missing_ok=True)

    def test_encoding_metadata_stored(self) -> None:
        """Detected encoding should be stored in metadata dict."""
        from app.processors.txt_processor import TXTProcessor

        content = "Simple ASCII text file content for testing metadata storage."
        path = self._write_temp(content.encode("utf-8"))
        try:
            result = TXTProcessor().extract(path)
            assert "encoding" in result.metadata
        finally:
            path.unlink(missing_ok=True)

    def test_missing_file_raises(self) -> None:
        from app.processors.txt_processor import TXTProcessor

        with pytest.raises(RuntimeError, match="Cannot read TXT file"):
            TXTProcessor().extract(Path("/nonexistent/path.txt"))

    def test_processing_time_recorded(self) -> None:
        from app.processors.txt_processor import TXTProcessor

        content = "Timing test with enough text to measure processing duration properly."
        path = self._write_temp(content.encode("utf-8"))
        try:
            result = TXTProcessor().extract(path)
            assert result.processing_time >= 0.0
        finally:
            path.unlink(missing_ok=True)


# =============================================================================
# PDF Processor Tests
# =============================================================================

class TestPDFProcessor:
    def _write_temp(self, data: bytes, suffix: str = ".pdf") -> Path:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return Path(tmp.name)

    def test_single_page_extraction(self) -> None:
        from app.processors.pdf_processor import PDFProcessor

        pdf_bytes = make_minimal_pdf(["Hello world from a PDF. This is page one."])
        path = self._write_temp(pdf_bytes)
        try:
            result = PDFProcessor().extract(path)
            assert result.page_count == 1
            assert "Hello" in result.clean_text
        finally:
            path.unlink(missing_ok=True)

    def test_multi_page_count(self) -> None:
        from app.processors.pdf_processor import PDFProcessor

        pdf_bytes = make_minimal_pdf(["Page one content here.", "Page two content here."])
        path = self._write_temp(pdf_bytes)
        try:
            result = PDFProcessor().extract(path)
            assert result.page_count == 2
        finally:
            path.unlink(missing_ok=True)

    def test_word_count_populated(self) -> None:
        from app.processors.pdf_processor import PDFProcessor

        pdf_bytes = make_minimal_pdf(["The quick brown fox jumps over the lazy dog."])
        path = self._write_temp(pdf_bytes)
        try:
            result = PDFProcessor().extract(path)
            assert result.word_count > 0
            assert result.character_count > 0
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_pdf_raises(self) -> None:
        from app.processors.pdf_processor import PDFProcessor

        path = self._write_temp(b"this is not a valid pdf file at all")
        try:
            with pytest.raises(RuntimeError, match="Failed to open PDF"):
                PDFProcessor().extract(path)
        finally:
            path.unlink(missing_ok=True)

    def test_processing_time_recorded(self) -> None:
        from app.processors.pdf_processor import PDFProcessor

        pdf_bytes = make_minimal_pdf(["Timing test content."])
        path = self._write_temp(pdf_bytes)
        try:
            result = PDFProcessor().extract(path)
            assert result.processing_time >= 0.0
        finally:
            path.unlink(missing_ok=True)


# =============================================================================
# DOCX Processor Tests
# =============================================================================

class TestDOCXProcessor:
    def _write_temp(self, data: bytes, suffix: str = ".docx") -> Path:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return Path(tmp.name)

    def test_paragraph_extraction(self) -> None:
        from app.processors.docx_processor import DOCXProcessor

        docx_bytes = make_minimal_docx([
            "Introduction heading",
            "This is a paragraph with several words for testing the docx processor extraction."
        ])
        path = self._write_temp(docx_bytes)
        try:
            result = DOCXProcessor().extract(path)
            assert "Introduction" in result.clean_text
            assert result.word_count > 0
        finally:
            path.unlink(missing_ok=True)

    def test_page_count_estimate(self) -> None:
        """Page count should be at least 1."""
        from app.processors.docx_processor import DOCXProcessor

        docx_bytes = make_minimal_docx(["Short doc."])
        path = self._write_temp(docx_bytes)
        try:
            result = DOCXProcessor().extract(path)
            assert result.page_count >= 1
        finally:
            path.unlink(missing_ok=True)

    def test_multiple_paragraphs(self) -> None:
        from app.processors.docx_processor import DOCXProcessor

        paras = [f"Paragraph {i} content here for testing." for i in range(5)]
        docx_bytes = make_minimal_docx(paras)
        path = self._write_temp(docx_bytes)
        try:
            result = DOCXProcessor().extract(path)
            assert result.word_count > 0
            assert result.character_count > 0
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_docx_raises(self) -> None:
        from app.processors.docx_processor import DOCXProcessor

        path = self._write_temp(b"not a docx file")
        try:
            with pytest.raises(RuntimeError, match="Failed to open DOCX"):
                DOCXProcessor().extract(path)
        finally:
            path.unlink(missing_ok=True)


# =============================================================================
# Processor Factory Tests
# =============================================================================

class TestProcessorFactory:
    def test_pdf_routing(self) -> None:
        from app.processors.pdf_processor import PDFProcessor
        from app.processors.processor_factory import ProcessorFactory

        factory = ProcessorFactory()
        processor = factory.get_processor("application/pdf")
        assert isinstance(processor, PDFProcessor)

    def test_docx_routing(self) -> None:
        from app.processors.docx_processor import DOCXProcessor
        from app.processors.processor_factory import ProcessorFactory

        factory = ProcessorFactory()
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        processor = factory.get_processor(mime)
        assert isinstance(processor, DOCXProcessor)

    def test_txt_routing(self) -> None:
        from app.processors.processor_factory import ProcessorFactory
        from app.processors.txt_processor import TXTProcessor

        factory = ProcessorFactory()
        processor = factory.get_processor("text/plain")
        assert isinstance(processor, TXTProcessor)

    def test_unsupported_format_raises(self) -> None:
        from app.processors.processor_factory import (
            ProcessorFactory,
            UnsupportedFormatError,
        )

        factory = ProcessorFactory()
        with pytest.raises(UnsupportedFormatError):
            factory.get_processor("application/x-msdownload")

    def test_processor_caching(self) -> None:
        """Same factory instance should return the same processor object."""
        from app.processors.processor_factory import ProcessorFactory

        factory = ProcessorFactory()
        p1 = factory.get_processor("text/plain")
        p2 = factory.get_processor("text/plain")
        assert p1 is p2

    def test_supported_mime_types(self) -> None:
        from app.processors.processor_factory import ProcessorFactory

        types = ProcessorFactory.supported_mime_types()
        assert "application/pdf" in types
        assert "text/plain" in types
        assert len(types) >= 3
