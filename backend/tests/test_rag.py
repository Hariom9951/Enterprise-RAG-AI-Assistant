"""
Enterprise RAG AI Assistant — RAG Integration & Unit Tests
============================================================
Tests context assembly, LLM provider payload formatting, citations, and API routes.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.services.llm_providers import (
    GeminiProvider,
    LLMProviderError,
    OpenAIProvider,
)
from app.services.rag_service import RAGService


# Helper to register and login a user for API testing
async def _register_and_login(client: AsyncClient, email: str) -> str:
    password = "SecurePassword123!"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return resp.json()["access_token"]


class TestLLMProviders:
    """Tests the httpx REST payload generation and response parsing for providers."""

    @pytest.mark.asyncio
    async def test_gemini_provider_success(self) -> None:
        """Verify that Gemini provider parses REST response and token usage details correctly."""
        provider = GeminiProvider(api_key="mock_key", model=settings.gemini_model)

        mock_response = httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Gemini response text [1]."}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 15,
                    "candidatesTokenCount": 8,
                    "totalTokenCount": 23,
                },
            },
        )

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            text, usage = await provider.generate_response(
                system_prompt="sys", user_prompt="usr", temperature=0.2, max_tokens=100
            )
            mock_post.assert_called_once()
            assert text == "Gemini response text [1]."
            assert usage["prompt_tokens"] == 15
            assert usage["completion_tokens"] == 8
            assert usage["total_tokens"] == 23

    @pytest.mark.asyncio
    async def test_openai_provider_success(self) -> None:
        """Verify that OpenAI provider parses standard API responses correctly."""
        provider = OpenAIProvider(api_key="mock_key", model="gpt-4o-mini")

        mock_response = httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "OpenAI response text [1].",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 6,
                    "total_tokens": 18,
                },
            },
        )

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            text, usage = await provider.generate_response(
                system_prompt="sys", user_prompt="usr", temperature=0.2, max_tokens=100
            )
            mock_post.assert_called_once()
            assert text == "OpenAI response text [1]."
            assert usage["prompt_tokens"] == 12
            assert usage["completion_tokens"] == 6
            assert usage["total_tokens"] == 18

    @pytest.mark.asyncio
    async def test_provider_missing_keys(self) -> None:
        """Ensure provider initialization raises errors if credentials are missing."""
        with patch("app.services.llm_providers.settings.gemini_api_key", None):
            gemini = GeminiProvider(api_key=None)
            with pytest.raises(LLMProviderError):
                await gemini.generate_response("sys", "usr")


class TestRAGService:
    """Tests context slicing, prompts, and pipeline execution inside RAGService."""

    @pytest.mark.asyncio
    async def test_context_assembly_and_token_budgeting(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Verify that context assembly strictly honors maximum token budgets."""
        user_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="large_context.txt",
            stored_filename="large_context.txt",
            mime_type="text/plain",
            file_size=1000,
            sha256_hash="hashlarge",
            storage_path="/tmp/large.txt",
            processing_status="COMPLETED",
        )
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="First extremely long segment representation...",
            token_count=10,
            character_count=50,
            word_count=5,
            reading_time_estimate=1.0,
            sha256_hash="hashc1",
            embedding=[0.1] * 768,
        )
        c2 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=1,
            text="Second extremely long segment representation...",
            token_count=10,
            character_count=50,
            word_count=5,
            reading_time_estimate=1.0,
            sha256_hash="hashc2",
            embedding=[0.2] * 768,
        )
        db_session.add_all([doc, c1, c2])
        await db_session.commit()

        rag_service = RAGService()

        # Test 1: budget supports both chunks
        context_str_all, included_all = rag_service._assemble_context(
            [(c1, doc, 0.9), (c2, doc, 0.8)], max_tokens=1000
        )
        assert len(included_all) == 2
        assert "First extremely long" in context_str_all
        assert "Second extremely long" in context_str_all

        # Test 2: budget only supports 1 chunk
        context_str_limited, included_limited = rag_service._assemble_context(
            [(c1, doc, 0.9), (c2, doc, 0.8)],
            max_tokens=60,  # Slices before the second chunk can fit
        )
        assert len(included_limited) == 1
        assert "Second extremely long" not in context_str_limited

    @pytest.mark.asyncio
    async def test_citation_parsing(self) -> None:
        """Verify that citations are extracted based on chunk pointers correctly."""
        rag_service = RAGService()
        doc = Document(id=uuid.uuid4(), original_filename="source.pdf")
        c1 = Chunk(id=uuid.uuid4(), text="First facts text block", page_number=1)
        c2 = Chunk(id=uuid.uuid4(), text="Second facts text block", page_number=3)

        included_chunks = [(c1, doc, 0.9, 1), (c2, doc, 0.8, 2)]

        # Simulate LLM response mentioning chunk 1
        citations = rag_service._generate_citations(
            "The revenue was positive [1].", included_chunks
        )
        assert len(citations) == 1
        assert citations[0]["citation_index"] == 1
        assert citations[0]["document_title"] == "source.pdf"
        assert citations[0]["page_number"] == 1

        # Simulate LLM response mentioning both chunks
        citations_both = rag_service._generate_citations(
            "Revenue rose [1] and costs fell [2].", included_chunks
        )
        assert len(citations_both) == 2
        assert citations_both[1]["citation_index"] == 2
        assert citations_both[1]["page_number"] == 3


