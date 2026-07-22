"""Prevent duplicate active incidents for the same deterministic rule.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "observability"


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("deduplication_key", sa.String(255), nullable=True),
        schema=SCHEMA,
    )
    op.execute(
        sa.text(
            """
            UPDATE observability.incidents
            SET deduplication_key = 'legacy:' || id::text
            WHERE deduplication_key IS NULL
            """
        )
    )
    op.alter_column("incidents", "deduplication_key", nullable=False, schema=SCHEMA)
    op.create_index(
        "uq_incidents_active_deduplication",
        "incidents",
        ["deduplication_key"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status IN ('open', 'acknowledged')"),
    )


def downgrade() -> None:
    op.drop_index("uq_incidents_active_deduplication", table_name="incidents", schema=SCHEMA)
    op.drop_column("incidents", "deduplication_key", schema=SCHEMA)
