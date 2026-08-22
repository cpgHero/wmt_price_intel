"""Add provider-safe location collection eligibility.

Revision ID: 0045_location_eligibility
Revises: 0044_report_pub_gate
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_location_eligibility"
down_revision: str | None = "0044_report_pub_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "retailer_location",
        sa.Column(
            "collection_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "retailer_location",
        sa.Column("collection_eligibility_reason", sa.Text()),
    )

    enabled_numeric_store_retailers = (
        "walmart_us",
        "albertsons_us",
        "giant_eagle_us",
        "heb_us",
        "kroger_us",
        "meijer_us",
        "safeway_us",
        "sams_club_us",
        "shoprite_us",
        "target_us",
        "trader_joes_us",
        "wegmans_us",
    )
    retailer_sql = ", ".join(f"'{retailer_id}'" for retailer_id in enabled_numeric_store_retailers)
    op.execute(
        sa.text(
            f"""
            UPDATE retailer_location AS location
            SET collection_eligible = false,
                collection_eligibility_reason = CASE
                  WHEN NOT retailer.active THEN 'retailer_not_enabled_for_collection'
                  WHEN lower(coalesce(location.status, '')) <> 'active'
                    THEN 'status_not_collection_eligible'
                  WHEN location.retailer_id = 'aldi_us'
                    AND location.store_number !~ '^[0-9]{{3}}-[0-9]{{3}}$'
                    THEN 'store_number_not_provider_safe'
                  WHEN location.retailer_id IN ({retailer_sql})
                    AND location.store_number !~ '^[0-9]+$'
                    THEN 'store_number_not_provider_safe'
                  WHEN location.retailer_id NOT IN ({retailer_sql}, 'aldi_us')
                    THEN 'retailer_has_no_store_collection_policy'
                  ELSE NULL
                END
            FROM retailer
            WHERE retailer.id = location.retailer_id
              AND (
                NOT retailer.active
                OR lower(coalesce(location.status, '')) <> 'active'
                OR (
                  location.retailer_id = 'aldi_us'
                  AND location.store_number !~ '^[0-9]{{3}}-[0-9]{{3}}$'
                )
                OR (
                  location.retailer_id IN ({retailer_sql})
                  AND location.store_number !~ '^[0-9]+$'
                )
                OR location.retailer_id NOT IN ({retailer_sql}, 'aldi_us')
              )
            """
        )
    )
    op.alter_column(
        "retailer_location",
        "collection_eligible",
        server_default=sa.false(),
    )
    op.create_index(
        "retailer_location_collection_eligible_idx",
        "retailer_location",
        ["retailer_id", "country", "state"],
        postgresql_where=sa.text("collection_eligible"),
    )


def downgrade() -> None:
    op.drop_index(
        "retailer_location_collection_eligible_idx",
        table_name="retailer_location",
    )
    op.drop_column("retailer_location", "collection_eligibility_reason")
    op.drop_column("retailer_location", "collection_eligible")
