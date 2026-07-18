"""
Enterprise RAG AI Assistant — Chat API Endpoints
==================================================
Exposes CRUD endpoints for conversations and Server-Sent Events (SSE) streaming.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_active_user, get_db
from app.models.chat_models import ChatSession
from app.models.user import User
from app.schemas.chat import (
    ChatMessageRequest,
    ChatSessionCreate,
    ChatSessionDetailResponse,
    ChatSessionRenameRequest,
    ChatSessionResponse,
)
from app.services.chat_service import ChatService

router = APIRouter()
chat_service = ChatService()


@router.post(
    "/session", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED
)
async def create_chat_session(
    payload: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Initialize a new conversational workspace session.
    """
    return await chat_service.create_session(
        db, user_id=current_user.id, title=payload.title
    )


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_chat_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List all conversation sessions owned by the active user.
    """
    return await chat_service.list_sessions(db, user_id=current_user.id)


@router.get("/session/{session_id}", response_model=ChatSessionDetailResponse)
async def get_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Retrieve full history logs for a conversational thread.
    """
    stmt = (
        select(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .options(selectinload(ChatSession.messages))
    )
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation session not found.",
        )
    return session


@router.put("/session/{session_id}", response_model=ChatSessionResponse)
async def rename_chat_session(
    session_id: uuid.UUID,
    payload: ChatSessionRenameRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Rename conversational thread display title.
    """
    session = await chat_service.rename_session(
        db, session_id, current_user.id, payload.title
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation session not found or unauthorized.",
        )
    return session


@router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Delete a conversation thread and all related messages.
    """
    deleted = await chat_service.delete_session(db, session_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation session not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/session/{session_id}/message")
async def chat_message_stream(
    session_id: uuid.UUID,
    payload: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """
    Post a message to an existing conversation thread and receive a Server-Sent Events (SSE) stream.
    """
    session = await chat_service.get_session(db, session_id, current_user.id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation session not found or unauthorized.",
        )

    async def sse_generator() -> AsyncGenerator[str, None]:
        async for chunk in chat_service.execute_chat_stream(
            db=db,
            session_id=session_id,
            user_id=current_user.id,
            question=payload.question,
            provider_name=payload.provider,
            model_name=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            use_reranker=payload.use_reranker,
            threshold=payload.threshold,
            top_k=payload.top_k,
        ):
            yield chunk

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def chat_global_stream(
    payload: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """
    Auto-creates a conversation thread and streams the answer using Server-Sent Events (SSE).
    """
    # Auto-create session
    session = await chat_service.create_session(
        db, user_id=current_user.id, title="New Conversation"
    )

    async def sse_generator() -> AsyncGenerator[str, None]:
        async for chunk in chat_service.execute_chat_stream(
            db=db,
            session_id=session.id,
            user_id=current_user.id,
            question=payload.question,
            provider_name=payload.provider,
            model_name=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            use_reranker=payload.use_reranker,
            threshold=payload.threshold,
            top_k=payload.top_k,
        ):
            yield chunk

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
