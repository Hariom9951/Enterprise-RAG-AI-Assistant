"""
Enterprise RAG AI Assistant — Phase 5.1 OAuth Token Vault Tests
===============================================================
Comprehensive test suite for AES-256-GCM token encryption and OAuthVaultService.

Coverage:
1. AES-256-GCM encryption/decryption round-trip.
2. Repeated encryption produces distinct ciphertexts (unique 12-byte nonces).
3. Ciphertext/nonce tampering and truncation are rejected.
4. Key length/format validation and missing key failure.
5. Tokens are stored in DB strictly in encrypted binary form.
6. Authorized user can retrieve and decrypt their own credentials.
7. Cross-tenant isolation (User A cannot access/update/revoke/delete User B's records).
8. Missing connections return None / fail safely.
9. Connection revocation and deletion lifecycles.
10. Safe metadata serialization (zero secret exposure).
11. Multi-provider coexistence and duplicate provider upsert handling.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import (
    DecryptionError,
    KeyConfigurationError,
    decrypt_token,
    encrypt_token,
    parse_master_key,
)
from app.models.oauth_models import UserConnectedApp
from app.models.user import User, UserRole
from app.schemas.oauth import (
    OAuthConnectionStatus,
)
from app.services.oauth_vault_service import (
    InactiveConnectionError,
    InvalidProviderError,
    OAuthVaultService,
)

TEST_KEY_HEX = secrets.token_hex(32)  # 64 hex characters (32 bytes)
TEST_KEY_BYTES = bytes.fromhex(TEST_KEY_HEX)


@pytest.fixture(autouse=True)
def set_test_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure test key is available in environment without affecting production config."""
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", TEST_KEY_HEX)


@pytest.fixture
def vault_service() -> OAuthVaultService:
    return OAuthVaultService()


