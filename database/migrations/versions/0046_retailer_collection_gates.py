"""Add retailer-isolated collection availability gates.

Revision ID: 0046_retailer_gates
Revises: 0045_location_eligibility
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_retailer_gates"
down_revision: str | None = "0045_location_eligibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_retailer_gate",
        sa.Column(
            "collection_run_id",
            sa.UUID(),
            sa.ForeignKey("collection_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("maximum_404_rate", sa.Numeric(6, 5), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "collection_run_id", "retailer_id", name="collection_retailer_gate_pk"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'passed', 'failed')",
            name="collection_retailer_gate_status_ck",
        ),
        sa.CheckConstraint("sample_size > 0", name="collection_retailer_gate_sample_size_ck"),
        sa.CheckConstraint(
            "maximum_404_rate >= 0 AND maximum_404_rate <= 1",
            name="collection_retailer_gate_404_rate_ck",
        ),
    )
    op.create_index(
        "collection_retailer_gate_status_idx",
        "collection_retailer_gate",
        ["collection_run_id", "status"],
    )
    # Preserve and make visible any preflight evidence created before retailer
    # gates became first-class records. Status is reconstructed per retailer,
    # never copied from the old run-wide decision.
    op.execute(
        sa.text(
            """
            INSERT INTO collection_retailer_gate (
              collection_run_id, retailer_id, status, sample_size,
              maximum_404_rate, resolved_at, reason
            )
            SELECT summary.collection_run_id, summary.retailer_id,
                   CASE
                     WHEN summary.open_count > 0 THEN 'pending'
                     WHEN summary.other_failures > 0 THEN 'failed'
                     WHEN summary.not_found::numeric / summary.sample_size
                       > summary.maximum_404_rate THEN 'failed'
                     ELSE 'passed'
                   END,
                   summary.sample_size, summary.maximum_404_rate,
                   CASE WHEN summary.open_count = 0 THEN now() ELSE NULL END,
                   CASE
                     WHEN summary.other_failures > 0
                       THEN summary.other_failures || ' terminal non-404 failure(s)'
                     WHEN summary.not_found::numeric / summary.sample_size
                       > summary.maximum_404_rate
                       THEN '404 rate ' || round(
                         summary.not_found::numeric / summary.sample_size, 3
                       ) || ' exceeded ' || round(summary.maximum_404_rate, 3)
                     ELSE NULL
                   END
            FROM (
              SELECT t.collection_run_id, t.retailer_id,
                     count(*)::integer AS sample_size,
                     count(*) FILTER (
                       WHERE t.status IN ('pending', 'running')
                     )::integer AS open_count,
                     count(*) FILTER (WHERE t.http_status = 404)::integer AS not_found,
                     count(*) FILTER (
                       WHERE t.status = 'failed' AND t.http_status IS DISTINCT FROM 404
                     )::integer AS other_failures,
                     COALESCE(
                       (r.availability_gate_config->>'max_billable_404_rate')::numeric,
                       0.5
                     ) AS maximum_404_rate
              FROM collection_task t
              JOIN collection_run r ON r.id = t.collection_run_id
              WHERE t.is_preflight
              GROUP BY t.collection_run_id, t.retailer_id,
                       r.availability_gate_config
            ) summary
            """
        )
    )
    op.drop_constraint(
        "collection_run_availability_gate_status_ck", "collection_run", type_="check"
    )
    op.create_check_constraint(
        "collection_run_availability_gate_status_ck",
        "collection_run",
        "availability_gate_status IN ('skipped', 'pending', 'passed', 'partial', 'failed')",
    )
    op.execute(
        sa.text(
            """
            UPDATE collection_run r
            SET availability_gate_status = summary.status
            FROM (
              SELECT collection_run_id,
                     CASE
                       WHEN bool_or(status = 'pending') THEN 'pending'
                       WHEN bool_or(status = 'failed') AND bool_or(status = 'passed')
                         THEN 'partial'
                       WHEN bool_or(status = 'failed') THEN 'failed'
                       ELSE 'passed'
                     END AS status
              FROM collection_retailer_gate
              GROUP BY collection_run_id
            ) summary
            WHERE r.id = summary.collection_run_id
            """
        )
    )


def downgrade() -> None:
    op.execute(
        "UPDATE collection_run SET availability_gate_status = 'failed' "
        "WHERE availability_gate_status = 'partial'"
    )
    op.drop_constraint(
        "collection_run_availability_gate_status_ck", "collection_run", type_="check"
    )
    op.create_check_constraint(
        "collection_run_availability_gate_status_ck",
        "collection_run",
        "availability_gate_status IN ('skipped', 'pending', 'passed', 'failed')",
    )
    op.drop_index("collection_retailer_gate_status_idx", table_name="collection_retailer_gate")
    op.drop_table("collection_retailer_gate")
