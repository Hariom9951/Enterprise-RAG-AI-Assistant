"""
Enterprise RAG AI Assistant — Base Processor
=============================================
Abstract base class and shared result dataclass for all document processors.

Design:
  - Each processor implements ``extract(path)`` and returns a ``ProcessingResult``.
  - The base class measures wall-clock ``processing_time`` automatically.
  - Normalisation is applied inside each processor via the shared ``normalizer``
    module so the Celery task never needs to know about text cleaning details.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

# =============================================================================
# Result Dataclass
# =============================================================================


@dataclass
class ProcessingResult:
    """
    Immutable extraction result returned by every processor.

    Attributes
    ----------
    raw_text:         Full text extracted directly from the file (pre-normalisation).
    clean_text:       Text after the full normalisation pipeline.
    language:         ISO 639-1 language code (e.g. ``"en"``) or ``"und"`` if
                      detection failed or text was too short.
    page_count:       Number of pages (always 1 for TXT files).
    word_count:       Whitespace-delimited word count of ``clean_text``.
    character_count:  ``len(clean_text)`` — character count including spaces.
    processing_time:  Elapsed seconds from ``extract()`` call to return.
    metadata:         Format-specific metadata dict (e.g. PDF title/author).
    """

    raw_text: str
    clean_text: str
    language: str
    page_count: int
    word_count: int
    character_count: int
    processing_time: float
    metadata: dict[str, str] = field(default_factory=dict)


# =============================================================================
# Abstract Base Processor
# =============================================================================


class BaseProcessor(ABC):
    """
    Abstract document processor.

    Subclasses override ``_extract(path)`` with format-specific logic.
    ``extract(path)`` wraps ``_extract`` to measure timing automatically.
    """

    def extract(self, path: Path) -> ProcessingResult:
        """
        Public entry point.  Calls ``_extract`` and injects ``processing_time``.

        Args:
            path: Absolute ``Path`` to the file on disk.

        Returns:
            Completed ``ProcessingResult`` with all fields populated.
        """
        start = time.perf_counter()
        result = self._extract(path)
        elapsed = time.perf_counter() - start
        # Inject timing — dataclasses are mutable so we assign directly
        result.processing_time = elapsed
        return result

    @abstractmethod
    def _extract(self, path: Path) -> ProcessingResult:
        """
        Format-specific extraction logic.  Must be implemented by every
        concrete processor.  ``processing_time`` will be overwritten by
        ``extract()`` so implementations can set it to ``0.0``.
        """
        ...  # pragma: no cover
