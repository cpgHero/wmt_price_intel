"""Add durable batch observability for Matching v2 AI review.

Revision ID: 0033_ai_review_batches
Revises: 0032_matching_v2_ai_drafts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_ai_review_batches"
down_revision: str | None = "0032_matching_v2_ai_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matching_v2_ai_review_batch",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "review_queue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_queue.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False, server_default="openai"),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_id", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("prompt_checksum", sa.Text(), nullable=False),
        sa.Column("requested_case_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "requested_case_count BETWEEN 1 AND 25",
            name="matching_v2_ai_review_batch_case_count_ck",
        ),
    )
    op.create_index(
        "matching_v2_ai_review_batch_queue_idx",
        "matching_v2_ai_review_batch",
        ["review_queue_id", "created_at"],
    )
    op.add_column(
        "matching_v2_ai_review_task",
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        INSERT INTO matching_v2_ai_review_batch (
          id, review_queue_id, idempotency_key, requested_by,
          model_provider, model_id, prompt_id, prompt_version, prompt_checksum,
          requested_case_count, created_at, updated_at
        )
        SELECT gen_random_uuid(), c.review_queue_id, 'legacy-task:' || t.id::text,
               t.requested_by, t.model_provider, t.model_id, t.prompt_id,
               t.prompt_version, t.prompt_checksum, 1, t.created_at, t.updated_at
        FROM matching_v2_ai_review_task t
        JOIN matching_v2_review_case c ON c.id = t.review_case_id
        """
    )
    op.execute(
        """
        UPDATE matching_v2_ai_review_task task
        SET batch_id = batch.id
        FROM matching_v2_ai_review_batch batch
        WHERE batch.idempotency_key = 'legacy-task:' || task.id::text
        """
    )
    op.alter_column("matching_v2_ai_review_task", "batch_id", nullable=False)
    op.create_foreign_key(
        "matching_v2_ai_review_task_batch_fk",
        "matching_v2_ai_review_task",
        "matching_v2_ai_review_batch",
        ["batch_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "matching_v2_ai_review_task_batch_idx",
        "matching_v2_ai_review_task",
        ["batch_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "matching_v2_ai_review_task_batch_idx",
        table_name="matching_v2_ai_review_task",
    )
    op.drop_constraint(
        "matching_v2_ai_review_task_batch_fk",
        "matching_v2_ai_review_task",
        type_="foreignkey",
    )
    op.drop_column("matching_v2_ai_review_task", "batch_id")
    op.drop_index(
        "matching_v2_ai_review_batch_queue_idx",
        table_name="matching_v2_ai_review_batch",
    )
    op.drop_table("matching_v2_ai_review_batch")
