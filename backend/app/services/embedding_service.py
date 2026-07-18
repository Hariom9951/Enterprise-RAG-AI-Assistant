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
from typing import Any

from loguru import logger
from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.chunk import Chunk


class EmbeddingService:
    """
    Service for loading and executing local vector embedding models.
    """

    _model: SentenceTransformer | None = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        pass

    @classmethod
    async def get_model(cls) -> SentenceTransformer:
        """
        Load and cache the SentenceTransformers model in an async-safe and thread-safe manner.
        Loads from config-defined EMBEDDING_MODEL path and loads on EMBEDDING_DEVICE.
        """
        if cls._model is None:
            async with cls._lock:
                # Double-check inside lock
                if cls._model is None:
                    model_name = settings.embedding_model
                    device = settings.embedding_device
                    logger.info(
                        f"Loading SentenceTransformers model '{model_name}' on device '{device}'..."
                    )
                    start_time = time.perf_counter()

                    # Force model loading in a separate thread to prevent blocking ASGI event loop during startup
                    cls._model = await asyncio.to_thread(
                        SentenceTransformer, model_name, device=device
                    )

                    duration = time.perf_counter() - start_time
                    logger.info(f"Loaded model successfully in {duration:.3f} seconds.")
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
