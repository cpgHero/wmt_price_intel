"""Add auditable unresolved-only recovery continuation lineage.

Revision ID: 0052_recovery_continuations
Revises: 0051_composite_evidence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052_recovery_continuations"
down_revision: str | None = "0051_composite_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collection_recovery_plan",
        sa.Column(
            "continuation_of_recovery_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_recovery_plan.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "collection_recovery_plan",
        sa.Column(
            "continuation_depth",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "collection_recovery_plan_continuation_ck",
        "collection_recovery_plan",
        "(continuation_of_recovery_plan_id IS NULL AND continuation_depth = 0) OR "
        "(continuation_of_recovery_plan_id IS NOT NULL AND continuation_depth > 0 "
        "AND continuation_depth <= 32 AND plan_mode = 'exact_launch' "
        "AND recovery_batch_id IS NOT NULL AND supersedes_recovery_plan_id IS NULL)",
    )
    op.create_index(
        "collection_recovery_plan_continuation_idx",
        "collection_recovery_plan",
        ["continuation_of_recovery_plan_id", "continuation_depth"],
    )
    op.create_index(
        "collection_recovery_plan_active_continuation_uq",
        "collection_recovery_plan",
        ["continuation_of_recovery_plan_id"],
        unique=True,
        postgresql_where=sa.text(
            "continuation_of_recovery_plan_id IS NOT NULL "
            "AND status NOT IN ('cancelled','superseded')"
        ),
    )
    op.execute(
        """
        CREATE FUNCTION validate_collection_recovery_continuation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          parent collection_recovery_plan%ROWTYPE;
          recovery_status text;
          terminal_sibling_count integer;
        BEGIN
          IF NEW.continuation_of_recovery_plan_id IS NULL THEN
            RETURN NEW;
          END IF;
          SELECT * INTO parent
          FROM collection_recovery_plan
          WHERE id = NEW.continuation_of_recovery_plan_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'recovery continuation parent does not exist';
          END IF;
          IF parent.recovery_batch_id IS NULL
             OR parent.organization_id <> NEW.organization_id
             OR parent.base_collection_run_id <> NEW.base_collection_run_id
             OR parent.recovery_batch_id IS DISTINCT FROM NEW.recovery_batch_id THEN
            RAISE EXCEPTION 'recovery continuation parent scope differs';
          END IF;
          IF NEW.continuation_depth <> parent.continuation_depth + 1 THEN
            RAISE EXCEPTION 'recovery continuation depth must immediately follow its parent';
          END IF;
          SELECT count(*) INTO terminal_sibling_count
          FROM collection_recovery_plan sibling
          WHERE sibling.continuation_of_recovery_plan_id = NEW.continuation_of_recovery_plan_id
            AND sibling.id <> NEW.id
            AND (
              sibling.recovery_collection_run_id IS NOT NULL
              OR sibling.status IN ('bound','ready','blocked')
            );
          IF terminal_sibling_count > 0 THEN
            RAISE EXCEPTION 'recovery continuation cannot branch after a bound child';
          END IF;
          IF parent.status NOT IN ('bound','ready')
             OR parent.recovery_collection_run_id IS NULL THEN
            RAISE EXCEPTION 'recovery continuation requires a bound or ready parent';
          END IF;
          SELECT status INTO recovery_status
          FROM collection_run
          WHERE id = parent.recovery_collection_run_id;
          IF recovery_status IS NULL OR recovery_status NOT IN (
            'succeeded','completed_with_warnings','failed','cancelled'
          ) THEN
            RAISE EXCEPTION 'recovery continuation requires a terminal parent run';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER collection_recovery_plan_continuation_validate_trg
        BEFORE INSERT OR UPDATE OF
          organization_id, base_collection_run_id, recovery_batch_id,
          continuation_of_recovery_plan_id, continuation_depth,
          recovery_collection_run_id, status
        ON collection_recovery_plan
        FOR EACH ROW
        EXECUTE FUNCTION validate_collection_recovery_continuation()
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    continuation_count = int(
        connection.execute(
            sa.text(
                "SELECT count(*) FROM collection_recovery_plan "
                "WHERE continuation_of_recovery_plan_id IS NOT NULL"
            )
        ).scalar_one()
    )
    if continuation_count:
        raise RuntimeError(
            "cannot downgrade 0052 while governed recovery-continuation lineage exists"
        )
    op.execute(
        "DROP TRIGGER collection_recovery_plan_continuation_validate_trg "
        "ON collection_recovery_plan"
    )
    op.execute("DROP FUNCTION validate_collection_recovery_continuation()")
    op.drop_index(
        "collection_recovery_plan_active_continuation_uq",
        table_name="collection_recovery_plan",
    )
    op.drop_index(
        "collection_recovery_plan_continuation_idx",
        table_name="collection_recovery_plan",
    )
    op.drop_constraint(
        "collection_recovery_plan_continuation_ck",
        "collection_recovery_plan",
        type_="check",
    )
    op.drop_column("collection_recovery_plan", "continuation_depth")
    op.drop_column("collection_recovery_plan", "continuation_of_recovery_plan_id")
