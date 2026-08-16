"""Add durable advisory AI drafts for Matching v2 certification.

Revision ID: 0032_matching_v2_ai_drafts
Revises: 0031_seed_normalization_only
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_matching_v2_ai_drafts"
down_revision: str | None = "0031_seed_normalization_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matching_v2_ai_review_task",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "review_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("prompt_id", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("prompt_checksum", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False, server_default="openai"),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("input_checksum", sa.Text(), nullable=False),
        sa.Column("input_document", postgresql.JSONB(), nullable=False),
        sa.Column("output_checksum", sa.Text()),
        sa.Column("output_document", postgresql.JSONB()),
        sa.Column(
            "usage",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_type", sa.Text()),
        sa.Column("last_error_message", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
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
            "status IN ('queued','running','succeeded','needs_review')",
            name="matching_v2_ai_review_task_status_ck",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5",
            name="matching_v2_ai_review_task_attempts_ck",
        ),
        sa.CheckConstraint(
            "prompt_checksum ~ '^[a-f0-9]{64}$' AND input_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_ai_review_task_input_checksum_ck",
        ),
        sa.CheckConstraint(
            "output_checksum IS NULL OR output_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_ai_review_task_output_checksum_ck",
        ),
    )
    op.create_index(
        "matching_v2_ai_review_task_claim_idx",
        "matching_v2_ai_review_task",
        ["status", "lease_expires_at", "created_at"],
    )
    op.create_index(
        "matching_v2_ai_review_task_case_idx",
        "matching_v2_ai_review_task",
        ["review_case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "matching_v2_ai_review_task_case_idx",
        table_name="matching_v2_ai_review_task",
    )
    op.drop_index(
        "matching_v2_ai_review_task_claim_idx",
        table_name="matching_v2_ai_review_task",
    )
    op.drop_table("matching_v2_ai_review_task")
