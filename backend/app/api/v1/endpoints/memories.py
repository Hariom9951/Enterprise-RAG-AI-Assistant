"""
Enterprise RAG AI Assistant — User Memory Endpoints
===================================================
RESTful API endpoints for user persistent memory management.

Guarantees:
- Strict user-isolation: All operations operate solely on memories owned by the authenticated user.
- No client-controlled user IDs, provenance claiming, or arbitrary fields.
- Soft-deletion lifecycle: Inactive memories cannot be read, updated, listed, or searched.
- Search is strictly bounded to keyword matching (at most 5 results).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import ActiveUser, DBSession
from app.schemas.common import PaginatedResponse
from app.schemas.user_memory import (
    MemoryType,
    UserMemoryCreate,
    UserMemoryResponse,
    UserMemorySearchResponse,
    UserMemoryUpdate,
)
from app.services.memory_service import MemoryService

router = APIRouter()
memory_service = MemoryService()


@router.post(
    "",
    response_model=UserMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a persistent memory",
    description="Store a new active memory for the authenticated user with 'user_explicit' provenance.",
)
async def create_memory(
    payload: UserMemoryCreate,
    db: DBSession,
    current_user: ActiveUser,
) -> UserMemoryResponse:
    memory = await memory_service.create_memory(
        db=db,
        user_id=current_user.id,
        data=payload,
    )
    return UserMemoryResponse.model_validate(memory)


@router.get(
    "",
    response_model=PaginatedResponse[UserMemoryResponse],
    status_code=status.HTTP_200_OK,
    summary="List active memories",
    description="List the authenticated user's active memories with optional type filtering and pagination.",
)
async def list_memories(
    db: DBSession,
    current_user: ActiveUser,
    memory_type: Annotated[
        MemoryType | None,
        Query(description="Filter by memory type (preference, fact, goal, context)"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (max 100)")
    ] = 20,
) -> PaginatedResponse[UserMemoryResponse]:
    items, total = await memory_service.list_memories(
        db=db,
        user_id=current_user.id,
        memory_type=memory_type,
        page=page,
        page_size=page_size,
    )
    validated_items = [UserMemoryResponse.model_validate(item) for item in items]
    return PaginatedResponse.create(
        items=validated_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/search",
    response_model=UserMemorySearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search active memories",
    description="Search active memories for the authenticated user using literal keyword matching (max 5 results).",
)
async def search_memories(
    db: DBSession,
    current_user: ActiveUser,
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=200,
            description="Search query string (1 to 200 characters)",
        ),
    ],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=5,
            description="Maximum number of memories to return (capped at 5)",
        ),
    ] = 5,
) -> UserMemorySearchResponse:
    memories = await memory_service.search_memories(
        db=db,
        user_id=current_user.id,
        query=q,
        limit=limit,
    )
    validated_items = [UserMemoryResponse.model_validate(m) for m in memories]
    return UserMemorySearchResponse(
        items=validated_items,
        query=q.strip(),
        total=len(validated_items),
    )


@router.get(
    "/{memory_id}",
    response_model=UserMemoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a memory",
    description="Retrieve a single active memory owned by the authenticated user.",
)
async def get_memory(
    memory_id: uuid.UUID,
    db: DBSession,
    current_user: ActiveUser,
) -> UserMemoryResponse:
    memory = await memory_service.get_memory(
        db=db,
        user_id=current_user.id,
        memory_id=memory_id,
    )
    return UserMemoryResponse.model_validate(memory)


@router.patch(
    "/{memory_id}",
    response_model=UserMemoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an active memory",
    description="Update the content or memory type of an active memory owned by the authenticated user.",
)
async def update_memory(
    memory_id: uuid.UUID,
    payload: UserMemoryUpdate,
    db: DBSession,
    current_user: ActiveUser,
) -> UserMemoryResponse:
    memory = await memory_service.update_memory(
        db=db,
        user_id=current_user.id,
        memory_id=memory_id,
        data=payload,
    )
    return UserMemoryResponse.model_validate(memory)


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a memory",
    description="Mark an active memory as inactive (soft deletion). Idempotent for the owner.",
)
async def delete_memory(
    memory_id: uuid.UUID,
    db: DBSession,
    current_user: ActiveUser,
) -> Response:
    await memory_service.soft_delete_memory(
        db=db,
        user_id=current_user.id,
        memory_id=memory_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
