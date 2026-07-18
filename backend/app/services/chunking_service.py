"""
Enterprise RAG AI Assistant — Chunking Service
===============================================
Deconstructs extracted document text into semantic chunks.

Features:
  - Recursive text splitting (headers -> paragraphs -> lines -> sentences -> words).
  - Heading awareness (Markdown '#', '##', etc. set section context).
  - Page awareness (form feed '\\x0c' characters update the active page number).
  - Tiktoken token counting for precise chunk size and overlap budgets.
  - Word count, character count, and estimated reading time calculations.
  - Metadata enrichment (inherits metadata from parent Document).
  - Duplicate chunk detection using SHA-256 hashes.
"""

from __future__ import annotations

import hashlib
import re
import uuid

import tiktoken
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.chunk import ChunkCreate, ChunkResponse

# Regex for sentence splitting: matches common punctuation followed by spaces or end of string.
# Avoids splitting on abbreviations by checking for standard word characters.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

# Regex for Markdown Headings (e.g. "# Heading Name" or "### Third-level heading")
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")


class ChunkingService:
    """Orchestrates document chunking and database persistence."""

    def __init__(self) -> None:
        try:
            self._encoder = tiktoken.get_encoding(settings.tokenizer_name)
        except Exception as exc:
            logger.warning(
                f"Failed to load tokenizer '{settings.tokenizer_name}', "
                f"falling back to default cl100k_base: {exc}"
            )
            self._encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a string using tiktoken."""
        return len(self._encoder.encode(text, disallowed_special=()))

    def split_text(
        self,
        text: str,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[ChunkCreate]:
        """
        Split a document's clean text into semantic chunks.

        Splits recursively by:
          1. Form Feed Page boundaries ('\\x0c')
          2. Markdown Headings ('# ', '## ', etc.)
          3. Paragraphs ('\\n\\n')
          4. Lines ('\\n')
          5. Sentences (using regex)
          6. Words (spaces)

        Respects the token count limit (chunk_size) and merges small blocks
        while maintaining the configured overlap buffer.

        Args:
            text:          The extracted, normalized document text.
            chunk_size:    The target size of each chunk in tokens.
            chunk_overlap: The target overlap in tokens between chunks.

        Returns:
            A list of ChunkCreate schema objects representing the generated chunks.
        """
        size_limit = chunk_size or settings.default_chunk_size
        overlap_limit = chunk_overlap or settings.default_chunk_overlap

        if size_limit > settings.max_chunk_size:
            logger.warning(
                f"Requested chunk_size {size_limit} exceeds max limit. "
                f"Capping at {settings.max_chunk_size}."
            )
            size_limit = settings.max_chunk_size

        if overlap_limit >= size_limit:
            overlap_limit = size_limit // 2

        # ── 1. Parse pages using form feed '\\x0c' ─────────────────────────────
        pages = text.split("\x0c")
        raw_chunks: list[ChunkCreate] = []
        chunk_index = 0

        # Global document trackers
        current_section: str | None = None
        current_heading_level: int | None = None

        for page_idx, page_content in enumerate(pages):
            page_num = page_idx + 1
            # Split page content into lines to detect headings and structure
            lines = page_content.split("\n")

            # Temporary buffer for semantic aggregation
            current_buffer: list[str] = []
            buffer_tokens = 0

            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # Check if the line is a Markdown heading
                header_match = _HEADER_RE.match(line_stripped)
                if header_match:
                    # Flush current buffer first before shifting section context
                    if current_buffer:
                        chunk_index = self._add_flushed_chunk(
                            current_buffer,
                            page_num,
                            current_section,
                            current_heading_level,
                            size_limit,
                            overlap_limit,
                            raw_chunks,
                            chunk_index,
                        )
                        current_buffer = []
                        buffer_tokens = 0

                    # Update active section header context
                    hashes, header_text = header_match.groups()
                    current_section = header_text.strip()
                    current_heading_level = len(hashes)

                # Count line tokens
                line_tokens = self.count_tokens(line)

                # If a single line exceeds the chunk size limit, recursively split it
                if line_tokens > size_limit:
                    # Flush current buffer first
                    if current_buffer:
                        chunk_index = self._add_flushed_chunk(
                            current_buffer,
                            page_num,
                            current_section,
                            current_heading_level,
                            size_limit,
                            overlap_limit,
                            raw_chunks,
                            chunk_index,
                        )
                        current_buffer = []
                        buffer_tokens = 0

                    # Recursively split the long line
                    split_parts = self._recursive_split_text(line, size_limit)
                    for part in split_parts:
                        part_tokens = self.count_tokens(part)
                        part_wc = len(part.split())
                        # 200 WPM = 3.33 words per second
                        reading_time = part_wc / 3.33

                        raw_chunks.append(
                            ChunkCreate(
                                chunk_index=chunk_index,
                                text=part,
                                token_count=part_tokens,
                                character_count=len(part),
                                word_count=part_wc,
                                reading_time_estimate=reading_time,
                                page_number=page_num,
                                section_title=current_section,
                                heading_level=current_heading_level,
                                language="und",
                                metadata={},
                                sha256_hash=hashlib.sha256(
                                    part.encode("utf-8")
                                ).hexdigest(),
                            )
                        )
                        chunk_index += 1
                else:
                    # Add to buffer if it fits, else flush and start new buffer with overlap
                    if buffer_tokens + line_tokens <= size_limit:
                        current_buffer.append(line)
                        buffer_tokens += line_tokens
                    else:
                        chunk_index = self._add_flushed_chunk(
                            current_buffer,
                            page_num,
                            current_section,
                            current_heading_level,
                            size_limit,
                            overlap_limit,
                            raw_chunks,
                            chunk_index,
                        )

                        # Set up the new buffer with overlap lines
                        overlap_lines: list[str] = []
                        overlap_tokens = 0
                        for prev_line in reversed(current_buffer):
                            prev_line_tokens = self.count_tokens(prev_line)
                            if overlap_tokens + prev_line_tokens <= overlap_limit:
                                overlap_lines.insert(0, prev_line)
                                overlap_tokens += prev_line_tokens
                            else:
                                break

                        current_buffer = overlap_lines + [line]
                        buffer_tokens = overlap_tokens + line_tokens

            # Flush remaining buffer at the end of the page
            if current_buffer:
                chunk_index = self._add_flushed_chunk(
                    current_buffer,
                    page_num,
                    current_section,
                    current_heading_level,
                    size_limit,
                    overlap_limit,
                    raw_chunks,
                    chunk_index,
                )

        return raw_chunks

    def _add_flushed_chunk(
        self,
        buffer_lines: list[str],
        page_num: int,
        section_title: str | None,
        heading_level: int | None,
        size_limit: int,
        overlap_limit: int,
        raw_chunks: list[ChunkCreate],
        chunk_index: int,
    ) -> int:
        """Helper to flush lines buffer, create ChunkCreate schemas, append to list, and return new index."""
        flushed_chunks = self._flush_buffer(
            buffer_lines,
            page_num,
            section_title,
            heading_level,
            size_limit,
            overlap_limit,
        )
        for fc in flushed_chunks:
            fc.chunk_index = chunk_index
            raw_chunks.append(fc)
            chunk_index += 1
        return chunk_index

    def _flush_buffer(
        self,
        buffer_lines: list[str],
        page_num: int,
        section_title: str | None,
        heading_level: int | None,
        size_limit: int,
        overlap_limit: int,
    ) -> list[ChunkCreate]:
        """Aggregate lines in buffer into a chunk, calculating stats."""
        text = "\n".join(buffer_lines).strip()
        if not text:
            return []

        tokens = self.count_tokens(text)
        wc = len(text.split())
        reading_time = wc / 3.33

        return [
            ChunkCreate(
                chunk_index=0,  # index overwritten by caller
                text=text,
                token_count=tokens,
                character_count=len(text),
                word_count=wc,
                reading_time_estimate=reading_time,
                page_number=page_num,
                section_title=section_title,
                heading_level=heading_level,
                language="und",
                metadata={},
                sha256_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        ]

    def _recursive_split_text(self, text: str, limit: int) -> list[str]:
        """Split text recursively into smaller strings that stay under the limit."""
        if self.count_tokens(text) <= limit:
            return [text]

        # Try sentence-level split
        sentences = _SENTENCE_SPLIT_RE.split(text)
        if len(sentences) > 1:
            chunks: list[str] = []
            current_chunk: list[str] = []
            current_tokens = 0
            for sent in sentences:
                sent_tokens = self.count_tokens(sent)
                if sent_tokens > limit:
                    # Line is still too big; split at word level
                    if current_chunk:
                        chunks.append(" ".join(current_chunk))
                        current_chunk = []
                        current_tokens = 0
                    word_chunks = self._split_by_words(sent, limit)
                    chunks.extend(word_chunks)
                elif current_tokens + sent_tokens <= limit:
                    current_chunk.append(sent)
                    current_tokens += sent_tokens
                else:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [sent]
                    current_tokens = sent_tokens
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            return chunks

        return self._split_by_words(text, limit)

    def _split_by_words(self, text: str, limit: int) -> list[str]:
        """Final fallback word-level splitter for extremely long text blocks."""
        words = text.split()
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_tokens = 0
        for word in words:
            word_tokens = self.count_tokens(word) + 1  # include space token approx
            if current_tokens + word_tokens <= limit:
                current_chunk.append(word)
                current_tokens += word_tokens
            else:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_tokens = word_tokens
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        return chunks

    async def chunk_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[ChunkResponse]:
        """
        Ingest Document text, split it into chunks, enrich metadata, check
        duplicates, and store chunks in the database.

        Ensures task idempotency: deletes all previously generated chunks
        associated with this document_id before inserting the new ones.
        """
        # 1. Fetch document and text
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            raise ValueError(f"Document {document_id} not found.")

        # Ensure processed document exists
        if doc.processing_status != "PROCESSED":
            raise ValueError(
                f"Cannot chunk document {document_id} as status is '{doc.processing_status}' (must be PROCESSED)."
            )

        # Lazy raise is active, so we query ProcessedDocument explicitly
        from app.models.processed_document import ProcessedDocument

        pd_result = await db.execute(
            select(ProcessedDocument).where(
                ProcessedDocument.document_id == document_id
            )
        )
        pd = pd_result.scalar_one_or_none()
        if pd is None:
            raise ValueError(f"Extracted text not found for document {document_id}.")

        logger.info(f"Chunking document {document_id} ({pd.character_count} chars).")

        # ── 2. Run splitting pass ─────────────────────────────────────────────
        raw_chunks = self.split_text(pd.clean_text, chunk_size, chunk_overlap)
        total_chunks = len(raw_chunks)

        # ── 3. Task Idempotency: Delete existing chunks first ──────────────────
        await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        await db.commit()

        # ── 4. Enrich metadata & check duplicates ──────────────────────────────
        stored_chunks: list[Chunk] = []
        seen_hashes: set[str] = set()

        for rc in raw_chunks:
            # Skip if this chunk is a duplicate within this run
            if rc.sha256_hash in seen_hashes:
                logger.debug(
                    f"Skipping duplicate chunk hash {rc.sha256_hash} in document {document_id}."
                )
                continue

            seen_hashes.add(rc.sha256_hash)

            # Build enriched metadata dictionary
            enriched_metadata = {
                "filename": doc.original_filename,
                "mime_type": doc.mime_type,
                "page_number": rc.page_number,
                "section": rc.section_title,
                "language": pd.language,
                "document_id": str(document_id),
                "upload_date": doc.created_at.isoformat(),
                "checksum": doc.sha256_hash,
                "processing_version": rc.version,
                "chunk_number": rc.chunk_index + 1,
                "total_chunks": total_chunks,
            }

            db_chunk = Chunk(
                document_id=document_id,
                chunk_index=rc.chunk_index,
                text=rc.text,
                token_count=rc.token_count,
                character_count=rc.character_count,
                word_count=rc.word_count,
                reading_time_estimate=rc.reading_time_estimate,
                page_number=rc.page_number,
                section_title=rc.section_title,
                heading_level=rc.heading_level,
                language=pd.language,
                chunk_metadata=enriched_metadata,
                sha256_hash=rc.sha256_hash,
                version=rc.version,
            )
            db.add(db_chunk)
            stored_chunks.append(db_chunk)

        await db.commit()

        # Refresh objects to fetch auto-generated UUIDs and timestamps
        for sc in stored_chunks:
            await db.refresh(sc)

        logger.info(
            f"Generated and persisted {len(stored_chunks)} chunks for document {document_id}."
        )
        return [ChunkResponse.model_validate(sc) for sc in stored_chunks]
