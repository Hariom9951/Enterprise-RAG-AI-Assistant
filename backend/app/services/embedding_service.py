"""
Enterprise RAG AI Assistant — Vector Embedding Service
========================================================
Manages generation of text vector embeddings using SentenceTransformers
and updates chunk records inside PostgreSQL/SQLite indexes.
"""

from __future__ import annotations

import asyncio
import datetime
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    # SentenceTransformer is only imported during type-checking (e.g. mypy, pyright).
    # At runtime the class is lazy-loaded inside get_model() to avoid pulling the
    # ~500 MB torch stack into memory on container startup.
    from sentence_transformers import SentenceTransformer

from app.config.settings import settings
from app.models.chunk import Chunk


class EmbeddingService:
    """
    Service for loading and executing local vector embedding models.
    """

    # _model holds the lazily-loaded SentenceTransformer instance.
    # The TYPE_CHECKING guard above makes the annotation valid for type checkers
    # without triggering a runtime import of the heavy sentence-transformers library.
    _model: SentenceTransformer | None = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        pass

    @classmethod
    async def get_model(cls) -> SentenceTransformer:
        """
        Lazily load and cache the SentenceTransformers model on first call.

        The import of ``sentence_transformers`` is intentionally deferred to
        this method body rather than the module level.  This prevents the
        ~500 MB library (and its transitive deps: torch, transformers, etc.)
        from being imported at container startup, which would exhaust RAM on
        memory-constrained runtimes such as Hugging Face Spaces free tier
        before the first HTTP request is received.

        Thread-safety is guaranteed by the class-level ``asyncio.Lock``.
        """
        if cls._model is None:
            async with cls._lock:
                # Double-check pattern — another coroutine may have loaded the
                # model while we were waiting for the lock.
                if cls._model is None:
                    # ── Deferred import (lazy-load) ───────────────────────────
                    # Imported here so the heavy torch/transformers stack is
                    # only pulled into memory when embedding is actually needed.
                    from sentence_transformers import (
                        SentenceTransformer,  # noqa: PLC0415
                    )

                    model_name = settings.embedding_model
                    device = settings.embedding_device
                    logger.info(
                        f"[Embedding] Lazy-loading SentenceTransformers model "
                        f"'{model_name}' on device '{device}'..."
                    )
                    start_time = time.perf_counter()

                    # Run synchronous model load in a thread pool to avoid
                    # blocking the ASGI event loop.
                    cls._model = await asyncio.to_thread(
                        SentenceTransformer, model_name, device=device
                    )

                    duration = time.perf_counter() - start_time
                    logger.info(
                        f"[Embedding] Model loaded successfully in {duration:.3f}s."
                    )
        return cls._model

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Asynchronously generate embeddings for a batch of texts using a threadpool.
        """
        start_time = time.perf_counter()
        model = await self.get_model()

        # model.encode is synchronous and cpu-heavy; run in thread pool
        embeddings = await asyncio.to_thread(
            model.encode,
            texts,
            batch_size=settings.embedding_batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Async import to prevent circular dependency
        from app.services.cache_service import cache_service

        await cache_service.record_latency("embedding", duration_ms)

        return [emb.tolist() for emb in embeddings]

    async def embed_document_chunks(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        progress_callback: Callable[[int, int], Any] | None = None,
    ) -> None:
        """
        Fetch all chunks of a document, generate embeddings in batches,
        and update the database. Runs idempotently.
        """
        query = (
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index.asc())
        )
        result = await db.execute(query)
        chunks = list(result.scalars().all())

        if not chunks:
            logger.warning(
                f"No chunks found for document {document_id}. Skipping embedding."
            )
            return

        total_chunks = len(chunks)
        logger.info(
            f"Generating embeddings for document {document_id} ({total_chunks} chunks)..."
        )

        batch_size = settings.embedding_batch_size
        model_name = settings.embedding_model
        version = "1.0.0"

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_texts = [c.text for c in batch_chunks]

            start_time = time.perf_counter()
            embeddings = await self.embed_batch(batch_texts)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Assign embeddings and metadata to Chunk records
            for idx, chunk in enumerate(batch_chunks):
                chunk.embedding = embeddings[idx]
                chunk.embedding_model = model_name
                chunk.embedding_version = version
                chunk.embedded_at = datetime.datetime.now(datetime.UTC)
                chunk.embedding_duration_ms = int(duration_ms / len(batch_chunks))

            await db.commit()

            processed = min(i + batch_size, total_chunks)
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(processed, total_chunks)
                    else:
                        progress_callback(processed, total_chunks)
                except Exception as e:
                    logger.warning(
                        f"Failed to execute embedding progress callback: {e}"
                    )

        logger.info(
            f"Finished generating embeddings for document {document_id} successfully."
        )
