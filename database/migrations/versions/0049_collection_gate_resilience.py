"""Add optional resilient retailer availability-gate policy.

Revision ID: 0049_gate_resilience
Revises: 0048_price_catalog
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_gate_resilience"
down_revision: str | None = "0048_price_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collection_retailer_gate",
        sa.Column("minimum_successful_samples", sa.Integer(), nullable=True),
    )
    op.add_column(
        "collection_retailer_gate",
        sa.Column("max_transient_nonbillable_failures", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "collection_retailer_gate_min_success_ck",
        "collection_retailer_gate",
        "minimum_successful_samples IS NULL OR "
        "(minimum_successful_samples >= 1 AND minimum_successful_samples <= sample_size)",
    )
    op.create_check_constraint(
        "collection_retailer_gate_max_transient_ck",
        "collection_retailer_gate",
        "max_transient_nonbillable_failures IS NULL OR "
        "(max_transient_nonbillable_failures >= 0 "
        "AND max_transient_nonbillable_failures <= sample_size)",
    )
    op.create_check_constraint(
        "collection_retailer_gate_resilience_pair_ck",
        "collection_retailer_gate",
        "(minimum_successful_samples IS NULL) = (max_transient_nonbillable_failures IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "collection_retailer_gate_resilience_pair_ck",
        "collection_retailer_gate",
        type_="check",
    )
    op.drop_constraint(
        "collection_retailer_gate_max_transient_ck",
        "collection_retailer_gate",
        type_="check",
    )
    op.drop_constraint(
        "collection_retailer_gate_min_success_ck",
        "collection_retailer_gate",
        type_="check",
    )
    op.drop_column("collection_retailer_gate", "max_transient_nonbillable_failures")
    op.drop_column("collection_retailer_gate", "minimum_successful_samples")
