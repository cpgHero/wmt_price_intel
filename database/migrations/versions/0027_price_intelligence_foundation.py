"""Add product-scoped Price Intelligence snapshots and governed location hierarchy.

Revision ID: 0027_price_intelligence
Revises: 0026_study_discovery
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_price_intelligence"
down_revision: str | None = "0026_study_discovery"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for column in ("region", "division", "market", "store_format"):
        op.add_column("retailer_location", sa.Column(column, sa.Text()))
    op.add_column("retailer_location", sa.Column("hierarchy_source", sa.Text()))
    op.add_column("retailer_location", sa.Column("hierarchy_version", sa.Text()))
    op.add_column(
        "retailer_location",
        sa.Column(
            "hierarchy_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "retailer_location_market_idx",
        "retailer_location",
        ["retailer_id", "region", "division", "market"],
    )

    op.create_table(
        "price_intelligence_snapshot",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_result_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("collection_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("comparability_fingerprint", sa.Text(), nullable=False),
        sa.Column("location_scope_checksum", sa.Text(), nullable=False),
        sa.Column("adapter_version", sa.Text(), nullable=False),
        sa.Column("source_checksums", postgresql.JSONB(), nullable=False),
        sa.Column("quality", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("observed_start", sa.DateTime(timezone=True)),
        sa.Column("observed_end", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "analysis_result_id",
            "retailer_id",
            name="price_intelligence_snapshot_analysis_retailer_uq",
        ),
        sa.CheckConstraint(
            "status IN ('building','ready','warning','blocked')",
            name="price_intelligence_snapshot_status_ck",
        ),
    )
    op.create_index(
        "price_intelligence_snapshot_history_idx",
        "price_intelligence_snapshot",
        ["retailer_id", "product_pack_id", "comparability_fingerprint", "observed_end"],
    )

    op.create_table(
        "price_intelligence_observation",
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_intelligence_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_product_id", sa.Text(), nullable=False),
        sa.Column("location_scope_key", sa.Text(), nullable=False),
        sa.Column(
            "retailer_location_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("retailer_location.id", ondelete="SET NULL"),
        ),
        sa.Column("offer_id", sa.Text(), nullable=False),
        sa.Column("current_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("regular_price", sa.Numeric(18, 4)),
        sa.Column("discounted_price", sa.Numeric(18, 4)),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("in_stock", sa.Boolean()),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("evidence_status", sa.Text(), nullable=False),
        sa.Column("quality_flags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint(
            "snapshot_id",
            "retailer_product_id",
            "location_scope_key",
            name="price_intelligence_observation_pk",
        ),
        sa.CheckConstraint(
            "evidence_status IN ('observed','uncertain')",
            name="price_intelligence_observation_status_ck",
        ),
    )
    op.create_index(
        "price_intelligence_observation_product_idx",
        "price_intelligence_observation",
        ["snapshot_id", "retailer_product_id", "current_price"],
    )
    op.create_index(
        "price_intelligence_observation_location_idx",
        "price_intelligence_observation",
        ["snapshot_id", "location_scope_key"],
    )

    op.create_table(
        "price_intelligence_product_snapshot",
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_intelligence_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_product_id", sa.Text(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("metric_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id",
            "retailer_product_id",
            name="price_intelligence_product_snapshot_pk",
        ),
    )

    op.create_table(
        "price_intelligence_exception",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_intelligence_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_product_id", sa.Text(), nullable=False),
        sa.Column("location_scope_key", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "snapshot_id",
            "retailer_product_id",
            "location_scope_key",
            "rule_id",
            name="price_intelligence_exception_identity_uq",
        ),
        sa.CheckConstraint(
            "severity IN ('review','high')",
            name="price_intelligence_exception_severity_ck",
        ),
        sa.CheckConstraint(
            "status IN ('open','confirmed','dismissed','resolved')",
            name="price_intelligence_exception_status_ck",
        ),
    )
    op.create_index(
        "price_intelligence_exception_queue_idx",
        "price_intelligence_exception",
        ["snapshot_id", "status", "severity", "created_at"],
    )

    op.create_table(
        "price_intelligence_exception_review",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "exception_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_intelligence_exception.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.Text(), nullable=False),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "price_intelligence_exception_review_idx",
        "price_intelligence_exception_review",
        ["exception_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "price_intelligence_exception_review_idx",
        table_name="price_intelligence_exception_review",
    )
    op.drop_table("price_intelligence_exception_review")
    op.drop_index(
        "price_intelligence_exception_queue_idx",
        table_name="price_intelligence_exception",
    )
    op.drop_table("price_intelligence_exception")
    op.drop_table("price_intelligence_product_snapshot")
    op.drop_index(
        "price_intelligence_observation_location_idx",
        table_name="price_intelligence_observation",
    )
    op.drop_index(
        "price_intelligence_observation_product_idx",
        table_name="price_intelligence_observation",
    )
    op.drop_table("price_intelligence_observation")
    op.drop_index(
        "price_intelligence_snapshot_history_idx",
        table_name="price_intelligence_snapshot",
    )
    op.drop_table("price_intelligence_snapshot")
    op.drop_index("retailer_location_market_idx", table_name="retailer_location")
    for column in (
        "hierarchy_verified",
        "hierarchy_version",
        "hierarchy_source",
        "store_format",
        "market",
        "division",
        "region",
    ):
        op.drop_column("retailer_location", column)
