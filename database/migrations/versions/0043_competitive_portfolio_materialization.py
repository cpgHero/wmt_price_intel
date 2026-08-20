"""Persist radius-native competitive portfolio read models.

Revision ID: 0043_comp_portfolio_mat
Revises: 0042_price_arch_matrix
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043_comp_portfolio_mat"
down_revision: str | None = "0042_price_arch_matrix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitive_portfolio_materialization",
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
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("radius_miles", sa.SmallInteger(), nullable=False),
        sa.Column("source_revision", sa.Text(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column(
            "materialized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "radius_miles IN (1, 3, 5)",
            name="competitive_portfolio_materialization_radius_ck",
        ),
        sa.UniqueConstraint(
            "analysis_result_id",
            "profile_id",
            "radius_miles",
            name="competitive_portfolio_materialization_scope_uq",
        ),
    )
    op.create_index(
        "competitive_portfolio_materialization_lookup_idx",
        "competitive_portfolio_materialization",
        ["analysis_result_id", "profile_id", "radius_miles"],
    )


def downgrade() -> None:
    op.drop_index(
        "competitive_portfolio_materialization_lookup_idx",
        table_name="competitive_portfolio_materialization",
    )
    op.drop_table("competitive_portfolio_materialization")
