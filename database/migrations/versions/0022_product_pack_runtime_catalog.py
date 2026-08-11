"""Add exact-version Product Pack and report-blueprint runtime catalog.

Revision ID: 0022_product_pack_runtime
Revises: 0021_collection_geography
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_product_pack_runtime"
down_revision: str | None = "0021_collection_geography"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "report_blueprint",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "report_blueprint_version",
        sa.Column(
            "report_blueprint_id",
            sa.Text(),
            sa.ForeignKey("report_blueprint.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False, server_default="1.0.0"),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("published_by", sa.Text(), nullable=False, server_default="repository-seed"),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("report_blueprint_id", "version"),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
            name="report_blueprint_version_pack_fk",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        "report_blueprint_version_checksum_uq",
        "report_blueprint_version",
        ["report_blueprint_id", "checksum"],
        unique=True,
    )
    op.add_column("product_pack", sa.Column("active_version", sa.Text()))
    op.add_column(
        "product_pack",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "product_pack_version",
        sa.Column("default_keyword", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("product_pack_version", sa.Column("report_blueprint_id", sa.Text()))
    op.add_column("product_pack_version", sa.Column("report_blueprint_version", sa.Text()))
    op.add_column("product_pack_version", sa.Column("report_blueprint_checksum", sa.Text()))
    op.add_column(
        "product_pack_version",
        sa.Column("published_by", sa.Text(), nullable=False, server_default="repository-seed"),
    )
    op.add_column("product_pack_version", sa.Column("release_notes", sa.Text()))
    op.create_foreign_key(
        "product_pack_active_version_fk",
        "product_pack",
        "product_pack_version",
        ["id", "active_version"],
        ["product_pack_id", "version"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "product_pack_version_blueprint_fk",
        "product_pack_version",
        "report_blueprint_version",
        ["report_blueprint_id", "report_blueprint_version"],
        ["report_blueprint_id", "version"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint(
        "product_pack_version_blueprint_fk",
        "product_pack_version",
        type_="foreignkey",
    )
    op.drop_constraint("product_pack_active_version_fk", "product_pack", type_="foreignkey")
    op.drop_column("product_pack_version", "release_notes")
    op.drop_column("product_pack_version", "published_by")
    op.drop_column("product_pack_version", "report_blueprint_checksum")
    op.drop_column("product_pack_version", "report_blueprint_version")
    op.drop_column("product_pack_version", "report_blueprint_id")
    op.drop_column("product_pack_version", "default_keyword")
    op.drop_column("product_pack", "updated_at")
    op.drop_column("product_pack", "active_version")
    op.drop_index(
        "report_blueprint_version_checksum_uq",
        table_name="report_blueprint_version",
    )
    op.drop_table("report_blueprint_version")
    op.drop_table("report_blueprint")
