"""
Enterprise RAG AI Assistant — Citation Tool
============================================
Formats chunk references into structured citations with source previews.
Supports APA, inline, and footnote citation styles.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_tool import BaseTool, ParameterSpec, PermissionLevel, ToolResult
from app.models.chunk import Chunk
from app.models.document import Document


class CitationTool(BaseTool):
    """
    Generate structured citations from chunk IDs.

    Accepts a list of chunk UUIDs and produces formatted citation strings
    plus short source text previews — without full text exposure.
    """

    id = "citation"
    name = "Citation Generator"
    description = (
        "Generate formatted citations from document chunk IDs. "
        "Use this after retrieving chunks to produce accurate source references "
        "for the final answer. Supports inline, APA, and footnote styles."
    )
    permission_level = PermissionLevel.USER
    parameters = [
        ParameterSpec(
            name="chunk_ids",
            type="array",
            description="List of chunk UUID strings to generate citations for.",
            required=True,
        ),
        ParameterSpec(
            name="format",
            type="string",
            description="Citation format style.",
            required=False,
            default="inline",
            enum=["inline", "apa", "footnote"],
        ),
        ParameterSpec(
            name="preview_chars",
            type="integer",
            description="Number of characters for the text preview snippet (20–500).",
            required=False,
            default=200,
            minimum=20,
            maximum=500,
        ),
    ]

    async def _run(
        self,
        params: dict[str, Any],
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> ToolResult:
        chunk_ids_raw: list[Any] = params["chunk_ids"]
        fmt: str = params["format"]
        preview_chars: int = params["preview_chars"]

        # Parse UUIDs
        parsed_ids: list[uuid.UUID] = []
        for raw in chunk_ids_raw:
            try:
                parsed_ids.append(uuid.UUID(str(raw)))
            except ValueError:
                continue  # Skip malformed IDs gracefully

        if not parsed_ids:
            return ToolResult(
                success=True,
                output=[],
                metadata={"total": 0, "format": fmt},
            )

        # Fetch chunks + documents in a single join query
        stmt = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Chunk.id.in_(parsed_ids),
                Document.user_id == user_id,  # Ownership enforcement
            )
        )
        res = await db.execute(stmt)
        rows = res.all()

        citations = []
        for idx, (chunk, doc) in enumerate(rows, start=1):
            preview = (chunk.text or "")[:preview_chars].strip()
            if len(chunk.text or "") > preview_chars:
                preview += "…"

            page = chunk.page_number or "?"
            section = chunk.section_title or ""
            filename = doc.original_filename

            if fmt == "apa":
                citation_text = (
                    f"{filename} (p. {page}). {section + '. ' if section else ''}"
                )
            elif fmt == "footnote":
                citation_text = f"[{idx}] {filename}, page {page}{', §' + section if section else ''}."
            else:  # inline
                citation_text = f"[{filename}, p. {page}]"

            citations.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(doc.id),
                    "document_name": filename,
                    "page_number": page,
                    "section_title": section or None,
                    "citation": citation_text,
                    "preview": preview,
                    "format": fmt,
                }
            )

        return ToolResult(
            success=True,
            output=citations,
            metadata={
                "total": len(citations),
                "format": fmt,
                "requested_ids": len(parsed_ids),
                "found": len(citations),
            },
        )
