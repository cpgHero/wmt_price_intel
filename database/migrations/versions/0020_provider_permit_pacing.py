"""Add rolling-window-safe provider permit pacing.

Revision ID: 0020_provider_permit_pacing
Revises: 0019_match_application_policy
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0020_provider_permit_pacing"
down_revision: str | None = "0019_match_application_policy"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "provider_rate_limit_state",
        sa.Column("next_permit_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("provider_rate_limit_state", "next_permit_at")
