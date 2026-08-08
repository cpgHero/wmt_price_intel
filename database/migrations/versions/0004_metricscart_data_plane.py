"""Add shared provider limiting and immutable dataset artifact metadata.

Revision ID: 0004_metricscart_data_plane
Revises: 0003_collection_control_plane
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_metricscart_data_plane"
down_revision: str | None = "0003_collection_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_rate_limit_state",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("budget_key", sa.Text(), nullable=False),
        sa.Column("second_window_start", sa.DateTime(timezone=True)),
        sa.Column("second_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minute_window_start", sa.DateTime(timezone=True)),
        sa.Column("minute_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paused_until", sa.DateTime(timezone=True)),
        sa.Column("last_429_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("provider", "budget_key"),
        sa.CheckConstraint("second_count >= 0", name="provider_rate_second_count_ck"),
        sa.CheckConstraint("minute_count >= 0", name="provider_rate_minute_count_ck"),
    )

    op.create_table(
        "dataset_artifact",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id", ondelete="CASCADE"),
        ),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False, unique=True),
        sa.Column("content_type", sa.Text()),
        sa.Column("row_count", sa.BigInteger()),
        sa.Column("byte_size", sa.BigInteger()),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "dataset_artifact_run_type_idx",
        "dataset_artifact",
        ["collection_run_id", "artifact_type", "created_at"],
    )
    op.add_column(
        "collection_task",
        sa.Column("raw_artifact_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        "collection_task_raw_artifact_fk",
        "collection_task",
        "dataset_artifact",
        ["raw_artifact_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("collection_task_raw_artifact_fk", "collection_task", type_="foreignkey")
    op.drop_column("collection_task", "raw_artifact_id")
    op.drop_index("dataset_artifact_run_type_idx", table_name="dataset_artifact")
    op.drop_table("dataset_artifact")
    op.drop_table("provider_rate_limit_state")
