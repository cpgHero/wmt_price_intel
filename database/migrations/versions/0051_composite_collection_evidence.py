"""Add immutable recovery plans and composite collection evidence lineage.

Revision ID: 0051_composite_evidence
Revises: 0050_location_reconcile
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051_composite_evidence"
down_revision: str | None = "0050_location_reconcile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_spend_authorization",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column("phase_key", sa.Text(), nullable=False),
        sa.Column("inventory_checksum", sa.String(length=64), nullable=False),
        sa.Column("authorized_run_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approved_credit_ceiling", sa.Integer(), nullable=False),
        sa.Column("unit_cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("authorized_by", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "approved_credit_ceiling > 0",
            name="collection_spend_authorization_ceiling_ck",
        ),
        sa.CheckConstraint(
            "unit_cost_usd = 0.002000",
            name="collection_spend_authorization_rate_ck",
        ),
        sa.CheckConstraint(
            "currency = 'USD'",
            name="collection_spend_authorization_currency_ck",
        ),
        sa.CheckConstraint(
            "status IN ('active','consumed','cancelled')",
            name="collection_spend_authorization_status_ck",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "phase_key",
            name="collection_spend_authorization_org_phase_uq",
        ),
    )
    op.create_table(
        "collection_recovery_batch",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column(
            "spend_authorization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_spend_authorization.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("phase_key", sa.Text(), nullable=False),
        sa.Column("inventory_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "authorized_run_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("approved_credit_ceiling", sa.Integer(), nullable=False),
        sa.Column("reserved_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "unit_cost_usd",
            sa.Numeric(precision=12, scale=6),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "approved_credit_ceiling > 0",
            name="collection_recovery_batch_ceiling_ck",
        ),
        sa.CheckConstraint(
            "unit_cost_usd = 0.002000",
            name="collection_recovery_batch_unit_cost_ck",
        ),
        sa.CheckConstraint(
            "currency = 'USD'",
            name="collection_recovery_batch_currency_ck",
        ),
        sa.CheckConstraint(
            "reserved_credits >= 0 AND reserved_credits <= approved_credit_ceiling",
            name="collection_recovery_batch_reserved_ck",
        ),
        sa.CheckConstraint(
            "status IN ('open','closed','cancelled')",
            name="collection_recovery_batch_status_ck",
        ),
    )
    op.create_index(
        "collection_recovery_batch_org_idx",
        "collection_recovery_batch",
        ["organization_id", "created_at"],
    )
    op.create_unique_constraint(
        "collection_recovery_batch_org_phase_uq",
        "collection_recovery_batch",
        ["organization_id", "phase_key"],
    )
    op.create_table(
        "collection_recovery_batch_run",
        sa.Column(
            "recovery_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_recovery_batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id"),
            nullable=False,
        ),
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "recovery_batch_id",
            "collection_run_id",
            name="collection_recovery_batch_run_pk",
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            name="collection_recovery_batch_run_collection_uq",
        ),
    )
    op.create_table(
        "collection_recovery_plan",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column(
            "base_collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id"),
            nullable=False,
        ),
        sa.Column(
            "recovery_collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id"),
            nullable=True,
        ),
        sa.Column(
            "recovery_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_recovery_batch.id"),
            nullable=True,
        ),
        sa.Column("plan_mode", sa.Text(), nullable=False, server_default="exact_launch"),
        sa.Column("reservation_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("selection_policy_version", sa.Text(), nullable=False),
        sa.Column("selection_checksum", sa.Text(), nullable=False),
        sa.Column("base_snapshot_checksum", sa.Text(), nullable=False),
        sa.Column(
            "selection_scope",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("plan_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_recovery_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_recovery_plan.id"),
            nullable=True,
        ),
        sa.Column("selected_task_count", sa.Integer(), nullable=False),
        sa.Column("maximum_credits", sa.Integer(), nullable=False),
        sa.Column("approved_credit_ceiling", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="approved"),
        sa.Column(
            "binding_manifest",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('approved','bound','ready','blocked','cancelled','superseded')",
            name="collection_recovery_plan_status_ck",
        ),
        sa.CheckConstraint(
            "selected_task_count > 0",
            name="collection_recovery_plan_task_count_ck",
        ),
        sa.CheckConstraint(
            "maximum_credits >= 0",
            name="collection_recovery_plan_maximum_credits_ck",
        ),
        sa.CheckConstraint(
            "approved_credit_ceiling >= maximum_credits",
            name="collection_recovery_plan_credit_ceiling_ck",
        ),
        sa.CheckConstraint(
            "plan_generation >= 1",
            name="collection_recovery_plan_generation_ck",
        ),
        sa.CheckConstraint(
            "plan_mode IN ('exact_launch','legacy_adoption')",
            name="collection_recovery_plan_mode_ck",
        ),
        sa.CheckConstraint(
            "(plan_mode = 'exact_launch' AND recovery_batch_id IS NOT NULL "
            "AND (reservation_active OR status IN ('superseded','cancelled'))) OR "
            "(plan_mode = 'legacy_adoption' AND recovery_batch_id IS NOT NULL "
            "AND NOT reservation_active)",
            name="collection_recovery_plan_batch_ck",
        ),
        sa.CheckConstraint(
            "recovery_collection_run_id IS NULL OR "
            "recovery_collection_run_id <> base_collection_run_id",
            name="collection_recovery_plan_distinct_runs_ck",
        ),
        sa.UniqueConstraint(
            "base_collection_run_id",
            "selection_checksum",
            "plan_generation",
            name="collection_recovery_plan_selection_uq",
        ),
        sa.UniqueConstraint(
            "recovery_collection_run_id",
            name="collection_recovery_plan_recovery_run_uq",
        ),
    )
    op.create_index(
        "collection_recovery_plan_base_idx",
        "collection_recovery_plan",
        ["base_collection_run_id", "created_at"],
    )
    op.create_table(
        "collection_retailer_unavailability_approval",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        sa.Column(
            "base_collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("base_snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("revoked_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active','revoked')",
            name="collection_retailer_unavailability_status_ck",
        ),
    )
    op.create_index(
        "collection_retailer_unavailability_active_idx",
        "collection_retailer_unavailability_approval",
        ["base_collection_run_id", "retailer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "collection_recovery_selection",
        sa.Column(
            "recovery_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_recovery_plan.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_task.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("canonical_request_key", sa.Text(), nullable=False),
        sa.Column("selection_reason", sa.Text(), nullable=False),
        sa.Column("source_snapshot", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint(
            "recovery_plan_id",
            "source_task_id",
            name="collection_recovery_selection_pk",
        ),
        sa.UniqueConstraint(
            "recovery_plan_id",
            "ordinal",
            name="collection_recovery_selection_ordinal_uq",
        ),
        sa.UniqueConstraint(
            "recovery_plan_id",
            "canonical_request_key",
            name="collection_recovery_selection_request_uq",
        ),
        sa.CheckConstraint("ordinal >= 0", name="collection_recovery_selection_ordinal_ck"),
        sa.CheckConstraint(
            "selection_reason IN "
            "('failed_gate_scope','cancelled_gate_scope','blocking_failure','transient_gap')",
            name="collection_recovery_selection_reason_ck",
        ),
    )

    op.drop_constraint(
        "analysis_input_set_collection_run_id_key",
        "analysis_input_set",
        type_="unique",
    )
    op.drop_constraint(
        "analysis_input_set_source_kind_ck",
        "analysis_input_set",
        type_="check",
    )
    op.add_column(
        "analysis_input_set",
        sa.Column("assembly_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "analysis_input_set",
        sa.Column("assembly_policy_version", sa.Text(), nullable=True),
    )
    op.add_column(
        "analysis_input_set",
        sa.Column("trust_state", sa.Text(), nullable=False, server_default="single_run"),
    )
    op.create_check_constraint(
        "analysis_input_set_source_kind_ck",
        "analysis_input_set",
        "source_kind IN ('live_collection','live_collection_composite','historical_import')",
    )
    op.create_check_constraint(
        "analysis_input_set_assembly_generation_ck",
        "analysis_input_set",
        "assembly_generation >= 1",
    )
    op.create_check_constraint(
        "analysis_input_set_trust_state_ck",
        "analysis_input_set",
        "trust_state IN ('single_run','ready','ready_with_warnings','blocked')",
    )
    op.create_unique_constraint(
        "analysis_input_set_collection_generation_uq",
        "analysis_input_set",
        ["collection_run_id", "assembly_generation"],
    )

    op.create_table(
        "analysis_input_component",
        sa.Column(
            "input_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_input_set.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_run.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("component_role", sa.Text(), nullable=False),
        sa.Column(
            "recovery_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_recovery_plan.id"),
            nullable=True,
        ),
        sa.Column("component_checksum", sa.Text(), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint(
            "input_set_id", "collection_run_id", name="analysis_input_component_pk"
        ),
        sa.UniqueConstraint("input_set_id", "ordinal", name="analysis_input_component_ordinal_uq"),
        sa.CheckConstraint("ordinal >= 0", name="analysis_input_component_ordinal_ck"),
        sa.CheckConstraint(
            "component_role IN ('base','recovery')",
            name="analysis_input_component_role_ck",
        ),
        sa.CheckConstraint(
            "(component_role = 'base' AND recovery_plan_id IS NULL) OR "
            "(component_role = 'recovery' AND recovery_plan_id IS NOT NULL)",
            name="analysis_input_component_plan_ck",
        ),
        sa.UniqueConstraint(
            "input_set_id",
            "recovery_plan_id",
            name="analysis_input_component_plan_uq",
        ),
    )
    op.create_index(
        "analysis_input_component_one_base_idx",
        "analysis_input_component",
        ["input_set_id"],
        unique=True,
        postgresql_where=sa.text("component_role = 'base'"),
    )
    op.create_table(
        "analysis_input_task_lineage",
        sa.Column(
            "input_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_input_set.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical_request_key", sa.Text(), nullable=False),
        sa.Column(
            "selected_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_task.id"),
            nullable=False,
        ),
        sa.Column("retailer_id", sa.Text(), sa.ForeignKey("retailer.id"), nullable=False),
        sa.Column("location_scope_key", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("evidence_outcome", sa.Text(), nullable=False),
        sa.Column(
            "superseded_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_task.id"),
            nullable=True,
        ),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint(
            "input_set_id",
            "canonical_request_key",
            name="analysis_input_task_lineage_pk",
        ),
        sa.UniqueConstraint(
            "input_set_id",
            "selected_task_id",
            name="analysis_input_task_lineage_selected_task_uq",
        ),
        sa.CheckConstraint(
            "page_number >= 1",
            name="analysis_input_task_lineage_page_ck",
        ),
        sa.CheckConstraint(
            "evidence_outcome IN ("
            "'usable_success','retained_billable_404','zero_credit_missing',"
            "'contract_missing','quarantined')",
            name="analysis_input_task_lineage_outcome_ck",
        ),
    )
    op.create_index(
        "analysis_input_task_lineage_retailer_idx",
        "analysis_input_task_lineage",
        ["input_set_id", "retailer_id", "evidence_outcome"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    composite_exists = connection.scalar(
        sa.text(
            "SELECT 1 FROM analysis_input_set "
            "WHERE source_kind = 'live_collection_composite' LIMIT 1"
        )
    )
    if composite_exists is not None:
        raise RuntimeError("cannot remove composite evidence while composite input sets exist")
    recovery_exists = connection.scalar(sa.text("SELECT 1 FROM collection_recovery_plan LIMIT 1"))
    if recovery_exists is not None:
        raise RuntimeError("cannot remove composite evidence while recovery plans exist")
    batch_exists = connection.scalar(sa.text("SELECT 1 FROM collection_recovery_batch LIMIT 1"))
    if batch_exists is not None:
        raise RuntimeError("cannot remove composite evidence while recovery batches exist")
    authorization_exists = connection.scalar(
        sa.text("SELECT 1 FROM collection_spend_authorization LIMIT 1")
    )
    if authorization_exists is not None:
        raise RuntimeError("cannot remove composite evidence while spend authorizations exist")
    unavailable_exists = connection.scalar(
        sa.text("SELECT 1 FROM collection_retailer_unavailability_approval LIMIT 1")
    )
    if unavailable_exists is not None:
        raise RuntimeError(
            "cannot remove composite evidence while retailer-unavailability approvals exist"
        )
    duplicate_input = connection.scalar(
        sa.text(
            "SELECT 1 FROM analysis_input_set GROUP BY collection_run_id "
            "HAVING count(*) > 1 LIMIT 1"
        )
    )
    if duplicate_input is not None:
        raise RuntimeError(
            "cannot restore one-input-per-run constraint while duplicate input sets exist"
        )
    op.drop_index(
        "analysis_input_task_lineage_retailer_idx",
        table_name="analysis_input_task_lineage",
    )
    op.drop_table("analysis_input_task_lineage")
    op.drop_index("analysis_input_component_one_base_idx", table_name="analysis_input_component")
    op.drop_table("analysis_input_component")
    op.drop_constraint(
        "analysis_input_set_collection_generation_uq",
        "analysis_input_set",
        type_="unique",
    )
    op.drop_constraint("analysis_input_set_trust_state_ck", "analysis_input_set", type_="check")
    op.drop_constraint(
        "analysis_input_set_assembly_generation_ck",
        "analysis_input_set",
        type_="check",
    )
    op.drop_constraint("analysis_input_set_source_kind_ck", "analysis_input_set", type_="check")
    op.create_check_constraint(
        "analysis_input_set_source_kind_ck",
        "analysis_input_set",
        "source_kind IN ('live_collection','historical_import')",
    )
    op.drop_column("analysis_input_set", "trust_state")
    op.drop_column("analysis_input_set", "assembly_policy_version")
    op.drop_column("analysis_input_set", "assembly_generation")
    op.create_unique_constraint(
        "analysis_input_set_collection_run_id_key",
        "analysis_input_set",
        ["collection_run_id"],
    )
    op.drop_table("collection_recovery_selection")
    op.drop_index(
        "collection_retailer_unavailability_active_idx",
        table_name="collection_retailer_unavailability_approval",
    )
    op.drop_table("collection_retailer_unavailability_approval")
    op.drop_index("collection_recovery_plan_base_idx", table_name="collection_recovery_plan")
    op.drop_table("collection_recovery_plan")
    op.drop_table("collection_recovery_batch_run")
    op.drop_constraint(
        "collection_recovery_batch_org_phase_uq",
        "collection_recovery_batch",
        type_="unique",
    )
    op.drop_index("collection_recovery_batch_org_idx", table_name="collection_recovery_batch")
    op.drop_table("collection_recovery_batch")
    op.drop_table("collection_spend_authorization")
