"""Add one-to-one product-match governance and reanalysis snapshots.

Revision ID: 0017_product_match_governance
Revises: 0016_analysis_archival
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_product_match_governance"
down_revision: str | None = "0016_analysis_archival"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "product_match_revision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column(
            "benchmark_retailer_id",
            sa.Text(),
            sa.ForeignKey("retailer.id"),
            nullable=False,
        ),
        sa.Column(
            "source_analysis_result_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("analysis_result.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="current"),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
        ),
        sa.UniqueConstraint(
            "organization_id",
            "product_pack_id",
            "product_pack_version",
            "benchmark_retailer_id",
            "revision",
            name="product_match_revision_scope_revision_uq",
        ),
        sa.CheckConstraint(
            "status IN ('current', 'superseded')",
            name="product_match_revision_status_ck",
        ),
    )
    op.create_index(
        "product_match_revision_current_uq",
        "product_match_revision",
        ["organization_id", "product_pack_id", "product_pack_version", "benchmark_retailer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'current'"),
    )
    op.create_table(
        "product_match_rule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_match_revision.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "competitor_retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False
        ),
        sa.Column("profile_id", sa.Text(), nullable=False),
        sa.Column("benchmark_product_id", sa.Text(), nullable=False),
        sa.Column("competitor_product_id", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False, server_default="user"),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "benchmark_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "competitor_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "revision_id",
            "competitor_retailer_id",
            "profile_id",
            "benchmark_product_id",
            "competitor_product_id",
            name="product_match_rule_pair_uq",
        ),
        sa.CheckConstraint(
            "decision IN ('confirmed', 'rejected')",
            name="product_match_rule_decision_ck",
        ),
        sa.CheckConstraint("origin IN ('user', 'automatic')", name="product_match_rule_origin_ck"),
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
    op.create_table(
        "product_match_review_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_match_revision.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column(
        "analysis_run",
        sa.Column(
            "match_revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_match_revision.id"),
        ),
    )
    op.add_column(
        "analysis_run",
        sa.Column(
            "source_analysis_result_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("analysis_result.id"),
        ),
    )
    op.drop_constraint("analysis_run_collection_pack_uq", "analysis_run", type_="unique")
    op.execute(
        "ALTER TABLE analysis_run ADD CONSTRAINT analysis_run_collection_pack_match_revision_uq "
        "UNIQUE NULLS NOT DISTINCT "
        "(collection_run_id, product_pack_id, product_pack_version, match_revision_id)"
    )
    op.create_index("analysis_run_match_revision_idx", "analysis_run", ["match_revision_id"])


def downgrade() -> None:
    op.drop_index("analysis_run_match_revision_idx", table_name="analysis_run")
    op.drop_constraint(
        "analysis_run_collection_pack_match_revision_uq", "analysis_run", type_="unique"
    )
    op.create_unique_constraint(
        "analysis_run_collection_pack_uq",
        "analysis_run",
        ["collection_run_id", "product_pack_id", "product_pack_version"],
    )
    op.drop_column("analysis_run", "source_analysis_result_id")
    op.drop_column("analysis_run", "match_revision_id")
    op.drop_table("product_match_review_event")
    op.drop_index("product_match_rule_confirmed_competitor_uq", table_name="product_match_rule")
    op.drop_index("product_match_rule_confirmed_benchmark_uq", table_name="product_match_rule")
    op.drop_table("product_match_rule")
    op.drop_index("product_match_revision_current_uq", table_name="product_match_revision")
    op.drop_table("product_match_revision")
