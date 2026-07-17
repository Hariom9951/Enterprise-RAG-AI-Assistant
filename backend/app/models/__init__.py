"""
ORM model stubs — implemented in Phase 3 when the database layer is added.

Place SQLAlchemy (or other ORM) model classes here.
Example structure (Phase 3):

    from sqlalchemy import Column, String, DateTime
    from sqlalchemy.dialects.postgresql import UUID
    from app.models.base import Base

    class Document(Base):
        __tablename__ = "documents"

        id         = Column(UUID, primary_key=True, default=uuid4)
        title      = Column(String(512), nullable=False)
        created_at = Column(DateTime(timezone=True), server_default=func.now())
"""
