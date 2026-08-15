"""Add immutable dual-review and adjudication persistence for Matching v2.

Revision ID: 0030_matching_v2_human_review
Revises: 0029_matching_architecture_v2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_matching_v2_human_review"
down_revision: str | None = "0029_matching_architecture_v2"
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
        "matching_v2_review_queue",
        _uuid(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_queue_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("product_pack_id", sa.Text(), nullable=False),
        sa.Column("product_pack_version", sa.Text(), nullable=False),
        sa.Column("policy_checksum", sa.Text(), nullable=False),
        sa.Column("source_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("sampling", postgresql.JSONB(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("document_checksum", sa.Text(), nullable=False),
        sa.Column("imported_by", sa.Text(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["product_pack_id", "product_pack_version"],
            ["product_pack_version.product_pack_id", "product_pack_version.version"],
        ),
        sa.UniqueConstraint(
            "organization_id",
            "external_queue_id",
            "version",
            name="matching_v2_review_queue_version_uq",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "document_checksum",
            name="matching_v2_review_queue_checksum_uq",
        ),
        sa.CheckConstraint(
            "document_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_review_queue_checksum_ck",
        ),
    )
    op.create_index(
        "matching_v2_review_queue_pack_idx",
        "matching_v2_review_queue",
        ["organization_id", "product_pack_id", "product_pack_version", "created_at"],
    )

    op.create_table(
        "matching_v2_review_case",
        _uuid(),
        sa.Column(
            "review_queue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_queue.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_case_id", sa.Text(), nullable=False),
        sa.Column("benchmark_listing_id", sa.Text(), nullable=False),
        sa.Column("competitor_listing_id", sa.Text(), nullable=False),
        sa.Column(
            "competitor_retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False
        ),
        sa.Column("stratum", sa.Text(), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False),
        sa.Column("case_document", postgresql.JSONB(), nullable=False),
        sa.Column("case_checksum", sa.Text(), nullable=False),
        _created_at(),
        sa.UniqueConstraint(
            "review_queue_id", "external_case_id", name="matching_v2_review_case_external_uq"
        ),
        sa.UniqueConstraint(
            "review_queue_id",
            "benchmark_listing_id",
            "competitor_listing_id",
            name="matching_v2_review_case_pair_uq",
        ),
        sa.CheckConstraint(
            "case_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_review_case_checksum_ck",
        ),
    )
    op.create_index(
        "matching_v2_review_case_queue_idx",
        "matching_v2_review_case",
        ["review_queue_id", "competitor_retailer_id", "stratum", "critical", "created_at"],
    )

    op.create_table(
        "matching_v2_review_submission",
        _uuid(),
        sa.Column(
            "review_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("allowed_tiers", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("submission_checksum", sa.Text(), nullable=False),
        sa.Column(
            "supersedes_submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_submission.id", ondelete="RESTRICT"),
        ),
        _created_at(),
        sa.UniqueConstraint(
            "review_case_id",
            "reviewer_id",
            "submission_checksum",
            name="matching_v2_review_submission_idempotency_uq",
        ),
        sa.UniqueConstraint(
            "submission_checksum", name="matching_v2_review_submission_checksum_uq"
        ),
        sa.CheckConstraint(
            "verdict IN ('comparable','not_comparable','insufficient_evidence')",
            name="matching_v2_review_submission_verdict_ck",
        ),
        sa.CheckConstraint(
            "(verdict = 'comparable' AND cardinality(allowed_tiers) > 0) OR "
            "(verdict <> 'comparable' AND cardinality(allowed_tiers) = 0)",
            name="matching_v2_review_submission_tiers_ck",
        ),
        sa.CheckConstraint(
            "submission_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_review_submission_checksum_ck",
        ),
    )
    op.create_index(
        "matching_v2_review_submission_case_idx",
        "matching_v2_review_submission",
        ["review_case_id", "reviewer_id", "created_at"],
    )

    op.create_table(
        "matching_v2_adjudication",
        _uuid(),
        sa.Column(
            "review_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("adjudicator_id", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("allowed_tiers", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("adjudication_checksum", sa.Text(), nullable=False),
        sa.Column(
            "supersedes_adjudication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_adjudication.id", ondelete="RESTRICT"),
        ),
        _created_at(),
        sa.UniqueConstraint("adjudication_checksum", name="matching_v2_adjudication_checksum_uq"),
        sa.CheckConstraint(
            "verdict IN ('comparable','not_comparable','insufficient_evidence')",
            name="matching_v2_adjudication_verdict_ck",
        ),
        sa.CheckConstraint(
            "(verdict = 'comparable' AND cardinality(allowed_tiers) > 0) OR "
            "(verdict <> 'comparable' AND cardinality(allowed_tiers) = 0)",
            name="matching_v2_adjudication_tiers_ck",
        ),
        sa.CheckConstraint(
            "adjudication_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_adjudication_checksum_ck",
        ),
    )
    op.create_index(
        "matching_v2_adjudication_case_idx",
        "matching_v2_adjudication",
        ["review_case_id", "created_at"],
    )

    op.create_table(
        "matching_v2_adjudication_submission",
        sa.Column(
            "adjudication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_adjudication.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_submission.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )

    op.execute(
        """
        CREATE FUNCTION prevent_matching_v2_review_record_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'Matching v2 review and adjudication records are immutable';
        END;
        $$
        """
    )
    for table_name in (
        "matching_v2_review_queue",
        "matching_v2_review_case",
        "matching_v2_review_submission",
        "matching_v2_adjudication",
        "matching_v2_adjudication_submission",
    ):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_immutable_trg
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION prevent_matching_v2_review_record_mutation()
            """
        )


def downgrade() -> None:
    for table_name in (
        "matching_v2_adjudication_submission",
        "matching_v2_adjudication",
        "matching_v2_review_submission",
        "matching_v2_review_case",
        "matching_v2_review_queue",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table_name}_immutable_trg ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS prevent_matching_v2_review_record_mutation()")
    op.drop_table("matching_v2_adjudication_submission")
    op.drop_index("matching_v2_adjudication_case_idx", table_name="matching_v2_adjudication")
    op.drop_table("matching_v2_adjudication")
    op.drop_index(
        "matching_v2_review_submission_case_idx",
        table_name="matching_v2_review_submission",
    )
    op.drop_table("matching_v2_review_submission")
    op.drop_index("matching_v2_review_case_queue_idx", table_name="matching_v2_review_case")
    op.drop_table("matching_v2_review_case")
    op.drop_index("matching_v2_review_queue_pack_idx", table_name="matching_v2_review_queue")
    op.drop_table("matching_v2_review_queue")
