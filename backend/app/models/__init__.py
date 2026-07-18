"""
ORM model registry — import all models here so Alembic autogenerate
can discover every table defined in the application.

Usage (in alembic/env.py):
    from app.models import *  # noqa: F401,F403
    target_metadata = Base.metadata
"""

from app.models.chunk import Chunk  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.processed_document import ProcessedDocument  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = ["User", "Document", "ProcessedDocument", "Chunk"]
