"""
Enterprise RAG AI Assistant — Secure OAuth Credential Vault Service
====================================================================
Manages the lifecycle of encrypted OAuth access/refresh credentials for personal applications.

Tenant Isolation & Security Guarantees:
- Every query strictly bounds UserConnectedApp by (user_id, provider).
- Plaintext tokens are encrypted immediately before database write using AES-256-GCM.
- Tokens are decrypted in-memory only upon explicit retrieval by the owning user.
- Zero logging of tokens, keys, plaintext, or ciphertext.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_token, encrypt_token
from app.models.oauth_models import VALID_PROVIDERS, UserConnectedApp
from app.schemas.oauth import (
    OAuthConnectionMetadata,
    OAuthConnectionStatus,
    OAuthConnectionStatusResponse,
)

AAD_CONTEXT_PREFIX: Final[str] = "nexusai:oauth:v1"


class OAuthVaultError(Exception):
    """Base exception for OAuth credential vault service."""


class InvalidProviderError(OAuthVaultError):
    """Raised when an unsupported provider is requested."""


class InactiveConnectionError(OAuthVaultError):
    """Raised when attempting to retrieve credentials for an inactive (revoked or expired) connection."""


class OAuthVaultService:
    """Service providing encrypted storage and retrieval for personal application tokens."""

    @staticmethod
    def _validate_provider(provider: str) -> str:
        norm = provider.lower().strip()
        if norm not in VALID_PROVIDERS:
            raise InvalidProviderError(
                f"Unsupported OAuth provider: {provider!r}. Must be one of: {sorted(VALID_PROVIDERS)}."
            )
        return norm

    @classmethod
    def build_aad(
        cls,
        user_id: uuid.UUID,
        provider: str,
        token_type: str = "access",
    ) -> bytes:
        """
        Generate associated authenticated data (AAD) binding ciphertext to tenant, provider, and token type.

        Format: nexusai:oauth:v1:<user_uuid>:<provider>:<token_type>
        """
        norm_provider = provider.lower().strip()
        return f"{AAD_CONTEXT_PREFIX}:{user_id!s}:{norm_provider}:{token_type}".encode()

    async def store_tokens(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
        key: str | bytes | None = None,
    ) -> UserConnectedApp:
        """
        Encrypt and persist access and refresh tokens for the given user and provider.
        If an entry already exists for (user_id, provider), updates tokens, scopes, and expiry.
        Applies AES-256-GCM authenticated encryption with AAD bound to user and provider.
        Handles concurrent insert races gracefully via database savepoints.
        """
        norm_provider = self._validate_provider(provider)

        if not access_token:
            raise ValueError("access_token cannot be empty.")

        access_aad = self.build_aad(user_id, norm_provider, "access")
        refresh_aad = self.build_aad(user_id, norm_provider, "refresh")

        enc_access = encrypt_token(access_token, key=key, associated_data=access_aad)
        enc_refresh = (
            encrypt_token(refresh_token, key=key, associated_data=refresh_aad)
            if refresh_token
            else None
        )

        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user_id,
            UserConnectedApp.provider == norm_provider,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()

        if record is None:
            record = UserConnectedApp(
                user_id=user_id,
                provider=norm_provider,
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                scopes=scopes or [],
                expires_at=expires_at,
                connection_status=OAuthConnectionStatus.CONNECTED.value,
            )
            db.add(record)
            try:
                async with db.begin_nested():
                    await db.flush()
            except IntegrityError:
                # Concurrent insert race: another transaction committed or flushed (user_id, provider) first.
                # The nested savepoint rolled back cleanly. Query the existing record and update.
                stmt = select(UserConnectedApp).where(
                    UserConnectedApp.user_id == user_id,
                    UserConnectedApp.provider == norm_provider,
                )
                res = await db.execute(stmt)
                record = res.scalar_one()
                record.encrypted_access_token = enc_access
                if enc_refresh is not None:
                    record.encrypted_refresh_token = enc_refresh
                if scopes is not None:
                    record.scopes = scopes
                record.expires_at = expires_at
                record.connection_status = OAuthConnectionStatus.CONNECTED.value
                await db.flush()
        else:
            record.encrypted_access_token = enc_access
            if enc_refresh is not None:
                record.encrypted_refresh_token = enc_refresh
            if scopes is not None:
                record.scopes = scopes
            record.expires_at = expires_at
            record.connection_status = OAuthConnectionStatus.CONNECTED.value
            await db.flush()

        return record

    async def get_decrypted_credentials(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        provider: str,
        key: str | bytes | None = None,
    ) -> dict[str, Any] | None:
        """
        Retrieve and decrypt active credentials for the owning user and provider.

        Enforces:
        - Strict tenant ownership (user_id and provider).
        - Connection must be active (status == 'connected').
        - Access token must not be expired if an expiry timestamp is set.

        Raises:
            InactiveConnectionError: If connection is revoked, marked expired, or past its expiration timestamp.

        Returns:
            Dictionary with 'access_token', 'refresh_token', 'scopes', 'expires_at', and 'status'.
            Returns None if no connection exists for (user_id, provider).
        """
        norm_provider = self._validate_provider(provider)

        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user_id,
            UserConnectedApp.provider == norm_provider,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()

        if record is None:
            return None

        # Fix 1: Reject inactive credentials
        if record.connection_status == OAuthConnectionStatus.REVOKED.value:
            raise InactiveConnectionError(
                f"Connection for provider '{norm_provider}' has been revoked."
            )

        if record.connection_status == OAuthConnectionStatus.EXPIRED.value:
            raise InactiveConnectionError(
                f"Connection for provider '{norm_provider}' is marked expired."
            )

        if record.connection_status != OAuthConnectionStatus.CONNECTED.value:
            raise InactiveConnectionError(
                f"Connection for provider '{norm_provider}' is inactive (status: {record.connection_status})."
            )

        if record.expires_at is not None:
            exp = (
                record.expires_at
                if record.expires_at.tzinfo is not None
                else record.expires_at.replace(tzinfo=UTC)
            )
            if exp <= datetime.now(UTC):
                raise InactiveConnectionError(
                    f"Access token for provider '{norm_provider}' expired at {exp.isoformat()}."
                )

        access_aad = self.build_aad(user_id, norm_provider, "access")
        access_token = decrypt_token(
            record.encrypted_access_token, key=key, associated_data=access_aad
        )

        refresh_token = None
        if record.encrypted_refresh_token:
            refresh_aad = self.build_aad(user_id, norm_provider, "refresh")
            refresh_token = decrypt_token(
                record.encrypted_refresh_token, key=key, associated_data=refresh_aad
            )

        return {
            "provider": record.provider,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "scopes": record.scopes,
            "expires_at": record.expires_at,
            "status": record.connection_status,
        }

    async def get_credentials_for_refresh(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        provider: str,
        key: str | bytes | None = None,
    ) -> dict[str, Any] | None:
        """
        Retrieve decrypted refresh credentials exclusively for OAuth token renewal flows.

        Enforces:
        - Strict tenant ownership (user_id and provider).
        - Rejects revoked connections (InactiveConnectionError) — revoked tokens can NEVER be refreshed.
        - Permits expired connections having a valid encrypted_refresh_token.
        - Returns None if connection does not exist or has no refresh token.
        """
        norm_provider = self._validate_provider(provider)

        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user_id,
            UserConnectedApp.provider == norm_provider,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()

        if record is None:
            return None

        if record.connection_status == OAuthConnectionStatus.REVOKED.value:
            raise InactiveConnectionError(
                f"Cannot refresh credentials: connection for provider '{norm_provider}' has been revoked."
            )

        if not record.encrypted_refresh_token:
            return None

        refresh_aad = self.build_aad(user_id, norm_provider, "refresh")
        refresh_token = decrypt_token(
            record.encrypted_refresh_token, key=key, associated_data=refresh_aad
        )

        return {
            "provider": record.provider,
            "refresh_token": refresh_token,
            "scopes": record.scopes,
            "expires_at": record.expires_at,
            "status": record.connection_status,
        }

    async def get_connection_metadata(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        provider: str,
    ) -> OAuthConnectionMetadata | None:
        """Retrieve safe connection metadata without secret tokens."""
        norm_provider = self._validate_provider(provider)

        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user_id,
            UserConnectedApp.provider == norm_provider,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if record is None:
            return None

        return OAuthConnectionMetadata.model_validate(record)

    async def list_connections(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> OAuthConnectionStatusResponse:
        """List safe metadata for all connected apps owned by user_id."""
        stmt = (
            select(UserConnectedApp)
            .where(UserConnectedApp.user_id == user_id)
            .order_by(UserConnectedApp.created_at.asc())
        )
        res = await db.execute(stmt)
        records = res.scalars().all()

        metas = [OAuthConnectionMetadata.model_validate(r) for r in records]
        return OAuthConnectionStatusResponse(connections=metas, total=len(metas))

    async def revoke_connection(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        provider: str,
    ) -> bool:
        """
        Mark connection as revoked locally in the vault and clear stored refresh token.

        Important Security & Integration Semantics:
        - Updates the local vault status to 'revoked' and nullifies encrypted_refresh_token.
        - Prevents ordinary credential retrieval (calls to get_decrypted_credentials will raise InactiveConnectionError).
        - Prevents future token refresh (calls to get_credentials_for_refresh will raise InactiveConnectionError).
        - Does NOT make outbound HTTP calls to third-party OAuth provider endpoints (Google, Notion, Jira).
          Provider-side OAuth token revocation will be integrated in Phase 5.2 alongside live API connectors.

        Returns True if found and revoked, False if connection does not exist.
        """
        norm_provider = self._validate_provider(provider)

        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user_id,
            UserConnectedApp.provider == norm_provider,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if record is None:
            return False

        record.connection_status = OAuthConnectionStatus.REVOKED.value
        record.encrypted_access_token = b""
        record.encrypted_refresh_token = None
        await db.flush()
        return True

    async def mark_connection_expired(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        provider: str,
    ) -> bool:
        """
        Mark connection status as 'expired' for the given user and provider.
        Strictly scoped to (user_id, provider) to eliminate cross-tenant impact.
        Returns True if marked expired, False if no connection was found.
        """
        norm_provider = self._validate_provider(provider)

        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user_id,
            UserConnectedApp.provider == norm_provider,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if record is None:
            return False

        if record.connection_status == OAuthConnectionStatus.CONNECTED.value:
            record.connection_status = OAuthConnectionStatus.EXPIRED.value
            await db.flush()
        return True

    async def delete_connection(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        provider: str,
    ) -> bool:
        """Permanently purge a connection and its credentials. Returns True if deleted, False otherwise."""
        norm_provider = self._validate_provider(provider)

        stmt = select(UserConnectedApp).where(
            UserConnectedApp.user_id == user_id,
            UserConnectedApp.provider == norm_provider,
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if record is None:
            return False

        await db.delete(record)
        await db.flush()
        return True
