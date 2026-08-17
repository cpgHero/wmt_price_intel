"""Allow one remediation retry for request-bound Matching v2 AI evidence.

Revision ID: 0036_ai_review_recovery
Revises: 0035_ai_review_retries
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0036_ai_review_recovery"
down_revision: str | None = "0035_ai_review_retries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "matching_v2_ai_review_task_retry_lineage_ck"


def _lineage_constraint(maximum_sequence: int) -> str:
    return (
        "(retry_of_task_id IS NULL AND retry_sequence = 0 AND retry_reason IS NULL) "
        f"OR (retry_of_task_id IS NOT NULL AND retry_sequence BETWEEN 1 AND "
        f"{maximum_sequence} AND length(btrim(retry_reason)) > 0)"
    )


def upgrade() -> None:
    op.drop_constraint(
        _CONSTRAINT,
        "matching_v2_ai_review_task",
        type_="check",
    )
    op.create_check_constraint(
        _CONSTRAINT,
        "matching_v2_ai_review_task",
        _lineage_constraint(4),
    )


def downgrade() -> None:
    op.drop_constraint(
        _CONSTRAINT,
        "matching_v2_ai_review_task",
        type_="check",
    )
    op.create_check_constraint(
        _CONSTRAINT,
        "matching_v2_ai_review_task",
        _lineage_constraint(3),
    )
