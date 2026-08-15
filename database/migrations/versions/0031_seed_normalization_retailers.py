"""Seed governed normalization-only retailers.

Revision ID: 0031_seed_normalization_only
Revises: 0030_matching_v2_human_review
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_seed_normalization_only"
down_revision: str | None = "0030_matching_v2_human_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO retailer (id, display_name, country, active, catalogued)
        VALUES
          ('giant_eagle_us', 'Giant Eagle', 'USA', false, true),
          ('meijer_us', 'Meijer', 'USA', false, true),
          ('sams_club_us', 'Sam''s Club', 'USA', false, true),
          ('shoprite_us', 'ShopRite', 'USA', false, true),
          ('trader_joes_us', 'Trader Joe''s', 'USA', false, true),
          ('wegmans_us', 'Wegmans', 'USA', false, true),
          ('whole_foods_market_us', 'Whole Foods Market', 'USA', false, true)
        ON CONFLICT (id) DO UPDATE SET
          display_name = EXCLUDED.display_name,
          country = EXCLUDED.country,
          catalogued = true
        """
    )


def downgrade() -> None:
    # These are canonical master-data identities. Retaining them is safer than
    # deleting rows that may have gained valid foreign-key references later.
    pass
