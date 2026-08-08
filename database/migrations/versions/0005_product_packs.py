"""Add immutable Product Pack versions.

Revision ID: 0005_product_packs
Revises: 0004_metricscart_data_plane
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_product_packs"
down_revision: str | None = "0004_metricscart_data_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_pack",
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
        "product_pack_version",
        sa.Column(
            "product_pack_id",
            sa.Text(),
            sa.ForeignKey("product_pack.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False, server_default="1.0.0"),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("product_pack_id", "version"),
    )
    op.create_index(
        "product_pack_version_checksum_idx",
        "product_pack_version",
        ["product_pack_id", "checksum"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("product_pack_version_checksum_idx", table_name="product_pack_version")
    op.drop_table("product_pack_version")
    op.drop_table("product_pack")
