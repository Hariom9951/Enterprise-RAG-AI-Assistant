"""
Enterprise RAG AI Assistant — AES-256-GCM Token Encryption Utility
==================================================================
Cryptographic vault utility for encrypting and decrypting OAuth credentials at rest.

Security Guarantees:
- Uses authenticated encryption with associated data (AEAD): AES-256-GCM.
- Generates a fresh, cryptographically secure 12-byte random nonce per encryption (NIST SP 800-38D).
- Uses a dedicated 256-bit (32-byte) ENCRYPTION_MASTER_KEY (never derived from SECRET_KEY).
- Binary payload format:
    [1-byte VERSION] + [12-byte NONCE] + [CIPHERTEXT + 16-byte GCM AUTH TAG]
- Fails closed on missing/malformed keys, corrupted payloads, tampered bytes, or version mismatch.
- Zero logging of keys, plaintext, or ciphertext.
"""

from __future__ import annotations

import os
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config.settings import settings

PAYLOAD_VERSION: Final[bytes] = b"\x01"
NONCE_LENGTH_BYTES: Final[int] = 12
TAG_LENGTH_BYTES: Final[int] = 16
MIN_PAYLOAD_LENGTH: Final[int] = (
    len(PAYLOAD_VERSION) + NONCE_LENGTH_BYTES + TAG_LENGTH_BYTES
)  # 29 bytes


class EncryptionVaultError(Exception):
    """Base exception for cryptographic vault operations."""


class KeyConfigurationError(EncryptionVaultError):
    """Raised when the master encryption key is missing, invalid, or wrong length."""


class EncryptionError(EncryptionVaultError):
    """Raised when an encryption operation fails."""


class DecryptionError(EncryptionVaultError):
    """Raised when decryption or tag authentication fails."""


def parse_master_key(raw_key: str | bytes | None) -> bytes:
    """
    Parse and validate exactly 32 bytes of key material for AES-256.

    Accepts:
      - 64-character hexadecimal string (e.g. from secrets.token_hex(32))
      - Raw 32 bytes

    Raises:
        KeyConfigurationError: If key is None, empty, wrong length, or invalid hex.
    """
    if raw_key is None:
        raise KeyConfigurationError(
            "ENCRYPTION_MASTER_KEY is not configured. A 32-byte key is strictly required."
        )

    key_bytes: bytes
    if isinstance(raw_key, str):
        cleaned = raw_key.strip()
        if not cleaned:
            raise KeyConfigurationError("ENCRYPTION_MASTER_KEY is empty.")
        if len(cleaned) == 64:
            try:
                key_bytes = bytes.fromhex(cleaned)
            except ValueError as exc:
                raise KeyConfigurationError(
                    "ENCRYPTION_MASTER_KEY is an invalid hex string."
                ) from exc
        else:
            raise KeyConfigurationError(
                f"ENCRYPTION_MASTER_KEY must be a 64-character hex-encoded string (32 bytes), got {len(cleaned)} characters."
            )
    elif isinstance(raw_key, bytes | bytearray):
        key_bytes = bytes(raw_key)
        if len(key_bytes) != 32:
            raise KeyConfigurationError(
                f"ENCRYPTION_MASTER_KEY material must be exactly 32 bytes, got {len(key_bytes)} bytes."
            )
    else:
        raise KeyConfigurationError("ENCRYPTION_MASTER_KEY must be a string or bytes.")

    return key_bytes


def get_master_key(key_override: str | bytes | None = None) -> bytes:
    """
    Resolve the active master encryption key.

    Precedence:
      1. Explicit key_override (used for dependency injection / tests)
      2. settings.encryption_master_key
      3. os.environ["ENCRYPTION_MASTER_KEY"]
    """
    if key_override is not None:
        return parse_master_key(key_override)

    configured_key = getattr(settings, "encryption_master_key", None) or os.environ.get(
        "ENCRYPTION_MASTER_KEY"
    )
    return parse_master_key(configured_key)


def encrypt_token(
    plaintext: str | bytes,
    key: str | bytes | None = None,
    associated_data: bytes | None = None,
) -> bytes:
    """
    Encrypt plaintext token with AES-256-GCM.

    Returns:
        Version (1 byte) + Nonce (12 bytes) + Ciphertext + GCM Tag (16 bytes).
    """
    key_bytes = get_master_key(key)

    if isinstance(plaintext, str):
        data = plaintext.encode("utf-8")
    elif isinstance(plaintext, bytes | bytearray):
        data = bytes(plaintext)
    else:
        raise EncryptionError("Plaintext must be str or bytes.")

    try:
        nonce = os.urandom(NONCE_LENGTH_BYTES)
        aesgcm = AESGCM(key_bytes)
        ciphertext_and_tag = aesgcm.encrypt(nonce, data, associated_data)
        return PAYLOAD_VERSION + nonce + ciphertext_and_tag
    except Exception as exc:
        raise EncryptionError(f"Encryption failed: {exc}") from exc


def decrypt_token(
    payload: bytes,
    key: str | bytes | None = None,
    associated_data: bytes | None = None,
) -> str:
    """
    Decrypt and authenticate AES-256-GCM payload.

    Returns:
        Decrypted plaintext as UTF-8 string.

    Raises:
        DecryptionError: If ciphertext is tampered, tag mismatch, or corrupted.
    """
    key_bytes = get_master_key(key)

    if not isinstance(payload, bytes | bytearray):
        raise DecryptionError("Payload must be bytes.")

    raw_payload = bytes(payload)
    if len(raw_payload) < MIN_PAYLOAD_LENGTH:
        raise DecryptionError(
            f"Malformed payload: length {len(raw_payload)} is less than minimum {MIN_PAYLOAD_LENGTH} bytes."
        )

    version_byte = raw_payload[: len(PAYLOAD_VERSION)]
    if version_byte != PAYLOAD_VERSION:
        raise DecryptionError(
            f"Unsupported payload version: {version_byte!r} (expected {PAYLOAD_VERSION!r})."
        )

    nonce = raw_payload[
        len(PAYLOAD_VERSION) : len(PAYLOAD_VERSION) + NONCE_LENGTH_BYTES
    ]
    ciphertext_and_tag = raw_payload[len(PAYLOAD_VERSION) + NONCE_LENGTH_BYTES :]

    try:
        aesgcm = AESGCM(key_bytes)
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data)
        return decrypted_bytes.decode("utf-8")
    except InvalidTag as exc:
        raise DecryptionError(
            "Authentication failed: data has been tampered with or key is incorrect."
        ) from exc
    except UnicodeDecodeError as exc:
        raise DecryptionError("Decrypted data is not a valid UTF-8 string.") from exc
    except Exception as exc:
        raise DecryptionError(f"Decryption failed: {exc}") from exc