@pytest.fixture
async def test_users(db_session: AsyncSession) -> tuple[User, User]:
    """Create two test users for tenant isolation testing."""
    user_a = User(
        id=uuid.uuid4(),
        full_name="Alice Tenant",
        email=f"alice_{uuid.uuid4().hex[:8]}@tenant.test",
        hashed_password="hashed_pw_alice",
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
    )
    user_b = User(
        id=uuid.uuid4(),
        full_name="Bob Tenant",
        email=f"bob_{uuid.uuid4().hex[:8]}@tenant.test",
        hashed_password="hashed_pw_bob",
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.flush()
    return user_a, user_b


# =============================================================================
# 1. AES-256-GCM Encryption / Decryption Round-Trip
# =============================================================================


def test_encryption_decryption_round_trip() -> None:
    """Verify that encrypted plaintext decrypts back to identical string."""
    secret_text = "ya29.a0AfH6SMA-test-oauth-token-value-12345"
    encrypted = encrypt_token(secret_text, key=TEST_KEY_HEX)
    decrypted = decrypt_token(encrypted, key=TEST_KEY_HEX)
    assert decrypted == secret_text


# =============================================================================
# 2. Nonce Uniqueness
# =============================================================================


def test_repeated_encryption_produces_unique_ciphertexts() -> None:
    """Ensure every encryption generates a distinct 12-byte random nonce."""
    secret_text = "consistent-secret-token"
    enc1 = encrypt_token(secret_text, key=TEST_KEY_HEX)
    enc2 = encrypt_token(secret_text, key=TEST_KEY_HEX)
    assert enc1 != enc2
    # Nonces (bytes 1 to 13) must differ
    assert enc1[1:13] != enc2[1:13]
    # Both decrypt correctly
    assert decrypt_token(enc1, key=TEST_KEY_HEX) == secret_text
    assert decrypt_token(enc2, key=TEST_KEY_HEX) == secret_text


# =============================================================================
# 3. Tamper Resistance and Corrupted Payload Rejection
# =============================================================================


def test_ciphertext_tampering_rejected() -> None:
    """Verify that tampering with any ciphertext byte raises DecryptionError."""
    encrypted = bytearray(encrypt_token("sensitive-payload", key=TEST_KEY_HEX))
    encrypted[-1] ^= 0xFF
    with pytest.raises(DecryptionError, match="Authentication failed"):
        decrypt_token(bytes(encrypted), key=TEST_KEY_HEX)


def test_nonce_tampering_rejected() -> None:
    """Verify that tampering with the nonce raises DecryptionError."""
    encrypted = bytearray(encrypt_token("sensitive-payload", key=TEST_KEY_HEX))
    encrypted[5] ^= 0xAA
    with pytest.raises(DecryptionError, match="Authentication failed"):
        decrypt_token(bytes(encrypted), key=TEST_KEY_HEX)


def test_unsupported_version_rejected() -> None:
    """Payloads with an unsupported version byte must fail closed."""
    encrypted = bytearray(encrypt_token("payload", key=TEST_KEY_HEX))
    encrypted[0] = 0x99  # Invalid version
    with pytest.raises(DecryptionError, match="Unsupported payload version"):
        decrypt_token(bytes(encrypted), key=TEST_KEY_HEX)


def test_truncated_payload_rejected() -> None:
    """Payloads shorter than the minimum header + nonce + tag length must fail closed."""
    short_payload = b"\x01" + b"x" * 15
    with pytest.raises(DecryptionError, match="Malformed payload"):
        decrypt_token(short_payload, key=TEST_KEY_HEX)


# =============================================================================
# 4. Key Validation and Fail-Closed Behavior
# =============================================================================


def test_missing_master_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing key configuration raises KeyConfigurationError."""
    monkeypatch.delenv("ENCRYPTION_MASTER_KEY", raising=False)
    monkeypatch.setattr(
        "app.config.settings.settings.encryption_master_key", None, raising=False
    )
    with pytest.raises(KeyConfigurationError, match="not configured"):
        encrypt_token("some_token", key=None)


def test_invalid_key_length_rejected() -> None:
    """Keys with incorrect lengths must be rejected."""
    with pytest.raises(KeyConfigurationError, match="64-character hex-encoded string"):
        parse_master_key("too-short-key")

    with pytest.raises(KeyConfigurationError, match="64-character hex-encoded string"):
        parse_master_key(secrets.token_hex(16))  # 32 chars = 16 bytes

    with pytest.raises(KeyConfigurationError, match="must be exactly 32 bytes"):
        parse_master_key(b"raw_bytes_too_short")


def test_invalid_hex_key_rejected() -> None:
    """Non-hex 64-char strings must be rejected."""
    non_hex_key = "Z" * 64
    with pytest.raises(KeyConfigurationError, match="invalid hex"):
        parse_master_key(non_hex_key)


# =============================================================================
# 5. Database Storage: Tokens Stored Strictly in Encrypted Form
# =============================================================================


@pytest.mark.asyncio
async def test_tokens_stored_strictly_encrypted(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Verify raw database row contains ciphertext, never plaintext tokens."""
    user_a, _ = test_users
    raw_access = "secret-access-token-xyz-123"
    raw_refresh = "secret-refresh-token-abc-987"

    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
        access_token=raw_access,
        refresh_token=raw_refresh,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )

    stmt = select(UserConnectedApp).where(
        UserConnectedApp.user_id == user_a.id,
        UserConnectedApp.provider == "gmail",
    )
    res = await db_session.execute(stmt)
    record = res.scalar_one()

    assert isinstance(record.encrypted_access_token, bytes)
    assert raw_access.encode() not in record.encrypted_access_token
    assert record.encrypted_refresh_token is not None
    assert raw_refresh.encode() not in record.encrypted_refresh_token
    assert raw_access not in repr(record)
    assert "encrypted_access_token" not in repr(record)


# =============================================================================
# 6. Authorized Credential Retrieval
# =============================================================================


