"""
Enterprise RAG AI Assistant — Processor Factory
================================================
Maps MIME types to their corresponding processor class instances.

Usage
-----
    factory = ProcessorFactory()
    processor = factory.get_processor("application/pdf")
    result = processor.extract(path)

Design:
  - Processors are instantiated lazily and cached per factory instance.
  - ``UnsupportedFormatError`` is raised for unregistered MIME types.
  - The factory can be extended by registering additional MIME types without
    modifying existing code (Open/Closed Principle).
"""

from __future__ import annotations

from app.processors.base_processor import BaseProcessor


class UnsupportedFormatError(ValueError):
    """Raised when a MIME type has no registered processor."""


class ProcessorFactory:
    """
    Creates and returns the correct ``BaseProcessor`` subclass for a given
    MIME type.

    Registered formats
    ------------------
    - ``application/pdf``                              → ``PDFProcessor``
    - ``application/vnd.openxmlformats-officedocument.wordprocessingml.document``
                                                       → ``DOCXProcessor``
    - ``text/plain``                                   → ``TXTProcessor``
    """

    # ── Registry ─────────────────────────────────────────────────────────────
    # Populated lazily to avoid importing heavy libraries at module load time.
    _REGISTRY: dict[str, str] = {
        "application/pdf": "app.processors.pdf_processor.PDFProcessor",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            "app.processors.docx_processor.DOCXProcessor"
        ),
        "text/plain": "app.processors.txt_processor.TXTProcessor",
    }

    def __init__(self) -> None:
        self._cache: dict[str, BaseProcessor] = {}

    def get_processor(self, mime_type: str) -> BaseProcessor:
        """
        Return a cached processor instance for ``mime_type``.

        Args:
            mime_type: MIME type string (e.g. ``"application/pdf"``).

        Returns:
            Concrete ``BaseProcessor`` subclass instance.

        Raises:
            UnsupportedFormatError: If no processor is registered for the MIME type.
        """
        if mime_type not in self._REGISTRY:
            supported = ", ".join(sorted(self._REGISTRY))
            raise UnsupportedFormatError(
                f"No processor registered for MIME type '{mime_type}'. "
                f"Supported types: {supported}"
            )

        if mime_type not in self._cache:
            self._cache[mime_type] = self._instantiate(mime_type)

        return self._cache[mime_type]

    def _instantiate(self, mime_type: str) -> BaseProcessor:
        """Dynamically import and instantiate the processor class."""
        dotted_path = self._REGISTRY[mime_type]
        module_path, class_name = dotted_path.rsplit(".", 1)

        import importlib
        module = importlib.import_module(module_path)
        cls: type[BaseProcessor] = getattr(module, class_name)
        return cls()

    @classmethod
    def supported_mime_types(cls) -> list[str]:
        """Return the list of MIME types with registered processors."""
        return list(cls._REGISTRY.keys())
