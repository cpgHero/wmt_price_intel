"""Add immutable governed analysis publications.

Revision ID: 0015_analysis_publications
Revises: 0014_report_renderer_versions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_analysis_publications"
down_revision: str | None = "0014_report_renderer_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_publication",
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
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="ready_to_share"),
        sa.Column("source_result_checksum", sa.Text(), nullable=False),
        sa.Column("publication_checksum", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "presentation_context",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("version > 0", name="analysis_publication_version_ck"),
        sa.CheckConstraint(
            "status IN ('ready_to_share', 'superseded')",
            name="analysis_publication_status_ck",
        ),
        sa.UniqueConstraint(
            "analysis_result_id",
            "version",
            name="analysis_publication_version_uq",
        ),
        sa.UniqueConstraint(
            "analysis_result_id",
            "publication_checksum",
            name="analysis_publication_checksum_uq",
        ),
    )
    op.create_index(
        "analysis_publication_latest_idx",
        "analysis_publication",
        ["analysis_result_id", "version"],
    )

    op.add_column(
        "report_artifact",
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_publication.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.drop_constraint(
        "report_artifact_renderer_identity_uq",
        "report_artifact",
        type_="unique",
    )
    op.create_index(
        "report_artifact_base_identity_uq",
        "report_artifact",
        ["analysis_run_id", "artifact_type", "renderer_version"],
        unique=True,
        postgresql_where=sa.text("publication_id IS NULL"),
    )
    op.create_index(
        "report_artifact_publication_identity_uq",
        "report_artifact",
        ["publication_id", "artifact_type", "renderer_version"],
        unique=True,
        postgresql_where=sa.text("publication_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("report_artifact_publication_identity_uq", table_name="report_artifact")
    op.drop_index("report_artifact_base_identity_uq", table_name="report_artifact")
    op.execute(
        """
        UPDATE report_artifact
        SET renderer_version = renderer_version || '-publication-' || publication_id::text
        WHERE publication_id IS NOT NULL
        """
    )
    op.drop_column("report_artifact", "publication_id")
    op.create_unique_constraint(
        "report_artifact_renderer_identity_uq",
        "report_artifact",
        ["analysis_run_id", "artifact_type", "renderer_version"],
    )
    op.drop_index("analysis_publication_latest_idx", table_name="analysis_publication")
    op.drop_table("analysis_publication")
