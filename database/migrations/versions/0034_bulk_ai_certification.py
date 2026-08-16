"""Add immutable audit evidence for guarded bulk AI certification.

Revision ID: 0034_bulk_ai_certification
Revises: 0033_ai_review_batches
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_bulk_ai_certification"
down_revision: str | None = "0033_ai_review_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matching_v2_bulk_certification_action",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "review_queue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_queue.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("policy_id", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("policy_checksum", sa.Text(), nullable=False),
        sa.Column("confirmation_checksum", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("case_ids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("audit_document", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="matching_v2_bulk_certification_idempotency_uq",
        ),
        sa.CheckConstraint(
            "action_type = 'approve_ai_matches'",
            name="matching_v2_bulk_certification_action_type_ck",
        ),
        sa.CheckConstraint(
            "case_count BETWEEN 1 AND 50 AND case_count = cardinality(case_ids)",
            name="matching_v2_bulk_certification_case_count_ck",
        ),
        sa.CheckConstraint(
            "policy_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_bulk_certification_policy_checksum_ck",
        ),
        sa.CheckConstraint(
            "confirmation_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_bulk_certification_confirmation_checksum_ck",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[a-f0-9]{64}$'",
            name="matching_v2_bulk_certification_idempotency_ck",
        ),
    )
    op.create_index(
        "matching_v2_bulk_certification_queue_idx",
        "matching_v2_bulk_certification_action",
        ["review_queue_id", "created_at"],
    )
    op.add_column(
        "matching_v2_review_submission",
        sa.Column("bulk_action_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "matching_v2_review_submission_bulk_action_fk",
        "matching_v2_review_submission",
        "matching_v2_bulk_certification_action",
        ["bulk_action_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "matching_v2_review_submission_bulk_action_idx",
        "matching_v2_review_submission",
        ["bulk_action_id"],
    )
    op.execute(
        """
        CREATE TRIGGER matching_v2_bulk_certification_action_immutable_trg
        BEFORE UPDATE OR DELETE ON matching_v2_bulk_certification_action
        FOR EACH ROW EXECUTE FUNCTION prevent_matching_v2_review_record_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS matching_v2_bulk_certification_action_immutable_trg "
        "ON matching_v2_bulk_certification_action"
    )
    op.drop_index(
        "matching_v2_review_submission_bulk_action_idx",
        table_name="matching_v2_review_submission",
    )
    op.drop_constraint(
        "matching_v2_review_submission_bulk_action_fk",
        "matching_v2_review_submission",
        type_="foreignkey",
    )
    op.drop_column("matching_v2_review_submission", "bulk_action_id")
    op.drop_index(
        "matching_v2_bulk_certification_queue_idx",
        table_name="matching_v2_bulk_certification_action",
    )
    op.drop_table("matching_v2_bulk_certification_action")