class TestRAGEndpoints:
    """Tests the REST endpoints for query generation, models listing, and statistics."""

    @pytest.fixture()
    def mock_vector(self) -> list[float]:
        return [0.1] * 768

    @pytest.mark.asyncio
    async def test_rag_query_pipeline_and_api(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        mock_vector: list[float],
    ) -> None:
        """Validate query endpoint pipelines, stats log generation, and citation returns."""
        token = await _register_and_login(client, "raguser@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        result_user = await db_session.execute(
            select(User).where(User.email == "raguser@example.com")
        )
        user = result_user.scalar_one()

        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            user_id=user.id,
            original_filename="rag_source.txt",
            stored_filename="rag_source.txt",
            mime_type="text/plain",
            file_size=100,
            sha256_hash="hashragdoc",
            storage_path="/tmp/rag_source.txt",
            processing_status="COMPLETED",
        )
        c1 = Chunk(
            id=uuid.uuid4(),
            document_id=doc_id,
            chunk_index=0,
            text="Enterprise vector database details.",
            token_count=5,
            character_count=35,
            word_count=5,
            reading_time_estimate=1.0,
            sha256_hash="hashragc1",
            language="en",
            embedding=mock_vector,
        )
        db_session.add_all([doc, c1])
        await db_session.commit()

        # Mocks
        mock_llm_response = (
            "Grounded response content [1].",
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        with (
            patch(
                "app.services.embedding_service.EmbeddingService.embed_batch",
                return_value=[mock_vector],
            ),
            patch(
                "app.services.llm_providers.GeminiProvider.generate_response",
                return_value=mock_llm_response,
            ),
        ):
            payload = {
                "question": "What are the vector database details?",
                "top_k": 3,
                "threshold": 0.0,
                "provider": "gemini",
            }

            # 1. Test POST /api/v1/rag/query
            resp = await client.post("/api/v1/rag/query", json=payload, headers=headers)
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert "answer" in data
            assert data["answer"] == "Grounded response content [1]."
            assert len(data["citations"]) == 1
            assert data["citations"][0]["document_title"] == "rag_source.txt"
            assert data["tokens_used"]["total_tokens"] == 15

            # 2. Test POST /api/v1/rag/query/document/{id}
            resp_scoped = await client.post(
                f"/api/v1/rag/query/document/{doc_id}", json=payload, headers=headers
            )
            assert resp_scoped.status_code == 200, resp_scoped.text
            scoped_data = resp_scoped.json()
            assert len(scoped_data["retrieved_chunks"]) == 1

            # 3. Test GET /api/v1/rag/models
            resp_models = await client.get("/api/v1/rag/models", headers=headers)
            assert resp_models.status_code == 200
            models = resp_models.json()
            assert len(models) == 3
            assert models[0]["provider"] == "GEMINI"

            # 4. Test GET /api/v1/rag/statistics
            resp_stats = await client.get("/api/v1/rag/statistics", headers=headers)
            assert resp_stats.status_code == 200
            stats = resp_stats.json()
            assert stats["total_queries"] >= 2
            assert stats["total_tokens_used"] >= 30
            assert stats["provider_distribution"]["GEMINI"] >= 2
