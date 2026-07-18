"""
Enterprise RAG AI Assistant — Chunk Endpoints Router
=====================================================
Defines endpoints for retrieving details of and deleting individual chunks.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.chunk import Chunk
from app.models.user import User
from app.schemas.chunk import ChunkResponse
from app.services import document_service

router = APIRouter()


@router.get(
    "/{chunk_id}",
    response_model=ChunkResponse,
    summary="Retrieve chunk details.",
    description="Fetch text content and statistics for a single chunk.",
)
async def get_chunk(
    chunk_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ChunkResponse:
    # 1. Fetch chunk record
    result = await db.execute(select(Chunk).where(Chunk.id == chunk_id))
    chunk = result.scalar_one_or_none()
    if chunk is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found.",
        )

    # 2. Verify ownership of the parent document
    await document_service.get_document_by_id(db, chunk.document_id, current_user.id)

    return ChunkResponse.model_validate(chunk)


@router.delete(
    "/{chunk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a chunk.",
    description="Remove a single text chunk from the index database.",
)
async def delete_chunk(
    chunk_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    # 1. Fetch chunk record
    result = await db.execute(select(Chunk).where(Chunk.id == chunk_id))
    chunk = result.scalar_one_or_none()
    if chunk is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found.",
        )

    # 2. Verify ownership of the parent document
    await document_service.get_document_by_id(db, chunk.document_id, current_user.id)

    # 3. Delete chunk record
    await db.delete(chunk)
    await db.commit()
