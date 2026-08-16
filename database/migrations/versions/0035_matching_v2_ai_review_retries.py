"""Add immutable retry lineage for Matching v2 AI review tasks.

Revision ID: 0035_ai_review_retries
Revises: 0034_bulk_ai_certification
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_ai_review_retries"
down_revision: str | None = "0034_bulk_ai_certification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "matching_v2_ai_review_task",
        sa.Column(
            "retry_of_task_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "matching_v2_ai_review_task",
        sa.Column(
            "retry_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "matching_v2_ai_review_task",
        sa.Column("retry_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "matching_v2_ai_review_task_retry_of_fk",
        "matching_v2_ai_review_task",
        "matching_v2_ai_review_task",
        ["retry_of_task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "matching_v2_ai_review_task_retry_lineage_ck",
        "matching_v2_ai_review_task",
        "(retry_of_task_id IS NULL AND retry_sequence = 0 AND retry_reason IS NULL) "
        "OR (retry_of_task_id IS NOT NULL AND retry_sequence BETWEEN 1 AND 3 "
        "AND length(btrim(retry_reason)) > 0)",
    )
    op.create_index(
        "matching_v2_ai_review_task_retry_of_uq",
        "matching_v2_ai_review_task",
        ["retry_of_task_id"],
        unique=True,
        postgresql_where=sa.text("retry_of_task_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "matching_v2_ai_review_task_retry_of_uq",
        table_name="matching_v2_ai_review_task",
    )
    op.drop_constraint(
        "matching_v2_ai_review_task_retry_lineage_ck",
        "matching_v2_ai_review_task",
        type_="check",
    )
    op.drop_constraint(
        "matching_v2_ai_review_task_retry_of_fk",
        "matching_v2_ai_review_task",
        type_="foreignkey",
    )
    op.drop_column("matching_v2_ai_review_task", "retry_reason")
    op.drop_column("matching_v2_ai_review_task", "retry_sequence")
    op.drop_column("matching_v2_ai_review_task", "retry_of_task_id")
