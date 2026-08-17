"""Allow governed queue-wide Matching v2 AI review batches.

Revision ID: 0038_large_ai_batches
Revises: 0037_bulk_ai_verdicts
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0038_large_ai_batches"
down_revision: str | None = "0037_bulk_ai_verdicts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "matching_v2_ai_review_batch"
_CONSTRAINT = "matching_v2_ai_review_batch_case_count_ck"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "requested_case_count BETWEEN 1 AND 1500",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "requested_case_count BETWEEN 1 AND 25",
    )
