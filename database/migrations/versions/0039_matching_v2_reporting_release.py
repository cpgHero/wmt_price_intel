"""Bind immutable Matching v2 gold-set releases to governed analysis runs.

Revision ID: 0039_matching_v2_reporting_release
Revises: 0038_large_ai_batches
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039_matching_v2_reporting_release"
down_revision: str | None = "0038_large_ai_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matching_v2_gold_set_release",
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
        sa.Column(
            "review_queue_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("matching_v2_review_queue.id"),
            nullable=False,
        ),
        sa.Column("external_gold_set_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_checksum", sa.Text(), nullable=False),
        sa.Column("released_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "review_queue_id",
            "document_checksum",
            name="matching_v2_gold_set_release_queue_checksum_uq",
        ),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
        ),
        sa.CheckConstraint(
            "document_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_gold_set_release_checksum_ck",
        ),
    )
    op.create_index(
        "matching_v2_gold_set_release_pack_idx",
        "matching_v2_gold_set_release",
        ["product_pack_id", "product_pack_version", "created_at"],
    )
    op.add_column(
        "analysis_run",
        sa.Column(
            "matching_v2_gold_set_release_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("matching_v2_gold_set_release.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "analysis_run_matching_v2_gold_set_release_idx",
        "analysis_run",
        ["matching_v2_gold_set_release_id"],
    )
    op.create_unique_constraint(
        "analysis_run_source_matching_v2_release_uq",
        "analysis_run",
        ["source_analysis_result_id", "matching_v2_gold_set_release_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "analysis_run_source_matching_v2_release_uq",
        "analysis_run",
        type_="unique",
    )
    op.drop_index(
        "analysis_run_matching_v2_gold_set_release_idx",
        table_name="analysis_run",
    )
    op.drop_column("analysis_run", "matching_v2_gold_set_release_id")
    op.drop_index(
        "matching_v2_gold_set_release_pack_idx",
        table_name="matching_v2_gold_set_release",
    )
    op.drop_table("matching_v2_gold_set_release")
