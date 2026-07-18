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

from app.db.session import get_db
from app.dependencies import get_current_active_user
from app.models.processed_document import ProcessedDocument
from app.models.user import User
from app.schemas.document import DocumentResponse, DocumentUpdate
from app.schemas.processed_document import ProcessedDocumentResponse
from app.services import document_service

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
