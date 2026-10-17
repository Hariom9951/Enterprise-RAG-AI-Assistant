"""
Enterprise RAG AI Assistant — UserMemory Model & Migration Tests (Phase 1)
===========================================================================
Validates:
1. SQLAlchemy metadata registration, column definitions, and primary/foreign keys.
2. Check constraints on memory_type, provenance, and confidence_score.
3. User foreign-key association and active/inactive lifecycle states.
4. SQLite test compatibility.
5. Migration graph linear continuity without applying migrations to production.
"""

from __future__ import annotations

import uuid
import sys
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import Base
from app.models.user import User
from app.models.user_memory import (
    VALID_MEMORY_TYPES,
    VALID_PROVENANCE_TYPES,
    UserMemory,
)


async def _create_test_user(db: AsyncSession, email: str = "memory_user@example.com") -> User:
    """Helper to create and persist an active test user."""
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name="Memory Test User",
        hashed_password=hash_password("SecurePass@123"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# =============================================================================
# 1. Metadata & Model Registration Tests
# =============================================================================


def test_user_memory_metadata_registration() -> None:
    """Verify that UserMemory table and columns are properly registered in Base.metadata."""
    table = Base.metadata.tables.get("user_memories")
    assert table is not None, "Table 'user_memories' must be in Base.metadata"

    expected_cols = {
        "id",
        "user_id",
        "content",
        "memory_type",
        "provenance",
        "confidence_score",
        "is_active",
        "metadata",
        "created_at",
        "updated_at",
    }
    actual_cols = {c.name for c in table.columns}
    assert expected_cols.issubset(actual_cols)

    # Verify primary key
    assert len(table.primary_key.columns) == 1
    assert "id" in table.primary_key.columns

    # Verify foreign key to users.id
    fks = list(table.foreign_keys)
    assert len(fks) >= 1
    user_fk = next((fk for fk in fks if fk.target_fullname == "users.id"), None)
    assert user_fk is not None
    assert user_fk.ondelete == "CASCADE"


def test_user_memory_table_args_constraints_and_indexes() -> None:
    """Verify check constraints and composite indexes are configured on UserMemory."""
    table = Base.metadata.tables["user_memories"]

    # Check constraint names
    ck_names = {ck.name for ck in table.constraints if hasattr(ck, "name") and ck.name}
    assert "ck_user_memories_memory_type" in ck_names
    assert "ck_user_memories_provenance" in ck_names
    assert "ck_user_memories_confidence_score" in ck_names

    # Indexes
    index_names = {idx.name for idx in table.indexes}
    assert "ix_user_memories_user_active" in index_names
    assert "ix_user_memories_user_type" in index_names


# =============================================================================
# 2. CRUD & Lifecycle Tests (SQLite Compatibility)
# =============================================================================


@pytest.mark.asyncio
async def test_create_valid_user_memories(db_session: AsyncSession) -> None:
    """Test successful creation and retrieval of user memories across all valid types."""
    user = await _create_test_user(db_session, "valid_types@example.com")

    memories_to_create = [
        UserMemory(
            user_id=user.id,
            content="Prefers concise technical answers in bullet points.",
            memory_type="preference",
            provenance="user_explicit",
            confidence_score=1.0,
            metadata_={"category": "style"},
        ),
        UserMemory(
            user_id=user.id,
            content="Working on project Apollo migration to Kubernetes.",
            memory_type="fact",
            provenance="agent_extracted",
            confidence_score=0.88,
            metadata_={"source_session": str(uuid.uuid4())},
        ),
        UserMemory(
            user_id=user.id,
            content="Target Q4 milestone: complete zero-trust access implementation.",
            memory_type="goal",
            provenance="user_explicit",
            confidence_score=0.95,
        ),
        UserMemory(
            user_id=user.id,
            content="Primary role: Senior Infrastructure Architect.",
            memory_type="context",
            provenance="system",
            confidence_score=None,
        ),
    ]

    db_session.add_all(memories_to_create)
    await db_session.commit()

    # Query all active memories for this user
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == user.id, UserMemory.is_active.is_(True))
        .order_by(UserMemory.created_at.asc())
    )
    result = await db_session.execute(stmt)
    records = list(result.scalars().all())

    assert len(records) == 4
    types_found = {r.memory_type for r in records}
    assert types_found == {"preference", "fact", "goal", "context"}

    # Verify representations and metadata
    pref = next(r for r in records if r.memory_type == "preference")
    assert pref.provenance == "user_explicit"
    assert pref.confidence_score == 1.0
    assert pref.metadata_ == {"category": "style"}
    assert repr(pref).startswith("<UserMemory")


