"""Archive obsolete analysis results without deleting their audit history.

Revision ID: 0016_analysis_archival
Revises: 0015_analysis_publications
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0016_analysis_archival"
down_revision: str | None = "0015_analysis_publications"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("analysis_result", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.create_index(
        "analysis_result_active_created_idx",
        "analysis_result",
        ["created_at"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("analysis_result_active_created_idx", table_name="analysis_result")
    op.drop_column("analysis_result", "archived_at")
