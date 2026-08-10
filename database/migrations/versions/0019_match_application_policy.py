"""Separate staged match revisions from the policy used by future collections.

Revision ID: 0019_match_application_policy
Revises: 0018_match_lens_eligibility
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0019_match_application_policy"
down_revision: str | None = "0018_match_lens_eligibility"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "product_match_application_policy",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("benchmark_retailer_id", sa.Text(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["benchmark_retailer_id"], ["retailer.id"]),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["product_match_revision.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "product_pack_id",
            "product_pack_version",
            "benchmark_retailer_id",
        ),
    )
    op.create_index(
        "product_match_application_policy_revision_idx",
        "product_match_application_policy",
        ["revision_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "product_match_application_policy_revision_idx",
        table_name="product_match_application_policy",
    )
    op.drop_table("product_match_application_policy")
