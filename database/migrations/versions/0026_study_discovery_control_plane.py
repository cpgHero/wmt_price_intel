"""Add governed study discovery, candidate profiling, and paid-work approvals.

Revision ID: 0026_study_discovery
Revises: 0025_retailer_pack_brand
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_study_discovery"
down_revision: str | None = "0025_retailer_pack_brand"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Discovery stages every PDP job before making the run worker-visible. This closes
    # a race where a fast worker could finish the first job while the API was still
    # adding the rest of the approved plan.
    op.drop_constraint(
        "product_detail_run_status_ck",
        "product_detail_enrichment_run",
        type_="check",
    )
    op.create_check_constraint(
        "product_detail_run_status_ck",
        "product_detail_enrichment_run",
        "status IN ('planning', 'active', 'completed', 'completed_with_errors', 'canceled')",
    )
    op.create_table(
        "study_discovery",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="query_review"),
        sa.Column("intake", postgresql.JSONB(), nullable=False),
        sa.Column("query_plan", postgresql.JSONB(), nullable=False),
        sa.Column("query_plan_checksum", sa.Text(), nullable=False),
        sa.Column("approval_state", postgresql.JSONB(), nullable=False),
        sa.Column(
            "geography_resolution_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("collection_geography_resolution.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "search_scope_estimate_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("collection_scope_estimate.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("collection_run.id", ondelete="SET NULL"),
        ),
        sa.Column("pdp_estimate", postgresql.JSONB()),
        sa.Column("pdp_plan_checksum", sa.Text()),
        sa.Column(
            "pdp_run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_detail_enrichment_run.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "product_pack_draft_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_pack_draft.id", ondelete="SET NULL"),
        ),
        sa.Column("profile_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('query_review','search_estimated','collecting','profiling',"
            "'profile_ready','pdp_estimated','enriching','draft_ready','certifying',"
            "'certified','published','failed','canceled')",
            name="study_discovery_status_ck",
        ),
    )
    op.create_index(
        "study_discovery_collection_run_uq",
        "study_discovery",
        ["collection_run_id"],
        unique=True,
        postgresql_where=sa.text("collection_run_id IS NOT NULL"),
    )
    op.create_table(
        "study_discovery_product",
        sa.Column(
            "study_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("study_discovery.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("retailer_product_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("admission_status", sa.Text(), nullable=False),
        sa.Column("admission_reason", sa.Text(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("store_count", sa.Integer(), nullable=False),
        sa.Column("zipcode_count", sa.Integer(), nullable=False),
        sa.Column("price_min", sa.Numeric(18, 4)),
        sa.Column("price_max", sa.Numeric(18, 4)),
        sa.Column("price_contexts", postgresql.JSONB(), nullable=False),
        sa.Column("representative_context", postgresql.JSONB(), nullable=False),
        sa.Column("brand_resolution", postgresql.JSONB(), nullable=False),
        sa.Column("identifiers", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source_artifact_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("study_id", "retailer_id", "retailer_product_id"),
        sa.CheckConstraint(
            "admission_status IN ('provisionally_admitted','excluded','review_required')",
            name="study_discovery_product_admission_ck",
        ),
    )
    op.create_index(
        "study_discovery_product_status_idx",
        "study_discovery_product",
        ["study_id", "admission_status", "retailer_id"],
    )
    op.create_table(
        "study_discovery_job",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "study_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("study_discovery.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("study_id", "idempotency_key"),
        sa.CheckConstraint(
            "kind IN ('profile','query_ai','product_pack_ai')",
            name="study_discovery_job_kind_ck",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','canceled')",
            name="study_discovery_job_status_ck",
        ),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 10", name="study_discovery_attempts_ck"),
    )
    op.create_index(
        "study_discovery_job_claim_idx",
        "study_discovery_job",
        ["status", "available_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("study_discovery_job_claim_idx", table_name="study_discovery_job")
    op.drop_table("study_discovery_job")
    op.drop_index("study_discovery_product_status_idx", table_name="study_discovery_product")
    op.drop_table("study_discovery_product")
    op.drop_index("study_discovery_collection_run_uq", table_name="study_discovery")
    op.drop_table("study_discovery")
    op.execute(
        "UPDATE product_detail_enrichment_run SET status = 'canceled', completed_at = now() "
        "WHERE status = 'planning'"
    )
    op.drop_constraint(
        "product_detail_run_status_ck",
        "product_detail_enrichment_run",
        type_="check",
    )
    op.create_check_constraint(
        "product_detail_run_status_ck",
        "product_detail_enrichment_run",
        "status IN ('active', 'completed', 'completed_with_errors', 'canceled')",
    )
