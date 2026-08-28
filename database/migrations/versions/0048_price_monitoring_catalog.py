"""Add durable Price Intelligence product catalogs.

Revision ID: 0048_price_catalog
Revises: 0047_attribute_reconcile
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048_price_catalog"
down_revision: str | None = "0047_attribute_reconcile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_monitoring_catalog_materialization",
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
        sa.Column("retailer_id", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.Text(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column(
            "materialized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "analysis_result_id",
            "retailer_id",
            name="price_monitoring_catalog_materialization_scope_uq",
        ),
    )
    op.create_index(
        "price_monitoring_catalog_materialization_lookup_idx",
        "price_monitoring_catalog_materialization",
        ["analysis_result_id", "retailer_id"],
    )

    op.drop_constraint(
        "report_materialization_stage_kind_ck",
        "report_materialization_stage",
        type_="check",
    )
    op.create_check_constraint(
        "report_materialization_stage_kind_ck",
        "report_materialization_stage",
        "document_kind IN ('price_architecture', 'price_catalog', "
        "'competitive_portfolio')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "report_materialization_stage_kind_ck",
        "report_materialization_stage",
        type_="check",
    )
    op.create_check_constraint(
        "report_materialization_stage_kind_ck",
        "report_materialization_stage",
        "document_kind IN ('price_architecture', 'competitive_portfolio')",
    )
    op.drop_index(
        "price_monitoring_catalog_materialization_lookup_idx",
        table_name="price_monitoring_catalog_materialization",
    )
    op.drop_table("price_monitoring_catalog_materialization")
