"""Add immutable collection geography snapshots and guarded estimates.

Revision ID: 0021_collection_geography
Revises: 0020_provider_permit_pacing
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_collection_geography"
down_revision: str | None = "0020_provider_permit_pacing"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "collection_geography_resolution",
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
        sa.Column("primary_retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="ready"),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'invalid')",
            name="collection_geography_resolution_status_ck",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "checksum",
            name="collection_geography_resolution_checksum_uq",
        ),
    )
    op.create_index(
        "collection_geography_resolution_created_idx",
        "collection_geography_resolution",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "collection_geography_location",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "resolution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_geography_resolution.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("retailer_location_id", postgresql.UUID(as_uuid=True)),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("store_number", sa.Text()),
        sa.Column("store_name", sa.Text()),
        sa.Column("zipcode", sa.Text(), nullable=False),
        sa.Column("city", sa.Text()),
        sa.Column("state", sa.Text()),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("selection_reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "role IN ('primary', 'competitor')",
            name="collection_geography_location_role_ck",
        ),
        sa.UniqueConstraint(
            "resolution_id",
            "retailer_id",
            "scope_key",
            name="collection_geography_location_scope_uq",
        ),
    )
    op.create_index(
        "collection_geography_location_retailer_idx",
        "collection_geography_location",
        ["resolution_id", "retailer_id", "role"],
    )
    op.create_index(
        "collection_geography_location_state_idx",
        "collection_geography_location",
        ["resolution_id", "state", "zipcode"],
    )

    op.create_table(
        "collection_geography_edge",
        sa.Column(
            "resolution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_geography_resolution.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "primary_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_geography_location.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "competitor_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_geography_location.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("distance_miles", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint(
            "resolution_id",
            "primary_location_id",
            "competitor_location_id",
            name="collection_geography_edge_pk",
        ),
        sa.CheckConstraint(
            "distance_miles >= 0",
            name="collection_geography_edge_distance_ck",
        ),
    )
    op.create_index(
        "collection_geography_edge_competitor_idx",
        "collection_geography_edge",
        ["resolution_id", "competitor_location_id"],
    )

    op.create_table(
        "collection_scope_estimate",
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
        sa.Column(
            "resolution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_geography_resolution.id"),
            nullable=False,
        ),
        sa.Column("definition_id", sa.Text(), nullable=False),
        sa.Column("configuration_checksum", sa.Text(), nullable=False),
        sa.Column("geography_checksum", sa.Text(), nullable=False),
        sa.Column("estimate", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "collection_scope_estimate_guard_idx",
        "collection_scope_estimate",
        ["id", "configuration_checksum", "geography_checksum", "expires_at"],
    )
    op.add_column(
        "collection_run",
        sa.Column(
            "scope_estimate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_scope_estimate.id"),
        ),
    )
    op.create_unique_constraint(
        "collection_run_scope_estimate_uq",
        "collection_run",
        ["scope_estimate_id"],
    )

    op.add_column(
        "collection_definition_version",
        sa.Column(
            "geography_resolution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_geography_resolution.id"),
        ),
    )
    op.create_index(
        "collection_definition_version_geography_idx",
        "collection_definition_version",
        ["geography_resolution_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "collection_definition_version_geography_idx",
        table_name="collection_definition_version",
    )
    op.drop_column("collection_definition_version", "geography_resolution_id")
    op.drop_constraint(
        "collection_run_scope_estimate_uq",
        "collection_run",
        type_="unique",
    )
    op.drop_column("collection_run", "scope_estimate_id")
    op.drop_index("collection_scope_estimate_guard_idx", table_name="collection_scope_estimate")
    op.drop_table("collection_scope_estimate")
    op.drop_index(
        "collection_geography_edge_competitor_idx",
        table_name="collection_geography_edge",
    )
    op.drop_table("collection_geography_edge")
    op.drop_index(
        "collection_geography_location_state_idx",
        table_name="collection_geography_location",
    )
    op.drop_index(
        "collection_geography_location_retailer_idx",
        table_name="collection_geography_location",
    )
    op.drop_table("collection_geography_location")
    op.drop_index(
        "collection_geography_resolution_created_idx",
        table_name="collection_geography_resolution",
    )
    op.drop_table("collection_geography_resolution")
