"""Add distribution-scoped product relationships and governed brand roles.

Revision ID: 0024_distribution_scoped_match_governance
Revises: 0023_product_pack_authoring
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_distribution_scoped_match_governance"
down_revision: str | None = "0023_product_pack_authoring"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_index("product_match_rule_confirmed_competitor_uq", table_name="product_match_rule")
    op.drop_index("product_match_rule_confirmed_benchmark_uq", table_name="product_match_rule")
    op.add_column("product_match_rule", sa.Column("comparison_family_key", sa.Text()))
    op.add_column(
        "product_match_rule",
        sa.Column("relationship_role", sa.Text(), server_default="primary"),
    )
    op.add_column("product_match_rule", sa.Column("scope_mode", sa.Text(), server_default="global"))
    op.add_column(
        "product_match_rule",
        sa.Column(
            "scope_definition",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("product_match_rule", sa.Column("scope_checksum", sa.Text()))
    op.add_column(
        "product_match_rule",
        sa.Column(
            "scope_artifact_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("dataset_artifact.id", ondelete="SET NULL"),
        ),
    )
    op.execute(
        """
        UPDATE product_match_rule
        SET comparison_family_key = 'legacy_' || substr(
              encode(digest(competitor_retailer_id || '|' || benchmark_product_id || '|' ||
                competitor_product_id, 'sha256'), 'hex'), 1, 24
            ),
            relationship_role = 'primary',
            scope_mode = 'global',
            scope_definition = '{"future_location_policy":"review"}'::jsonb,
            scope_checksum = encode(digest('global', 'sha256'), 'hex')
        """
    )
    for column in (
        "comparison_family_key",
        "relationship_role",
        "scope_mode",
        "scope_definition",
        "scope_checksum",
    ):
        op.alter_column("product_match_rule", column, nullable=False)
    op.create_check_constraint(
        "product_match_rule_role_ck",
        "product_match_rule",
        "relationship_role IN ('primary', 'alternative')",
    )
    op.create_check_constraint(
        "product_match_rule_scope_mode_ck",
        "product_match_rule",
        "scope_mode IN ('global', 'observed_benchmark_product_footprint', "
        "'explicit_benchmark_locations')",
    )
    op.create_index(
        "product_match_rule_confirmed_benchmark_uq",
        "product_match_rule",
        ["revision_id", "competitor_retailer_id", "benchmark_product_id"],
        unique=True,
        postgresql_where=sa.text(
            "decision = 'confirmed' AND relationship_role = 'primary' AND scope_mode = 'global'"
        ),
    )
    op.create_index(
        "product_match_rule_confirmed_competitor_uq",
        "product_match_rule",
        ["revision_id", "competitor_retailer_id", "competitor_product_id"],
        unique=True,
        postgresql_where=sa.text(
            "decision = 'confirmed' AND relationship_role = 'primary' AND scope_mode = 'global'"
        ),
    )
    op.create_index(
        "product_match_rule_scoped_resolution_idx",
        "product_match_rule",
        ["revision_id", "competitor_retailer_id", "comparison_family_key", "scope_mode"],
    )

    op.create_table(
        "brand_classification_revision",
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
        sa.Column("benchmark_retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
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
            name="brand_classification_revision_scope_revision_uq",
        ),
        sa.CheckConstraint(
            "status IN ('current', 'superseded')",
            name="brand_classification_revision_status_ck",
        ),
    )
    op.create_index(
        "brand_classification_revision_current_uq",
        "brand_classification_revision",
        ["organization_id", "product_pack_id", "product_pack_version", "benchmark_retailer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'current'"),
    )
    op.create_table(
        "brand_classification_rule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("brand_classification_revision.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("normalized_brand", sa.Text(), nullable=False),
        sa.Column("display_brand", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "revision_id", "retailer_id", "normalized_brand", name="brand_classification_rule_uq"
        ),
        sa.CheckConstraint(
            "role IN ('private_label', 'regional', 'national', 'unclassified')",
            name="brand_classification_rule_role_ck",
        ),
        sa.CheckConstraint(
            "decision IN ('confirmed', 'rejected')",
            name="brand_classification_rule_decision_ck",
        ),
        sa.CheckConstraint(
            "origin IN ('product_pack', 'deterministic', 'user')",
            name="brand_classification_rule_origin_ck",
        ),
    )
    op.create_table(
        "brand_classification_application_policy",
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("benchmark_retailer_id", sa.Text(), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["benchmark_retailer_id"], ["retailer.id"]),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["brand_classification_revision.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "product_pack_id", "product_pack_version", "benchmark_retailer_id"
        ),
    )
    op.create_index(
        "brand_classification_application_policy_revision_idx",
        "brand_classification_application_policy",
        ["revision_id"],
    )
    op.create_table(
        "brand_classification_review_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("brand_classification_revision.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.drop_constraint(
        "analysis_run_collection_pack_match_revision_uq", "analysis_run", type_="unique"
    )
    op.add_column(
        "analysis_run",
        sa.Column(
            "brand_revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("brand_classification_revision.id"),
        ),
    )
    op.execute(
        "ALTER TABLE analysis_run ADD CONSTRAINT analysis_run_collection_pack_match_revision_uq "
        "UNIQUE NULLS NOT DISTINCT (collection_run_id, product_pack_id, product_pack_version, "
        "match_revision_id, brand_revision_id)"
    )
    op.create_index("analysis_run_brand_revision_idx", "analysis_run", ["brand_revision_id"])


def downgrade() -> None:
    op.drop_index("analysis_run_brand_revision_idx", table_name="analysis_run")
    op.drop_constraint(
        "analysis_run_collection_pack_match_revision_uq", "analysis_run", type_="unique"
    )
    op.drop_column("analysis_run", "brand_revision_id")
    op.execute(
        "ALTER TABLE analysis_run ADD CONSTRAINT analysis_run_collection_pack_match_revision_uq "
        "UNIQUE NULLS NOT DISTINCT (collection_run_id, product_pack_id, product_pack_version, "
        "match_revision_id)"
    )
    op.drop_table("brand_classification_review_event")
    op.drop_index(
        "brand_classification_application_policy_revision_idx",
        table_name="brand_classification_application_policy",
    )
    op.drop_table("brand_classification_application_policy")
    op.drop_table("brand_classification_rule")
    op.drop_index(
        "brand_classification_revision_current_uq", table_name="brand_classification_revision"
    )
    op.drop_table("brand_classification_revision")
    op.drop_index("product_match_rule_scoped_resolution_idx", table_name="product_match_rule")
    op.drop_index("product_match_rule_confirmed_competitor_uq", table_name="product_match_rule")
    op.drop_index("product_match_rule_confirmed_benchmark_uq", table_name="product_match_rule")
    op.drop_constraint("product_match_rule_scope_mode_ck", "product_match_rule", type_="check")
    op.drop_constraint("product_match_rule_role_ck", "product_match_rule", type_="check")
    for column in (
        "scope_artifact_id",
        "scope_checksum",
        "scope_definition",
        "scope_mode",
        "relationship_role",
        "comparison_family_key",
    ):
        op.drop_column("product_match_rule", column)
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
