"""
Enterprise RAG AI Assistant — Memory Service Layer
===================================================
Business logic and database data-access layer for persistent user memories.

Architectural and Security Guarantees:
- Every query enforces user ownership (UserMemory.user_id == user_id).
- Soft deletion retains records for auditability while excluding them
  from active retrieval, lists, and keyword search.
- Conservative duplicate detection normalizes content (whitespace collapse,
  casing) within user and memory_type scopes without altering displayed text.
- Prevents clients from claiming agent/system provenance or forging user ownership.
- Pure keyword-based matching for search; no external vector/embedding dependencies.
- Zero secrets or private user content logged in application traces.

Concurrency Strategy & Limitations:
- When running on PostgreSQL, a transaction-level advisory lock (via
  ``pg_advisory_xact_lock(hashtext(...))``) is acquired for the
  ``(user_id, memory_type)`` key. This serializes concurrent inserts on the
  same user/type combination without altering historical migrations or
  introducing new database constraints.
- When running on SQLite (test harness), SQLite table-level locks naturally serialize
  writes.
- In distributed environments, 32-bit hash collisions on ``hashtext`` could
  theoretically serialize two distinct user keys, which is safe but may slightly
  limit throughput if millions of concurrent memory creations occur simultaneously.
"""

from __future__ import annotations

import uuid
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, BadRequestException, ConflictException, NotFoundException
import re

from app.models.user_memory import UserMemory
from app.schemas.user_memory import (
    ExplicitMemoryResult,
    MemoryCreationStatus,
    MemoryType,
    UserMemoryCreate,
    UserMemoryResponse,
    UserMemoryUpdate,
    validate_safe_memory_content,
)


def normalize_memory_content(content: str) -> str:
    """
    Normalize content for duplicate comparison.

    Trims leading/trailing whitespace, collapses internal whitespace sequences
    to single spaces, and normalizes to lowercase.
    """
    return " ".join(content.strip().split()).lower()


_RETRIEVAL_STOP_WORDS: set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can",
    "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't",
    "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers",
    "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its",
    "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs",
    "them", "themselves", "then", "there", "there's", "these", "they",
    "they'd", "they'll", "they're", "they've", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "wasn't", "we",
    "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's",
    "when", "when's", "where", "where's", "which", "while", "who", "who's",
    "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you",
    "you'd", "you'll", "you're", "you've", "your", "yours", "yourself",
    "yourselves", "tell", "please", "want", "like", "know", "give"
}


