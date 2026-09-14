"""Add explicit customer report access grants.

Revision ID: 0057_customer_report_access
Revises: 0056_customer_auth_provisioning
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057_customer_report_access"
down_revision: str | None = "0056_customer_auth_provisioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_primary_key() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "customer_report_access",
        _uuid_primary_key(),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "analysis_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"),
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active','revoked','expired')",
            name="customer_report_access_status_ck",
        ),
    )
    op.create_index(
        "customer_report_access_account_level_uq",
        "customer_report_access",
        ["account_id", "analysis_result_id"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NULL"),
    )
    op.create_index(
        "customer_report_access_workspace_level_uq",
        "customer_report_access",
        ["account_id", "workspace_id", "analysis_result_id"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )
    op.create_index(
        "customer_report_access_account_idx",
        "customer_report_access",
        ["account_id", "status", "created_at"],
    )
    op.create_index(
        "customer_report_access_workspace_idx",
        "customer_report_access",
        ["workspace_id", "status", "created_at"],
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )
    op.create_index(
        "customer_report_access_analysis_idx",
        "customer_report_access",
        ["analysis_result_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "customer_report_access_workspace_level_uq",
        table_name="customer_report_access",
    )
    op.drop_index(
        "customer_report_access_account_level_uq",
        table_name="customer_report_access",
    )
    op.drop_index("customer_report_access_analysis_idx", table_name="customer_report_access")
    op.drop_index("customer_report_access_workspace_idx", table_name="customer_report_access")
    op.drop_index("customer_report_access_account_idx", table_name="customer_report_access")
    op.drop_table("customer_report_access")
