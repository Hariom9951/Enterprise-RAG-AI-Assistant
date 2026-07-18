"""
Enterprise RAG AI Assistant — Document Lookup Tool
====================================================
Retrieves document records, individual pages, and specific chunks by ID.
Enforces user ownership on every query — users can only access their own documents.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import BaseTool, ParameterSpec, PermissionLevel, ToolResult
from app.models.chunk import Chunk
from app.models.document import Document


class DocumentLookupTool(BaseTool):
    """
    Retrieve detailed document or chunk information by ID.

    Enforces strict ownership: only documents belonging to the requesting
    user are accessible. Returns None for unauthorized access rather than
    raising errors to prevent information leakage.
    """

    id = "document_lookup"
    name = "Document Lookup"
    description = (
        "Retrieve a document's metadata, a specific page's chunks, "
        "or an individual chunk by its ID. Use this when you need "
        "precise document content or need to verify a source reference."
    )
    permission_level = PermissionLevel.USER
    parameters = [
        ParameterSpec(
            name="document_id",
            type="string",
            description="UUID of the document to retrieve.",
            required=True,
        ),
        ParameterSpec(
            name="page_number",
            type="integer",
            description="If provided, return only chunks from this page (1-indexed).",
            required=False,
            default=None,
            minimum=1,
        ),
        ParameterSpec(
            name="chunk_id",
            type="string",
            description="If provided, return this specific chunk by its UUID.",
            required=False,
            default=None,
        ),
        ParameterSpec(
            name="include_metadata",
            type="boolean",
            description="Whether to include full chunk metadata in the response.",
            required=False,
            default=True,
        ),
    ]

    async def _run(
        self,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> ToolResult:
        document_id_str: str = params["document_id"]
        page_number: int | None = params.get("page_number")
        chunk_id_str: str | None = params.get("chunk_id")
        include_metadata: bool = params.get("include_metadata", True)

        # Parse and validate document UUID
        try:
            document_id = uuid.UUID(document_id_str)
        except ValueError:
            return ToolResult(
                success=False,
                output=None,
                error=f"Invalid document_id format: {document_id_str!r}",
            )

        # Fetch document — enforce ownership
        stmt = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()

        if doc is None:
            return ToolResult(
                success=True,
                output=None,
                metadata={"reason": "Document not found or access denied."},
            )

        doc_meta = {
            "id": str(doc.id),
            "filename": doc.original_filename,
            "mime_type": doc.mime_type,
            "file_size_bytes": doc.file_size,
            "processing_status": doc.processing_status,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

        # ── Specific chunk lookup ─────────────────────────────────────────────
        if chunk_id_str:
            try:
                chunk_id = uuid.UUID(chunk_id_str)
            except ValueError:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Invalid chunk_id format: {chunk_id_str!r}",
                )

            chunk_stmt = select(Chunk).where(
                Chunk.id == chunk_id,
                Chunk.document_id == document_id,
            )
            chunk_res = await db.execute(chunk_stmt)
            chunk = chunk_res.scalar_one_or_none()

            if chunk is None:
                return ToolResult(
                    success=True,
                    output=None,
                    metadata={"reason": "Chunk not found in this document."},
                )

            chunk_data = _chunk_to_dict(chunk, include_metadata)
            return ToolResult(
                success=True,
                output={"document": doc_meta, "chunk": chunk_data},
                metadata={"lookup_type": "chunk"},
            )

        # ── Page-level chunk lookup ───────────────────────────────────────────
        if page_number is not None:
            page_stmt = (
                select(Chunk)
                .where(
                    Chunk.document_id == document_id, Chunk.page_number == page_number
                )
                .order_by(Chunk.chunk_index.asc())
            )
            page_res = await db.execute(page_stmt)
            page_chunks = list(page_res.scalars().all())

            return ToolResult(
                success=True,
                output={
                    "document": doc_meta,
                    "page_number": page_number,
                    "chunks": [
                        _chunk_to_dict(c, include_metadata) for c in page_chunks
                    ],
                },
                metadata={"lookup_type": "page", "chunk_count": len(page_chunks)},
            )

        # ── Document metadata only ────────────────────────────────────────────
        return ToolResult(
            success=True,
            output={"document": doc_meta},
            metadata={"lookup_type": "metadata"},
        )


def _chunk_to_dict(chunk: Chunk, include_metadata: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(chunk.id),
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "page_number": chunk.page_number,
        "section_title": chunk.section_title,
        "language": chunk.language,
        "token_count": chunk.token_count,
    }
    if include_metadata:
        data["metadata"] = chunk.chunk_metadata or {}
    return data
