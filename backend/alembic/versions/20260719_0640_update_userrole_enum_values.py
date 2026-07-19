"""update userrole enum values

Revision ID: b308be7e5f1b
Revises: 433ba6730bf1
Create Date: 2026-07-19 06:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b308be7e5f1b'
down_revision: str | None = '433ba6730bf1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update enum values safely in PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE userrole RENAME VALUE 'user' TO 'USER'")
        op.execute("ALTER TYPE userrole RENAME VALUE 'admin' TO 'ADMIN'")
        # 2. Update default constraints
        op.alter_column('users', 'role', server_default='USER')


def downgrade() -> None:
    # 1. Revert default constraints and enum values safely in PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column('users', 'role', server_default='user')
        op.execute("ALTER TYPE userrole RENAME VALUE 'USER' TO 'user'")
        op.execute("ALTER TYPE userrole RENAME VALUE 'ADMIN' TO 'admin'")
