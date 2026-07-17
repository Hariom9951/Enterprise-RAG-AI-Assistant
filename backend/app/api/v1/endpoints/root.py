"""
Enterprise RAG AI Assistant — API v1 Endpoints: Root
=====================================================
GET /  →  {"message": "Enterprise RAG AI Assistant API"}
"""

from fastapi import APIRouter
from fastapi import status

from app.schemas.common import MessageResponse

router = APIRouter()


@router.get(
    "/",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Root",
    description="Returns a welcome message confirming the API is reachable.",
    tags=["root"],
)
async def root() -> MessageResponse:
    """
    **Root endpoint.**

    Returns a simple JSON message that confirms the API gateway is up.
    This endpoint is intentionally unauthenticated so that infrastructure
    health-probes can reach it without credentials.
    """
    return MessageResponse(message="Enterprise RAG AI Assistant API")
