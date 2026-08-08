"""Create the canonical, country-aware location master.

Revision ID: 0002_location_master
Revises: 0001_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_location_master"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEEDED_RETAILERS = [
    {
        "id": "walmart_us",
        "display_name": "Walmart (US)",
        "country": "USA",
        "active": True,
        "catalogued": True,
    },
    {
        "id": "aldi_us",
        "display_name": "ALDI",
        "country": "USA",
        "active": True,
        "catalogued": True,
    },
    {
        "id": "amazon_us_same_day",
        "display_name": "Amazon Same Day (US)",
        "country": "USA",
        "active": True,
        "catalogued": True,
    },
    {
        "id": "albertsons_us",
        "display_name": "Albertsons",
        "country": "USA",
        "active": False,
        "catalogued": True,
    },
    {
        "id": "heb_us",
        "display_name": "H-E-B",
        "country": "USA",
        "active": False,
        "catalogued": True,
    },
    {
        "id": "kroger_us",
        "display_name": "Kroger",
        "country": "USA",
        "active": False,
        "catalogued": True,
    },
    {
        "id": "safeway_us",
        "display_name": "Safeway",
        "country": "USA",
        "active": False,
        "catalogued": True,
    },
    {
        "id": "target_us",
        "display_name": "Target",
        "country": "USA",
        "active": False,
        "catalogued": True,
    },
    {
        "id": "walmart_mx",
        "display_name": "Walmart (Mexico)",
        "country": "MEXICO",
        "active": False,
        "catalogued": True,
    },
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    retailer = op.create_table(
        "retailer",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("catalogued", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.bulk_insert(retailer, SEEDED_RETAILERS)

    op.create_table(
        "retailer_alias",
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column(
            "retailer_id",
            sa.Text(),
            sa.ForeignKey("retailer.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("alias", "country", name="retailer_alias_pk"),
    )
    op.create_index("retailer_alias_retailer_idx", "retailer_alias", ["retailer_id"])

    op.create_table(
        "location_import_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("imported_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("skipped_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("retailer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="location_import_run_status_ck",
        ),
    )

    op.create_table(
        "retailer_location",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "retailer_id",
            sa.Text(),
            sa.ForeignKey("retailer.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_location_id", sa.Text()),
        sa.Column("store_number", sa.Text(), nullable=False),
        sa.Column("store_name", sa.Text()),
        sa.Column("raw_zipcode", sa.Text()),
        sa.Column("zipcode", sa.Text()),
        sa.Column("street", sa.Text()),
        sa.Column("address", sa.Text()),
        sa.Column("city", sa.Text()),
        sa.Column("state", sa.Text()),
        sa.Column("county", sa.Text()),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("status", sa.Text()),
        sa.Column("source_created_at", sa.Text()),
        sa.Column("source_row_id", sa.Text()),
        sa.Column(
            "last_import_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("location_import_run.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw_row", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "retailer_id",
            "provider",
            "store_number",
            "country",
            name="retailer_location_identity_uq",
        ),
    )
    op.create_index(
        "retailer_location_zip_idx",
        "retailer_location",
        ["retailer_id", "country", "zipcode"],
    )
    op.create_index(
        "retailer_location_latlon_idx",
        "retailer_location",
        ["latitude", "longitude"],
    )
    op.create_index(
        "retailer_location_search_idx",
        "retailer_location",
        ["retailer_id", "store_number"],
    )


def downgrade() -> None:
    op.drop_index("retailer_location_search_idx", table_name="retailer_location")
    op.drop_index("retailer_location_latlon_idx", table_name="retailer_location")
    op.drop_index("retailer_location_zip_idx", table_name="retailer_location")
    op.drop_table("retailer_location")
    op.drop_table("location_import_run")
    op.drop_index("retailer_alias_retailer_idx", table_name="retailer_alias")
    op.drop_table("retailer_alias")
    op.drop_table("retailer")
