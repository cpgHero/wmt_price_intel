"""Include immutable Matching v2 releases in governed run identity.

Revision ID: 0040_match_v2_replay_identity
Revises: 0039_match_v2_report_release
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0040_match_v2_replay_identity"
down_revision: str | None = "0039_match_v2_report_release"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "analysis_run_collection_pack_match_revision_uq"
_TABLE = "analysis_run"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="unique")
    op.execute(
        f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_CONSTRAINT} "
        "UNIQUE NULLS NOT DISTINCT (collection_run_id, product_pack_id, "
        "product_pack_version, match_revision_id, brand_revision_id, "
        "matching_v2_gold_set_release_id)"
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="unique")
    op.execute(
        f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_CONSTRAINT} "
        "UNIQUE NULLS NOT DISTINCT (collection_run_id, product_pack_id, "
        "product_pack_version, match_revision_id, brand_revision_id)"
    )
