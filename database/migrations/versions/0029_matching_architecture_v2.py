"""Add evidence-governed Matching Architecture v2 shadow persistence.

Revision ID: 0029_matching_architecture_v2
Revises: 0028_pdp_renormalization
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_matching_architecture_v2"
down_revision: str | None = "0028_pdp_renormalization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "trade_item_v2",
        _uuid(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("identifiers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("package_configuration", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("identity_checksum", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="provisional"),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        _created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
        ),
        sa.UniqueConstraint(
            "organization_id", "identity_checksum", name="trade_item_v2_identity_uq"
        ),
        sa.CheckConstraint(
            "status IN ('provisional','verified','disputed','retired')",
            name="trade_item_v2_status_ck",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="trade_item_v2_effective_period_ck",
        ),
    )
    op.create_index(
        "trade_item_v2_pack_idx",
        "trade_item_v2",
        ["organization_id", "product_pack_id", "status"],
    )

    op.create_table(
        "retailer_listing_v2",
        _uuid(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("retailer_product_id", sa.Text(), nullable=False),
        sa.Column(
            "legacy_canonical_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_product.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "trade_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trade_item_v2.id", ondelete="SET NULL"),
        ),
        sa.Column("identity", postgresql.JSONB(), nullable=False),
        sa.Column("identifiers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("identity_checksum", sa.Text(), nullable=False),
        sa.Column(
            "identity_basis", sa.Text(), nullable=False, server_default="retailer_listing_only"
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        _created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "organization_id",
            "retailer_id",
            "retailer_product_id",
            name="retailer_listing_v2_identity_uq",
        ),
        sa.CheckConstraint(
            "identity_basis IN ('verified_gtin_package','manufacturer_identifier',"
            "'retailer_listing_only','human_approved')",
            name="retailer_listing_v2_basis_ck",
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive','disputed','retired')",
            name="retailer_listing_v2_status_ck",
        ),
    )
    op.create_index("retailer_listing_v2_trade_item_idx", "retailer_listing_v2", ["trade_item_id"])
    op.create_index(
        "retailer_listing_v2_retailer_idx",
        "retailer_listing_v2",
        ["retailer_id", "retailer_product_id", "status"],
    )

    op.create_table(
        "product_attribute_fact_v2",
        _uuid(),
        sa.Column(
            "retailer_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_listing_v2.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "trade_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trade_item_v2.id", ondelete="CASCADE"),
        ),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("attribute_name", sa.Text(), nullable=False),
        sa.Column("raw_value", postgresql.JSONB(), nullable=False),
        sa.Column("normalized_value", postgresql.JSONB(), nullable=False),
        sa.Column("unit", sa.Text()),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("source_checksum", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extraction_method", sa.Text(), nullable=False),
        sa.Column("reliability", sa.Numeric(5, 4), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="unreviewed"),
        sa.Column("reviewer", sa.Text()),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
        ),
        sa.UniqueConstraint(
            "source_checksum", "attribute_name", name="product_attribute_fact_v2_source_uq"
        ),
        sa.CheckConstraint(
            "num_nonnulls(retailer_listing_id, trade_item_id) = 1",
            name="product_attribute_fact_v2_subject_ck",
        ),
        sa.CheckConstraint(
            "source_kind IN ('search','pdp','manufacturer','brand_foundation',"
            "'ocr','vision','human')",
            name="product_attribute_fact_v2_source_kind_ck",
        ),
        sa.CheckConstraint(
            "extraction_method IN ('structured','rule','ocr','vision','manual')",
            name="product_attribute_fact_v2_extraction_ck",
        ),
        sa.CheckConstraint(
            "reliability BETWEEN 0 AND 1", name="product_attribute_fact_v2_reliability_ck"
        ),
        sa.CheckConstraint(
            "review_status IN ('unreviewed','verified','rejected','conflicted','superseded')",
            name="product_attribute_fact_v2_review_ck",
        ),
    )
    op.create_index(
        "product_attribute_fact_v2_listing_idx",
        "product_attribute_fact_v2",
        ["retailer_listing_id", "attribute_name", "review_status", "observed_at"],
    )
    op.create_index(
        "product_attribute_fact_v2_trade_item_idx",
        "product_attribute_fact_v2",
        ["trade_item_id", "attribute_name", "review_status", "observed_at"],
    )

    op.create_table(
        "match_policy_version_v2",
        _uuid(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("document_checksum", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
        ),
        sa.UniqueConstraint(
            "organization_id", "policy_id", "version", name="match_policy_version_v2_uq"
        ),
        sa.UniqueConstraint(
            "organization_id", "document_checksum", name="match_policy_version_v2_checksum_uq"
        ),
        sa.CheckConstraint(
            "status IN ('draft','shadow','certified','retired')",
            name="match_policy_version_v2_status_ck",
        ),
    )

    op.create_table(
        "product_match_candidate_v2",
        _uuid(),
        sa.Column(
            "policy_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("match_policy_version_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "benchmark_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_listing_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "competitor_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_listing_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("blocking_reasons", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("candidate_generator", sa.Text(), nullable=False),
        sa.Column("candidate_generator_version", sa.Text(), nullable=False),
        sa.Column("priority_score", sa.Numeric(8, 6)),
        sa.Column("status", sa.Text(), nullable=False, server_default="candidate"),
        _created_at(),
        sa.UniqueConstraint(
            "policy_version_id",
            "benchmark_listing_id",
            "competitor_listing_id",
            name="product_match_candidate_v2_pair_uq",
        ),
        sa.CheckConstraint(
            "status IN ('candidate','evaluated','suppressed')",
            name="product_match_candidate_v2_status_ck",
        ),
    )
    op.create_index(
        "product_match_candidate_v2_queue_idx",
        "product_match_candidate_v2",
        ["policy_version_id", "status", "priority_score", "created_at"],
    )

    op.create_table(
        "product_match_edge_v2",
        _uuid(),
        sa.Column(
            "policy_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("match_policy_version_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_match_candidate_v2.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "benchmark_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_listing_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "competitor_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_listing_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tier", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("brand_relationship", sa.Text(), nullable=False),
        sa.Column("eligible_price_bases", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("evidence_coverage", postgresql.JSONB(), nullable=False),
        sa.Column("applicability", postgresql.JSONB(), nullable=False),
        sa.Column("decision_origin", sa.Text(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column(
            "supersedes_edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_match_edge_v2.id", ondelete="SET NULL"),
        ),
        _created_at(),
        sa.UniqueConstraint(
            "policy_version_id",
            "benchmark_listing_id",
            "competitor_listing_id",
            "effective_from",
            name="product_match_edge_v2_claim_uq",
        ),
        sa.CheckConstraint(
            "tier IS NULL OR tier IN ('exact_item','exact_specification','equivalent_product',"
            "'comparable_substitute','custom_approved')",
            name="product_match_edge_v2_tier_ck",
        ),
        sa.CheckConstraint(
            "status IN ('candidate','auto_approved','human_approved','rejected','expired',"
            "'superseded','needs_revalidation','unresolved','not_comparable')",
            name="product_match_edge_v2_status_ck",
        ),
        sa.CheckConstraint(
            "(tier IS NULL AND cardinality(eligible_price_bases) = 0) OR "
            "(tier IS NOT NULL AND cardinality(eligible_price_bases) > 0)",
            name="product_match_edge_v2_price_bases_ck",
        ),
        sa.CheckConstraint(
            "decision_origin IN ('deterministic_rule','model_assisted','human','legacy')",
            name="product_match_edge_v2_origin_ck",
        ),
    )
    op.create_index(
        "product_match_edge_v2_benchmark_idx",
        "product_match_edge_v2",
        ["policy_version_id", "benchmark_listing_id", "status"],
    )
    op.create_index(
        "product_match_edge_v2_competitor_idx",
        "product_match_edge_v2",
        ["policy_version_id", "competitor_listing_id", "status"],
    )

    op.create_table(
        "product_match_attribute_evidence_v2",
        _uuid(),
        sa.Column(
            "match_edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_match_edge_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attribute_name", sa.Text(), nullable=False),
        sa.Column("attribute_role", sa.Text(), nullable=False),
        sa.Column("benchmark_value", postgresql.JSONB(), nullable=False),
        sa.Column("competitor_value", postgresql.JSONB(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("benchmark_source_reference", sa.Text()),
        sa.Column("competitor_source_reference", sa.Text()),
        sa.Column("weight", sa.Numeric(8, 6), nullable=False, server_default="1"),
        sa.Column("rationale", sa.Text()),
        _created_at(),
        sa.UniqueConstraint(
            "match_edge_id", "attribute_name", name="product_match_attribute_evidence_v2_uq"
        ),
        sa.CheckConstraint(
            "attribute_role IN ('identity','hard_blocker','required_exact','soft_comparator',"
            "'descriptive','ignored')",
            name="product_match_attribute_evidence_v2_role_ck",
        ),
        sa.CheckConstraint(
            "outcome IN ('match','conflict','unknown','ignored','within_tolerance')",
            name="product_match_attribute_evidence_v2_outcome_ck",
        ),
        sa.CheckConstraint("weight >= 0", name="product_match_attribute_evidence_v2_weight_ck"),
    )

    op.create_table(
        "match_group_v2",
        _uuid(),
        sa.Column(
            "policy_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("match_policy_version_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("group_key", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("definition", postgresql.JSONB(), nullable=False, server_default="{}"),
        _created_at(),
        sa.UniqueConstraint("policy_version_id", "group_key", name="match_group_v2_policy_key_uq"),
        sa.CheckConstraint(
            "purpose IN ('product_relationship','comparable_cohort','assortment_rollup')",
            name="match_group_v2_purpose_ck",
        ),
        sa.CheckConstraint(
            "status IN ('active','draft','retired')", name="match_group_v2_status_ck"
        ),
    )

    op.create_table(
        "match_group_member_v2",
        _uuid(),
        sa.Column(
            "match_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("match_group_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "retailer_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_listing_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "match_edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_match_edge_v2.id", ondelete="SET NULL"),
        ),
        sa.Column("member_role", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("applicability", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        _created_at(),
        sa.UniqueConstraint(
            "match_group_id", "retailer_listing_id", name="match_group_member_v2_uq"
        ),
        sa.CheckConstraint(
            "member_role IN ('anchor','benchmark_member','competitor_member','alternative')",
            name="match_group_member_v2_role_ck",
        ),
    )

    op.create_table(
        "store_catchment_policy_v2",
        _uuid(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("benchmark_retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column(
            "competitor_retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False
        ),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="shadow"),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        _created_at(),
        sa.UniqueConstraint(
            "organization_id", "policy_id", "version", name="store_catchment_policy_v2_uq"
        ),
        sa.CheckConstraint(
            "method IN ('nearest','radius','drive_time','merchant_group',"
            "'same_zip','service_area')",
            name="store_catchment_policy_v2_method_ck",
        ),
        sa.CheckConstraint(
            "status IN ('draft','shadow','certified','retired')",
            name="store_catchment_policy_v2_status_ck",
        ),
    )

    op.create_table(
        "store_catchment_v2",
        _uuid(),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("store_catchment_policy_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "benchmark_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_location.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "competitor_location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_location.id", ondelete="CASCADE"),
        ),
        sa.Column("competitor_service_area_key", sa.Text()),
        sa.Column("distance_miles", sa.Numeric(10, 4)),
        sa.Column("drive_time_minutes", sa.Numeric(10, 2)),
        sa.Column("market_group", sa.Text()),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        _created_at(),
        sa.CheckConstraint(
            "num_nonnulls(competitor_location_id, competitor_service_area_key) = 1",
            name="store_catchment_v2_competitor_context_ck",
        ),
        sa.CheckConstraint(
            "distance_miles IS NULL OR distance_miles >= 0",
            name="store_catchment_v2_distance_ck",
        ),
    )
    op.create_index(
        "store_catchment_v2_benchmark_idx",
        "store_catchment_v2",
        ["policy_id", "benchmark_location_id"],
    )

    op.create_table(
        "local_comparison_observation_v2",
        _uuid(),
        sa.Column(
            "analysis_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "match_edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_match_edge_v2.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "benchmark_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_listing_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "competitor_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retailer_listing_v2.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "competitor_retailer_id",
            sa.Text(),
            sa.ForeignKey("retailer.id"),
            nullable=False,
        ),
        sa.Column("policy_revision", sa.Text(), nullable=False),
        sa.Column("price_basis", sa.Text(), nullable=False),
        sa.Column("benchmark_location_scope_key", sa.Text(), nullable=False),
        sa.Column("competitor_location_scope_key", sa.Text()),
        sa.Column("benchmark_offer_id", sa.Text()),
        sa.Column("competitor_offer_id", sa.Text()),
        sa.Column("benchmark_value", sa.Numeric(18, 6)),
        sa.Column("competitor_value", sa.Numeric(18, 6)),
        sa.Column("competitor_minus_benchmark", sa.Numeric(18, 6)),
        sa.Column("winner", sa.Text()),
        sa.Column("semantic_coverage", sa.Boolean(), nullable=False),
        sa.Column("availability_coverage", sa.Boolean(), nullable=False),
        sa.Column("price_coverage", sa.Boolean(), nullable=False),
        sa.Column("coverage_reason", sa.Text(), nullable=False),
        sa.Column("selection_status", sa.Text(), nullable=False),
        sa.Column("selection_policy", sa.Text(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("selection_rank", sa.Integer()),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("source_authority", sa.Text(), nullable=False),
        _created_at(),
        sa.UniqueConstraint(
            "analysis_result_id",
            "match_edge_id",
            "benchmark_listing_id",
            "competitor_listing_id",
            "competitor_retailer_id",
            "policy_revision",
            "price_basis",
            "benchmark_location_scope_key",
            "competitor_location_scope_key",
            "competitor_offer_id",
            name="local_comparison_observation_v2_grain_uq",
        ),
        sa.CheckConstraint(
            "price_basis IN ('exact_package','normalized_unit','random_weight_unit')",
            name="local_comparison_observation_v2_basis_ck",
        ),
        sa.CheckConstraint(
            "winner IS NULL OR winner IN ('benchmark_lower','competitor_lower','parity')",
            name="local_comparison_observation_v2_winner_ck",
        ),
        sa.CheckConstraint(
            "coverage_reason IN ('comparable','no_eligible_match','no_geographic_overlap',"
            "'matched_product_not_observed','price_unavailable_or_stale','collection_failure',"
            "'attribute_evidence_incomplete','match_review_required')",
            name="local_comparison_observation_v2_coverage_ck",
        ),
        sa.CheckConstraint(
            "selection_status IN ('selected','eligible_not_selected','unscored')",
            name="local_comparison_observation_v2_selection_ck",
        ),
        sa.CheckConstraint(
            "selection_policy IN ('lowest_eligible_local_offer','nearest_eligible_offer',"
            "'representative_assortment')",
            name="local_comparison_observation_v2_policy_ck",
        ),
        sa.CheckConstraint("candidate_count >= 0", name="local_comparison_v2_candidates_ck"),
        sa.CheckConstraint(
            "source_authority = 'search_location_observation'",
            name="local_comparison_observation_v2_authority_ck",
        ),
    )
    op.create_index(
        "local_comparison_observation_v2_benchmark_idx",
        "local_comparison_observation_v2",
        ["analysis_result_id", "benchmark_location_scope_key", "selection_status"],
    )
    op.create_index(
        "local_comparison_observation_v2_edge_idx",
        "local_comparison_observation_v2",
        ["match_edge_id", "coverage_reason", "selection_status"],
    )
    op.create_index(
        "local_comparison_observation_v2_selected_uq",
        "local_comparison_observation_v2",
        [
            "analysis_result_id",
            "benchmark_listing_id",
            "competitor_retailer_id",
            "policy_revision",
            "benchmark_location_scope_key",
            "price_basis",
        ],
        unique=True,
        postgresql_where=sa.text("selection_status = 'selected'"),
    )
    op.create_index(
        "local_comparison_observation_v2_unscored_uq",
        "local_comparison_observation_v2",
        [
            "analysis_result_id",
            "benchmark_listing_id",
            "competitor_retailer_id",
            "policy_revision",
            "benchmark_location_scope_key",
            "price_basis",
            "coverage_reason",
        ],
        unique=True,
        postgresql_where=sa.text("selection_status = 'unscored'"),
    )

    op.create_table(
        "product_match_decision_event_v2",
        _uuid(),
        sa.Column(
            "match_edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_match_edge_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.Text()),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        _created_at(),
    )
    op.create_index(
        "product_match_decision_event_v2_edge_idx",
        "product_match_decision_event_v2",
        ["match_edge_id", "created_at"],
    )

    op.create_table(
        "product_match_revalidation_event_v2",
        _uuid(),
        sa.Column(
            "match_edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_match_edge_v2.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger_kind", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("prior_checksum", sa.Text()),
        sa.Column("new_checksum", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        _created_at(),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "trigger_kind IN ('identifier','title','package','attribute','brand','image',"
            "'supplier_geography','distribution','policy')",
            name="product_match_revalidation_event_v2_trigger_ck",
        ),
        sa.CheckConstraint(
            "status IN ('queued','reviewed','reapproved','rejected','superseded')",
            name="product_match_revalidation_event_v2_status_ck",
        ),
    )
    op.create_index(
        "product_match_revalidation_event_v2_queue_idx",
        "product_match_revalidation_event_v2",
        ["status", "trigger_kind", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "local_comparison_observation_v2_unscored_uq",
        table_name="local_comparison_observation_v2",
    )
    op.drop_index(
        "local_comparison_observation_v2_selected_uq",
        table_name="local_comparison_observation_v2",
    )
    op.drop_index(
        "product_match_revalidation_event_v2_queue_idx",
        table_name="product_match_revalidation_event_v2",
    )
    op.drop_table("product_match_revalidation_event_v2")
    op.drop_index(
        "product_match_decision_event_v2_edge_idx", table_name="product_match_decision_event_v2"
    )
    op.drop_table("product_match_decision_event_v2")
    op.drop_index(
        "local_comparison_observation_v2_edge_idx", table_name="local_comparison_observation_v2"
    )
    op.drop_index(
        "local_comparison_observation_v2_benchmark_idx",
        table_name="local_comparison_observation_v2",
    )
    op.drop_table("local_comparison_observation_v2")
    op.drop_index("store_catchment_v2_benchmark_idx", table_name="store_catchment_v2")
    op.drop_table("store_catchment_v2")
    op.drop_table("store_catchment_policy_v2")
    op.drop_table("match_group_member_v2")
    op.drop_table("match_group_v2")
    op.drop_table("product_match_attribute_evidence_v2")
    op.drop_index("product_match_edge_v2_competitor_idx", table_name="product_match_edge_v2")
    op.drop_index("product_match_edge_v2_benchmark_idx", table_name="product_match_edge_v2")
    op.drop_table("product_match_edge_v2")
    op.drop_index("product_match_candidate_v2_queue_idx", table_name="product_match_candidate_v2")
    op.drop_table("product_match_candidate_v2")
    op.drop_table("match_policy_version_v2")
    op.drop_index(
        "product_attribute_fact_v2_trade_item_idx", table_name="product_attribute_fact_v2"
    )
    op.drop_index("product_attribute_fact_v2_listing_idx", table_name="product_attribute_fact_v2")
    op.drop_table("product_attribute_fact_v2")
    op.drop_index("retailer_listing_v2_retailer_idx", table_name="retailer_listing_v2")
    op.drop_index("retailer_listing_v2_trade_item_idx", table_name="retailer_listing_v2")
    op.drop_table("retailer_listing_v2")
    op.drop_index("trade_item_v2_pack_idx", table_name="trade_item_v2")
    op.drop_table("trade_item_v2")
