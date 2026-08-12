"""Add immutable Retailer Packs, brand foundations, and discovery queue.

Revision ID: 0025_retailer_pack_brand
Revises: 0024_scoped_match_brand
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_retailer_pack_brand"
down_revision: str | None = "0024_scoped_match_brand"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO retailer (id, display_name, country, active, catalogued)
        VALUES ('whole_foods_market_us', 'Whole Foods Market', 'USA', false, true)
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.create_table(
        "brand_foundation",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("active_version", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "brand_foundation_version",
        sa.Column(
            "brand_foundation_id",
            sa.Text(),
            sa.ForeignKey("brand_foundation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("published_by", sa.Text(), nullable=False),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("brand_foundation_id", "version"),
    )
    op.create_index(
        "brand_foundation_version_checksum_uq",
        "brand_foundation_version",
        ["brand_foundation_id", "checksum"],
        unique=True,
    )
    op.create_foreign_key(
        "brand_foundation_active_version_fk",
        "brand_foundation",
        "brand_foundation_version",
        ["id", "active_version"],
        ["brand_foundation_id", "version"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "retailer_pack",
        sa.Column(
            "retailer_id",
            sa.Text(),
            sa.ForeignKey("retailer.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("active_version", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "retailer_pack_version",
        sa.Column(
            "retailer_id",
            sa.Text(),
            sa.ForeignKey("retailer_pack.retailer_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("brand_foundation_id", sa.Text(), nullable=False),
        sa.Column("brand_foundation_version", sa.Text(), nullable=False),
        sa.Column("published_by", sa.Text(), nullable=False),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("retailer_id", "version"),
        sa.ForeignKeyConstraint(
            ["brand_foundation_id", "brand_foundation_version"],
            [
                "brand_foundation_version.brand_foundation_id",
                "brand_foundation_version.version",
            ],
            name="retailer_pack_version_brand_foundation_fk",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "retailer_pack_version_checksum_uq",
        "retailer_pack_version",
        ["retailer_id", "checksum"],
        unique=True,
    )
    op.create_foreign_key(
        "retailer_pack_active_version_fk",
        "retailer_pack",
        "retailer_pack_version",
        ["retailer_id", "active_version"],
        ["retailer_id", "version"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "brand_discovery_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("observed_brand_raw", sa.Text(), nullable=False),
        sa.Column("observed_brand_normalized", sa.Text(), nullable=False),
        sa.Column("source_job_id", sa.Text()),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("status", sa.Text(), nullable=False, server_default="Pending"),
        sa.Column("proposed_canonical_brand_id", sa.Text()),
        sa.Column("decision", sa.Text()),
        sa.Column("decision_notes", sa.Text()),
        sa.Column("reviewed_by", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 100", name="brand_discovery_score_ck"),
        sa.CheckConstraint(
            "status IN ('Pending','Approved','Rejected','Needs Evidence')",
            name="brand_discovery_status_ck",
        ),
    )
    op.create_index(
        "brand_discovery_open_identity_uq",
        "brand_discovery_queue",
        ["retailer_id", "observed_brand_normalized"],
        unique=True,
        postgresql_where=sa.text("status IN ('Pending','Needs Evidence')"),
    )


def downgrade() -> None:
    op.drop_index("brand_discovery_open_identity_uq", table_name="brand_discovery_queue")
    op.drop_table("brand_discovery_queue")
    op.drop_constraint("retailer_pack_active_version_fk", "retailer_pack", type_="foreignkey")
    op.drop_index("retailer_pack_version_checksum_uq", table_name="retailer_pack_version")
    op.drop_table("retailer_pack_version")
    op.drop_table("retailer_pack")
    op.drop_constraint("brand_foundation_active_version_fk", "brand_foundation", type_="foreignkey")
    op.drop_index("brand_foundation_version_checksum_uq", table_name="brand_foundation_version")
    op.drop_table("brand_foundation_version")
    op.drop_table("brand_foundation")
    op.execute("DELETE FROM retailer WHERE id = 'whole_foods_market_us'")
