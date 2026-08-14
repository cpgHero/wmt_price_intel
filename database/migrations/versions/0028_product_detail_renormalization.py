"""Add immutable, versioned PDP re-normalization evidence.

Revision ID: 0028_pdp_renormalization
Revises: 0027_price_intelligence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_pdp_renormalization"
down_revision: str | None = "0027_price_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_detail_normalization",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "product_detail_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_detail_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("normalizer_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("document", postgresql.JSONB()),
        sa.Column("document_checksum", sa.Text()),
        sa.Column("source_raw_checksum", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="product_detail_normalization_status_ck",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="product_detail_normalization_attempts_ck"),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 20", name="product_detail_normalization_max_attempts_ck"
        ),
        sa.CheckConstraint(
            "(status = 'succeeded' AND document IS NOT NULL AND document_checksum IS NOT NULL) "
            "OR status <> 'succeeded'",
            name="product_detail_normalization_document_ck",
        ),
        sa.UniqueConstraint(
            "product_detail_snapshot_id",
            "normalizer_version",
            name="product_detail_normalization_snapshot_version_uq",
        ),
    )
    op.create_index(
        "product_detail_normalization_claim_idx",
        "product_detail_normalization",
        ["status", "available_at", "lease_expires_at", "created_at"],
    )
    op.create_index(
        "product_detail_normalization_snapshot_idx",
        "product_detail_normalization",
        ["product_detail_snapshot_id", "normalizer_version", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "product_detail_normalization_snapshot_idx",
        table_name="product_detail_normalization",
    )
    op.drop_index(
        "product_detail_normalization_claim_idx",
        table_name="product_detail_normalization",
    )
    op.drop_table("product_detail_normalization")
