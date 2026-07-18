"""
Enterprise RAG AI Assistant — Document Endpoints Router
======================================================
Defines all endpoints for uploading documents, listing, downloading metadata,
renaming, and deleting resources.

Permissions:
  - All routes require a valid JWT Access Token.
  - Users are isolated and can only read/write their own records.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.chunk import Chunk
from app.models.processed_document import ProcessedDocument
from app.models.user import User
from app.schemas.chunk import (
    ChunkResponse,
    ChunkSummaryResponse,
    DocumentEmbeddingStatusResponse,
    DocumentEmbeddingSummaryResponse,
)
from app.schemas.document import DocumentResponse, DocumentUpdate
from app.schemas.processed_document import ProcessedDocumentResponse
from app.services import document_service
from app.tasks.document_tasks import embed_document

router = APIRouter()


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document.",
    description="Ingest a PDF, DOCX, or TXT file, validate size/MIME type, calculate checksum, and save.",
)
async def upload_document(
    file: UploadFile = File(..., description="The document file to ingest."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentResponse:
    return await document_service.upload_document(
        db=db,
        user_id=current_user.id,
        file=file,
    )


@router.get(
    "",
    response_model=list[DocumentResponse],
    summary="List user documents.",
    description="Retrieve all documents uploaded by the current user with pagination and search filtering.",
)
async def list_documents(
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return."),
    offset: int = Query(default=0, ge=0, description="Record pagination offset."),
    search: str | None = Query(default=None, description="Search term for original filename."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[DocumentResponse]:
    docs = await document_service.get_user_documents(
        db=db,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        search_query=search,
    )
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Retrieve document metadata.",
    description="Fetch details of a single document including its ingestion and processing status.",
)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentResponse:
    doc = await document_service.get_document_by_id(
        db=db,
        doc_id=document_id,
        user_id=current_user.id,
    )
    return DocumentResponse.model_validate(doc)


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Rename a document.",
    description="Change the display name of a document. Extension modification is prohibited.",
)
async def rename_document(
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentResponse:
    doc = await document_service.update_document_metadata(
        db=db,
        doc_id=document_id,
        user_id=current_user.id,
        original_filename=payload.original_filename,
    )
    return DocumentResponse.model_validate(doc)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document.",
    description="Deletes a document's database metadata record and unlinks its physical file from storage.",
)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    await document_service.delete_document(
        db=db,
        doc_id=document_id,
        user_id=current_user.id,
    )


@router.get(
    "/{document_id}/status",
    summary="Get document processing status.",
    description="Check the current background parsing stage of the document.",
)
async def get_document_status(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    doc = await document_service.get_document_by_id(db, document_id, current_user.id)
    return {"id": str(doc.id), "status": doc.processing_status}


@router.get(
    "/{document_id}/text",
    response_model=ProcessedDocumentResponse,
    summary="Retrieve extracted document text.",
    description=(
        "Returns the extracted and normalised text content for a processed document. "
        "Returns HTTP 202 if the document is still being processed, "
        "HTTP 404 if text extraction has not yet run."
    ),
)
async def get_document_text(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProcessedDocumentResponse:
    # Verify ownership first
    doc = await document_service.get_document_by_id(db, document_id, current_user.id)

    # If still in pipeline, return 202 Accepted
    if doc.processing_status in ("UPLOADED", "QUEUED", "PROCESSING"):
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={
                "message": "Document is still being processed.",
                "processing_status": doc.processing_status,
            },
        )

    # Fetch ProcessedDocument record
    pd_result = await db.execute(
        select(ProcessedDocument).where(
            ProcessedDocument.document_id == document_id
        )
    )
    pd_record = pd_result.scalar_one_or_none()

    if pd_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed text not found. The document may have failed processing.",
        )

    return ProcessedDocumentResponse.model_validate(pd_record)


@router.get(
    "/{document_id}/chunks",
    response_model=list[ChunkResponse],
    summary="Get document chunks.",
    description="Retrieve paginated list of semantic chunks for a processed document.",
)
async def get_document_chunks(
    document_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, description="Search filter for text within chunks."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ChunkResponse]:
    # Check ownership
    await document_service.get_document_by_id(db, document_id, current_user.id)

    # Query chunks
    query = select(Chunk).where(Chunk.document_id == document_id)
    if search:
        query = query.where(Chunk.text.ilike(f"%{search}%"))

    query = query.order_by(Chunk.chunk_index.asc()).offset(offset).limit(limit)
    result = await db.execute(query)
    chunks = result.scalars().all()
    return [ChunkResponse.model_validate(c) for c in chunks]


@router.get(
    "/{document_id}/chunk-summary",
    response_model=ChunkSummaryResponse,
    summary="Get document chunk summary.",
    description="Retrieve statistical aggregation of chunks generated for a document.",
)
async def get_document_chunk_summary(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ChunkSummaryResponse:
    # Check ownership
    await document_service.get_document_by_id(db, document_id, current_user.id)

    # Get chunks count & stats
    query = select(Chunk).where(Chunk.document_id == document_id)
    result = await db.execute(query)
    chunks = result.scalars().all()

    if not chunks:
        return ChunkSummaryResponse(
            total_chunks=0,
            total_tokens=0,
            average_chunk_size=0.0,
            min_chunk_size=0,
            max_chunk_size=0,
            reading_time_estimate=0.0,
            languages=[],
        )

    token_counts = [c.token_count for c in chunks]
    total_chunks = len(chunks)
    total_tokens = sum(token_counts)
    languages = list(set(c.language for c in chunks if c.language))

    return ChunkSummaryResponse(
        total_chunks=total_chunks,
        total_tokens=total_tokens,
        average_chunk_size=total_tokens / total_chunks,
        min_chunk_size=min(token_counts),
        max_chunk_size=max(token_counts),
        reading_time_estimate=sum(c.reading_time_estimate for c in chunks),
        languages=languages,
    )


@router.post(
    "/{document_id}/embed",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate vector embeddings.",
    description="Force triggers / reruns the vector embedding generation pipeline for all chunks of this document.",
)
async def generate_document_embeddings(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    # Check ownership
    await document_service.get_document_by_id(db, document_id, current_user.id)

    # Trigger task in background
    embed_document.delay(str(document_id))

    return {"message": "Embedding generation task scheduled successfully."}


@router.get(
    "/{document_id}/embedding-status",
    response_model=DocumentEmbeddingStatusResponse,
    summary="Get document embedding progress status.",
    description="Retrieve generation status, completion percentage, and processed vs remaining chunk counts.",
)
async def get_document_embedding_status(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentEmbeddingStatusResponse:
    # Check ownership
    doc = await document_service.get_document_by_id(db, document_id, current_user.id)

    # Count total chunks
    from sqlalchemy import func
    total_query = select(func.count(Chunk.id)).where(Chunk.document_id == document_id)
    total_res = await db.execute(total_query)
    total_chunks = total_res.scalar() or 0

    # Count embedded chunks
    embedded_query = select(func.count(Chunk.id)).where(
        Chunk.document_id == document_id, Chunk.embedding.is_not(None)
    )
    embedded_res = await db.execute(embedded_query)
    processed_chunks = embedded_res.scalar() or 0

    remaining_chunks = max(0, total_chunks - processed_chunks)
    percentage = (processed_chunks / total_chunks) * 100 if total_chunks > 0 else 0.0

    # Determine status
    status_str = "QUEUED"
    if doc.processing_status == "FAILED":
        status_str = "FAILED"
    elif processed_chunks == total_chunks and total_chunks > 0:
        status_str = "COMPLETED"
    elif processed_chunks > 0:
        status_str = "PROCESSING"

    # Get model used
    model_used = settings.embedding_model
    if processed_chunks > 0:
        model_query = select(Chunk.embedding_model).where(
            Chunk.document_id == document_id, Chunk.embedding_model.is_not(None)
        ).limit(1)
        model_res = await db.execute(model_query)
        model_used = model_res.scalar() or settings.embedding_model

    # Cumulative duration
    duration_query = select(func.sum(Chunk.embedding_duration_ms)).where(
        Chunk.document_id == document_id
    )
    duration_res = await db.execute(duration_query)
    processing_time_ms = int(duration_res.scalar() or 0)

    return DocumentEmbeddingStatusResponse(
        document_id=document_id,
        status=status_str,
        percentage_complete=percentage,
        processed_chunks=processed_chunks,
        remaining_chunks=remaining_chunks,
        model_used=model_used,
        vector_dimension=settings.vector_dimension,
        processing_time_ms=processing_time_ms,
        error_message=None if status_str != "FAILED" else "Document processing task failed.",
    )


@router.get(
    "/{document_id}/embedding-summary",
    response_model=DocumentEmbeddingSummaryResponse,
    summary="Get document embedding summary.",
    description="Retrieve statistical aggregation of vector properties and duration.",
)
async def get_document_embedding_summary(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentEmbeddingSummaryResponse:
    # Check ownership
    await document_service.get_document_by_id(db, document_id, current_user.id)

    # Sum stats
    from sqlalchemy import func
    stats_query = select(
        func.count(Chunk.id),
        func.sum(Chunk.embedding_duration_ms),
    ).where(Chunk.document_id == document_id, Chunk.embedding.is_not(None))
    stats_res = await db.execute(stats_query)
    stats_row = stats_res.first()

    total_embedded = 0
    total_duration_ms = 0
    if stats_row:
        total_embedded = stats_row[0] or 0
        total_duration_ms = int(stats_row[1] or 0)

    # Get model used and pipeline version
    model_used = settings.embedding_model
    version = "1.0.0"
    if total_embedded > 0:
        meta_query = select(Chunk.embedding_model, Chunk.embedding_version).where(
            Chunk.document_id == document_id, Chunk.embedding.is_not(None)
        ).limit(1)
        meta_res = await db.execute(meta_query)
        meta_row = meta_res.first()
        if meta_row:
            model_used = meta_row[0] or settings.embedding_model
            version = meta_row[1] or "1.0.0"

    return DocumentEmbeddingSummaryResponse(
        document_id=document_id,
        total_embedded=total_embedded,
        vector_dimension=settings.vector_dimension,
        model_used=model_used,
        version=version,
        total_duration_ms=total_duration_ms,
    )
