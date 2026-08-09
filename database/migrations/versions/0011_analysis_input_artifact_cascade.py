"""Cascade analysis input links when their dataset artifact is deleted.

Revision ID: 0011_input_artifact_cascade
Revises: 0010_analysis_input_sets
"""

from __future__ import annotations

from alembic import op

revision: str = "0011_input_artifact_cascade"
down_revision: str | None = "0010_analysis_input_sets"
branch_labels: str | None = None
depends_on: str | None = None

_CONSTRAINT = "analysis_input_artifact_dataset_artifact_id_fkey"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "analysis_input_artifact", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "analysis_input_artifact",
        "dataset_artifact",
        ["dataset_artifact_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "analysis_input_artifact", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "analysis_input_artifact",
        "dataset_artifact",
        ["dataset_artifact_id"],
        ["id"],
    )
