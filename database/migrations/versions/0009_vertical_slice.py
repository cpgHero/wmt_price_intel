"""Add availability preflight and durable analysis orchestration.

Revision ID: 0009_vertical_slice
Revises: 0008_metricscart_billing
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_vertical_slice"
down_revision: str | None = "0008_metricscart_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("collection_run_status_ck", "collection_run", type_="check")
    op.create_check_constraint(
        "collection_run_status_ck",
        "collection_run",
        "status IN ('queued', 'running', 'cancel_requested', 'cancelled', "
        "'succeeded', 'completed_with_warnings', 'failed')",
    )
    op.add_column(
        "collection_run",
        sa.Column(
            "availability_gate_status",
            sa.Text(),
            nullable=False,
            server_default="skipped",
        ),
    )
    op.add_column(
        "collection_run",
        sa.Column(
            "availability_gate_config",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_check_constraint(
        "collection_run_availability_gate_status_ck",
        "collection_run",
        "availability_gate_status IN ('skipped', 'pending', 'passed', 'failed')",
    )
    op.add_column(
        "collection_task",
        sa.Column("is_preflight", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "collection_task_preflight_claim_idx",
        "collection_task",
        ["collection_run_id", "is_preflight", "status", "available_at"],
    )

    op.add_column(
        "analysis_run",
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column("analysis_run", sa.Column("locked_by", sa.Text()))
    op.add_column("analysis_run", sa.Column("locked_at", sa.DateTime(timezone=True)))
    op.add_column("analysis_run", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "analysis_run",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_run",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column("analysis_run", sa.Column("last_error", sa.Text()))
    op.create_check_constraint(
        "analysis_run_attempt_count_ck",
        "analysis_run",
        "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10",
    )
    op.create_unique_constraint(
        "analysis_run_collection_pack_uq",
        "analysis_run",
        ["collection_run_id", "product_pack_id", "product_pack_version"],
    )
    op.create_index(
        "analysis_run_queue_claim_idx",
        "analysis_run",
        ["status", "available_at", "lease_expires_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("analysis_run_queue_claim_idx", table_name="analysis_run")
    op.drop_constraint("analysis_run_collection_pack_uq", "analysis_run", type_="unique")
    op.drop_constraint("analysis_run_attempt_count_ck", "analysis_run", type_="check")
    for column in (
        "last_error",
        "max_attempts",
        "attempt_count",
        "lease_expires_at",
        "locked_at",
        "locked_by",
        "available_at",
    ):
        op.drop_column("analysis_run", column)

    op.drop_index("collection_task_preflight_claim_idx", table_name="collection_task")
    op.drop_column("collection_task", "is_preflight")
    op.drop_constraint(
        "collection_run_availability_gate_status_ck", "collection_run", type_="check"
    )
    op.drop_column("collection_run", "availability_gate_config")
    op.drop_column("collection_run", "availability_gate_status")
    op.execute(
        "UPDATE collection_run SET status = 'succeeded' WHERE status = 'completed_with_warnings'"
    )
    op.drop_constraint("collection_run_status_ck", "collection_run", type_="check")
    op.create_check_constraint(
        "collection_run_status_ck",
        "collection_run",
        "status IN ('queued', 'running', 'cancel_requested', 'cancelled', 'succeeded', 'failed')",
    )
