"""Add immutable Matching v2 attribute-evidence reconciliation decisions.

Revision ID: 0047_attribute_reconcile
Revises: 0046_retailer_gates
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_attribute_reconcile"
down_revision: str | None = "0046_retailer_gates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matching_v2_attribute_evidence_decision",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "review_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_review_case.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ai_review_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_ai_review_task.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("proposal_checksum", sa.Text(), nullable=False),
        sa.Column("proposal_document", postgresql.JSONB(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decision_checksum", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "supersedes_decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching_v2_attribute_evidence_decision.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "decision IN ('verified', 'rejected')",
            name="matching_v2_attribute_evidence_decision_value_ck",
        ),
        sa.CheckConstraint(
            "proposal_checksum ~ '^[a-f0-9]{64}$' AND decision_checksum ~ '^[a-f0-9]{64}$'",
            name="matching_v2_attribute_evidence_decision_checksum_ck",
        ),
    )
    op.create_index(
        "matching_v2_attribute_evidence_decision_case_idx",
        "matching_v2_attribute_evidence_decision",
        ["review_case_id", "proposal_checksum", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "matching_v2_attribute_evidence_decision_case_idx",
        table_name="matching_v2_attribute_evidence_decision",
    )
    op.drop_table("matching_v2_attribute_evidence_decision")
