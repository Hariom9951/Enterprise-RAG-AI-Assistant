"""
Enterprise RAG AI Assistant — Users Endpoints
=============================================
User profile management endpoints.

Routes:
    GET /users/me  — Retrieve the authenticated user's own profile
"""

from fastapi import APIRouter, status

from app.dependencies import ActiveUser
from app.schemas.auth import UserResponse

router = APIRouter()


# =============================================================================
# Get Current User Profile
# =============================================================================


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get my profile",
    description=(
        "Returns the profile of the currently authenticated user. "
        "Requires a valid JWT access token in the Authorization header."
    ),
    tags=["users"],
)
async def get_me(current_user: ActiveUser) -> UserResponse:
    """
    **Retrieve the authenticated user's profile.**

    - Requires ``Authorization: Bearer <access_token>`` header.
    - Returns 401 if the token is missing or invalid.
    - Returns 403 if the account is suspended.
    """
    return UserResponse.model_validate(current_user)
