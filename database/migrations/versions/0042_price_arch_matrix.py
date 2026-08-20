"""Persist governed Price Architecture Matrix read models.

Revision ID: 0042_price_arch_matrix
Revises: 0041_governed_replay_generation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_price_arch_matrix"
down_revision: str | None = "0041_governed_replay_generation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_architecture_materialization",
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
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("fixed_increment", sa.Numeric(4, 2), nullable=False),
        sa.Column("brand_type", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False, server_default=""),
        sa.Column("state", sa.Text(), nullable=False, server_default=""),
        sa.Column("city", sa.Text(), nullable=False, server_default=""),
        sa.Column("zipcode", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_revision", sa.Text(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column(
            "materialized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "mode IN ('benchmark_anchored', 'fixed_range')",
            name="price_architecture_materialization_mode_ck",
        ),
        sa.CheckConstraint(
            "fixed_increment IN (0.50, 1.00)",
            name="price_architecture_materialization_increment_ck",
        ),
        sa.CheckConstraint(
            "brand_type IN ('all', 'private_label', 'regional', 'national', 'unclassified')",
            name="price_architecture_materialization_brand_type_ck",
        ),
        sa.UniqueConstraint(
            "analysis_result_id",
            "mode",
            "fixed_increment",
            "brand_type",
            "brand",
            "state",
            "city",
            "zipcode",
            name="price_architecture_materialization_scope_uq",
        ),
    )
    op.create_index(
        "price_architecture_materialization_lookup_idx",
        "price_architecture_materialization",
        ["analysis_result_id", "mode", "fixed_increment", "brand_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "price_architecture_materialization_lookup_idx",
        table_name="price_architecture_materialization",
    )
    op.drop_table("price_architecture_materialization")
