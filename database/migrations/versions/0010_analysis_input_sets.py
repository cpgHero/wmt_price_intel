"""Add immutable live and historical analysis input sets.

Revision ID: 0010_analysis_input_sets
Revises: 0009_vertical_slice
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_analysis_input_sets"
down_revision: str | None = "0009_vertical_slice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("collection_run_trigger_schedule_ck", "collection_run", type_="check")
    op.drop_constraint("collection_run_trigger_type_ck", "collection_run", type_="check")
    op.create_check_constraint(
        "collection_run_trigger_type_ck",
        "collection_run",
        "trigger_type IN ('manual', 'scheduled', 'historical_import')",
    )
    op.create_check_constraint(
        "collection_run_trigger_schedule_ck",
        "collection_run",
        "(trigger_type IN ('manual', 'historical_import') "
        "AND schedule_id IS NULL AND scheduled_for IS NULL) OR "
        "(trigger_type = 'scheduled' AND schedule_id IS NOT NULL "
        "AND scheduled_for IS NOT NULL)",
    )

    op.create_table(
        "analysis_input_set",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("stable_key", sa.Text(), nullable=False),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("analysis_config", postgresql.JSONB(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("manifest_checksum", sa.Text(), nullable=False),
        sa.Column("total_rows", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "source_kind IN ('live_collection', 'historical_import')",
            name="analysis_input_set_source_kind_ck",
        ),
        sa.CheckConstraint(
            "status IN ('preparing', 'ready', 'failed')",
            name="analysis_input_set_status_ck",
        ),
        sa.CheckConstraint("total_rows >= 0", name="analysis_input_set_total_rows_ck"),
        sa.UniqueConstraint(
            "organization_id",
            "source_kind",
            "manifest_checksum",
            name="analysis_input_set_manifest_uq",
        ),
    )
    op.create_index(
        "analysis_input_set_ready_idx",
        "analysis_input_set",
        ["status", "source_kind", "created_at"],
    )
    op.create_index(
        "analysis_input_set_pack_idx",
        "analysis_input_set",
        ["product_pack_id", "product_pack_version", "created_at"],
    )

    op.create_table(
        "analysis_input_artifact",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "input_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_input_set.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dataset_artifact.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("adapter_id", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_format", sa.Text(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.CheckConstraint("ordinal >= 0", name="analysis_input_artifact_ordinal_ck"),
        sa.CheckConstraint("row_count >= 0", name="analysis_input_artifact_rows_ck"),
        sa.UniqueConstraint("input_set_id", "ordinal", name="analysis_input_artifact_ordinal_uq"),
        sa.UniqueConstraint(
            "input_set_id",
            "dataset_artifact_id",
            name="analysis_input_artifact_dataset_uq",
        ),
    )
    op.create_index(
        "analysis_input_artifact_retailer_idx",
        "analysis_input_artifact",
        ["input_set_id", "retailer_id", "ordinal"],
    )

    op.add_column(
        "analysis_run",
        sa.Column(
            "input_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_input_set.id", name="analysis_run_input_set_fk"),
        ),
    )
    op.create_index("analysis_run_input_set_idx", "analysis_run", ["input_set_id"])


def downgrade() -> None:
    op.drop_index("analysis_run_input_set_idx", table_name="analysis_run")
    op.drop_constraint("analysis_run_input_set_fk", "analysis_run", type_="foreignkey")
    op.drop_column("analysis_run", "input_set_id")
    op.drop_index("analysis_input_artifact_retailer_idx", table_name="analysis_input_artifact")
    op.drop_table("analysis_input_artifact")
    op.drop_index("analysis_input_set_pack_idx", table_name="analysis_input_set")
    op.drop_index("analysis_input_set_ready_idx", table_name="analysis_input_set")
    op.drop_table("analysis_input_set")

    op.execute("DELETE FROM collection_run WHERE trigger_type = 'historical_import'")
    op.drop_constraint("collection_run_trigger_schedule_ck", "collection_run", type_="check")
    op.drop_constraint("collection_run_trigger_type_ck", "collection_run", type_="check")
    op.create_check_constraint(
        "collection_run_trigger_type_ck",
        "collection_run",
        "trigger_type IN ('manual', 'scheduled')",
    )
    op.create_check_constraint(
        "collection_run_trigger_schedule_ck",
        "collection_run",
        "(trigger_type = 'manual' AND schedule_id IS NULL AND scheduled_for IS NULL) OR "
        "(trigger_type = 'scheduled' AND schedule_id IS NOT NULL "
        "AND scheduled_for IS NOT NULL)",
    )