@pytest.mark.asyncio
async def test_authorized_user_retrieval(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Owning user can retrieve decrypted credentials."""
    user_a, _ = test_users
    raw_access = "github-secret-access-token"
    expiry = datetime(2027, 1, 1, 12, 0, tzinfo=UTC)

    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="github",
        access_token=raw_access,
        scopes=["repo:read"],
        expires_at=expiry,
    )

    creds = await vault_service.get_decrypted_credentials(
        db=db_session,
        user_id=user_a.id,
        provider="github",
    )
    assert creds is not None
    assert creds["access_token"] == raw_access
    assert creds["refresh_token"] is None
    assert creds["scopes"] == ["repo:read"]
    assert creds["status"] == OAuthConnectionStatus.CONNECTED.value


# =============================================================================
# 7. Cross-Tenant Isolation
# =============================================================================


@pytest.mark.asyncio
async def test_cross_tenant_isolation(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """User B cannot retrieve, update, revoke, or delete User A's connection."""
    user_a, user_b = test_users

    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="github",
        access_token="github-token-for-user-a",
        scopes=["repo:read"],
    )

    # User B attempts to read User A's Github connection
    creds_b = await vault_service.get_decrypted_credentials(
        db=db_session,
        user_id=user_b.id,
        provider="github",
    )
    assert creds_b is None

    # User B attempts to view metadata
    meta_b = await vault_service.get_connection_metadata(
        db=db_session,
        user_id=user_b.id,
        provider="github",
    )
    assert meta_b is None

    # User B attempts to revoke User A's connection
    revoked_b = await vault_service.revoke_connection(
        db=db_session,
        user_id=user_b.id,
        provider="github",
    )
    assert revoked_b is False

    # User B attempts to delete User A's connection
    deleted_b = await vault_service.delete_connection(
        db=db_session,
        user_id=user_b.id,
        provider="github",
    )
    assert deleted_b is False

    # Verify User A's credentials remain untouched and connected
    creds_a = await vault_service.get_decrypted_credentials(
        db=db_session,
        user_id=user_a.id,
        provider="github",
    )
    assert creds_a is not None
    assert creds_a["access_token"] == "github-token-for-user-a"
    assert creds_a["status"] == OAuthConnectionStatus.CONNECTED.value


# =============================================================================
# 8. Missing Connection Handling
# =============================================================================


@pytest.mark.asyncio
async def test_missing_connection_handling(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Querying non-existent connection returns None cleanly."""
    user_a, _ = test_users
    creds = await vault_service.get_decrypted_credentials(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
    )
    assert creds is None

    meta = await vault_service.get_connection_metadata(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
    )
    assert meta is None


# =============================================================================
# 9. Revocation and Deletion Lifecycles
# =============================================================================


@pytest.mark.asyncio
async def test_revocation_and_deletion(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Verify revoking updates status and deleting purges the record."""
    user_a, _ = test_users

    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
        access_token="gmail-token",
    )

    # Revoke
    success = await vault_service.revoke_connection(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
    )
    assert success is True

    meta = await vault_service.get_connection_metadata(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
    )
    assert meta is not None
    assert meta.connection_status == OAuthConnectionStatus.REVOKED.value

    # Ordinary credential retrieval must raise InactiveConnectionError
    with pytest.raises(InactiveConnectionError, match="revoked"):
        await vault_service.get_decrypted_credentials(
            db=db_session,
            user_id=user_a.id,
            provider="gmail",
        )

    # Refresh retrieval must also raise InactiveConnectionError for revoked status
    with pytest.raises(InactiveConnectionError, match="revoked"):
        await vault_service.get_credentials_for_refresh(
            db=db_session,
            user_id=user_a.id,
            provider="gmail",
        )

    # Delete
    del_success = await vault_service.delete_connection(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
    )
    assert del_success is True

    # After deletion, must not exist
    assert (
        await vault_service.get_connection_metadata(
            db=db_session, user_id=user_a.id, provider="gmail"
        )
        is None
    )


