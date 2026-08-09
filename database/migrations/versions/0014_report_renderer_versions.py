"""Version immutable report renderer outputs.

Revision ID: 0014_report_renderer_versions
Revises: 0013_governed_ai
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_report_renderer_versions"
down_revision: str | None = "0013_governed_ai"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_artifact",
        sa.Column(
            "renderer_version",
            sa.Text(),
            nullable=True,
            server_default="legacy",
        ),
    )
    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 row_number() OVER (
                   PARTITION BY analysis_run_id, artifact_type
                   ORDER BY created_at DESC, id DESC
                 ) AS duplicate_rank
          FROM report_artifact
        )
        UPDATE report_artifact AS artifact
        SET renderer_version = CASE
          WHEN ranked.duplicate_rank = 1 THEN 'legacy'
          ELSE 'legacy-' || artifact.id::text
        END
        FROM ranked
        WHERE ranked.id = artifact.id
        """
    )
    op.alter_column("report_artifact", "renderer_version", nullable=False)
    op.drop_constraint("report_artifact_identity_uq", "report_artifact", type_="unique")
    op.create_unique_constraint(
        "report_artifact_renderer_identity_uq",
        "report_artifact",
        ["analysis_run_id", "artifact_type", "renderer_version"],
    )


def downgrade() -> None:
    op.drop_constraint("report_artifact_renderer_identity_uq", "report_artifact", type_="unique")
    op.create_unique_constraint(
        "report_artifact_identity_uq",
        "report_artifact",
        ["analysis_run_id", "artifact_type", "dataset_artifact_id"],
    )
    op.drop_column("report_artifact", "renderer_version")