def _estimate_memory_tokens(text: str) -> int:
    """Estimate token count using tiktoken if available, else conservative ratio."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)



class MemoryService:
    """Data-access and business logic for persistent user memories."""

    @staticmethod
    async def create_explicit_memory(
        db: AsyncSession,
        user_id: uuid.UUID,
        content: str,
        memory_type: MemoryType | str,
        raise_on_error: bool = False,
    ) -> ExplicitMemoryResult:
        """
        Explicit memory creation workflow.

        Invoked only when the user explicitly requests to remember or save information.
        Sets provenance to 'user_explicit' and confidence score to 1.0 (indicating
        user-asserted preference/fact, never external independent verification).

        Args:
            db: Active database session.
            user_id: Authenticated user ID (derived from JWT, never client input).
            content: Raw memory text.
            memory_type: Category (preference, fact, goal, context).
            raise_on_error: If True, raises HTTP/AppExceptions on invalid content or duplicates.
                           If False, returns an ExplicitMemoryResult detailing the status.

        Returns:
            ExplicitMemoryResult with outcome status, created memory, or conflict details.
        """
        # 1. Parse and validate memory type
        type_str = memory_type.value if isinstance(memory_type, MemoryType) else str(memory_type).strip().lower()
        valid_types = {t.value for t in MemoryType}
        if type_str not in valid_types:
            err_msg = f"Unsupported memory type '{type_str}'. Allowed: {', '.join(sorted(valid_types))}."
            if raise_on_error:
                raise BadRequestException(message=err_msg)
            return ExplicitMemoryResult(
                status=MemoryCreationStatus.INVALID_CONTENT,
                error_message=err_msg,
            )

        # 2. Content validation & privacy/credential screening
        try:
            cleaned_content = validate_safe_memory_content(content)
        except ValueError as val_err:
            raw_err = str(val_err)
            if "transcript" in raw_err.lower():
                status = MemoryCreationStatus.REJECTED_TRANSCRIPT
            elif "personal identifier" in raw_err.lower() or "card" in raw_err.lower() or "national id" in raw_err.lower():
                status = MemoryCreationStatus.REJECTED_PRIVACY
            elif "credential" in raw_err.lower() or "secret" in raw_err.lower():
                status = MemoryCreationStatus.REJECTED_SECRET
            else:
                status = MemoryCreationStatus.INVALID_CONTENT

            if raise_on_error:
                raise BadRequestException(message=raw_err)
            return ExplicitMemoryResult(status=status, error_message=raw_err)

        target_norm = normalize_memory_content(cleaned_content)

        try:
            # 3. Transaction-level concurrency serialization for PostgreSQL
            bind = db.get_bind()
            if bind is not None and getattr(bind.dialect, "name", "") == "postgresql":
                lock_key = f"user_memory:{user_id}:{type_str}"
                await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_key))))

            # 4. Duplicate detection in user + memory_type scope
            stmt = select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.memory_type == type_str,
                UserMemory.is_active.is_(True),
            )
            result = await db.execute(stmt)
            existing = result.scalars().all()

            for mem in existing:
                if normalize_memory_content(mem.content) == target_norm:
                    dup_msg = (
                        f"An active memory with identical content already exists under type '{type_str}'."
                    )
                    if raise_on_error:
                        raise ConflictException(
                            message=dup_msg,
                            detail={"conflicting_memory_id": str(mem.id), "memory_type": type_str},
                        )
                    return ExplicitMemoryResult(
                        status=MemoryCreationStatus.DUPLICATE,
                        conflicting_memory_id=mem.id,
                        error_message=dup_msg,
                    )

            # 5. Persist with server-controlled provenance
            memory = UserMemory(
                user_id=user_id,
                content=cleaned_content,
                memory_type=type_str,
                provenance="user_explicit",
                confidence_score=1.0,
                is_active=True,
                metadata_={},
            )
            db.add(memory)
            await db.flush()
            await db.refresh(memory)

            # Privacy-safe log: lengths and IDs only, never raw content or credentials
            logger.info(
                "Created user memory",
                extra={
                    "memory_id": str(memory.id),
                    "user_id": str(user_id),
                    "memory_type": type_str,
                    "content_length": len(cleaned_content),
                },
            )

            response_dto = UserMemoryResponse.model_validate(memory)
            result_dto = ExplicitMemoryResult(
                status=MemoryCreationStatus.CREATED,
                memory=response_dto,
            )
            # Attach private ORM reference for internal callers
            setattr(result_dto, "_raw_memory", memory)
            return result_dto

        except (ConflictException, BadRequestException):
            raise
        except SQLAlchemyError as exc:
            logger.exception("Database error while creating user memory")
            await db.rollback()
            raise AppException(
                message="A database error occurred while creating the memory.",
                status_code=500,
            ) from exc

    @staticmethod
    async def create_memory(
        db: AsyncSession,
        user_id: uuid.UUID,
        data: UserMemoryCreate,
    ) -> UserMemory:
        """
        Create a new persistent memory for the authenticated user via REST endpoint.
        Delegates to create_explicit_memory with raise_on_error=True.
        """
        result = await MemoryService.create_explicit_memory(
            db=db,
            user_id=user_id,
            content=data.content,
            memory_type=data.memory_type,
            raise_on_error=True,
        )
        raw_mem = getattr(result, "_raw_memory", None)
        if raw_mem is not None:
            return raw_mem

        # Fallback query if raw memory not attached
        stmt = select(UserMemory).where(UserMemory.id == result.memory.id)
        res = await db.execute(stmt)
        return res.scalar_one()

    @staticmethod
    async def list_memories(
        db: AsyncSession,
        user_id: uuid.UUID,
        memory_type: MemoryType | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[UserMemory], int]:
        """
        List active memories belonging to the authenticated user with pagination.
        """
        try:
            base_filters = [
                UserMemory.user_id == user_id,
                UserMemory.is_active.is_(True),
            ]
            if memory_type is not None:
                base_filters.append(UserMemory.memory_type == memory_type.value)

            # Count total matching records
            count_stmt = select(func.count(UserMemory.id)).where(*base_filters)
            count_res = await db.execute(count_stmt)
            total = count_res.scalar_one()

            # Retrieve paginated items
            offset = (page - 1) * page_size
            items_stmt = (
                select(UserMemory)
                .where(*base_filters)
                .order_by(UserMemory.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            items_res = await db.execute(items_stmt)
            items = list(items_res.scalars().all())

            return items, total

        except SQLAlchemyError as exc:
            logger.exception("Database error while listing user memories")
            raise AppException(
                message="A database error occurred while listing memories.",
                status_code=500,
            ) from exc

    @staticmethod
    async def get_memory(
        db: AsyncSession,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
    ) -> UserMemory:
        """
        Retrieve a single active memory owned by the authenticated user.

        Raises:
            NotFoundException: If missing, inactive, or belonging to another user.
        """
        try:
            stmt = select(UserMemory).where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
                UserMemory.is_active.is_(True),
            )
            result = await db.execute(stmt)
            memory = result.scalar_one_or_none()

            if memory is None:
                raise NotFoundException(message="Memory not found.")

            return memory

        except NotFoundException:
            raise
        except SQLAlchemyError as exc:
            logger.exception("Database error while retrieving user memory")
            raise AppException(
                message="A database error occurred while retrieving the memory.",
                status_code=500,
            ) from exc

    @staticmethod
    async def update_memory(
        db: AsyncSession,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        data: UserMemoryUpdate,
    ) -> UserMemory:
        """
        Update content or type of an active memory owned by the user.

        Enforces duplicate detection across other active memories of the user.
        """
        try:
            stmt = select(UserMemory).where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
                UserMemory.is_active.is_(True),
            )
            result = await db.execute(stmt)
            memory = result.scalar_one_or_none()

            if memory is None:
                raise NotFoundException(message="Memory not found.")

            target_content = (
                validate_safe_memory_content(data.content)
                if data.content is not None
                else memory.content
            )
            target_type = (
                data.memory_type.value
                if data.memory_type is not None
                else memory.memory_type
            )

            # Run duplicate check against other active memories of this type
            target_norm = normalize_memory_content(target_content)
            dup_stmt = select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.memory_type == target_type,
                UserMemory.is_active.is_(True),
                UserMemory.id != memory_id,
            )
            dup_res = await db.execute(dup_stmt)
            other_memories = dup_res.scalars().all()

            for other in other_memories:
                if normalize_memory_content(other.content) == target_norm:
                    raise ConflictException(
                        message=f"An active memory with this content already exists under type '{target_type}'.",
                        detail={"conflicting_memory_id": str(other.id), "memory_type": target_type},
                    )

            memory.content = target_content
            memory.memory_type = target_type
            await db.flush()
            await db.refresh(memory)

            logger.info(
                "Updated user memory",
                extra={
                    "memory_id": str(memory_id),
                    "user_id": str(user_id),
                    "memory_type": target_type,
                    "content_length": len(target_content),
                },
            )
            return memory

        except (NotFoundException, ConflictException, BadRequestException):
            raise
        except SQLAlchemyError as exc:
            logger.exception("Database error while updating user memory")
            await db.rollback()
            raise AppException(
                message="A database error occurred while updating the memory.",
                status_code=500,
            ) from exc

    @staticmethod
    async def soft_delete_memory(
        db: AsyncSession,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
    ) -> bool:
        """
        Soft-delete an active memory by setting is_active=False.

        Idempotent for the memory owner. Returns 404 for missing or foreign memories.
        """
        try:
            stmt = select(UserMemory).where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
            )
            result = await db.execute(stmt)
            memory = result.scalar_one_or_none()

            if memory is None:
                raise NotFoundException(message="Memory not found.")

            if memory.is_active:
                memory.is_active = False
                await db.flush()

            logger.info(
                "Soft-deleted user memory",
                extra={"memory_id": str(memory_id), "user_id": str(user_id)},
            )
            return True

        except NotFoundException:
            raise
        except SQLAlchemyError as exc:
            logger.exception("Database error while soft-deleting user memory")
            await db.rollback()
            raise AppException(
                message="A database error occurred while deleting the memory.",
                status_code=500,
            ) from exc

    @staticmethod
    async def search_memories(
        db: AsyncSession,
        user_id: uuid.UUID,
        query: str,
        limit: int = 5,
    ) -> list[UserMemory]:
        """
        Perform keyword matching on active memories belonging to the user.

        Guarantees:
        - Only searches active memories of the authenticated user.
        - Result count capped at maximum 5.
        - Uses safe parameterized search with escaped wildcard characters.
        - Pure keyword match (not semantic/vector search).
        """
        cleaned_q = query.strip()
        if not cleaned_q:
            raise BadRequestException(message="Search query cannot be empty.")
        if len(cleaned_q) > 200:
            raise BadRequestException(message="Search query cannot exceed 200 characters.")

        capped_limit = max(1, min(limit, 5))

        try:
            # Escape SQL LIKE wildcard characters for literal matching
            escaped_q = (
                cleaned_q.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )

            stmt = (
                select(UserMemory)
                .where(
                    UserMemory.user_id == user_id,
                    UserMemory.is_active.is_(True),
                    UserMemory.content.ilike(f"%{escaped_q}%", escape="\\"),
                )
                .order_by(UserMemory.updated_at.desc())
                .limit(capped_limit)
            )
            result = await db.execute(stmt)
            items = list(result.scalars().all())

            logger.info(
                "Searched user memories",
                extra={
                    "user_id": str(user_id),
                    "result_count": len(items),
                },
            )
            return items

        except BadRequestException:
            raise
        except SQLAlchemyError as exc:
            logger.exception("Database error while searching user memories")
            raise AppException(
                message="A database error occurred while searching memories.",
                status_code=500,
            ) from exc

    @staticmethod
    async def retrieve_relevant_memories(
        db: AsyncSession,
        user_id: uuid.UUID,
        question: str,
        limit: int = 5,
        max_tokens: int = 500,
    ) -> list[UserMemory]:
        """
        Bounded, relevance-ranked memory retrieval for agent context grounding.

        Guarantees:
        - Authenticated user ID enforced directly in database query (never client-controlled).
        - Retrieves only active memories belonging to this specific user.
        - Relevance scoring based on meaningful question keywords (excluding stop words).
        - Irrelevant memories (score <= 0) are strictly excluded (no blind recency inclusion).
        - Bounded result count: at most 5 memories.
        - Strict token budget: stops before exceeding max_tokens (default 500 tokens).
        - Pure keyword and relevance matching; zero third-party or vector dependencies.
        - Read-only; performs no writes or automated extraction.

        Limitations:
        - Keyword matching is lexical and does not perform semantic embeddings or vector search.
          Synonyms not present in the memory text will not match.
        """
        cleaned_question = question.strip()
        if not cleaned_question:
            return []

        words = re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", cleaned_question.lower())
        keywords = {w for w in words if w not in _RETRIEVAL_STOP_WORDS and len(w) >= 3}

        preference_intent_words = {
            "preference", "preferences", "prefer", "style", "formatting",
            "setting", "settings", "profile", "goal", "goals", "habit", "background"
        }
        has_preference_intent = bool(set(words).intersection(preference_intent_words))

        if not keywords and not has_preference_intent:
            return []

        try:
            stmt = select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.is_active.is_(True),
            )
            result = await db.execute(stmt)
            candidates = list(result.scalars().all())

            if not candidates:
                return []

            scored_candidates: list[tuple[float, UserMemory]] = []
            for mem in candidates:
                if not mem.content or not mem.content.strip():
                    continue

                norm_text = normalize_memory_content(mem.content)
                mem_tokens = set(re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", norm_text))

                score = 0.0
                # Exact token overlap
                token_matches = len(keywords.intersection(mem_tokens))
                score += token_matches * 2.0

                # Substring matching for compound keywords (e.g. 'python3', 'darkmode')
                for kw in keywords:
                    if kw in norm_text and kw not in mem_tokens:
                        score += 1.0

                # Memory type boost if the question explicitly refers to preferences or goals
                if has_preference_intent and mem.memory_type in ("preference", "goal"):
                    score += 1.5

                if score > 0.0:
                    scored_candidates.append((score, mem))

            if not scored_candidates:
                return []

            # Sort by relevance score descending, then recency descending
            scored_candidates.sort(key=lambda x: (x[0], x[1].updated_at), reverse=True)

            max_count = min(limit, 5)
            selected: list[UserMemory] = []
            current_tokens = 0

            for _score, mem in scored_candidates:
                if len(selected) >= max_count:
                    break
                mem_tokens = _estimate_memory_tokens(mem.content) + 15
                if current_tokens + mem_tokens > max_tokens:
                    break
                selected.append(mem)
                current_tokens += mem_tokens

            logger.info(
                "Retrieved relevant memories for agent context",
                extra={
                    "user_id": str(user_id),
                    "candidate_count": len(candidates),
                    "matched_count": len(scored_candidates),
                    "selected_count": len(selected),
                    "token_estimate": current_tokens,
                },
            )
            return selected

        except SQLAlchemyError as exc:
            logger.exception("Database error while retrieving relevant memories")
            return []
        except Exception as exc:
            logger.warning(f"Unexpected error in memory retrieval: {exc}")
            return []

