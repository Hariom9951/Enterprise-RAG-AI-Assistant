"""create_search_queries_table

Revision ID: 05581a690882
Revises: 51f133e6de2a
Create Date: 2026-07-18 09:09:40.924536
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '05581a690882'
down_revision: str | None = '51f133e6de2a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'search_queries',
        sa.Column('id', sa.Uuid(), nullable=False, comment='Universally unique identifier for this search query log.'),
        sa.Column('user_id', sa.Uuid(), nullable=False, comment='User who ran this search query.'),
        sa.Column('query_text', sa.String(length=1020), nullable=False, comment='The raw text query searched by the user.'),
        sa.Column('search_type', sa.String(length=20), nullable=False, comment='Type of search execution (e.g., SEMANTIC, HYBRID).'),
        sa.Column('top_k', sa.Integer(), nullable=False, comment='Configured top-k document search count.'),
        sa.Column('similarity_threshold', sa.Float(), nullable=False, comment='Configured similarity distance pruning threshold.'),
        sa.Column('total_results', sa.Integer(), nullable=False, comment='Number of semantic chunks matched and returned.'),
        sa.Column('response_time_ms', sa.Integer(), nullable=False, comment='Database search response latency in milliseconds.'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='UTC timestamp when this record was first created.'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='UTC timestamp of the most recent update to this record.'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('search_queries')
