"""Allow explicit immutable rebuild generations for governed analysis replays.

Revision ID: 0041_governed_replay_generation
Revises: 0040_match_v2_replay_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_governed_replay_generation"
down_revision: str | None = "0040_match_v2_replay_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "analysis_run"
_COLLECTION_CONSTRAINT = "analysis_run_collection_pack_match_revision_uq"
_SOURCE_CONSTRAINT = "analysis_run_source_matching_v2_release_uq"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "replay_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(_TABLE, sa.Column("replay_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "analysis_run_replay_generation_ck",
        _TABLE,
        "replay_generation >= 1",
    )
    op.drop_constraint(_SOURCE_CONSTRAINT, _TABLE, type_="unique")
    op.drop_constraint(_COLLECTION_CONSTRAINT, _TABLE, type_="unique")
    op.create_unique_constraint(
        _SOURCE_CONSTRAINT,
        _TABLE,
        [
            "source_analysis_result_id",
            "matching_v2_gold_set_release_id",
            "replay_generation",
        ],
    )
    op.execute(
        f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_COLLECTION_CONSTRAINT} "
        "UNIQUE NULLS NOT DISTINCT (collection_run_id, product_pack_id, "
        "product_pack_version, match_revision_id, brand_revision_id, "
        "matching_v2_gold_set_release_id, replay_generation)"
    )


def downgrade() -> None:
    connection = op.get_bind()
    repeated = connection.scalar(
        sa.text("SELECT 1 FROM analysis_run WHERE replay_generation > 1 LIMIT 1")
    )
    if repeated is not None:
        raise RuntimeError(
            "cannot remove governed replay generations while rebuilt analysis runs exist"
        )
    op.drop_constraint(_COLLECTION_CONSTRAINT, _TABLE, type_="unique")
    op.drop_constraint(_SOURCE_CONSTRAINT, _TABLE, type_="unique")
    op.create_unique_constraint(
        _SOURCE_CONSTRAINT,
        _TABLE,
        ["source_analysis_result_id", "matching_v2_gold_set_release_id"],
    )
    op.execute(
        f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_COLLECTION_CONSTRAINT} "
        "UNIQUE NULLS NOT DISTINCT (collection_run_id, product_pack_id, "
        "product_pack_version, match_revision_id, brand_revision_id, "
        "matching_v2_gold_set_release_id)"
    )
    op.drop_constraint("analysis_run_replay_generation_ck", _TABLE, type_="check")
    op.drop_column(_TABLE, "replay_reason")
    op.drop_column(_TABLE, "replay_generation")
