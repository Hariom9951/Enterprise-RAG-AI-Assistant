"""
Service layer stubs — implemented in Phase 4 when RAG features are added.

Services encapsulate business logic and coordinate between:
  - API endpoints (presentation layer)
  - Repositories / ORM models (data layer)
  - External providers (LLM, vector store, etc.)

Example structure (Phase 4):

    class DocumentService:
        def __init__(self, db: AsyncSession, vector_store: VectorStore):
            self.db = db
            self.vector_store = vector_store

        async def ingest(self, file: UploadFile) -> Document:
            ...

        async def search(self, query: str, top_k: int = 5) -> list[Chunk]:
            ...
"""
