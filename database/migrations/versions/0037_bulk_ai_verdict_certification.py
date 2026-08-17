"""Allow bulk certification of comparable and not-comparable AI recommendations.

Revision ID: 0037_bulk_ai_verdict_certification
Revises: 0036_ai_review_recovery
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0037_bulk_ai_verdict_certification"
down_revision: str | None = "0036_ai_review_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "matching_v2_bulk_certification_action"
_CONSTRAINT = "matching_v2_bulk_certification_action_type_ck"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "action_type IN ('approve_ai_matches', 'certify_ai_recommendations')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "action_type = 'approve_ai_matches'",
    )