# =============================================================================
# 10. Safe Metadata Serialization (No Secrets)
# =============================================================================


@pytest.mark.asyncio
async def test_metadata_contains_zero_secrets(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Verify serialized metadata responses contain no secret fields."""
    user_a, _ = test_users
    token_secret = "super-secret-access-token"

    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="google_drive",
        access_token=token_secret,
        scopes=["drive.readonly", "drive.metadata.readonly"],
    )

    meta = await vault_service.get_connection_metadata(
        db=db_session,
        user_id=user_a.id,
        provider="google_drive",
    )
    assert meta is not None
    dumped = meta.model_dump()

    # Assert no secret keys exist in the schema
    assert "encrypted_access_token" not in dumped
    assert "encrypted_refresh_token" not in dumped
    assert "access_token" not in dumped
    assert "refresh_token" not in dumped

    # Verify JSON string contains no token text
    json_str = meta.model_dump_json()
    assert token_secret not in json_str


# =============================================================================
# 11. Multi-Provider Coexistence and Upsert
# =============================================================================


@pytest.mark.asyncio
async def test_multi_provider_and_upsert(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """User can store multiple distinct providers; re-storing updates existing connection."""
    user_a, _ = test_users

    # Store Gmail and GitHub
    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
        access_token="initial-gmail-token",
        scopes=["gmail.readonly"],
    )
    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="github",
        access_token="initial-github-token",
        scopes=["repo:read"],
    )

    connections = await vault_service.list_connections(
        db=db_session,
        user_id=user_a.id,
    )
    assert connections.total == 2
    providers = {c.provider for c in connections.connections}
    assert providers == {"gmail", "github"}

    # Upsert Gmail connection with refreshed token
    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
        access_token="refreshed-gmail-token",
        scopes=["gmail.readonly", "gmail.metadata"],
    )

    # Total must still be 2 (upserted, not duplicated)
    connections_after = await vault_service.list_connections(
        db=db_session,
        user_id=user_a.id,
    )
    assert connections_after.total == 2

    # Verify refreshed token
    updated_creds = await vault_service.get_decrypted_credentials(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
    )
    assert updated_creds is not None
    assert updated_creds["access_token"] == "refreshed-gmail-token"
    assert "gmail.metadata" in updated_creds["scopes"]


@pytest.mark.asyncio
async def test_invalid_provider_rejected(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Unsupported provider identifiers must be rejected with InvalidProviderError."""
    user_a, _ = test_users
    with pytest.raises(InvalidProviderError, match="Unsupported OAuth provider"):
        await vault_service.store_tokens(
            db=db_session,
            user_id=user_a.id,
            provider="unsupported_service",
            access_token="token",
        )


# =============================================================================
# 12. Inactive & Expired Credential Rejection (Fix 1 & Fix 4)
# =============================================================================


@pytest.mark.asyncio
async def test_inactive_and_expired_connections_rejected(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Connector calls via get_decrypted_credentials must reject expired or revoked connections."""
    user_a, _ = test_users

    # 1. Past expiration timestamp
    past_expiry = datetime.now(UTC) - timedelta(minutes=15)
    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
        access_token="expired-token",
        expires_at=past_expiry,
    )
    with pytest.raises(InactiveConnectionError, match="expired"):
        await vault_service.get_decrypted_credentials(
            db=db_session,
            user_id=user_a.id,
            provider="gmail",
        )

    # 2. Future expiration timestamp -> works normally
    future_expiry = datetime.now(UTC) + timedelta(hours=2)
    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
        access_token="active-token",
        expires_at=future_expiry,
    )
    creds = await vault_service.get_decrypted_credentials(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
    )
    assert creds is not None
    assert creds["access_token"] == "active-token"

    # 3. Connection explicitly marked expired
    stmt = select(UserConnectedApp).where(
        UserConnectedApp.user_id == user_a.id,
        UserConnectedApp.provider == "gmail",
    )
    record = (await db_session.execute(stmt)).scalar_one()
    record.connection_status = OAuthConnectionStatus.EXPIRED.value
    await db_session.flush()

    with pytest.raises(InactiveConnectionError, match="expired"):
        await vault_service.get_decrypted_credentials(
            db=db_session,
            user_id=user_a.id,
            provider="gmail",
        )

    # 4. Connection revoked
    record.connection_status = OAuthConnectionStatus.REVOKED.value
    await db_session.flush()

    with pytest.raises(InactiveConnectionError, match="revoked"):
        await vault_service.get_decrypted_credentials(
            db=db_session,
            user_id=user_a.id,
            provider="gmail",
        )


@pytest.mark.asyncio
async def test_refresh_credentials_path_permits_expired_but_rejects_revoked(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Dedicated get_credentials_for_refresh allows expired tokens to be renewed, but blocks revoked tokens."""
    user_a, _ = test_users
    past_expiry = datetime.now(UTC) - timedelta(hours=1)

    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="github",
        access_token="expired-github-access",
        refresh_token="valid-github-refresh",
        expires_at=past_expiry,
    )

    # Standard connector retrieval is blocked
    with pytest.raises(InactiveConnectionError, match="expired"):
        await vault_service.get_decrypted_credentials(
            db=db_session,
            user_id=user_a.id,
            provider="github",
        )

    # Refresh retrieval succeeds and returns decrypted refresh_token
    refresh_creds = await vault_service.get_credentials_for_refresh(
        db=db_session,
        user_id=user_a.id,
        provider="github",
    )
    assert refresh_creds is not None
    assert refresh_creds["refresh_token"] == "valid-github-refresh"

    # Now revoke connection
    await vault_service.revoke_connection(
        db=db_session,
        user_id=user_a.id,
        provider="github",
    )

    # Refresh retrieval must now fail closed
    with pytest.raises(InactiveConnectionError, match="revoked"):
        await vault_service.get_credentials_for_refresh(
            db=db_session,
            user_id=user_a.id,
            provider="github",
        )


# =============================================================================
# 13. AES-GCM Associated Authenticated Data (AAD) Cryptographic Binding (Fix 2)
# =============================================================================


@pytest.mark.asyncio
async def test_aad_binding_cryptographic_isolation(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """
    Verify that ciphertexts are cryptographically bound to owning user_id, provider, and token_type.
    Copying ciphertext to another user's or provider's record MUST fail AES-GCM authentication.
    """
    user_a, user_b = test_users

    # 1. Direct AAD cryptographic check
    aad_user_a = vault_service.build_aad(user_a.id, "gmail", "access")
    aad_user_b = vault_service.build_aad(user_b.id, "gmail", "access")
    aad_jira = vault_service.build_aad(user_a.id, "jira", "access")
    aad_refresh = vault_service.build_aad(user_a.id, "gmail", "refresh")

    ciphertext = encrypt_token(
        "secret-token", key=TEST_KEY_HEX, associated_data=aad_user_a
    )

    # Decrypt with correct AAD succeeds
    assert (
        decrypt_token(ciphertext, key=TEST_KEY_HEX, associated_data=aad_user_a)
        == "secret-token"
    )

    # Decrypt with wrong user AAD fails authentication
    with pytest.raises(DecryptionError, match="Authentication failed"):
        decrypt_token(ciphertext, key=TEST_KEY_HEX, associated_data=aad_user_b)

    # Decrypt with wrong provider AAD fails authentication
    with pytest.raises(DecryptionError, match="Authentication failed"):
        decrypt_token(ciphertext, key=TEST_KEY_HEX, associated_data=aad_jira)

    # Decrypt with wrong token_type AAD fails authentication
    with pytest.raises(DecryptionError, match="Authentication failed"):
        decrypt_token(ciphertext, key=TEST_KEY_HEX, associated_data=aad_refresh)

    # Decrypt without AAD fails authentication
    with pytest.raises(DecryptionError, match="Authentication failed"):
        decrypt_token(ciphertext, key=TEST_KEY_HEX, associated_data=None)

    # 2. Database level cross-tenant ciphertext transplant rejection
    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="gmail",
        access_token="user-a-gmail-access-token",
    )
    stmt_a = select(UserConnectedApp).where(
        UserConnectedApp.user_id == user_a.id,
        UserConnectedApp.provider == "gmail",
    )
    record_a = (await db_session.execute(stmt_a)).scalar_one()

    # Manually create a row for User B using User A's ciphertext
    malicious_record_b = UserConnectedApp(
        user_id=user_b.id,
        provider="gmail",
        encrypted_access_token=record_a.encrypted_access_token,  # Stolen ciphertext
        scopes=[],
        connection_status=OAuthConnectionStatus.CONNECTED.value,
    )
    db_session.add(malicious_record_b)
    await db_session.flush()

    # User B attempting to decrypt User A's stolen ciphertext fails authentication
    with pytest.raises(DecryptionError, match="Authentication failed"):
        await vault_service.get_decrypted_credentials(
            db=db_session,
            user_id=user_b.id,
            provider="gmail",
        )


# =============================================================================
# 14. Upsert & Savepoint Concurrency Handling (Fix 3)
# =============================================================================


@pytest.mark.asyncio
async def test_concurrent_upsert_savepoint_handling(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """
    Verify store_tokens handles duplicate / concurrent insert attempts cleanly via savepoints.

    Note on concurrency testing:
    Realistic multi-threaded concurrency under SQLite is limited because SQLite acquires a database-level
    write lock. Concurrency safety is guaranteed by the uq_user_connected_apps_user_provider unique constraint
    paired with SQLAlchemy savepoint rollback (begin_nested) and subsequent update.
    """
    user_a, _ = test_users

    # Initial insertion
    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="linkedin",
        access_token="linkedin-token-1",
        scopes=["openid", "profile"],
    )

    # Re-storing (upsert) for the same user and provider
    await vault_service.store_tokens(
        db=db_session,
        user_id=user_a.id,
        provider="linkedin",
        access_token="linkedin-token-2",
        scopes=["openid", "profile", "email"],
    )

    creds = await vault_service.get_decrypted_credentials(
        db=db_session,
        user_id=user_a.id,
        provider="linkedin",
    )
    assert creds is not None
    assert creds["access_token"] == "linkedin-token-2"
    assert "email" in creds["scopes"]

    # Verify only one row exists
    stmt = select(UserConnectedApp).where(
        UserConnectedApp.user_id == user_a.id,
        UserConnectedApp.provider == "linkedin",
    )
    records = (await db_session.execute(stmt)).scalars().all()
    assert len(records) == 1


# =============================================================================
# 16. Provider Allowlist & Inactive Provider Rejection (Phase 5.2)
# =============================================================================


def test_provider_model_and_schema_agreement() -> None:
    """Verify that model VALID_PROVIDERS exactly agrees with OAuthProvider schema values."""
    from app.models.oauth_models import VALID_PROVIDERS
    from app.schemas.oauth import OAuthProvider

    schema_providers = {p.value for p in OAuthProvider}
    assert VALID_PROVIDERS == schema_providers
    assert VALID_PROVIDERS == {"gmail", "google_drive", "github", "linkedin"}


@pytest.mark.asyncio
async def test_unsupported_and_inactive_providers_rejected(
    db_session: AsyncSession,
    vault_service: OAuthVaultService,
    test_users: tuple[User, User],
) -> None:
    """Inactive/unsupported providers (notion, jira, arbitrary) must be rejected with ValueError."""
    user_a, _ = test_users
    for inactive in ["notion", "jira", "dropbox", "slack", "arbitrary"]:
        with pytest.raises(Exception, match="Unsupported OAuth provider"):
            await vault_service.store_tokens(
                db=db_session,
                user_id=user_a.id,
                provider=inactive,
                access_token="any-token",
            )

