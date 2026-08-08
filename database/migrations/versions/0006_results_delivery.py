"""Add immutable analysis results, QA issues, report artifacts, and audit events.

Revision ID: 0006_results_delivery
Revises: 0005_product_packs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_results_delivery"
down_revision: str | None = "0005_product_packs"
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
        "analysis_run",
        _uuid_primary_key(),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("code_version", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="analysis_run_status_ck",
        ),
    )
    op.create_index(
        "analysis_run_collection_idx",
        "analysis_run",
        ["collection_run_id", "created_at"],
    )

    op.create_table(
        "analysis_result",
        _uuid_primary_key(),
        sa.Column(
            "analysis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_run.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("analysis_id", sa.Text(), nullable=False, unique=True),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("analysis_result_created_idx", "analysis_result", ["created_at"])

    op.create_table(
        "validation_issue",
        _uuid_primary_key(),
        sa.Column(
            "analysis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("issue_type", sa.Text(), nullable=False),
        sa.Column("entity_ref", postgresql.JSONB()),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB()),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("resolution", postgresql.JSONB()),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'blocker')",
            name="validation_issue_severity_ck",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')",
            name="validation_issue_status_ck",
        ),
    )
    op.create_index(
        "validation_issue_analysis_idx",
        "validation_issue",
        ["analysis_run_id", "status", "severity"],
    )

    op.create_table(
        "report_artifact",
        _uuid_primary_key(),
        sa.Column(
            "analysis_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column(
            "dataset_artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dataset_artifact.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "artifact_type IN ('html', 'xlsx', 'leadership_email', 'audit_zip')",
            name="report_artifact_type_ck",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'failed')",
            name="report_artifact_status_ck",
        ),
        sa.UniqueConstraint(
            "analysis_run_id",
            "artifact_type",
            "dataset_artifact_id",
            name="report_artifact_identity_uq",
        ),
    )
    op.create_index(
        "report_artifact_analysis_idx",
        "report_artifact",
        ["analysis_run_id", "artifact_type", "created_at"],
    )

    op.create_table(
        "audit_event",
        _uuid_primary_key(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id")),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text()),
        sa.Column("entity_id", sa.Text()),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("audit_event_entity_idx", "audit_event", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("audit_event_entity_idx", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index("report_artifact_analysis_idx", table_name="report_artifact")
    op.drop_table("report_artifact")
    op.drop_index("validation_issue_analysis_idx", table_name="validation_issue")
    op.drop_table("validation_issue")
    op.drop_index("analysis_result_created_idx", table_name="analysis_result")
    op.drop_table("analysis_result")
    op.drop_index("analysis_run_collection_idx", table_name="analysis_run")
    op.drop_table("analysis_run")
