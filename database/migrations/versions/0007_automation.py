"""Add schedules, automation state, alerts, and leased email delivery.

Revision ID: 0007_automation
Revises: 0006_results_delivery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_automation"
down_revision: str | None = "0006_results_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_primary_key() -> sa.Column[object]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "collection_schedule",
        _uuid_primary_key(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column(
            "definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_definition.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("cron_expression", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scheduled_for", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
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
    )
    op.create_index(
        "collection_schedule_due_idx",
        "collection_schedule",
        ["enabled", "next_run_at", "lease_expires_at"],
    )
    op.add_column(
        "collection_run",
        sa.Column("trigger_type", sa.Text(), nullable=False, server_default="manual"),
    )
    op.add_column(
        "collection_run",
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_schedule.id"),
        ),
    )
    op.add_column("collection_run", sa.Column("scheduled_for", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "collection_run_trigger_type_ck",
        "collection_run",
        "trigger_type IN ('manual', 'scheduled')",
    )
    op.create_check_constraint(
        "collection_run_trigger_schedule_ck",
        "collection_run",
        "(trigger_type = 'manual' AND schedule_id IS NULL AND scheduled_for IS NULL) OR "
        "(trigger_type = 'scheduled' AND schedule_id IS NOT NULL AND scheduled_for IS NOT NULL)",
    )
    op.create_unique_constraint(
        "collection_run_schedule_slot_uq",
        "collection_run",
        ["schedule_id", "scheduled_for"],
    )
    op.add_column(
        "collection_schedule",
        sa.Column(
            "last_collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id"),
        ),
    )

    op.create_table(
        "alert_definition",
        _uuid_primary_key(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column("stable_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", "stable_key", name="alert_definition_org_key_uq"),
    )
    op.create_table(
        "alert_definition_version",
        _uuid_primary_key(),
        sa.Column(
            "alert_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("alert_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("alert_definition_id", "version", name="alert_definition_version_uq"),
        sa.UniqueConstraint("alert_definition_id", "checksum", name="alert_definition_checksum_uq"),
    )
    op.create_index(
        "alert_definition_version_latest_idx",
        "alert_definition_version",
        ["alert_definition_id", "version"],
    )

    op.create_table(
        "analysis_automation_state",
        sa.Column(
            "analysis_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="processing"),
        sa.Column("locked_by", sa.Text()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('processing', 'processed', 'failed')",
            name="analysis_automation_state_status_ck",
        ),
    )
    op.create_index(
        "analysis_automation_claim_idx",
        "analysis_automation_state",
        ["status", "lease_expires_at", "created_at"],
    )

    op.create_table(
        "alert_event",
        _uuid_primary_key(),
        sa.Column(
            "alert_definition_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("alert_definition_version.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "baseline_analysis_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id"),
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_value", sa.Numeric()),
        sa.Column("baseline_value", sa.Numeric()),
        sa.Column("change_value", sa.Numeric()),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('triggered', 'suppressed', 'not_triggered')",
            name="alert_event_status_ck",
        ),
        sa.UniqueConstraint(
            "alert_definition_version_id",
            "analysis_result_id",
            name="alert_event_evaluation_uq",
        ),
    )
    op.create_index("alert_event_created_idx", "alert_event", ["status", "created_at"])

    op.create_table(
        "email_delivery",
        _uuid_primary_key(),
        sa.Column("alert_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alert_event.id")),
        sa.Column(
            "analysis_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("delivery_type", sa.Text(), nullable=False),
        sa.Column("recipients", postgresql.JSONB(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text()),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("provider_message_id", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "delivery_type IN ('alert', 'analysis_report')",
            name="email_delivery_type_ck",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')",
            name="email_delivery_status_ck",
        ),
    )
    op.create_index(
        "email_delivery_claim_idx",
        "email_delivery",
        ["status", "available_at", "lease_expires_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("email_delivery_claim_idx", table_name="email_delivery")
    op.drop_table("email_delivery")
    op.drop_index("alert_event_created_idx", table_name="alert_event")
    op.drop_table("alert_event")
    op.drop_index("analysis_automation_claim_idx", table_name="analysis_automation_state")
    op.drop_table("analysis_automation_state")
    op.drop_index("alert_definition_version_latest_idx", table_name="alert_definition_version")
    op.drop_table("alert_definition_version")
    op.drop_table("alert_definition")
    op.drop_column("collection_schedule", "last_collection_run_id")
    op.drop_constraint("collection_run_schedule_slot_uq", "collection_run", type_="unique")
    op.drop_constraint("collection_run_trigger_schedule_ck", "collection_run", type_="check")
    op.drop_constraint("collection_run_trigger_type_ck", "collection_run", type_="check")
    op.drop_column("collection_run", "scheduled_for")
    op.drop_column("collection_run", "schedule_id")
    op.drop_column("collection_run", "trigger_type")
    op.drop_index("collection_schedule_due_idx", table_name="collection_schedule")
    op.drop_table("collection_schedule")
