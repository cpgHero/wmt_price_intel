"""Add immutable, audit-bound collection scope projections.

Revision ID: 0053_scope_projections
Revises: 0052_recovery_continuations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053_scope_projections"
down_revision: str | None = "0052_recovery_continuations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_scope_projection",
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
        sa.Column("projection_kind", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("base_snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "source_audit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("location_eligibility_reconciliation_run.id"),
            nullable=True,
        ),
        sa.Column("source_evidence_checksum", sa.String(length=64), nullable=False),
        sa.Column("raw_task_count", sa.Integer(), nullable=False),
        sa.Column("retained_task_count", sa.Integer(), nullable=False),
        sa.Column("excluded_task_count", sa.Integer(), nullable=False),
        sa.Column("raw_location_count", sa.Integer(), nullable=False),
        sa.Column("retained_location_count", sa.Integer(), nullable=False),
        sa.Column("excluded_location_count", sa.Integer(), nullable=False),
        sa.Column("raw_task_retention_ratio", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("governed_coverage_ratio", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column(
            "minimum_scoreable_coverage",
            sa.Numeric(precision=8, scale=6),
            nullable=False,
            server_default="0.950000",
        ),
        sa.Column("scorecard_disposition", sa.Text(), nullable=False),
        sa.Column("projection_checksum", sa.String(length=64), nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "projection_kind IN ('canonical_alias_collapse','limited_provider_footprint')",
            name="collection_scope_projection_kind_ck",
        ),
        sa.CheckConstraint(
            "raw_task_count > 0 AND retained_task_count > 0 "
            "AND excluded_task_count >= 0 "
            "AND retained_task_count + excluded_task_count = raw_task_count",
            name="collection_scope_projection_counts_ck",
        ),
        sa.CheckConstraint(
            "raw_location_count > 0 AND retained_location_count > 0 "
            "AND excluded_location_count >= 0 "
            "AND retained_location_count + excluded_location_count = raw_location_count",
            name="collection_scope_projection_location_counts_ck",
        ),
        sa.CheckConstraint(
            "raw_task_retention_ratio >= 0 AND raw_task_retention_ratio <= 1 "
            "AND governed_coverage_ratio >= 0 AND governed_coverage_ratio <= 1 "
            "AND minimum_scoreable_coverage > 0 AND minimum_scoreable_coverage <= 1",
            name="collection_scope_projection_coverage_ck",
        ),
        sa.CheckConstraint(
            "scorecard_disposition IN ('scoreable','unavailable')",
            name="collection_scope_projection_disposition_ck",
        ),
        sa.CheckConstraint(
            "(projection_kind = 'canonical_alias_collapse' AND source_audit_id IS NOT NULL) OR "
            "(projection_kind = 'limited_provider_footprint' AND source_audit_id IS NULL)",
            name="collection_scope_projection_audit_ck",
        ),
        sa.CheckConstraint(
            "(projection_kind = 'canonical_alias_collapse' "
            " AND governed_coverage_ratio = 1 AND scorecard_disposition = 'scoreable') OR "
            "(projection_kind = 'limited_provider_footprint' "
            " AND ((governed_coverage_ratio >= minimum_scoreable_coverage "
            "       AND scorecard_disposition = 'scoreable') "
            "      OR (governed_coverage_ratio < minimum_scoreable_coverage "
            "          AND scorecard_disposition = 'unavailable')))",
            name="collection_scope_projection_scoreability_ck",
        ),
        sa.UniqueConstraint(
            "base_collection_run_id",
            "retailer_id",
            "projection_checksum",
            name="collection_scope_projection_checksum_uq",
        ),
    )
    op.create_index(
        "collection_scope_projection_run_retailer_idx",
        "collection_scope_projection",
        ["base_collection_run_id", "retailer_id", "created_at"],
    )
    op.create_table(
        "collection_scope_projection_task",
        sa.Column(
            "scope_projection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_scope_projection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_task.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("canonical_request_key", sa.String(length=64), nullable=False),
        sa.Column("disposition", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "mapped_retained_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_task.id"),
            nullable=True,
        ),
        sa.Column("source_snapshot", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint(
            "scope_projection_id",
            "source_task_id",
            name="collection_scope_projection_task_pk",
        ),
        sa.UniqueConstraint(
            "scope_projection_id",
            "ordinal",
            name="collection_scope_projection_task_ordinal_uq",
        ),
        sa.UniqueConstraint(
            "scope_projection_id",
            "canonical_request_key",
            name="collection_scope_projection_task_request_uq",
        ),
        sa.CheckConstraint("ordinal >= 0", name="collection_scope_projection_task_ordinal_ck"),
        sa.CheckConstraint(
            "disposition IN ('retained','excluded')",
            name="collection_scope_projection_task_disposition_ck",
        ),
        sa.CheckConstraint(
            "(disposition = 'retained' AND mapped_retained_task_id IS NULL) OR "
            "(disposition = 'excluded')",
            name="collection_scope_projection_task_mapping_ck",
        ),
    )
    op.add_column(
        "collection_recovery_plan",
        sa.Column(
            "scope_projection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_scope_projection.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "collection_recovery_plan",
        sa.Column("scope_projection_checksum", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "collection_recovery_plan_scope_projection_ck",
        "collection_recovery_plan",
        "(scope_projection_id IS NULL AND scope_projection_checksum IS NULL) OR "
        "(scope_projection_id IS NOT NULL AND scope_projection_checksum IS NOT NULL)",
    )
    op.create_table(
        "analysis_input_scope_projection",
        sa.Column(
            "input_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_input_set.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scope_projection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collection_scope_projection.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("projection_checksum", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "input_set_id",
            "scope_projection_id",
            name="analysis_input_scope_projection_pk",
        ),
        sa.UniqueConstraint(
            "input_set_id",
            "ordinal",
            name="analysis_input_scope_projection_ordinal_uq",
        ),
        sa.CheckConstraint("ordinal >= 0", name="analysis_input_scope_projection_ordinal_ck"),
    )
    op.execute(
        """
        CREATE FUNCTION validate_collection_scope_projection_header()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          run_organization uuid;
          definition_config jsonb;
          audit_status text;
        BEGIN
          SELECT r.organization_id, v.config
          INTO run_organization, definition_config
          FROM collection_run r
          JOIN collection_definition_version v ON v.id = r.definition_version_id
          WHERE r.id = NEW.base_collection_run_id;
          IF NOT FOUND OR run_organization <> NEW.organization_id THEN
            RAISE EXCEPTION 'scope projection organization differs from its base run';
          END IF;
          IF NEW.retailer_id = COALESCE(definition_config->>'benchmark_retailer', '')
             OR NOT EXISTS (
               SELECT 1
               FROM jsonb_array_elements(
                 COALESCE(definition_config->'retailers', '[]'::jsonb)
               ) AS retailer
               WHERE retailer->>'retailer_id' = NEW.retailer_id
                 AND COALESCE((retailer->>'enabled')::boolean, false)
             ) THEN
            RAISE EXCEPTION 'scope projection must target an enabled non-benchmark retailer';
          END IF;
          IF NEW.projection_kind = 'canonical_alias_collapse' THEN
            SELECT status INTO audit_status
            FROM location_eligibility_reconciliation_run
            WHERE id = NEW.source_audit_id;
            IF NOT FOUND OR audit_status <> 'completed' THEN
              RAISE EXCEPTION 'canonical alias projection requires a completed location audit';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER collection_scope_projection_header_validate_trg
        BEFORE INSERT ON collection_scope_projection
        FOR EACH ROW EXECUTE FUNCTION validate_collection_scope_projection_header()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_collection_scope_projection_task()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          projection_kind_value text;
          projection_base_run uuid;
          projection_retailer text;
          source_run uuid;
          source_retailer text;
          mapped_run uuid;
          mapped_retailer text;
        BEGIN
          SELECT projection_kind, base_collection_run_id, retailer_id
          INTO projection_kind_value, projection_base_run, projection_retailer
          FROM collection_scope_projection
          WHERE id = NEW.scope_projection_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'scope projection header does not exist';
          END IF;
          IF NEW.disposition = 'retained' AND NEW.mapped_retained_task_id IS NOT NULL THEN
            RAISE EXCEPTION 'retained projection tasks cannot map to another task';
          END IF;
          IF NEW.disposition = 'excluded'
             AND projection_kind_value = 'canonical_alias_collapse'
             AND NEW.mapped_retained_task_id IS NULL THEN
            RAISE EXCEPTION 'canonical alias exclusions require a retained canonical mapping';
          END IF;
          IF NEW.disposition = 'excluded'
             AND projection_kind_value = 'limited_provider_footprint'
             AND NEW.mapped_retained_task_id IS NOT NULL THEN
            RAISE EXCEPTION 'provider-footprint exclusions cannot invent a canonical mapping';
          END IF;
          SELECT collection_run_id, retailer_id INTO source_run, source_retailer
          FROM collection_task WHERE id = NEW.source_task_id;
          IF NOT FOUND OR source_run <> projection_base_run
             OR source_retailer <> projection_retailer THEN
            RAISE EXCEPTION 'scope projection source task differs from its header scope';
          END IF;
          IF NEW.mapped_retained_task_id IS NOT NULL THEN
            SELECT collection_run_id, retailer_id INTO mapped_run, mapped_retailer
            FROM collection_task WHERE id = NEW.mapped_retained_task_id;
            IF NOT FOUND OR mapped_run <> projection_base_run
               OR mapped_retailer <> projection_retailer THEN
              RAISE EXCEPTION 'mapped canonical task differs from its projection scope';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER collection_scope_projection_task_validate_trg
        BEFORE INSERT ON collection_scope_projection_task
        FOR EACH ROW EXECUTE FUNCTION validate_collection_scope_projection_task()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_collection_scope_projection_mapping()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF NEW.mapped_retained_task_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM collection_scope_projection_task retained
            WHERE retained.scope_projection_id = NEW.scope_projection_id
              AND retained.source_task_id = NEW.mapped_retained_task_id
              AND retained.disposition = 'retained'
          ) THEN
            RAISE EXCEPTION 'mapped canonical task is not retained by the same projection';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER collection_scope_projection_mapping_validate_trg
        AFTER INSERT OR UPDATE ON collection_scope_projection_task
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION validate_collection_scope_projection_mapping()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_collection_scope_projection_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'collection scope projections and their task inventories are immutable';
        END;
        $$
        """
    )
    for table in ("collection_scope_projection", "collection_scope_projection_task"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_immutable_trg
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION prevent_collection_scope_projection_mutation()
            """
        )
    op.execute(
        """
        CREATE FUNCTION validate_analysis_input_scope_projection()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          projection collection_scope_projection%ROWTYPE;
          input_run uuid;
          input_org uuid;
        BEGIN
          SELECT * INTO projection FROM collection_scope_projection
          WHERE id = NEW.scope_projection_id;
          SELECT collection_run_id, organization_id INTO input_run, input_org
          FROM analysis_input_set WHERE id = NEW.input_set_id;
          IF NOT FOUND OR projection.id IS NULL
             OR projection.base_collection_run_id <> input_run
             OR projection.organization_id <> input_org
             OR projection.projection_checksum <> NEW.projection_checksum THEN
            RAISE EXCEPTION 'analysis input scope-projection binding is inconsistent';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER analysis_input_scope_projection_validate_trg
        BEFORE INSERT OR UPDATE ON analysis_input_scope_projection
        FOR EACH ROW EXECUTE FUNCTION validate_analysis_input_scope_projection()
        """
    )
    op.execute(
        """
        CREATE TRIGGER analysis_input_scope_projection_immutable_trg
        BEFORE UPDATE OR DELETE ON analysis_input_scope_projection
        FOR EACH ROW EXECUTE FUNCTION prevent_collection_scope_projection_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_completed_location_eligibility_audit()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.status = 'completed' THEN
            RAISE EXCEPTION 'completed location eligibility reconciliation audits are immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER location_eligibility_reconciliation_completed_immutable_trg
        BEFORE UPDATE OR DELETE ON location_eligibility_reconciliation_run
        FOR EACH ROW EXECUTE FUNCTION protect_completed_location_eligibility_audit()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_recovery_plan_scope_projection()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          projection collection_scope_projection%ROWTYPE;
        BEGIN
          IF NEW.scope_projection_id IS NULL THEN
            RETURN NEW;
          END IF;
          SELECT * INTO projection
          FROM collection_scope_projection
          WHERE id = NEW.scope_projection_id;
          IF NOT FOUND
             OR projection.organization_id <> NEW.organization_id
             OR projection.base_collection_run_id <> NEW.base_collection_run_id
             OR projection.base_snapshot_checksum <> NEW.base_snapshot_checksum
             OR projection.projection_checksum <> NEW.scope_projection_checksum THEN
            RAISE EXCEPTION 'recovery plan scope projection binding is inconsistent';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER collection_recovery_plan_scope_projection_validate_trg
        BEFORE INSERT OR UPDATE OF
          organization_id, base_collection_run_id, base_snapshot_checksum,
          scope_projection_id, scope_projection_checksum
        ON collection_recovery_plan
        FOR EACH ROW EXECUTE FUNCTION validate_recovery_plan_scope_projection()
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    if int(connection.scalar(sa.text("SELECT count(*) FROM collection_scope_projection")) or 0):
        raise RuntimeError(
            "cannot downgrade 0053 while immutable collection scope projections exist"
        )
    op.execute(
        "DROP TRIGGER collection_recovery_plan_scope_projection_validate_trg "
        "ON collection_recovery_plan"
    )
    op.execute("DROP FUNCTION validate_recovery_plan_scope_projection()")
    op.execute(
        "DROP TRIGGER location_eligibility_reconciliation_completed_immutable_trg "
        "ON location_eligibility_reconciliation_run"
    )
    op.execute("DROP FUNCTION protect_completed_location_eligibility_audit()")
    op.execute(
        "DROP TRIGGER analysis_input_scope_projection_immutable_trg "
        "ON analysis_input_scope_projection"
    )
    op.execute(
        "DROP TRIGGER analysis_input_scope_projection_validate_trg "
        "ON analysis_input_scope_projection"
    )
    op.execute("DROP FUNCTION validate_analysis_input_scope_projection()")
    op.execute(
        "DROP TRIGGER collection_scope_projection_task_validate_trg "
        "ON collection_scope_projection_task"
    )
    op.execute("DROP FUNCTION validate_collection_scope_projection_task()")
    op.execute(
        "DROP TRIGGER collection_scope_projection_header_validate_trg "
        "ON collection_scope_projection"
    )
    op.execute("DROP FUNCTION validate_collection_scope_projection_header()")
    op.execute(
        "DROP TRIGGER collection_scope_projection_mapping_validate_trg "
        "ON collection_scope_projection_task"
    )
    op.execute("DROP FUNCTION validate_collection_scope_projection_mapping()")
    for table in ("collection_scope_projection_task", "collection_scope_projection"):
        op.execute(f"DROP TRIGGER {table}_immutable_trg ON {table}")
    op.execute("DROP FUNCTION prevent_collection_scope_projection_mutation()")
    op.drop_table("analysis_input_scope_projection")
    op.drop_constraint(
        "collection_recovery_plan_scope_projection_ck",
        "collection_recovery_plan",
        type_="check",
    )
    op.drop_column("collection_recovery_plan", "scope_projection_checksum")
    op.drop_column("collection_recovery_plan", "scope_projection_id")
    op.drop_table("collection_scope_projection_task")
    op.drop_index(
        "collection_scope_projection_run_retailer_idx",
        table_name="collection_scope_projection",
    )
    op.drop_table("collection_scope_projection")
