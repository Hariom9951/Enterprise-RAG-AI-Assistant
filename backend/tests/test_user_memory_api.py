"""
Enterprise RAG AI Assistant — User Memory API & Service Tests
=============================================================
Tests for persistent user memory lifecycle, security isolation,
deduplication, search, and validation constraints.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_memory import UserMemory
from app.schemas.user_memory import (
    MemoryType,
    UserMemoryCreate,
    UserMemoryUpdate,
    validate_safe_memory_content,
)
from app.services.memory_service import MemoryService, normalize_memory_content



# =============================================================================
# Helper Utilities
# =============================================================================


async def _register_and_get_token(client: AsyncClient, email: str) -> str:
    """Register a unique user and return their JWT access token."""
    password = "SecurePassword123!"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


# =============================================================================
# 1. Router Registration & Authentication Enforcement
# =============================================================================


@pytest.mark.asyncio
async def test_memory_endpoints_require_authentication(client: AsyncClient) -> None:
    """Verify that all memory endpoints reject unauthenticated requests with 401."""
    random_id = uuid.uuid4()

    # GET /api/v1/memories
    res_list = await client.get("/api/v1/memories")
    assert res_list.status_code == 401

    # POST /api/v1/memories
    res_post = await client.post(
        "/api/v1/memories",
        json={"content": "I like dark mode", "memory_type": "preference"},
    )
    assert res_post.status_code == 401

    # GET /api/v1/memories/{id}
    res_get = await client.get(f"/api/v1/memories/{random_id}")
    assert res_get.status_code == 401

    # PATCH /api/v1/memories/{id}
    res_patch = await client.patch(
        f"/api/v1/memories/{random_id}",
        json={"content": "New content"},
    )
    assert res_patch.status_code == 401

    # DELETE /api/v1/memories/{id}
    res_del = await client.delete(f"/api/v1/memories/{random_id}")
    assert res_del.status_code == 401

    # GET /api/v1/memories/search
    res_search = await client.get("/api/v1/memories/search?q=test")
    assert res_search.status_code == 401


# =============================================================================
# 2. Complete Lifecycle: Create, Read, Update, Delete
# =============================================================================


@pytest.mark.asyncio
async def test_memory_lifecycle(client: AsyncClient) -> None:
    """Test full CRUD lifecycle for active user memories."""
    token = await _register_and_get_token(client, "lifecycle_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Memory
    payload = {
        "content": "I prefer python type hints everywhere.",
        "memory_type": "preference",
    }
    create_resp = await client.post("/api/v1/memories", json=payload, headers=headers)
    assert create_resp.status_code == 201
    data = create_resp.json()
    memory_id = data["id"]
    assert data["content"] == "I prefer python type hints everywhere."
    assert data["memory_type"] == "preference"
    assert data["provenance"] == "user_explicit"
    assert data["confidence_score"] == 1.0
    assert data["is_active"] is True
    assert "metadata" in data

    # 2. Get Single Memory
    get_resp = await client.get(f"/api/v1/memories/{memory_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == memory_id

    # 3. Update Memory
    update_payload = {
        "content": "I prefer strict python type hints with mypy.",
        "memory_type": "preference",
    }
    patch_resp = await client.patch(
        f"/api/v1/memories/{memory_id}", json=update_payload, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["content"] == "I prefer strict python type hints with mypy."

    # 4. Soft Delete Memory
    del_resp = await client.delete(f"/api/v1/memories/{memory_id}", headers=headers)
    assert del_resp.status_code == 204

    # 5. Verify Soft-Deleted Memory is Not Accessible
    get_after_del = await client.get(f"/api/v1/memories/{memory_id}", headers=headers)
    assert get_after_del.status_code == 404

    # 6. Verify Deletion Idempotence for the Owner
    del_again = await client.delete(f"/api/v1/memories/{memory_id}", headers=headers)
    assert del_again.status_code == 204

    # 7. Verify List does not include the deleted memory
    list_resp = await client.get("/api/v1/memories", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 0
    assert len(list_resp.json()["items"]) == 0


# =============================================================================
# 3. Validation, Conservative Credential Screening, and Forged Fields
# =============================================================================


@pytest.mark.asyncio
async def test_validation_and_credential_screening(client: AsyncClient) -> None:
    """Test validation bounds, conservative credential rejection, and forged field rejection."""
    token = await _register_and_get_token(client, "val_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Empty content
    res_empty = await client.post(
        "/api/v1/memories",
        json={"content": "   ", "memory_type": "preference"},
        headers=headers,
    )
    assert res_empty.status_code == 422

    # Over 2000 characters
    res_long = await client.post(
        "/api/v1/memories",
        json={"content": "x" * 2001, "memory_type": "preference"},
        headers=headers,
    )
    assert res_long.status_code == 422

    # Invalid memory type
    res_bad_type = await client.post(
        "/api/v1/memories",
        json={"content": "Valid text", "memory_type": "unsupported_type"},
        headers=headers,
    )
    assert res_bad_type.status_code == 422

    # Attempt to inject forged user_id or provenance (extra fields forbidden)
    res_forged = await client.post(
        "/api/v1/memories",
        json={
            "content": "Valid text",
            "memory_type": "fact",
            "user_id": str(uuid.uuid4()),
            "provenance": "agent_extracted",
        },
        headers=headers,
    )
    assert res_forged.status_code == 422

    # Credential rejection: OpenAI key
    res_openai = await client.post(
        "/api/v1/memories",
        json={
            "content": "My key is sk-abcdef1234567890abcdef123456",
            "memory_type": "fact",
        },
        headers=headers,
    )
    assert res_openai.status_code == 422

    # Credential rejection: GitHub token
    res_gh = await client.post(
        "/api/v1/memories",
        json={
            "content": "Use ghp_1234567890abcdef1234567890abcdef1234",
            "memory_type": "fact",
        },
        headers=headers,
    )
    assert res_gh.status_code == 422

    # Credential rejection: Private key header
    res_pem = await client.post(
        "/api/v1/memories",
        json={
            "content": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
            "memory_type": "fact",
        },
        headers=headers,
    )
    assert res_pem.status_code == 422

    # Ordinary text mentioning "api", "tokens", or "keys" MUST NOT be rejected
    res_ordinary = await client.post(
        "/api/v1/memories",
        json={
            "content": "I want to learn how OAuth access tokens and API keys work securely.",
            "memory_type": "goal",
        },
        headers=headers,
    )
    assert res_ordinary.status_code == 201


# =============================================================================
# 4. Content Normalization and Deduplication
# =============================================================================


@pytest.mark.asyncio
async def test_content_deduplication(client: AsyncClient) -> None:
    """Verify duplicate detection collapses whitespace and compares case-insensitively."""
    token = await _register_and_get_token(client, "dedup_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create base memory
    res1 = await client.post(
        "/api/v1/memories",
        json={"content": "I prefer dark mode in UI.", "memory_type": "preference"},
        headers=headers,
    )
    assert res1.status_code == 201

    # 2. Attempt duplicate with varying whitespace and casing
    res_dup = await client.post(
        "/api/v1/memories",
        json={
            "content": "   i   PREFER   dark    mode   in   UI.  \n",
            "memory_type": "preference",
        },
        headers=headers,
    )
    assert res_dup.status_code == 409
    error_data = res_dup.json()
    assert "already exists" in error_data["error"]["message"].lower()

    # 3. Same content under DIFFERENT memory_type is ALLOWED
    res_diff_type = await client.post(
        "/api/v1/memories",
        json={"content": "I prefer dark mode in UI.", "memory_type": "fact"},
        headers=headers,
    )
    assert res_diff_type.status_code == 201


# =============================================================================
# 5. Multi-User Tenant Isolation
# =============================================================================


@pytest.mark.asyncio
async def test_multi_user_tenant_isolation(client: AsyncClient) -> None:
    """Verify that users cannot see, update, search, or delete each other's memories."""
    token_a = await _register_and_get_token(client, "user_a@example.com")
    token_b = await _register_and_get_token(client, "user_b@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates a memory
    res_a = await client.post(
        "/api/v1/memories",
        json={
            "content": "User A confidential architectural fact",
            "memory_type": "fact",
        },
        headers=headers_a,
    )
    assert res_a.status_code == 201
    mem_a_id = res_a.json()["id"]

    # User B can create the EXACT same content without conflict (isolated scopes)
    res_b_create = await client.post(
        "/api/v1/memories",
        json={
            "content": "User A confidential architectural fact",
            "memory_type": "fact",
        },
        headers=headers_b,
    )
    assert res_b_create.status_code == 201

    # User B cannot retrieve User A's memory (indistinguishable 404)
    res_b_get = await client.get(f"/api/v1/memories/{mem_a_id}", headers=headers_b)
    assert res_b_get.status_code == 404

    # User B cannot update User A's memory
    res_b_patch = await client.patch(
        f"/api/v1/memories/{mem_a_id}",
        json={"content": "Hacked content"},
        headers=headers_b,
    )
    assert res_b_patch.status_code == 404

    # User B cannot delete User A's memory
    res_b_del = await client.delete(f"/api/v1/memories/{mem_a_id}", headers=headers_b)
    assert res_b_del.status_code == 404

    # User B's search does not surface User A's memory
    res_b_search = await client.get(
        "/api/v1/memories/search?q=architectural", headers=headers_b
    )
    assert res_b_search.status_code == 200
    # Only User B's own memory is returned
    items = res_b_search.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] != mem_a_id


