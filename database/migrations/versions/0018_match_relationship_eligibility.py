"""Make governed product relationships lens-independent.

Revision ID: 0018_match_lens_eligibility
Revises: 0017_product_match_governance
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_match_lens_eligibility"
down_revision: str | None = "0017_product_match_governance"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_index("product_match_rule_confirmed_competitor_uq", table_name="product_match_rule")
    op.drop_index("product_match_rule_confirmed_benchmark_uq", table_name="product_match_rule")
    op.drop_constraint("product_match_rule_pair_uq", "product_match_rule", type_="unique")
    op.add_column(
        "product_match_rule",
        sa.Column("eligible_profile_ids", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.execute("UPDATE product_match_rule SET eligible_profile_ids = ARRAY[profile_id]::text[]")
    op.alter_column(
        "product_match_rule",
        "eligible_profile_ids",
        existing_type=postgresql.ARRAY(sa.Text()),
        nullable=False,
    )
    op.create_check_constraint(
        "product_match_rule_eligible_profiles_ck",
        "product_match_rule",
        "cardinality(eligible_profile_ids) > 0",
    )
    op.create_unique_constraint(
        "product_match_rule_pair_uq",
        "product_match_rule",
        [
            "revision_id",
            "competitor_retailer_id",
            "benchmark_product_id",
            "competitor_product_id",
        ],
    )
    op.create_index(
        "product_match_rule_confirmed_benchmark_uq",
        "product_match_rule",
        ["revision_id", "competitor_retailer_id", "benchmark_product_id"],
        unique=True,
        postgresql_where=sa.text("decision = 'confirmed'"),
    )
    op.create_index(
        "product_match_rule_confirmed_competitor_uq",
        "product_match_rule",
        ["revision_id", "competitor_retailer_id", "competitor_product_id"],
        unique=True,
        postgresql_where=sa.text("decision = 'confirmed'"),
    )


def downgrade() -> None:
    op.drop_index("product_match_rule_confirmed_competitor_uq", table_name="product_match_rule")
    op.drop_index("product_match_rule_confirmed_benchmark_uq", table_name="product_match_rule")
    op.drop_constraint("product_match_rule_pair_uq", "product_match_rule", type_="unique")
    op.drop_constraint(
        "product_match_rule_eligible_profiles_ck", "product_match_rule", type_="check"
    )
    op.drop_column("product_match_rule", "eligible_profile_ids")
    op.create_unique_constraint(
        "product_match_rule_pair_uq",
        "product_match_rule",
        [
            "revision_id",
            "competitor_retailer_id",
            "profile_id",
            "benchmark_product_id",
            "competitor_product_id",
        ],
    )
    op.create_index(
        "product_match_rule_confirmed_benchmark_uq",
        "product_match_rule",
        ["revision_id", "competitor_retailer_id", "profile_id", "benchmark_product_id"],
        unique=True,
        postgresql_where=sa.text("decision = 'confirmed'"),
    )
    op.create_index(
        "product_match_rule_confirmed_competitor_uq",
        "product_match_rule",
        ["revision_id", "competitor_retailer_id", "profile_id", "competitor_product_id"],
        unique=True,
        postgresql_where=sa.text("decision = 'confirmed'"),
    )
