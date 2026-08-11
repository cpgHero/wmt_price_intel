"""Add governed Product Pack draft, evidence, validation, and audit state.

Revision ID: 0023_product_pack_authoring
Revises: 0022_product_pack_runtime
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_product_pack_authoring"
down_revision: str | None = "0022_product_pack_runtime"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "product_pack_draft",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("base_version", sa.Text()),
        sa.Column("proposed_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("report_blueprint", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'validating', 'candidate', 'certified', 'published', 'abandoned')",
            name="product_pack_draft_status_ck",
        ),
        sa.CheckConstraint("revision >= 1", name="product_pack_draft_revision_ck"),
        sa.UniqueConstraint(
            "product_pack_id",
            "proposed_version",
            name="product_pack_draft_pack_version_uq",
        ),
    )
    op.create_index(
        "product_pack_draft_status_updated_idx",
        "product_pack_draft",
        ["status", "updated_at"],
    )
    op.create_table(
        "product_pack_draft_revision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_pack_draft.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("report_blueprint", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "draft_id",
            "revision",
            name="product_pack_draft_revision_uq",
        ),
    )
    op.create_table(
        "product_pack_evidence_set",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_pack_draft.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.BigInteger()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind IN ('serp', 'pdp', 'classification', 'attribute', 'comparison', "
            "'compact_golden', 'full_golden')",
            name="product_pack_evidence_kind_ck",
        ),
        sa.CheckConstraint("byte_size >= 0", name="product_pack_evidence_size_ck"),
        sa.UniqueConstraint(
            "draft_id", "kind", "checksum", name="product_pack_evidence_checksum_uq"
        ),
    )
    op.create_table(
        "product_pack_validation_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_pack_draft.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("draft_checksum", sa.Text(), nullable=False),
        sa.Column("suite", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("gates", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("engine_version", sa.Text()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "suite IN ('quick', 'compact', 'full', 'publication')",
            name="product_pack_validation_suite_ck",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'cancelled')",
            name="product_pack_validation_status_ck",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts >= 1",
            name="product_pack_validation_attempt_ck",
        ),
    )
    op.create_index(
        "product_pack_validation_claim_idx",
        "product_pack_validation_run",
        ["status", "lease_expires_at", "created_at"],
    )
    op.create_table(
        "product_pack_review_event",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_pack_draft.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "product_pack_version",
        sa.Column(
            "certification_validation_run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_pack_validation_run.id", ondelete="SET NULL"),
        ),
    )


def downgrade() -> None:
    op.drop_column("product_pack_version", "certification_validation_run_id")
    op.drop_table("product_pack_review_event")
    op.drop_index("product_pack_validation_claim_idx", table_name="product_pack_validation_run")
    op.drop_table("product_pack_validation_run")
    op.drop_table("product_pack_evidence_set")
    op.drop_table("product_pack_draft_revision")
    op.drop_index("product_pack_draft_status_updated_idx", table_name="product_pack_draft")
    op.drop_table("product_pack_draft")
