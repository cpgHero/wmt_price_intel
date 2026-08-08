"""Backfill MetricsCart 404 billing and preserve success-page semantics.

Revision ID: 0008_metricscart_billing
Revises: 0007_automation
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_metricscart_billing"
down_revision: str | None = "0007_automation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _recalculate_run_credits() -> None:
    op.execute(
        """
        UPDATE collection_run AS run
        SET actual_credits = totals.actual_credits
        FROM (
          SELECT collection_run_id, COALESCE(sum(billable_credits), 0)::integer AS actual_credits
          FROM collection_task
          GROUP BY collection_run_id
        ) AS totals
        WHERE totals.collection_run_id = run.id
        """
    )


def upgrade() -> None:
    op.execute(
        """
        UPDATE collection_task
        SET billable_credits = credits_per_success
        WHERE http_status = 404
          AND billable_credits = 0
        """
    )
    _recalculate_run_credits()


def downgrade() -> None:
    op.execute(
        """
        UPDATE collection_task
        SET billable_credits = 0
        WHERE http_status = 404
        """
    )
    _recalculate_run_credits()