# =============================================================================
# 6. Duplicate Update Behavior
# =============================================================================


@pytest.mark.asyncio
async def test_duplicate_update_behavior(client: AsyncClient) -> None:
    """Verify that updating memory A to match existing memory B raises 409 Conflict."""
    token = await _register_and_get_token(client, "update_dup@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Create memory 1
    res1 = await client.post(
        "/api/v1/memories",
        json={"content": "Master Kubernetes", "memory_type": "goal"},
        headers=headers,
    )
    assert res1.status_code == 201
    mem1_id = res1.json()["id"]

    # Create memory 2
    res2 = await client.post(
        "/api/v1/memories",
        json={"content": "Master Rust", "memory_type": "goal"},
        headers=headers,
    )
    assert res2.status_code == 201
    mem2_id = res2.json()["id"]

    # Updating memory 2 to "Master Kubernetes" should be rejected as duplicate
    res_conflict = await client.patch(
        f"/api/v1/memories/{mem2_id}",
        json={"content": "  master   kubernetes  "},
        headers=headers,
    )
    assert res_conflict.status_code == 409

    # Updating memory 1 without changing content should succeed (does not conflict with itself)
    res_self = await client.patch(
        f"/api/v1/memories/{mem1_id}",
        json={"content": "Master Kubernetes"},
        headers=headers,
    )
    assert res_self.status_code == 200


# =============================================================================
# 7. Search Endpoint: Keyword Limits, Inactive Filtering, and Disclaimers
# =============================================================================


@pytest.mark.asyncio
async def test_search_memories_keyword_and_limits(client: AsyncClient) -> None:
    """Verify search caps results at 5, excludes inactive memories, and requires non-empty query."""
    token = await _register_and_get_token(client, "search_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Seed 6 memories containing the term 'benchmark'
    created_ids = []
    for i in range(6):
        res = await client.post(
            "/api/v1/memories",
            json={
                "content": f"Database benchmark latency metric {i}",
                "memory_type": "fact",
            },
            headers=headers,
        )
        assert res.status_code == 201
        created_ids.append(res.json()["id"])

    # Soft delete the first memory
    await client.delete(f"/api/v1/memories/{created_ids[0]}", headers=headers)

    # Empty query should fail
    res_empty = await client.get("/api/v1/memories/search?q=", headers=headers)
    assert res_empty.status_code in (400, 422)

    # Search query
    res_search = await client.get(
        "/api/v1/memories/search?q=benchmark&limit=5", headers=headers
    )
    assert res_search.status_code == 200
    search_data = res_search.json()

    # Results capped at 5
    assert len(search_data["items"]) == 5
    # Deleted memory is excluded
    returned_ids = [item["id"] for item in search_data["items"]]
    assert created_ids[0] not in returned_ids
    # Disclaimer present
    assert "Keyword match only" in search_data["disclaimer"]


# =============================================================================
# 8. Pagination and Type Filtering
# =============================================================================


@pytest.mark.asyncio
async def test_pagination_and_type_filtering(client: AsyncClient) -> None:
    """Test filtering by memory_type and bounded pagination calculation."""
    token = await _register_and_get_token(client, "paging_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Create 3 preferences and 2 goals
    for i in range(3):
        await client.post(
            "/api/v1/memories",
            json={"content": f"Preference rule {i}", "memory_type": "preference"},
            headers=headers,
        )
    for i in range(2):
        await client.post(
            "/api/v1/memories",
            json={"content": f"Goal item {i}", "memory_type": "goal"},
            headers=headers,
        )

    # Filter by preference
    res_pref = await client.get("/api/v1/memories?memory_type=preference", headers=headers)
    assert res_pref.status_code == 200
    pref_data = res_pref.json()
    assert pref_data["total"] == 3
    assert len(pref_data["items"]) == 3
    assert all(item["memory_type"] == "preference" for item in pref_data["items"])

    # Pagination: page 1 of size 2
    res_p1 = await client.get(
        "/api/v1/memories?memory_type=preference&page=1&page_size=2",
        headers=headers,
    )
    assert res_p1.status_code == 200
    p1_data = res_p1.json()
    assert len(p1_data["items"]) == 2
    assert p1_data["page"] == 1
    assert p1_data["pages"] == 2
    assert p1_data["total"] == 3


# =============================================================================
# 9. Phase 3: Explicit Memory Creation Workflow & Return Statuses
# =============================================================================


@pytest.mark.asyncio
async def test_explicit_memory_creation_workflow_statuses(
    db_session: AsyncSession,
) -> None:
    """Test MemoryService.create_explicit_memory statuses without throwing exceptions."""
    user_id = uuid.uuid4()

    # 1. Success -> CREATED
    res1 = await MemoryService.create_explicit_memory(
        db=db_session,
        user_id=user_id,
        content="Explicitly remember that I use Python 3.12.",
        memory_type=MemoryType.PREFERENCE,
        raise_on_error=False,
    )
    from app.schemas.user_memory import MemoryCreationStatus

    assert res1.status == MemoryCreationStatus.CREATED
    assert res1.memory is not None
    assert res1.memory.provenance == "user_explicit"
    assert res1.memory.confidence_score == 1.0

    # 2. Duplicate -> DUPLICATE
    res2 = await MemoryService.create_explicit_memory(
        db=db_session,
        user_id=user_id,
        content="  explicitly  remember   that  i  use  PYTHON  3.12.  ",
        memory_type=MemoryType.PREFERENCE,
        raise_on_error=False,
    )
    assert res2.status == MemoryCreationStatus.DUPLICATE
    assert res2.conflicting_memory_id == res1.memory.id
    assert "already exists" in (res2.error_message or "").lower()

    # 3. Secret -> REJECTED_SECRET
    res3 = await MemoryService.create_explicit_memory(
        db=db_session,
        user_id=user_id,
        content="Remember my OpenAI key: sk-abcdef1234567890abcdef123456",
        memory_type=MemoryType.FACT,
        raise_on_error=False,
    )
    assert res3.status == MemoryCreationStatus.REJECTED_SECRET
    assert res3.memory is None

    # 4. Transcript -> REJECTED_TRANSCRIPT
    res4 = await MemoryService.create_explicit_memory(
        db=db_session,
        user_id=user_id,
        content="User: Do you like tea?\nAssistant: Yes, tea is wonderful.",
        memory_type=MemoryType.CONTEXT,
        raise_on_error=False,
    )
    assert res4.status == MemoryCreationStatus.REJECTED_TRANSCRIPT
    assert res4.memory is None

    # 5. PII -> REJECTED_PRIVACY
    res5 = await MemoryService.create_explicit_memory(
        db=db_session,
        user_id=user_id,
        content="My credit card number is 4111-2222-3333-4444.",
        memory_type=MemoryType.FACT,
        raise_on_error=False,
    )
    assert res5.status == MemoryCreationStatus.REJECTED_PRIVACY
    assert res5.memory is None

    # 6. Invalid Type -> INVALID_CONTENT
    res6 = await MemoryService.create_explicit_memory(
        db=db_session,
        user_id=user_id,
        content="Valid text",
        memory_type="invalid_type",
        raise_on_error=False,
    )
    assert res6.status == MemoryCreationStatus.INVALID_CONTENT


# =============================================================================
# 10. Phase 3: Transcript and PII Rejection at API Boundary
# =============================================================================


@pytest.mark.asyncio
async def test_transcript_and_pii_rejection_at_api_boundary(
    client: AsyncClient,
) -> None:
    """Verify that multi-turn dialogs and sensitive PII are rejected by the API."""
    token = await _register_and_get_token(client, "privacy_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Raw transcript
    res_transcript = await client.post(
        "/api/v1/memories",
        json={
            "content": "Human: Please summarize the quarterly report.\nAI: Here is the summary.",
            "memory_type": "context",
        },
        headers=headers,
    )
    assert res_transcript.status_code == 422
    assert "conversation transcript" in res_transcript.text.lower()

    # Credit card PII
    res_card = await client.post(
        "/api/v1/memories",
        json={
            "content": "My payment card is 4111-2222-3333-4444",
            "memory_type": "fact",
        },
        headers=headers,
    )
    assert res_card.status_code == 422
    assert "personal identifier" in res_card.text.lower()

    # SSN PII
    res_ssn = await client.post(
        "/api/v1/memories",
        json={
            "content": "My SSN is 123-45-6789",
            "memory_type": "fact",
        },
        headers=headers,
    )
    assert res_ssn.status_code == 422
    assert "personal identifier" in res_ssn.text.lower()


# =============================================================================
# 11. Phase 3: Rejected Content Not Persisted & Conflicts Preserved
# =============================================================================


@pytest.mark.asyncio
async def test_rejected_content_not_persisted_and_conflict_preserved(
    client: AsyncClient,
) -> None:
    """Verify failed memory creations do not leave ghost rows and existing rows are unchanged."""
    token = await _register_and_get_token(client, "integrity_user@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a legitimate initial memory
    res_initial = await client.post(
        "/api/v1/memories",
        json={
            "content": "Original goal: finish migration review",
            "memory_type": "goal",
        },
        headers=headers,
    )
    assert res_initial.status_code == 201
    initial_id = res_initial.json()["id"]

    # 2. Attempt invalid / duplicate / credential creations
    await client.post(
        "/api/v1/memories",
        json={"content": "  ORIGINAL GOAL: finish migration review  ", "memory_type": "goal"},
        headers=headers,
    )
    await client.post(
        "/api/v1/memories",
        json={"content": "sk-12345678901234567890123456", "memory_type": "goal"},
        headers=headers,
    )
    await client.post(
        "/api/v1/memories",
        json={"content": "User: hi\nAssistant: hello", "memory_type": "goal"},
        headers=headers,
    )

    # 3. Verify total memories for user is EXACTLY 1
    res_list = await client.get("/api/v1/memories", headers=headers)
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 1
    items = res_list.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == initial_id
    # Existing content was NOT modified or corrupted by duplicate conflict attempts
    assert items[0]["content"] == "Original goal: finish migration review"

