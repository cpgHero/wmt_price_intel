"""Add durable location-eligibility reconciliation audits.

Revision ID: 0050_location_reconcile
Revises: 0049_gate_resilience
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050_location_reconcile"
down_revision: str | None = "0049_gate_resilience"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "location_eligibility_reconciliation_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("catalog_path", sa.Text(), nullable=False),
        sa.Column("catalog_sha256", sa.Text(), nullable=False),
        sa.Column("snapshot_sha256", sa.Text(), nullable=False),
        sa.Column("reviewed_plan_sha256", sa.Text(), nullable=False),
        sa.Column(
            "retailer_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("scanned_rows", sa.Integer(), nullable=False),
        sa.Column("changed_rows", sa.Integer(), nullable=False),
        sa.Column("eligible_before", sa.Integer(), nullable=False),
        sa.Column("eligible_after", sa.Integer(), nullable=False),
        sa.Column("enabled_rows", sa.Integer(), nullable=False),
        sa.Column("disabled_rows", sa.Integer(), nullable=False),
        sa.Column("reason_counts_before", postgresql.JSONB(), nullable=False),
        sa.Column("reason_counts_after", postgresql.JSONB(), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="location_eligibility_reconciliation_status_ck",
        ),
        sa.CheckConstraint(
            "scanned_rows >= 0 AND changed_rows >= 0 AND changed_rows <= scanned_rows",
            name="location_eligibility_reconciliation_row_counts_ck",
        ),
        sa.CheckConstraint(
            "eligible_before >= 0 AND eligible_after >= 0 "
            "AND eligible_before <= scanned_rows AND eligible_after <= scanned_rows",
            name="location_eligibility_reconciliation_eligible_counts_ck",
        ),
        sa.CheckConstraint(
            "enabled_rows >= 0 AND disabled_rows >= 0 "
            "AND enabled_rows + disabled_rows <= changed_rows",
            name="location_eligibility_reconciliation_change_counts_ck",
        ),
    )
    op.create_index(
        "location_eligibility_reconciliation_started_idx",
        "location_eligibility_reconciliation_run",
        ["started_at"],
    )


def downgrade() -> None:
    audit_count = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM location_eligibility_reconciliation_run")
    )
    if int(audit_count or 0) > 0:
        raise RuntimeError(
            "cannot downgrade 0050_location_reconcile while eligibility audit history exists"
        )
    op.drop_index(
        "location_eligibility_reconciliation_started_idx",
        table_name="location_eligibility_reconciliation_run",
    )
    op.drop_table("location_eligibility_reconciliation_run")
