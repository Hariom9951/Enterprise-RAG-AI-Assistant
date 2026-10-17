"""
Enterprise RAG AI Assistant — OAuth Foundation & GitHub Router
==============================================================
Exposes user connection management, authorization initiation, and callback handling.
GitHub OAuth 2.0 Web Application Flow is active in Phase 5.6.2.
Other providers (Gmail, Google Drive, LinkedIn) remain 501 stubs until Phase 5.6.3+.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db.session import get_db
from app.dependencies import get_current_user, get_optional_current_user
from app.models.oauth_models import VALID_PROVIDERS
from app.models.user import User
from app.schemas.oauth import (
    OAuthAuthorizeResponse,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    OAuthConnectionStatusResponse,
    OAuthDisconnectResponse,
)
from app.services.github_oauth_service import (
    GitHubOAuthConfigurationError,
    GitHubOAuthExchangeError,
    GitHubOAuthInsufficientScopeError,
    GitHubOAuthNetworkError,
    GitHubOAuthResponseError,
    github_oauth_service,
)
from app.services.oauth_state_service import (
    OAuthInvalidRedirectError,
    OAuthSecurityError,
    OAuthStateMismatchError,
    OAuthStateReplayOrNotFoundError,
    OAuthStateStorageError,
    oauth_state_service,
)
from app.services.oauth_vault_service import OAuthVaultService

router = APIRouter()
_vault_service = OAuthVaultService()


@router.get(
    "/connections",
    response_model=OAuthConnectionStatusResponse,
    summary="List connected personal applications",
    description="Retrieve safe connection metadata and statuses for all apps linked to the current user.",
)
async def list_user_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthConnectionStatusResponse:
    """Return all personal app connections for the authenticated user without sensitive tokens."""
    return await _vault_service.list_connections(db=db, user_id=current_user.id)


@router.post(
    "/{provider}/disconnect",
    response_model=OAuthDisconnectResponse,
    summary="Disconnect a personal application",
    description="Revoke stored credentials and mark the connection as revoked in the OAuth vault.",
)
async def disconnect_provider(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthDisconnectResponse:
    """Locally revoke personal application credentials for the authenticated user."""
    norm_provider = provider.lower().strip()
    if norm_provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider!r}. Must be one of: {sorted(VALID_PROVIDERS)}.",
        )

    success = await _vault_service.revoke_connection(
        db=db,
        user_id=current_user.id,
        provider=norm_provider,
    )

    if not success:
        return OAuthDisconnectResponse(
            success=False,
            provider=norm_provider,
            message=f"No active connection found for provider '{norm_provider}'.",
        )

    return OAuthDisconnectResponse(
        success=True,
        provider=norm_provider,
        message=f"Successfully disconnected provider '{norm_provider}'.",
    )


@router.get(
    "/{provider}/authorize",
    response_model=OAuthAuthorizeResponse,
    summary="Initiate OAuth authorization flow",
    description="Generate secure state and return third-party OAuth authorization URL.",
)
async def oauth_authorize(
    provider: str,
    frontend_redirect_url: str | None = Query(
        default=None,
        description="Optional safe post-auth redirect URL (e.g. '/settings').",
    ),
    redirect: bool = Query(
        default=False,
        description="If True, return HTTP 307 redirect instead of JSON.",
    ),
    current_user: User | None = Depends(get_optional_current_user),
) -> OAuthAuthorizeResponse | RedirectResponse:
    """
    Generate cryptographically random state and construct the provider authorization URL.
    Requires an authenticated user session.
    """
    norm_provider = provider.lower().strip()
    if norm_provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider!r}. Must be one of: {sorted(VALID_PROVIDERS)}.",
        )

    if norm_provider != "github":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Provider OAuth authorization flow for '{provider}' will be activated in Phase 5.6.3+.",
        )

    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to initiate OAuth flow.",
        )


    # Check that GitHub client credentials are set
    try:
        github_oauth_service.validate_configuration()
    except GitHubOAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    # Generate short-lived, single-use state bound to user and provider
    try:
        state_res = await oauth_state_service.create_state(
            user_id=current_user.id,
            provider="github",
            frontend_redirect_url=frontend_redirect_url,
        )
    except OAuthInvalidRedirectError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except OAuthSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    callback_url = settings.get_oauth_callback_url("github")
    auth_url = github_oauth_service.get_authorization_url(
        state=state_res.state,
        redirect_uri=callback_url,
    )

    if redirect:
        return RedirectResponse(
            url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    return OAuthAuthorizeResponse(
        authorization_url=auth_url,
        provider="github",
        state=state_res.state,
    )


@router.get(
    "/{provider}/callback",
    response_model=OAuthCallbackResponse,
    summary="OAuth callback handler",
    description="Exchange authorization code, validate scopes, and persist encrypted credentials.",
)
async def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = Query(
        default=None, description="OAuth authorization code."
    ),
    state: str | None = Query(
        default=None, description="OAuth state parameter."
    ),
    error: str | None = Query(
        default=None, description="Provider error code (e.g. access_denied)."
    ),
    error_description: str | None = Query(
        default=None, description="Provider error description."
    ),
    redirect: bool = Query(
        default=False,
        description="If True, return HTTP 303 redirect instead of JSON.",
    ),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthCallbackResponse | RedirectResponse:
    """
    Process OAuth authorization callback:
    - Atomically consumes state to prevent replay attacks.
    - Validates user and provider binding.
    - Exchanges authorization code for access token via confidential client flow.
    - Validates granted scopes.
    - Stores encrypted tokens via OAuthVaultService.
    """
    norm_provider = provider.lower().strip()
    if norm_provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider!r}. Must be one of: {sorted(VALID_PROVIDERS)}.",
        )

    if norm_provider != "github":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Provider OAuth callback handler for '{provider}' will be activated in Phase 5.6.3+.",
        )

    accept_header = request.headers.get("accept", "")
    wants_browser_redirect = redirect or (
        "text/html" in accept_header and "application/json" not in accept_header
    )

    # 1. Handle user consent denial or provider-reported error
    if error:
        safe_redirect = "/settings"
        if state:
            try:
                state_data = await oauth_state_service.consume_state(
                    state=state,
                    expected_provider="github",
                    expected_user_id=None,
                )
                safe_redirect = state_data.frontend_redirect_url
            except Exception:
                pass

        err_desc = error_description or error
        if wants_browser_redirect:
            dest = f"{safe_redirect}?provider=github&status=error&error={quote_plus(error)}"
            return RedirectResponse(
                url=dest, status_code=status.HTTP_303_SEE_OTHER
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub OAuth authorization failed: {err_desc}",
        )

    # 2. Assert code and state presence
    if not code or not code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required OAuth 'code' parameter.",
        )
    if not state or not state.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required OAuth 'state' parameter.",
        )

    # 3. Account-linking guard: NEVER silently link credentials when unauthenticated!
    if current_user is None:
        if wants_browser_redirect:
            # Safe browser handoff: redirect unauthenticated browser navigations to frontend
            # handoff destination so the authenticated frontend SPA can submit the exchange
            # with its active session JWT. State is preserved and code is NOT exchanged.
            safe_redirect = await oauth_state_service.peek_redirect_url(
                state=state, expected_provider="github"
            )
            dest = f"{safe_redirect}?provider=github&code={quote_plus(code)}&state={quote_plus(state)}&action=link"
            return RedirectResponse(
                url=dest, status_code=status.HTTP_303_SEE_OTHER
            )
        # Direct API calls without authentication MUST be rejected to prevent account-linking hijacks
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to complete OAuth connection.",
        )

    # 4. Authenticated request: atomically consume and validate state with strict tenant binding
    try:
        state_data = await oauth_state_service.consume_state(
            state=state,
            expected_provider="github",
            expected_user_id=current_user.id,
        )
    except OAuthStateMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth state mismatch or invalid user session: {exc}",
        )
    except OAuthStateReplayOrNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth state is invalid, expired, or already consumed: {exc}",
        )
    except OAuthStateStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OAuth state storage unavailable: {exc}",
        )

    target_user_id = current_user.id
    safe_redirect_url = state_data.frontend_redirect_url

    # 5. Exchange authorization code with GitHub
    callback_url = settings.get_oauth_callback_url("github")
    try:
        token_data = await github_oauth_service.exchange_code_for_token(
            code=code,
            redirect_uri=callback_url,
            required_scopes=settings.github_scopes_list,
        )
    except GitHubOAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except GitHubOAuthInsufficientScopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except GitHubOAuthExchangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except (GitHubOAuthNetworkError, GitHubOAuthResponseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    # 6. Persist encrypted credentials into vault (AES-256-GCM + AAD)
    try:
        await _vault_service.store_tokens(
            db=db,
            user_id=target_user_id,
            provider="github",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            scopes=token_data.get("scopes", []),
            expires_at=token_data.get("expires_at"),
        )
    except Exception as exc:
        logger.error(f"[oauth_callback] Failed to store encrypted credentials: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store encrypted credentials.",
        )

    # 7. Response dispatch (303 Redirect for browsers vs. JSON for API clients)
    if wants_browser_redirect:
        dest_url = f"{safe_redirect_url}?provider=github&status=connected"
        return RedirectResponse(
            url=dest_url, status_code=status.HTTP_303_SEE_OTHER
        )

    return OAuthCallbackResponse(
        success=True,
        provider="github",
        message="Successfully connected GitHub application.",
        redirect_url=safe_redirect_url,
    )


@router.post(
    "/{provider}/callback",
    response_model=OAuthCallbackResponse,
    summary="Complete OAuth connection (authenticated)",
    description="Exchange authorization code, validate scopes, and persist encrypted credentials with strict user binding.",
)
async def oauth_callback_post(
    provider: str,
    payload: OAuthCallbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthCallbackResponse:
    """
    Process authenticated OAuth authorization code submission from frontend SPA.
    Atomically consumes state, verifies caller matches state owner, exchanges code,
    and stores encrypted credentials in vault.
    """
    norm_provider = provider.lower().strip()
    if norm_provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider!r}. Must be one of: {sorted(VALID_PROVIDERS)}.",
        )

    if norm_provider != "github":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Provider OAuth callback handler for '{provider}' will be activated in Phase 5.6.3+.",
        )

    # Atomically consume and validate state with strict tenant user binding
    try:
        state_data = await oauth_state_service.consume_state(
            state=payload.state,
            expected_provider="github",
            expected_user_id=current_user.id,
        )
    except OAuthStateMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth state mismatch or invalid user session: {exc}",
        )
    except OAuthStateReplayOrNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth state is invalid, expired, or already consumed: {exc}",
        )
    except OAuthStateStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OAuth state storage unavailable: {exc}",
        )

    callback_url = settings.get_oauth_callback_url("github")
    try:
        token_data = await github_oauth_service.exchange_code_for_token(
            code=payload.code,
            redirect_uri=callback_url,
            required_scopes=settings.github_scopes_list,
        )
    except GitHubOAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except GitHubOAuthInsufficientScopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except GitHubOAuthExchangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except (GitHubOAuthNetworkError, GitHubOAuthResponseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    try:
        await _vault_service.store_tokens(
            db=db,
            user_id=current_user.id,
            provider="github",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            scopes=token_data.get("scopes", []),
            expires_at=token_data.get("expires_at"),
        )
    except Exception as exc:
        logger.error(f"[oauth_callback_post] Failed to store encrypted credentials: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store encrypted credentials.",
        )

    return OAuthCallbackResponse(
        success=True,
        provider="github",
        message="Successfully connected GitHub application.",
        redirect_url=state_data.frontend_redirect_url,
    )
