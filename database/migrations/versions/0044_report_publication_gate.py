"""Add the durable report-publication trust gate.

Revision ID: 0044_report_pub_gate
Revises: 0043_comp_portfolio_mat
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_report_pub_gate"
down_revision: str | None = "0043_comp_portfolio_mat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing reports have already passed their historical release process. New
    # results start pending and become visible only after the durable gate passes.
    op.add_column(
        "analysis_result",
        sa.Column(
            "reporting_status",
            sa.Text(),
            nullable=False,
            server_default="ready",
        ),
    )
    op.create_check_constraint(
        "analysis_result_reporting_status_ck",
        "analysis_result",
        "reporting_status IN ('pending', 'ready', 'blocked')",
    )
    op.alter_column(
        "analysis_result",
        "reporting_status",
        server_default="pending",
    )
    op.create_index(
        "analysis_result_reporting_status_idx",
        "analysis_result",
        ["reporting_status", "created_at"],
    )

    op.create_table(
        "report_materialization_job",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "analysis_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="awaiting_publication",
        ),
        sa.Column("stage", sa.Text(), nullable=False, server_default="awaiting_publication"),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("work_plan", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("audit_document", postgresql.JSONB()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
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
            "status IN ('awaiting_publication', 'queued', 'running', 'retry_wait', "
            "'succeeded', 'blocked')",
            name="report_materialization_job_status_ck",
        ),
        sa.CheckConstraint(
            "progress_current >= 0 AND progress_total >= 0 AND progress_current <= progress_total",
            name="report_materialization_job_progress_ck",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="report_materialization_job_attempts_ck",
        ),
    )
    op.create_index(
        "report_materialization_job_claim_idx",
        "report_materialization_job",
        ["status", "available_at", "lease_expires_at", "created_at"],
    )

    op.create_table(
        "report_materialization_stage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("report_materialization_job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_kind", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
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
            "document_kind IN ('price_architecture', 'competitive_portfolio')",
            name="report_materialization_stage_kind_ck",
        ),
        sa.UniqueConstraint(
            "job_id",
            "document_kind",
            "scope_key",
            name="report_materialization_stage_scope_uq",
        ),
    )
    op.create_index(
        "report_materialization_stage_job_idx",
        "report_materialization_stage",
        ["job_id", "document_kind"],
    )


def downgrade() -> None:
    op.drop_index("report_materialization_stage_job_idx", table_name="report_materialization_stage")
    op.drop_table("report_materialization_stage")
    op.drop_index("report_materialization_job_claim_idx", table_name="report_materialization_job")
    op.drop_table("report_materialization_job")
    op.drop_index("analysis_result_reporting_status_idx", table_name="analysis_result")
    op.drop_constraint(
        "analysis_result_reporting_status_ck",
        "analysis_result",
        type_="check",
    )
    op.drop_column("analysis_result", "reporting_status")
