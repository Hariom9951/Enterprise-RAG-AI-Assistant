"""
Services package — business logic layer.

Phase 2 services:
  - auth_service: registration, login, token refresh
  - user_service: user CRUD operations
"""

from app.services.auth_service import (
    authenticate_user,
    refresh_access_token,
    register_user,
)
from app.services.chat_history_service import (
    ChatHistoryService,
    chat_history_service,
)
from app.services.github_oauth_service import (
    GitHubOAuthService,
    github_oauth_service,
)
from app.services.memory_service import MemoryService, normalize_memory_content
from app.services.oauth_state_service import (
    OAuthStateService,
    oauth_state_service,
)
from app.services.token_revocation_service import (
    TokenRevocationService,
    token_revocation_service,
)
from app.services.user_service import create_user, get_user_by_email, get_user_by_id

__all__ = [
    "register_user",
    "authenticate_user",
    "refresh_access_token",
    "get_user_by_id",
    "get_user_by_email",
    "create_user",
    "MemoryService",
    "normalize_memory_content",
    "TokenRevocationService",
    "token_revocation_service",
    "ChatHistoryService",
    "chat_history_service",
    "OAuthStateService",
    "oauth_state_service",
    "GitHubOAuthService",
    "github_oauth_service",
]

