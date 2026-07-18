"""create_rag_queries_table

Revision ID: 6bcda2f24301
Revises: 05581a690882
Create Date: 2026-07-18 09:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6bcda2f24301'
down_revision: str | None = '05581a690882'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'rag_queries',
        sa.Column('id', sa.Uuid(), nullable=False, comment='Universally unique identifier for this RAG query log.'),
        sa.Column('user_id', sa.Uuid(), nullable=False, comment='User who ran this search query.'),
        sa.Column('query_text', sa.String(length=1020), nullable=False, comment='The raw text query asked by the user.'),
        sa.Column('answer_text', sa.Text(), nullable=False, comment='The generated RAG answer.'),
        sa.Column('provider', sa.String(length=50), nullable=False, comment='LLM Provider used (gemini, openai, ollama).'),
        sa.Column('model_name', sa.String(length=100), nullable=False, comment='Name of the model used.'),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, comment='Tokens used in the prompt context.'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, comment='Tokens generated in completion.'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, comment='Total token usage.'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, comment='Total latency of the search + generation in milliseconds.'),
        sa.Column('confidence_score', sa.Float(), nullable=False, comment='Calculated confidence score based on similarity.'),
        sa.Column('citations', sa.JSON(), nullable=True, comment='Citations associated with chunks in the answer.'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='UTC timestamp when this record was first created.'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='UTC timestamp of the most recent update to this record.'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('rag_queries')
