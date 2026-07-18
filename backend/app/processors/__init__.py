"""
Enterprise RAG AI Assistant — Processors Package
=================================================
Exports the public API for the document processing engine.
"""

from app.processors.base_processor import (
    BaseProcessor,  # noqa: F401
    ProcessingResult,  # noqa: F401
)
from app.processors.processor_factory import (
    ProcessorFactory,  # noqa: F401
    UnsupportedFormatError,  # noqa: F401
)

__all__ = [
    "BaseProcessor",
    "ProcessingResult",
    "ProcessorFactory",
    "UnsupportedFormatError",
]
