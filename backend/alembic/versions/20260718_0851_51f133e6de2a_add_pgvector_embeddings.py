"""add_pgvector_embeddings

Revision ID: 51f133e6de2a
Revises: 224c26d47e35
Create Date: 2026-07-18 08:51:41.407013
"""

from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '51f133e6de2a'
down_revision: str | None = '224c26d47e35'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable extension only if dialect is PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Add columns
    op.add_column('chunks', sa.Column('embedding', pgvector.sqlalchemy.Vector(768), nullable=True, comment='Vector embedding of the chunk text.'))
    op.add_column('chunks', sa.Column('embedding_model', sa.String(length=255), nullable=True, comment='Name of the embedding model used.'))
    op.add_column('chunks', sa.Column('embedding_version', sa.String(length=50), nullable=True, comment='Version of the embedding pipeline.'))
    op.add_column('chunks', sa.Column('embedded_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when the embedding was generated.'))
    op.add_column('chunks', sa.Column('embedding_duration_ms', sa.Integer(), nullable=True, comment='Duration of embedding generation in milliseconds.'))

    # 3. Create pgvector index only on PostgreSQL
    if is_postgres:
        op.create_index('ix_chunks_embedding', 'chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Drop index only on PostgreSQL
    if is_postgres:
        op.drop_index('ix_chunks_embedding', table_name='chunks', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})

    # 2. Drop columns
    op.drop_column('chunks', 'embedding_duration_ms')
    op.drop_column('chunks', 'embedded_at')
    op.drop_column('chunks', 'embedding_version')
    op.drop_column('chunks', 'embedding_model')
    op.drop_column('chunks', 'embedding')
