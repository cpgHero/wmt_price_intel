"""Add durable governed AI task audit records.

Revision ID: 0013_governed_ai
Revises: 0012_product_details
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_governed_ai"
down_revision: str | None = "0012_product_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_task",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "analysis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("analysis_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("prompt_template_id", sa.Text(), nullable=False),
        sa.Column("prompt_template_version", sa.Text(), nullable=False),
        sa.Column("prompt_template_checksum", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("input_checksum", sa.Text(), nullable=False),
        sa.Column("input_document", postgresql.JSONB(), nullable=False),
        sa.Column("output_checksum", sa.Text()),
        sa.Column("output_document", postgresql.JSONB()),
        sa.Column(
            "validation",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
            "role IN ('insight', 'narrative')",
            name="agent_task_role_ck",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'needs_review')",
            name="agent_task_status_ck",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5",
            name="agent_task_attempts_ck",
        ),
    )
    op.create_index(
        "agent_task_analysis_idx",
        "agent_task",
        ["analysis_run_id", "role", "created_at"],
    )
    op.create_index(
        "agent_task_lease_idx",
        "agent_task",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("agent_task_lease_idx", table_name="agent_task")
    op.drop_index("agent_task_analysis_idx", table_name="agent_task")
    op.drop_table("agent_task")