@pytest.mark.asyncio
async def test_active_and_soft_delete_lifecycle(db_session: AsyncSession) -> None:
    """Verify that is_active flag reliably distinguishes active from archived/soft-deleted memories."""
    user = await _create_test_user(db_session, "lifecycle@example.com")

    m1 = UserMemory(
        user_id=user.id,
        content="Active preference 1",
        memory_type="preference",
        is_active=True,
    )
    m2 = UserMemory(
        user_id=user.id,
        content="Active preference 2",
        memory_type="preference",
        is_active=True,
    )
    db_session.add_all([m1, m2])
    await db_session.commit()

    # Soft-delete m1
    m1.is_active = False
    await db_session.commit()

    # Default query: only active
    active_stmt = select(UserMemory).where(
        UserMemory.user_id == user.id,
        UserMemory.is_active.is_(True),
    )
    active_res = await db_session.execute(active_stmt)
    active_records = list(active_res.scalars().all())

    assert len(active_records) == 1
    assert active_records[0].id == m2.id

    # Management query: include all states
    all_stmt = select(UserMemory).where(UserMemory.user_id == user.id)
    all_res = await db_session.execute(all_stmt)
    all_records = list(all_res.scalars().all())
    assert len(all_records) == 2


@pytest.mark.asyncio
async def test_user_memory_isolation_and_hard_delete(db_session: AsyncSession) -> None:
    """Verify tenant isolation between users and hard deletion semantics."""
    user_a = await _create_test_user(db_session, "user_a@example.com")
    user_b = await _create_test_user(db_session, "user_b@example.com")

    mem_a = UserMemory(
        user_id=user_a.id,
        content="User A private secret preference",
        memory_type="preference",
    )
    mem_b = UserMemory(
        user_id=user_b.id,
        content="User B private secret preference",
        memory_type="preference",
    )
    db_session.add_all([mem_a, mem_b])
    await db_session.commit()

    # User B query must strictly NEVER return User A's memory
    b_stmt = select(UserMemory).where(UserMemory.user_id == user_b.id)
    b_records = list((await db_session.execute(b_stmt)).scalars().all())
    assert len(b_records) == 1
    assert b_records[0].content == "User B private secret preference"
    assert b_records[0].user_id == user_b.id

    # Hard deletion of User A's memory
    await db_session.delete(mem_a)
    await db_session.commit()

    # Confirm permanent removal
    a_stmt = select(UserMemory).where(UserMemory.id == mem_a.id)
    a_records = list((await db_session.execute(a_stmt)).scalars().all())
    assert len(a_records) == 0


@pytest.mark.asyncio
async def test_invalid_memory_type_rejected(db_session: AsyncSession) -> None:
    """Check constraint rejects invalid memory types."""
    user = await _create_test_user(db_session, "bad_type@example.com")
    user_id = user.id

    bad_memory = UserMemory(
        user_id=user_id,
        content="This has an illegal memory type.",
        memory_type="illegal_type",
        provenance="user_explicit",
    )
    db_session.add(bad_memory)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_invalid_provenance_rejected(db_session: AsyncSession) -> None:
    """Check constraint rejects invalid provenance values."""
    user = await _create_test_user(db_session, "bad_prov@example.com")
    user_id = user.id

    bad_memory = UserMemory(
        user_id=user_id,
        content="This has an illegal provenance.",
        memory_type="fact",
        provenance="untrusted_ai",
    )
    db_session.add(bad_memory)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_invalid_confidence_score_rejected(db_session: AsyncSession) -> None:
    """Check constraint enforces confidence_score boundaries in [0.0, 1.0]."""
    user = await _create_test_user(db_session, "bad_conf@example.com")
    user_id = user.id

    # Score > 1.0
    too_high = UserMemory(
        user_id=user_id,
        content="Confidence too high",
        memory_type="fact",
        confidence_score=1.5,
    )
    db_session.add(too_high)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # Score < 0.0
    too_low = UserMemory(
        user_id=user_id,
        content="Confidence too low",
        memory_type="fact",
        confidence_score=-0.2,
    )
    db_session.add(too_low)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# =============================================================================
# 3. Alembic Migration Graph Integrity Tests
# =============================================================================


def test_alembic_migration_graph_continuity() -> None:
    """Verify that Alembic migration history is single-headed and properly ordered."""
    import ast
    from pathlib import Path
    import subprocess

    backend_dir = Path(__file__).resolve().parent.parent

    # 1. Parse migration file AST to verify identifiers without package conflict
    migration_file = backend_dir / "alembic" / "versions" / "20261016_add_user_memories_table.py"
    assert migration_file.exists(), f"Migration file must exist at {migration_file}"

    tree = ast.parse(migration_file.read_text(encoding="utf-8"))
    variables: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if isinstance(node.value, ast.Constant):
                variables[node.target.id] = node.value.value
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value, ast.Constant):
                    variables[t.id] = node.value.value

    assert variables.get("revision") == "e7f8a9b0c1d2"
    assert variables.get("down_revision") == "d4e5f6a7b8c9"

    # 2. Run alembic CLI in subprocess to guarantee full migration graph integrity
    alembic_exe = Path(sys.prefix) / "Scripts" / "alembic.exe"
    cmd = (
        [str(alembic_exe), "heads"]
        if alembic_exe.exists()
        else [sys.executable, "-m", "alembic", "heads"]
    )
    res = subprocess.run(
        cmd,
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"alembic heads failed: {res.stderr}"
    lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
    assert len(lines) == 1, f"Expected exactly 1 migration head, got: {lines}"
    assert "e7f8a9b0c1d2" in lines[0]
