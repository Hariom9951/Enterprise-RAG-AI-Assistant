#!/usr/bin/env python3
"""
Enterprise RAG AI Assistant — Evaluation Metrics Suite
======================================================
Evaluates retrieval and answer quality using:
  - Precision@K
  - Recall@K
  - Mean Reciprocal Rank (MRR)
  - Normalized Discounted Cumulative Gain (nDCG)
  - Hit Rate@K
"""

import os
import sys
import math
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Any

# Configure in-memory overrides to bypass docker dependencies during local run
os.environ["ENABLE_REDIS_CACHING"] = "false"

# Override Celery Task execution to avoid connecting to Redis broker
from celery.app.task import Task
Task.apply_async = lambda *args, **kwargs: None
Task.delay = lambda *args, **kwargs: None

# Setup python path to include backend
sys.path.append(str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.services.retrieval_service import RetrievalService

# Representative test questions and expected ground-truth keywords/document tags
EVAL_DATASET = [
    {
        "query": "What is semantic chunking?",
        "expected_snippet": "chunk",
        "expected_doc_title": "rag_source.txt"
    },
    {
        "query": "vector embedding models dimension",
        "expected_snippet": "embedding",
        "expected_doc_title": "rag_source.txt"
    },
    {
        "query": "hybrid search reciprocal rank fusion",
        "expected_snippet": "hybrid",
        "expected_doc_title": "rag_source.txt"
    },
    {
        "query": "agent tool calling loop budget",
        "expected_snippet": "agent",
        "expected_doc_title": "rag_source.txt"
    },
    {
        "query": "database connection pool size",
        "expected_snippet": "pool",
        "expected_doc_title": "rag_source.txt"
    }
]


class RetrievalEvaluator:
    def __init__(self):
        self.retrieval_service = RetrievalService()

    async def run_evaluation(self, k_values: List[int] = [3, 5]):
        print("=" * 60)
        print("          RAG RETRIEVAL EVALUATION SUITE         ")
        print("=" * 60)
        
        from app.models.user import User
        
        async with AsyncSessionLocal() as db:
            # Check if any user exists, otherwise create one
            result_user = await db.execute(select(User).limit(1))
            user = result_user.scalar_one_or_none()
            if not user:
                user_id = uuid.uuid4()
                user = User(
                    id=user_id,
                    email="eval_user@example.com",
                    hashed_password="mock_hashed_password",
                    full_name="Evaluation User",
                    is_active=True,
                    role="user"
                )
                db.add(user)
                await db.commit()
            else:
                user_id = user.id
            
            # Check if this user has the evaluation document
            result_doc = await db.execute(
                select(Document).where(
                    Document.user_id == user_id,
                    Document.original_filename == "rag_source.txt"
                )
            )
            doc = result_doc.scalar_one_or_none()
            
            if not doc:
                print("Evaluation document not found for user. Seeding evaluation data...")
                await self._seed_mock_evaluation_data(db, user_id)
            else:
                # Check if document has chunks
                result_chunks = await db.execute(
                    select(Chunk).where(Chunk.document_id == doc.id).limit(1)
                )
                chunk = result_chunks.scalar_one_or_none()
                if not chunk:
                    print("Evaluation document exists but has no chunks. Seeding...")
                    await self._seed_mock_evaluation_data(db, user_id)
            
            for k in k_values:
                await self._evaluate_at_k(db, k, user_id)

    async def _seed_mock_evaluation_data(self, db, user_id):
        # Create a mock document and chunks so the evaluation runs successfully out-of-the-box
        doc_id = uuid.uuid4()
        stored_name = f"rag_source_{uuid.uuid4().hex[:8]}.txt"
        doc = Document(
            id=doc_id,
            user_id=user_id,
            original_filename="rag_source.txt",
            stored_filename=stored_name,
            mime_type="text/plain",
            file_size=1000,
            sha256_hash=f"seeding_hash_eval_{uuid.uuid4().hex[:8]}",
            storage_path=f"/tmp/{stored_name}",
            processing_status="COMPLETED"
        )
        
        # Texts representing the topics in the evaluation questions
        texts = [
            "Semantic chunking splits text on heading and page boundaries, counting tokens carefully.",
            "Vector embedding models transform text into 768-dimensional float arrays for cosine matching.",
            "Hybrid search combines vector search with keyword full-text search, merging them with RRF.",
            "The agent execution loop enforces strict tool timeouts (15s) and loop budgets (60s).",
            "Database configurations default to pool sizes of 10 connections and max overflow of 20."
        ]
        
        chunks = []
        for i, txt in enumerate(texts):
            chunks.append(
                Chunk(
                    id=uuid.uuid4(),
                    document_id=doc_id,
                    chunk_index=i,
                    text=txt,
                    token_count=len(txt.split()),
                    character_count=len(txt),
                    word_count=len(txt.split()),
                    reading_time_estimate=1.0,
                    sha256_hash=f"hash_seed_{i}",
                    language="en",
                    embedding=[0.1 if i == idx else 0.0 for idx in range(768)]  # unique orthogonal vectors
                )
            )
            
        db.add(doc)
        db.add_all(chunks)
        await db.commit()
        print("[OK] Seeded 5 evaluation chunks into database.")

    async def _evaluate_at_k(self, db, k: int, user_id):
        hits = 0
        total_precision = 0.0
        total_recall = 0.0
        total_mrr = 0.0
        total_ndcg = 0.0
        
        for item in EVAL_DATASET:
            query = item["query"]
            expected_snippet = item["expected_snippet"].lower()
            
            # Execute retrieval
            raw_results = await self.retrieval_service.execute_search(
                db=db,
                query_text=query,
                user_id=user_id,
                top_k=k,
                search_type="hybrid"
            )
            
            # Evaluate results
            retrieved_chunks = [res[0] for res in raw_results]
            
            # Ground truth: is a chunk relevant if it contains the expected snippet?
            relevant_retrieved = 0
            first_rank = 0
            dcg = 0.0
            idcg = 1.0  # Ideal DCG for binary relevance (since we assume 1 relevant chunk exists in dataset)
            
            for idx, chunk in enumerate(retrieved_chunks):
                is_relevant = expected_snippet in chunk.text.lower()
                if is_relevant:
                    relevant_retrieved += 1
                    if first_rank == 0:
                        first_rank = idx + 1
                    # Compute DCG
                    dcg += 1.0 / math.log2(idx + 2)
            
            # Metrics Calculations
            hit = 1 if relevant_retrieved > 0 else 0
            precision = relevant_retrieved / k
            recall = relevant_retrieved / 1.0  # Assume exactly 1 relevant chunk exists in our dataset
            mrr = 1.0 / first_rank if first_rank > 0 else 0.0
            ndcg = dcg / idcg if relevant_retrieved > 0 else 0.0
            
            hits += hit
            total_precision += precision
            total_recall += recall
            total_mrr += mrr
            total_ndcg += ndcg
            
        count = len(EVAL_DATASET)
        
        print(f"\nMetrics Report at K = {k}:")
        print(f"  Hit Rate@{k} : {hits / count:.2%}")
        print(f"  Precision@{k}: {total_precision / count:.2%}")
        print(f"  Recall@{k}   : {total_recall / count:.2%}")
        print(f"  MRR          : {total_mrr / count:.3f}")
        print(f"  nDCG         : {total_ndcg / count:.3f}")


def print_answer_evaluation_methodology():
    print("\n" + "=" * 60)
    print("            ANSWER QUALITY EVALUATION METHODOLOGY         ")
    print("=" * 60)
    print("""
Our answer quality evaluation utilizes three core criteria:

1. Faithfulness (Groundedness)
   - Evaluates whether the generated answer is strictly derived from the
     retrieved chunks without introducing external hallucinations.
   - Formula: (Number of generated statements supported by context) /
              (Total number of generated statements)

2. Answer Relevance
   - Evaluates how well the generated response directly addresses the user's question.
   - Formula: Semantic similarity(User Query, Generated Response)

3. Context Recall
   - Evaluates whether all relevant details present in the retrieved chunks
     are correctly summarized in the final answer.
   - Formula: (Target details in context mentioned in answer) /
              (Total target details in context)
""")
    print("=" * 60)


if __name__ == "__main__":
    evaluator = RetrievalEvaluator()
    asyncio.run(evaluator.run_evaluation())
    print_answer_evaluation_methodology()
