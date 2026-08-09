"""Add canonical products and the durable Product Details enrichment queue.

Revision ID: 0012_product_details
Revises: 0011_input_artifact_cascade
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_product_details"
down_revision: str | None = "0011_input_artifact_cascade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "canonical_product",
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
        sa.Column("canonical_product_id", sa.Text(), nullable=False),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("retailer_product_id", sa.Text(), nullable=False),
        sa.Column("identifiers", postgresql.JSONB(), nullable=False),
        sa.Column("identity", postgresql.JSONB(), nullable=False),
        sa.Column("identity_checksum", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "organization_id",
            "retailer_id",
            "retailer_product_id",
            name="canonical_product_retailer_product_uq",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "canonical_product_id",
            name="canonical_product_stable_id_uq",
        ),
    )
    op.create_index(
        "canonical_product_retailer_idx",
        "canonical_product",
        ["retailer_id", "retailer_product_id"],
    )

    op.create_table(
        "canonical_product_context",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "canonical_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_product.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("context_checksum", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "canonical_product_id",
            "context_checksum",
            name="canonical_product_context_uq",
        ),
    )

    op.create_table(
        "product_detail_enrichment_run",
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
        sa.Column("max_credits", sa.Integer(), nullable=False),
        sa.Column("planned_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("max_credits > 0", name="product_detail_run_max_credits_ck"),
        sa.CheckConstraint("planned_credits >= 0", name="product_detail_run_planned_ck"),
        sa.CheckConstraint("actual_credits >= 0", name="product_detail_run_actual_ck"),
        sa.CheckConstraint("planned_credits <= max_credits", name="product_detail_run_ceiling_ck"),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'completed_with_errors', 'canceled')",
            name="product_detail_run_status_ck",
        ),
    )

    op.create_table(
        "product_detail_job",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "enrichment_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_detail_enrichment_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "canonical_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_product.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("endpoint", postgresql.JSONB(), nullable=False),
        sa.Column("request_context", postgresql.JSONB(), nullable=False),
        sa.Column("request_checksum", sa.Text(), nullable=False),
        sa.Column("credits_per_call", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_http_status", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column("billable_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("credits_per_call > 0", name="product_detail_job_credits_ck"),
        sa.CheckConstraint("attempt_count >= 0", name="product_detail_job_attempts_ck"),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10", name="product_detail_job_max_attempts_ck"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name="product_detail_job_status_ck",
        ),
        sa.UniqueConstraint(
            "enrichment_run_id",
            "request_checksum",
            name="product_detail_job_request_uq",
        ),
    )
    op.create_index(
        "product_detail_job_claim_idx",
        "product_detail_job",
        ["status", "available_at", "priority", "created_at"],
    )
    op.create_index(
        "product_detail_job_product_idx",
        "product_detail_job",
        ["canonical_product_id", "created_at"],
    )

    op.create_table(
        "product_detail_snapshot",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "canonical_product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_product.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_detail_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_detail_job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_checksum", sa.Text(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("billable_credits", sa.Integer(), nullable=False),
        sa.Column("raw_storage_uri", sa.Text(), nullable=False),
        sa.Column("raw_checksum", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cache_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("attempt_number > 0", name="product_detail_snapshot_attempt_ck"),
        sa.CheckConstraint("billable_credits >= 0", name="product_detail_snapshot_credits_ck"),
        sa.UniqueConstraint(
            "product_detail_job_id",
            "attempt_number",
            name="product_detail_snapshot_attempt_uq",
        ),
    )
    op.create_index(
        "product_detail_snapshot_cache_idx",
        "product_detail_snapshot",
        ["canonical_product_id", "request_checksum", "cache_expires_at"],
        postgresql_where=sa.text("normalized"),
    )


def downgrade() -> None:
    op.drop_index("product_detail_snapshot_cache_idx", table_name="product_detail_snapshot")
    op.drop_table("product_detail_snapshot")
    op.drop_index("product_detail_job_product_idx", table_name="product_detail_job")
    op.drop_index("product_detail_job_claim_idx", table_name="product_detail_job")
    op.drop_table("product_detail_job")
    op.drop_table("product_detail_enrichment_run")
    op.drop_table("canonical_product_context")
    op.drop_index("canonical_product_retailer_idx", table_name="canonical_product")
    op.drop_table("canonical_product")
