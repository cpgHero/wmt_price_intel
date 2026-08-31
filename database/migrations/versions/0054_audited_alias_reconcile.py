"""Add audited alias reconciliation with explicit denominator gaps.

Revision ID: 0054_audited_alias_reconcile
Revises: 0053_scope_projections
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_audited_alias_reconcile"
down_revision: str | None = "0053_scope_projections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collection_scope_projection",
        sa.Column(
            "denominator_gap_location_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "collection_scope_projection_denominator_gap_ck",
        "collection_scope_projection",
        "denominator_gap_location_count >= 0",
    )
    op.drop_constraint(
        "collection_scope_projection_kind_ck",
        "collection_scope_projection",
        type_="check",
    )
    op.create_check_constraint(
        "collection_scope_projection_kind_ck",
        "collection_scope_projection",
        "projection_kind IN ("
        "'canonical_alias_collapse','limited_provider_footprint',"
        "'audited_alias_reconciliation')",
    )
    op.drop_constraint(
        "collection_scope_projection_audit_ck",
        "collection_scope_projection",
        type_="check",
    )
    op.create_check_constraint(
        "collection_scope_projection_audit_ck",
        "collection_scope_projection",
        "(projection_kind IN ('canonical_alias_collapse','audited_alias_reconciliation') "
        " AND source_audit_id IS NOT NULL) OR "
        "(projection_kind = 'limited_provider_footprint' AND source_audit_id IS NULL)",
    )
    op.drop_constraint(
        "collection_scope_projection_scoreability_ck",
        "collection_scope_projection",
        type_="check",
    )
    op.create_check_constraint(
        "collection_scope_projection_scoreability_ck",
        "collection_scope_projection",
        "(projection_kind = 'canonical_alias_collapse' "
        " AND policy_version = 'collection-scope-projection-v1' "
        " AND denominator_gap_location_count = 0 "
        " AND governed_coverage_ratio = 1 AND scorecard_disposition = 'scoreable') OR "
        "(projection_kind = 'limited_provider_footprint' "
        " AND policy_version = 'collection-scope-projection-v1' "
        " AND denominator_gap_location_count = 0 "
        " AND ((governed_coverage_ratio >= minimum_scoreable_coverage "
        "       AND scorecard_disposition = 'scoreable') "
        "      OR (governed_coverage_ratio < minimum_scoreable_coverage "
        "          AND scorecard_disposition = 'unavailable'))) OR "
        "(projection_kind = 'audited_alias_reconciliation' "
        " AND policy_version = 'audited-alias-reconciliation-v1' "
        " AND minimum_scoreable_coverage = 0.950000 "
        " AND denominator_gap_location_count > 0 "
        " AND governed_coverage_ratio = ROUND("
        "       retained_location_count::numeric / "
        "       (retained_location_count + denominator_gap_location_count), 6) "
        " AND ((governed_coverage_ratio >= minimum_scoreable_coverage "
        "       AND scorecard_disposition = 'scoreable') "
        "      OR (governed_coverage_ratio < minimum_scoreable_coverage "
        "          AND scorecard_disposition = 'unavailable')))",
    )
    op.create_index(
        "collection_scope_projection_task_source_idx",
        "collection_scope_projection_task",
        ["source_task_id", "scope_projection_id"],
    )

    op.execute(
        """
        CREATE FUNCTION scope_projection_canonical_jsonb(value jsonb)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE STRICT
        AS $$
        DECLARE
          result text;
        BEGIN
          IF jsonb_typeof(value) = 'object' THEN
            SELECT '{' || COALESCE(
                     string_agg(
                       to_json(entry.key)::text || ':'
                         || scope_projection_canonical_jsonb(entry.val),
                       ',' ORDER BY entry.key COLLATE "C"
                     ),
                     ''
                   ) || '}'
            INTO result
            FROM jsonb_each(value) AS entry(key, val);
            RETURN result;
          ELSIF jsonb_typeof(value) = 'array' THEN
            SELECT '[' || COALESCE(
                     string_agg(
                       scope_projection_canonical_jsonb(entry.val),
                       ',' ORDER BY entry.ordinal
                     ),
                     ''
                   ) || ']'
            INTO result
            FROM jsonb_array_elements(value) WITH ORDINALITY AS entry(val, ordinal);
            RETURN result;
          END IF;
          RETURN value::text;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION scope_projection_quote_plus(value text)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE STRICT
        AS $$
        DECLARE
          bytes bytea := convert_to(value, 'UTF8');
          result text := '';
          index integer;
          octet integer;
        BEGIN
          IF octet_length(bytes) = 0 THEN RETURN result; END IF;
          FOR index IN 0..octet_length(bytes) - 1 LOOP
            octet := get_byte(bytes, index);
            IF (octet BETWEEN 48 AND 57) OR (octet BETWEEN 65 AND 90)
               OR (octet BETWEEN 97 AND 122) OR octet IN (45, 46, 95, 126) THEN
              result := result || chr(octet);
            ELSIF octet = 32 THEN
              result := result || '+';
            ELSE
              result := result || '%' || upper(lpad(to_hex(octet), 2, '0'));
            END IF;
          END LOOP;
          RETURN result;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION scope_projection_task_request_identity(task_id uuid, contract jsonb)
        RETURNS jsonb
        LANGUAGE plpgsql
        STABLE STRICT
        AS $$
        DECLARE
          task collection_task%ROWTYPE;
          normalized_contract jsonb;
          supported jsonb;
          required_params jsonb;
          default_params jsonb;
          params jsonb;
          overrides jsonb;
          filtered_overrides jsonb;
          keyword text;
          sort_value text;
          template text;
          catalog_checksum text;
          missing_required text[];
        BEGIN
          SELECT * INTO task FROM collection_task WHERE id = task_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'scope projection request task does not exist'; END IF;
          IF jsonb_typeof(contract) <> 'object' THEN
            RAISE EXCEPTION 'scope projection request requires a sealed provider contract';
          END IF;
          IF contract->>'retailer_id' IS DISTINCT FROM task.retailer_id
             OR contract->>'adapter_id' IS DISTINCT FROM task.adapter_id
             OR COALESCE(contract->>'path', '') = '' THEN
            RAISE EXCEPTION 'scope projection frozen provider contract differs from its task';
          END IF;
          SELECT COALESCE(
            jsonb_agg(to_jsonb(value) ORDER BY value COLLATE "C"), '[]'::jsonb
          )
          INTO supported
          FROM jsonb_array_elements_text(
            COALESCE(contract->'supported_params', '[]')
          ) AS supported_param(value);
          SELECT COALESCE(
            jsonb_agg(to_jsonb(value) ORDER BY value COLLATE "C"), '[]'::jsonb
          )
          INTO required_params
          FROM jsonb_array_elements_text(
            COALESCE(contract->'required_params', '[]')
          ) AS required_param(value);
          default_params := COALESCE(contract->'default_request_params', '{}'::jsonb);
          IF jsonb_typeof(default_params) <> 'object' THEN
            RAISE EXCEPTION 'scope projection provider defaults must be an object';
          END IF;
          normalized_contract := jsonb_build_object(
            'retailer_id', task.retailer_id,
            'adapter_id', task.adapter_id,
            'method', upper(COALESCE(contract->>'method', 'GET')),
            'path', contract->>'path',
            'supported_params', supported,
            'required_params', required_params,
            'default_sort', contract->'default_sort',
            'default_request_params', default_params
          );
          catalog_checksum := encode(
            digest(
              convert_to(scope_projection_canonical_jsonb(normalized_contract), 'UTF8'),
              'sha256'
            ),
            'hex'
          );
          params := default_params;
          IF supported ? 'zipcode' THEN
            params := jsonb_set(params, '{zipcode}', to_jsonb(task.zipcode), true);
          END IF;
          IF supported ? 'page' THEN
            params := jsonb_set(params, '{page}', to_jsonb(task.page_number), true);
          END IF;
          keyword := btrim(COALESCE(task.request_payload->>'keyword', ''));
          IF task.retailer_id = 'amazon_us_same_day' THEN
            template := task.request_payload->>'amazon_same_day_url_template';
            IF COALESCE(btrim(template), '') = '' THEN
              RAISE EXCEPTION 'Amazon Same Day request identity requires its URL template';
            END IF;
            params := jsonb_set(
              params,
              '{url}',
              to_jsonb(replace(template, '{{keyword}}', scope_projection_quote_plus(keyword))),
              true
            );
          ELSE
            IF keyword = '' OR task.store_number IS NULL THEN
              RAISE EXCEPTION 'store request identity requires keyword and store number';
            END IF;
            params := jsonb_set(params, '{keyword}', to_jsonb(keyword), true);
            IF supported ? 'store' THEN
              params := jsonb_set(params, '{store}', to_jsonb(task.store_number), true);
            END IF;
          END IF;
          sort_value := COALESCE(
            NULLIF(task.request_payload->>'sort', ''), NULLIF(contract->>'default_sort', '')
          );
          IF sort_value IS NOT NULL AND supported ? 'sort' THEN
            params := jsonb_set(params, '{sort}', to_jsonb(sort_value), true);
          END IF;
          overrides := COALESCE(task.request_payload->'request_overrides', '{}'::jsonb);
          IF jsonb_typeof(overrides) <> 'object' THEN
            RAISE EXCEPTION 'scope projection request overrides must be an object';
          END IF;
          IF overrides ?| ARRAY['x-api-key', 'page', 'zipcode', 'store'] THEN
            RAISE EXCEPTION 'scope projection request overrides contain a protected parameter';
          END IF;
          SELECT COALESCE(jsonb_object_agg(entry.key, entry.value), '{}'::jsonb)
          INTO filtered_overrides
          FROM jsonb_each(overrides) AS entry(key, value)
          WHERE entry.value <> 'null'::jsonb;
          params := params || filtered_overrides;
          SELECT array_agg(required.value ORDER BY required.value COLLATE "C")
          INTO missing_required
          FROM jsonb_array_elements_text(required_params) AS required(value)
          WHERE NOT params ? required.value
             OR CASE jsonb_typeof(params->required.value)
                  WHEN 'null' THEN true
                  WHEN 'boolean' THEN NOT (params->>required.value)::boolean
                  WHEN 'number' THEN (params->>required.value)::numeric = 0
                  WHEN 'string' THEN params->>required.value = ''
                  WHEN 'array' THEN jsonb_array_length(params->required.value) = 0
                  WHEN 'object' THEN params->required.value = '{}'::jsonb
                  ELSE true
                END;
          IF missing_required IS NOT NULL THEN
            RAISE EXCEPTION 'scope projection request is missing required provider parameters';
          END IF;
          RETURN jsonb_build_object(
            'retailer_id', task.retailer_id,
            'adapter_id', task.adapter_id,
            'catalog_contract_checksum', catalog_checksum,
            'method', upper(COALESCE(contract->>'method', 'GET')),
            'path', contract->>'path',
            'params', params
          );
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_collection_scope_projection_header()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          run_organization uuid;
          run_status text;
          definition_config jsonb;
          definition_geography_resolution uuid;
          prelocked_geography_resolution uuid;
          audit_status text;
          audit_retailers text[];
          manifest_source_evidence jsonb;
        BEGIN
          IF NEW.projection_kind = 'audited_alias_reconciliation' THEN
            SELECT v.geography_resolution_id
            INTO prelocked_geography_resolution
            FROM collection_run r
            JOIN collection_definition_version v ON v.id = r.definition_version_id
            WHERE r.id = NEW.base_collection_run_id;
            IF NOT FOUND OR prelocked_geography_resolution IS NULL THEN
              RAISE EXCEPTION
                'audited reconciliation requires a definition-bound frozen geography';
            END IF;
            PERFORM task.id
            FROM collection_task task
            WHERE task.collection_run_id = NEW.base_collection_run_id
              AND task.retailer_id = NEW.retailer_id
            ORDER BY task.id
            FOR SHARE;
            PERFORM geography.id
            FROM collection_geography_location geography
            WHERE geography.resolution_id = prelocked_geography_resolution
              AND EXISTS (
                SELECT 1
                FROM collection_task task
                WHERE task.collection_run_id = NEW.base_collection_run_id
                  AND task.retailer_id = NEW.retailer_id
                  AND task.retailer_id = geography.retailer_id
                  AND task.location_scope_key = geography.scope_key
              )
            ORDER BY geography.id
            FOR SHARE;
            SELECT r.organization_id, r.status, v.config, v.geography_resolution_id
            INTO run_organization, run_status, definition_config,
                 definition_geography_resolution
            FROM collection_run r
            JOIN collection_definition_version v ON v.id = r.definition_version_id
            WHERE r.id = NEW.base_collection_run_id
            FOR UPDATE OF r FOR SHARE OF v;
            IF definition_geography_resolution
                 IS DISTINCT FROM prelocked_geography_resolution THEN
              RAISE EXCEPTION
                'audited reconciliation frozen geography changed during approval';
            END IF;
          ELSE
            SELECT r.organization_id, r.status, v.config, v.geography_resolution_id
            INTO run_organization, run_status, definition_config,
                 definition_geography_resolution
            FROM collection_run r
            JOIN collection_definition_version v ON v.id = r.definition_version_id
            WHERE r.id = NEW.base_collection_run_id;
          END IF;
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
          IF NEW.projection_kind IN (
            'canonical_alias_collapse', 'audited_alias_reconciliation'
          ) THEN
            SELECT status, retailer_ids INTO audit_status, audit_retailers
            FROM location_eligibility_reconciliation_run
            WHERE id = NEW.source_audit_id;
            IF NOT FOUND OR audit_status <> 'completed' THEN
              RAISE EXCEPTION 'audited alias projection requires a completed location audit';
            END IF;
            IF NEW.projection_kind = 'audited_alias_reconciliation'
               AND NOT COALESCE(NEW.retailer_id = ANY(audit_retailers), false) THEN
              RAISE EXCEPTION 'audited reconciliation retailer is absent from its location audit';
            END IF;
          END IF;
          IF NEW.projection_kind = 'audited_alias_reconciliation' THEN
            IF run_status NOT IN (
              'succeeded', 'completed_with_warnings', 'failed', 'cancelled'
            ) THEN
              RAISE EXCEPTION
                'audited reconciliation requires a terminal immutable base run';
            END IF;
            PERFORM 1 FROM collection_geography_resolution
            WHERE id = definition_geography_resolution FOR UPDATE;
            IF NOT FOUND THEN
              RAISE EXCEPTION
                'audited reconciliation requires a definition-bound frozen geography';
            END IF;
            manifest_source_evidence := NEW.manifest->'source_evidence';
            IF NEW.policy_version <> 'audited-alias-reconciliation-v1'
               OR encode(
                    digest(
                      convert_to(scope_projection_canonical_jsonb(NEW.manifest), 'UTF8'),
                      'sha256'
                    ),
                    'hex'
                  ) IS DISTINCT FROM NEW.projection_checksum
               OR jsonb_typeof(manifest_source_evidence) IS DISTINCT FROM 'object'
               OR encode(
                    digest(
                      convert_to(
                        scope_projection_canonical_jsonb(manifest_source_evidence), 'UTF8'
                      ),
                      'sha256'
                    ),
                    'hex'
                  ) IS DISTINCT FROM NEW.source_evidence_checksum
               OR NEW.manifest->>'policy_version' IS DISTINCT FROM NEW.policy_version
               OR NEW.manifest->>'base_collection_run_id'
                    IS DISTINCT FROM NEW.base_collection_run_id::text
               OR NEW.manifest->>'retailer_id' IS DISTINCT FROM NEW.retailer_id
               OR NEW.manifest->>'projection_kind' IS DISTINCT FROM NEW.projection_kind
               OR NEW.manifest->>'base_snapshot_checksum'
                    IS DISTINCT FROM NEW.base_snapshot_checksum
               OR NEW.manifest->>'source_audit_id' IS DISTINCT FROM NEW.source_audit_id::text
               OR NEW.manifest->>'source_evidence_checksum'
                    IS DISTINCT FROM NEW.source_evidence_checksum
               OR (NEW.manifest->>'raw_task_count')::integer
                    IS DISTINCT FROM NEW.raw_task_count
               OR (NEW.manifest->>'retained_task_count')::integer
                    IS DISTINCT FROM NEW.retained_task_count
               OR (NEW.manifest->>'excluded_task_count')::integer
                    IS DISTINCT FROM NEW.excluded_task_count
               OR (NEW.manifest->>'raw_location_count')::integer
                    IS DISTINCT FROM NEW.raw_location_count
               OR (NEW.manifest->>'retained_location_count')::integer
                    IS DISTINCT FROM NEW.retained_location_count
               OR (NEW.manifest->>'excluded_location_count')::integer
                    IS DISTINCT FROM NEW.excluded_location_count
               OR (NEW.manifest->>'denominator_gap_location_count')::integer
                    IS DISTINCT FROM NEW.denominator_gap_location_count
               OR (NEW.manifest->>'raw_task_retention_ratio')::numeric
                    IS DISTINCT FROM NEW.raw_task_retention_ratio
               OR (NEW.manifest->>'governed_coverage_ratio')::numeric
                    IS DISTINCT FROM NEW.governed_coverage_ratio
               OR (NEW.manifest->>'minimum_scoreable_coverage')::numeric
                    IS DISTINCT FROM NEW.minimum_scoreable_coverage
               OR NEW.manifest->>'scorecard_disposition'
                    IS DISTINCT FROM NEW.scorecard_disposition
               OR (NEW.manifest->>'coverage_numerator_location_count')::integer
                    IS DISTINCT FROM NEW.retained_location_count
               OR (NEW.manifest->>'coverage_denominator_location_count')::integer
                    IS DISTINCT FROM (
                      NEW.retained_location_count + NEW.denominator_gap_location_count
                    )
               OR NEW.manifest->>'coverage_semantics' IS DISTINCT FROM
                    'provider_safe_scopes_over_provider_safe_plus_audited_unpaired_gaps'
               OR COALESCE(NEW.manifest->>'inventory_checksum', '') !~ '^[0-9a-f]{64}$'
               OR manifest_source_evidence->>'kind'
                    IS DISTINCT FROM 'audited_alias_reconciliation_evidence'
               OR manifest_source_evidence->'location_audit'->>'audit_id'
                    IS DISTINCT FROM NEW.source_audit_id::text
               OR jsonb_typeof(
                    manifest_source_evidence->'request_identity'->'contracts'
                  ) IS DISTINCT FROM 'object' THEN
              RAISE EXCEPTION 'audited reconciliation manifest is not checksum-bound to its header';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_collection_scope_projection_task()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          projection collection_scope_projection%ROWTYPE;
          source_run uuid;
          source_retailer text;
          source_location uuid;
          source_store text;
          source_location_scope_key text;
          source_eligible boolean;
          source_adapter text;
          source_zipcode text;
          source_page integer;
          source_max_pages integer;
          source_stop_on_empty boolean;
          source_stop_on_short_page boolean;
          source_credits_per_success integer;
          source_priority integer;
          source_max_attempts integer;
          source_is_preflight boolean;
          source_request_payload jsonb;
          source_request_fingerprint text;
          source_status text;
          source_completed_at timestamptz;
          source_attempt_count integer;
          source_billable_credits integer;
          source_http_status integer;
          source_failure_class text;
          source_last_error text;
          source_result_count integer;
          source_raw_artifact_id uuid;
          source_artifact_run uuid;
          source_artifact_checksum text;
          source_artifact_type text;
          source_artifact_metadata jsonb;
          source_artifact_immutable boolean;
          frozen_location uuid;
          frozen_store text;
          frozen_zipcode text;
          frozen_latitude double precision;
          frozen_longitude double precision;
          frozen_city text;
          frozen_state text;
          mapped_run uuid;
          mapped_retailer text;
          actual_identity jsonb;
          expected_request_key text;
          expected_persisted_fingerprint text;
          expected_parameter_names jsonb;
          identity_entry jsonb;
          sealed_contract jsonb;
          provenance_mode text;
          expected_request_identity_provenance jsonb;
        BEGIN
          SELECT * INTO projection
          FROM collection_scope_projection
          WHERE id = NEW.scope_projection_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'scope projection header does not exist';
          END IF;
          IF NEW.ordinal < 0 OR NEW.ordinal >= projection.raw_task_count THEN
            RAISE EXCEPTION 'scope projection task ordinal is outside its sealed inventory';
          END IF;
          IF NEW.disposition = 'retained' AND NEW.mapped_retained_task_id IS NOT NULL THEN
            RAISE EXCEPTION 'retained projection tasks cannot map to another task';
          END IF;
          IF NEW.disposition = 'excluded'
             AND projection.projection_kind = 'canonical_alias_collapse'
             AND NEW.mapped_retained_task_id IS NULL THEN
            RAISE EXCEPTION 'canonical alias exclusions require a retained canonical mapping';
          END IF;
          IF NEW.disposition = 'excluded'
             AND projection.projection_kind = 'limited_provider_footprint'
             AND NEW.mapped_retained_task_id IS NOT NULL THEN
            RAISE EXCEPTION 'provider-footprint exclusions cannot invent a canonical mapping';
          END IF;
          IF projection.projection_kind = 'audited_alias_reconciliation' THEN
            IF NEW.disposition = 'retained' AND (
              NEW.reason <> 'provider_safe_canonical_scope'
              OR NEW.mapped_retained_task_id IS NOT NULL
            ) THEN
              RAISE EXCEPTION
                'audited reconciliation retained scope has an invalid reason or mapping';
            END IF;
            IF NEW.disposition = 'excluded'
               AND NEW.reason = 'audited_alias_of_provider_safe_canonical_scope'
               AND NEW.mapped_retained_task_id IS NULL THEN
              RAISE EXCEPTION 'audited exact alias requires a retained canonical mapping';
            END IF;
            IF NEW.disposition = 'excluded'
               AND NEW.reason = 'audited_provider_unsafe_unpaired_scope_gap'
               AND NEW.mapped_retained_task_id IS NOT NULL THEN
              RAISE EXCEPTION 'audited unpaired scope gap cannot invent a canonical mapping';
            END IF;
            IF NEW.disposition = 'excluded' AND NEW.reason NOT IN (
              'audited_alias_of_provider_safe_canonical_scope',
              'audited_provider_unsafe_unpaired_scope_gap'
            ) THEN
              RAISE EXCEPTION 'audited reconciliation exclusion has an unsupported reason';
            END IF;
          END IF;
          IF projection.projection_kind = 'audited_alias_reconciliation' THEN
            SELECT t.collection_run_id, t.retailer_id, t.retailer_location_id,
                   t.store_number, t.location_scope_key, l.collection_eligible,
                   t.adapter_id, t.zipcode, t.page_number, t.max_pages,
                   t.stop_on_empty, t.stop_on_short_page, t.credits_per_success,
                   t.priority, t.max_attempts, t.is_preflight,
                   t.request_payload, t.request_fingerprint,
                   t.status, t.completed_at, t.attempt_count, t.billable_credits,
                   t.http_status, t.failure_class, t.last_error, t.result_count,
                   t.raw_artifact_id, geography.retailer_location_id,
                   geography.store_number, geography.zipcode, geography.latitude,
                   geography.longitude, geography.city, geography.state
            INTO source_run, source_retailer, source_location, source_store,
                 source_location_scope_key, source_eligible, source_adapter, source_zipcode,
                 source_page, source_max_pages, source_stop_on_empty, source_stop_on_short_page,
                 source_credits_per_success, source_priority, source_max_attempts,
                 source_is_preflight, source_request_payload,
                 source_request_fingerprint, source_status, source_completed_at,
                 source_attempt_count, source_billable_credits, source_http_status,
                 source_failure_class, source_last_error, source_result_count,
                 source_raw_artifact_id, frozen_location, frozen_store, frozen_zipcode,
                 frozen_latitude, frozen_longitude, frozen_city, frozen_state
            FROM collection_task t
            JOIN collection_run run ON run.id = t.collection_run_id
            JOIN collection_definition_version version
              ON version.id = run.definition_version_id
            JOIN collection_geography_location geography
              ON geography.resolution_id = version.geography_resolution_id
             AND geography.retailer_id = t.retailer_id
             AND geography.scope_key = t.location_scope_key
            JOIN retailer_location l ON l.id = t.retailer_location_id
            WHERE t.id = NEW.source_task_id
            FOR SHARE OF t, run, version, geography, l;
            IF source_raw_artifact_id IS NOT NULL THEN
              SELECT artifact.collection_run_id, artifact.checksum, artifact.artifact_type,
                     artifact.metadata, artifact.immutable
              INTO source_artifact_run, source_artifact_checksum, source_artifact_type,
                   source_artifact_metadata, source_artifact_immutable
              FROM dataset_artifact artifact
              WHERE artifact.id = source_raw_artifact_id
              FOR SHARE OF artifact;
              IF NOT FOUND THEN
                RAISE EXCEPTION
                  'audited reconciliation source task references a missing raw artifact';
              END IF;
            END IF;
          ELSE
            SELECT t.collection_run_id, t.retailer_id
            INTO source_run, source_retailer
            FROM collection_task t
            WHERE t.id = NEW.source_task_id;
          END IF;
          IF NOT FOUND OR source_run <> projection.base_collection_run_id
             OR source_retailer <> projection.retailer_id THEN
            RAISE EXCEPTION 'scope projection source task differs from its header scope';
          END IF;
          IF projection.projection_kind = 'audited_alias_reconciliation' THEN
            identity_entry := projection.manifest->'source_evidence'->'request_identity'
              ->'contracts'->source_adapter;
            sealed_contract := identity_entry->'contract';
            IF jsonb_typeof(identity_entry) IS DISTINCT FROM 'object'
               OR identity_entry->>'retailer_id' IS DISTINCT FROM source_retailer
               OR identity_entry->>'adapter_id' IS DISTINCT FROM source_adapter
               OR jsonb_typeof(sealed_contract) IS DISTINCT FROM 'object' THEN
              RAISE EXCEPTION 'audited reconciliation task has no sealed adapter contract';
            END IF;
            expected_persisted_fingerprint := encode(
              digest(
                convert_to(
                  scope_projection_canonical_jsonb(source_request_payload), 'UTF8'
                ),
                'sha256'
              ),
              'hex'
            );
            IF NEW.source_snapshot->'task'->>'task_id'
                 IS DISTINCT FROM NEW.source_task_id::text
               OR NEW.source_snapshot->'task'->>'retailer_id'
                 IS DISTINCT FROM source_retailer
               OR NEW.source_snapshot->'task'->>'adapter_id'
                 IS DISTINCT FROM source_adapter
               OR NEW.source_snapshot->'task'->>'collection_run_id'
                 IS DISTINCT FROM source_run::text
               OR NEW.source_snapshot->'task'->>'location_scope_key'
                 IS DISTINCT FROM source_location_scope_key
               OR NEW.source_snapshot->'task'->>'retailer_location_id'
                 IS DISTINCT FROM source_location::text
               OR NEW.source_snapshot->'task'->>'store_number'
                 IS DISTINCT FROM source_store
               OR NEW.source_snapshot->'task'->>'zipcode'
                 IS DISTINCT FROM source_zipcode
               OR NEW.source_snapshot->'task'->'location_snapshot'
                 IS DISTINCT FROM jsonb_build_object(
                   'latitude', frozen_latitude,
                   'longitude', frozen_longitude,
                   'city', frozen_city,
                   'state', frozen_state
                 )
               OR NEW.source_snapshot->'task'->>'page_number'
                 IS DISTINCT FROM source_page::text
               OR NEW.source_snapshot->'task'->>'max_pages'
                 IS DISTINCT FROM source_max_pages::text
               OR NEW.source_snapshot->'task'->>'stop_on_empty'
                 IS DISTINCT FROM source_stop_on_empty::text
               OR NEW.source_snapshot->'task'->>'stop_on_short_page'
                 IS DISTINCT FROM source_stop_on_short_page::text
               OR NEW.source_snapshot->'task'->>'credits_per_success'
                 IS DISTINCT FROM source_credits_per_success::text
               OR NEW.source_snapshot->'task'->>'priority'
                 IS DISTINCT FROM source_priority::text
               OR NEW.source_snapshot->'task'->>'max_attempts'
                 IS DISTINCT FROM source_max_attempts::text
               OR NEW.source_snapshot->'task'->>'is_preflight'
                 IS DISTINCT FROM source_is_preflight::text
               OR NEW.source_snapshot->'task'->>'attempt_count'
                 IS DISTINCT FROM source_attempt_count::text
               OR NEW.source_snapshot->'task'->>'status'
                 IS DISTINCT FROM source_status
               OR NEW.source_snapshot->'task'->'http_status'
                 IS DISTINCT FROM COALESCE(to_jsonb(source_http_status), 'null'::jsonb)
               OR NEW.source_snapshot->'task'->'failure_class'
                 IS DISTINCT FROM COALESCE(to_jsonb(source_failure_class), 'null'::jsonb)
               OR NEW.source_snapshot->'task'->>'billable_credits'
                 IS DISTINCT FROM source_billable_credits::text
               OR NEW.source_snapshot->'task'->'raw_artifact_id'
                 IS DISTINCT FROM COALESCE(
                   to_jsonb(source_raw_artifact_id::text), 'null'::jsonb
                 )
               OR NEW.source_snapshot->'task'->'result_count'
                 IS DISTINCT FROM COALESCE(to_jsonb(source_result_count), 'null'::jsonb)
               OR NEW.source_snapshot->'current_location_eligible'
                 IS DISTINCT FROM COALESCE(to_jsonb(source_eligible), 'null'::jsonb)
               OR NEW.source_snapshot->'raw_artifact'
                 IS DISTINCT FROM jsonb_build_object(
                   'id', source_raw_artifact_id::text,
                   'checksum', source_artifact_checksum,
                   'provider', source_artifact_metadata->>'provider',
                   'retailer_id', source_artifact_metadata->>'retailer_id',
                   'adapter_id', source_artifact_metadata->>'adapter_id',
                   'http_status', source_artifact_metadata->'http_status',
                   'body_checksum', source_artifact_metadata->>'body_checksum'
                 )
               OR NEW.source_snapshot->'provider_error_evidence'->'mutable_diagnostic'
                 IS DISTINCT FROM jsonb_build_object(
                   'task_http_status', source_http_status,
                   'failure_class', source_failure_class,
                   'last_error_sha256', encode(
                     digest(convert_to(COALESCE(source_last_error, ''), 'UTF8'), 'sha256'),
                     'hex'
                   )
                 )
               OR NEW.source_snapshot->'provider_error_evidence'->'verified'
                 IS DISTINCT FROM 'null'::jsonb
               OR NEW.source_snapshot->'task'->'persisted_request_payload'
                 IS DISTINCT FROM source_request_payload
               OR NEW.source_snapshot->'task'->>'persisted_request_fingerprint'
                 IS DISTINCT FROM source_request_fingerprint
               OR source_request_fingerprint IS DISTINCT FROM expected_persisted_fingerprint THEN
              RAISE EXCEPTION 'audited reconciliation source snapshot differs from its actual task';
            END IF;
            IF source_request_payload ? '_provider_request_contract' THEN
              provenance_mode := 'frozen_task_contract';
              IF jsonb_typeof(source_request_payload->'_provider_request_contract')
                   IS DISTINCT FROM 'object'
                 OR source_request_payload->'_provider_request_contract'
                   IS DISTINCT FROM sealed_contract THEN
                RAISE EXCEPTION 'persisted provider contract differs from the sealed contract';
              END IF;
            ELSE
              provenance_mode := 'reconstructed_current_catalog';
            END IF;
            actual_identity := scope_projection_task_request_identity(
              NEW.source_task_id, sealed_contract
            );
            expected_request_identity_provenance := jsonb_build_object(
              'mode', provenance_mode,
              'sealed_contract_checksum', actual_identity->>'catalog_contract_checksum',
              'verified_fields', CASE
                WHEN provenance_mode = 'frozen_task_contract' THEN
                  jsonb_build_array('frozen_provider_request_contract')
                ELSE jsonb_build_array(
                  'persisted_request_payload',
                  'persisted_request_fingerprint',
                  'same_run_adapter_and_task_inputs'
                )
              END,
              'unverified_fields', CASE
                WHEN provenance_mode = 'frozen_task_contract' THEN '[]'::jsonb
                ELSE jsonb_build_array(
                  'historical_parameter_values',
                  'historical_catalog_defaults'
                )
              END
            );
            expected_request_key := encode(
              digest(
                convert_to(scope_projection_canonical_jsonb(actual_identity), 'UTF8'),
                'sha256'
              ),
              'hex'
            );
            IF NEW.source_snapshot->'task'->'effective_request_identity'
                 IS DISTINCT FROM actual_identity
               OR identity_entry->>'sealed_contract_checksum'
                 IS DISTINCT FROM actual_identity->>'catalog_contract_checksum'
               OR NEW.source_snapshot->'task'->'request_payload'
                 IS DISTINCT FROM (
                   source_request_payload || jsonb_build_object(
                     '_provider_request_contract', sealed_contract
                   )
                 )
               OR NEW.source_snapshot->'task'->>'request_fingerprint'
                 IS DISTINCT FROM encode(
                   digest(
                     convert_to(
                       scope_projection_canonical_jsonb(
                         source_request_payload || jsonb_build_object(
                           '_provider_request_contract', sealed_contract
                         )
                       ),
                       'UTF8'
                     ),
                     'sha256'
                   ),
                   'hex'
                 )
               OR NEW.source_snapshot->'task'->'request_identity_provenance'
                 IS DISTINCT FROM expected_request_identity_provenance
               OR NEW.source_snapshot->>'canonical_request_key'
                 IS DISTINCT FROM expected_request_key
               OR NEW.canonical_request_key IS DISTINCT FROM expected_request_key THEN
              RAISE EXCEPTION
                'audited reconciliation request identity differs from its actual task';
            END IF;
            IF provenance_mode = 'reconstructed_current_catalog' THEN
              IF source_raw_artifact_id IS NULL THEN
                IF source_status <> 'cancelled'
                   OR source_attempt_count <> 0
                   OR source_billable_credits <> 0
                   OR source_http_status IS NOT NULL THEN
                  RAISE EXCEPTION 'uncalled legacy reconstruction is not a zero-use cancellation';
                END IF;
              ELSE
                SELECT COALESCE(
                  jsonb_agg(
                    to_jsonb(parameter_name) ORDER BY parameter_name COLLATE "C"
                  ),
                  '[]'
                )
                INTO expected_parameter_names
                FROM jsonb_object_keys(actual_identity->'params') AS names(parameter_name);
                IF source_artifact_run IS DISTINCT FROM source_run
                   OR NOT COALESCE(source_artifact_immutable, false)
                   OR source_attempt_count < 1
                   OR source_status NOT IN ('succeeded', 'failed')
                   OR source_completed_at IS NULL
                   OR source_http_status IS NULL
                   OR source_http_status < 100
                   OR source_http_status > 599
                   OR source_artifact_type IS DISTINCT FROM 'raw_provider_response'
                   OR COALESCE(source_artifact_checksum, '') !~ '^[0-9a-f]{64}$'
                   OR COALESCE(source_artifact_metadata->>'body_checksum', '')
                        !~ '^[0-9a-f]{64}$'
                   OR source_artifact_metadata->>'provider' IS DISTINCT FROM 'metricscart'
                   OR source_artifact_metadata->>'retailer_id'
                        IS DISTINCT FROM source_retailer
                   OR source_artifact_metadata->>'adapter_id'
                        IS DISTINCT FROM source_adapter
                   OR source_artifact_metadata->>'task_id'
                        IS DISTINCT FROM NEW.source_task_id::text
                   OR upper(source_artifact_metadata->>'request_method')
                        IS DISTINCT FROM actual_identity->>'method'
                   OR source_artifact_metadata->>'request_path'
                        IS DISTINCT FROM actual_identity->>'path'
                   OR source_artifact_metadata->'request_parameter_names'
                        IS DISTINCT FROM expected_parameter_names
                   OR COALESCE(source_artifact_metadata->>'http_status', '')
                        !~ '^[1-5][0-9]{2}$'
                   OR (source_artifact_metadata->>'http_status')::integer
                        IS DISTINCT FROM source_http_status THEN
                  RAISE EXCEPTION 'called legacy task conflicts with immutable artifact evidence';
                END IF;
              END IF;
            END IF;
            IF source_location IS NULL THEN
              RAISE EXCEPTION 'audited reconciliation requires a durable physical location';
            END IF;
            IF frozen_location IS NULL
               OR source_location IS DISTINCT FROM frozen_location
               OR source_store IS DISTINCT FROM frozen_store
               OR source_zipcode IS DISTINCT FROM frozen_zipcode THEN
              RAISE EXCEPTION 'audited reconciliation task differs from frozen geography';
            END IF;
            IF NEW.disposition = 'retained' AND (
              NOT COALESCE(source_eligible, false) OR source_store !~ '^[0-9]{8}$'
            ) THEN
              RAISE EXCEPTION 'audited reconciliation retained a provider-unsafe scope';
            END IF;
            IF NEW.disposition = 'excluded' AND (
              COALESCE(source_eligible, true) OR source_store !~ '^[0-9]{7}$'
            ) THEN
              RAISE EXCEPTION 'audited reconciliation excluded a scope not proven provider-unsafe';
            END IF;
          END IF;
          IF NEW.mapped_retained_task_id IS NOT NULL THEN
            IF projection.projection_kind = 'audited_alias_reconciliation' THEN
              SELECT collection_run_id, retailer_id INTO mapped_run, mapped_retailer
              FROM collection_task WHERE id = NEW.mapped_retained_task_id
              FOR SHARE;
            ELSE
              SELECT collection_run_id, retailer_id INTO mapped_run, mapped_retailer
              FROM collection_task WHERE id = NEW.mapped_retained_task_id;
            END IF;
            IF NOT FOUND OR mapped_run <> projection.base_collection_run_id
               OR mapped_retailer <> projection.retailer_id THEN
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
        CREATE OR REPLACE FUNCTION validate_collection_scope_projection_mapping()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          projection_kind_value text;
          exact_alias boolean;
        BEGIN
          IF NEW.mapped_retained_task_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM collection_scope_projection_task retained
            WHERE retained.scope_projection_id = NEW.scope_projection_id
              AND retained.source_task_id = NEW.mapped_retained_task_id
              AND retained.disposition = 'retained'
          ) THEN
            RAISE EXCEPTION 'mapped canonical task is not retained by the same projection';
          END IF;
          IF NEW.mapped_retained_task_id IS NOT NULL THEN
            SELECT projection_kind INTO projection_kind_value
            FROM collection_scope_projection WHERE id = NEW.scope_projection_id;
            IF projection_kind_value = 'audited_alias_reconciliation' THEN
              SELECT source.adapter_id = retained.adapter_id
                     AND source.zipcode = retained.zipcode
                     AND source.page_number = retained.page_number
                     AND retained.store_number = lpad(source.store_number, 8, '0')
                     AND length(source.store_number) = 7
                     AND length(retained.store_number) = 8
                     AND (
                       source.request_payload
                         - '_provider_request_contract' - 'store_number'
                     ) = (
                       retained.request_payload
                         - '_provider_request_contract' - 'store_number'
                     )
              INTO exact_alias
              FROM collection_task source
              JOIN collection_task retained ON retained.id = NEW.mapped_retained_task_id
              WHERE source.id = NEW.source_task_id;
            ELSE
              exact_alias := true;
            END IF;
            IF NOT COALESCE(exact_alias, false) THEN
              RAISE EXCEPTION 'mapped canonical task is not an exact provider-request alias';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_collection_scope_projection_complete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          inventory_count integer;
          retained_count integer;
          excluded_count integer;
          raw_locations integer;
          retained_locations integer;
          excluded_locations integer;
          gap_locations integer;
          invalid_reason_count integer;
          conflicting_location_count integer;
          source_multi_target_count integer;
          target_multi_source_count integer;
          paired_gap_count integer;
          actual_scope_task_count integer;
          audit_mismatch_count integer;
          identity_inventory_mismatch_count integer;
          expected_audit_evidence jsonb;
          actual_inventory_checksum text;
        BEGIN
          SELECT count(*)::integer,
                 count(*) FILTER (WHERE disposition = 'retained')::integer,
                 count(*) FILTER (WHERE disposition = 'excluded')::integer,
                 count(DISTINCT task.retailer_location_id)::integer,
                 count(DISTINCT task.retailer_location_id)
                   FILTER (WHERE item.disposition = 'retained')::integer,
                 count(DISTINCT task.retailer_location_id)
                   FILTER (WHERE item.disposition = 'excluded')::integer,
                 count(DISTINCT task.retailer_location_id)
                   FILTER (
                     WHERE item.reason = 'audited_provider_unsafe_unpaired_scope_gap'
                   )::integer,
                 count(*) FILTER (
                   WHERE item.disposition = 'retained'
                         AND (item.reason <> 'provider_safe_canonical_scope'
                              OR item.mapped_retained_task_id IS NOT NULL)
                      OR item.disposition = 'excluded'
                         AND item.reason = 'audited_alias_of_provider_safe_canonical_scope'
                         AND item.mapped_retained_task_id IS NULL
                      OR item.disposition = 'excluded'
                         AND item.reason = 'audited_provider_unsafe_unpaired_scope_gap'
                         AND item.mapped_retained_task_id IS NOT NULL
                      OR item.disposition = 'excluded'
                         AND item.reason NOT IN (
                           'audited_alias_of_provider_safe_canonical_scope',
                           'audited_provider_unsafe_unpaired_scope_gap'
                         )
                 )::integer,
                 encode(
                   digest(
                     convert_to(
                       '{"items":[' || COALESCE(
                         string_agg(
                           scope_projection_canonical_jsonb(
                             jsonb_build_object(
                               'source_task_id', item.source_task_id::text,
                               'canonical_request_key', item.canonical_request_key,
                               'disposition', item.disposition,
                               'reason', item.reason,
                               'mapped_retained_task_id',
                                 item.mapped_retained_task_id::text,
                               'source_snapshot', item.source_snapshot
                             )
                           ),
                           ',' ORDER BY item.ordinal
                         ),
                         ''
                       ) || ']}',
                       'UTF8'
                     ),
                     'sha256'
                   ),
                   'hex'
                 )
          INTO inventory_count, retained_count, excluded_count, raw_locations,
               retained_locations, excluded_locations, gap_locations, invalid_reason_count,
               actual_inventory_checksum
          FROM collection_scope_projection_task item
          JOIN collection_task task ON task.id = item.source_task_id
          WHERE item.scope_projection_id = NEW.id;

          SELECT count(*)::integer INTO actual_scope_task_count
          FROM collection_task task
          WHERE task.collection_run_id = NEW.base_collection_run_id
            AND task.retailer_id = NEW.retailer_id;

          IF inventory_count <> NEW.raw_task_count
             OR inventory_count <> actual_scope_task_count
             OR retained_count <> NEW.retained_task_count
             OR excluded_count <> NEW.excluded_task_count
             OR raw_locations <> NEW.raw_location_count
             OR retained_locations <> NEW.retained_location_count
             OR excluded_locations <> NEW.excluded_location_count THEN
            RAISE EXCEPTION 'scope projection sealed inventory counts do not reconcile';
          END IF;
          IF NEW.projection_kind = 'audited_alias_reconciliation' THEN
            SELECT jsonb_build_object(
              'kind', 'location_eligibility_reconciliation',
              'audit_id', audit.id::text,
              'catalog_sha256', audit.catalog_sha256,
              'snapshot_sha256', audit.snapshot_sha256,
              'reviewed_plan_sha256', audit.reviewed_plan_sha256,
              'retailer_ids', (
                SELECT COALESCE(
                  jsonb_agg(to_jsonb(retailer_id) ORDER BY retailer_id COLLATE "C"),
                  '[]'
                )
                FROM unnest(audit.retailer_ids) AS retailer(retailer_id)
              ),
              'status', audit.status,
              'scanned_rows', audit.scanned_rows,
              'changed_rows', audit.changed_rows,
              'eligible_before', audit.eligible_before,
              'eligible_after', audit.eligible_after,
              'changes', audit.changes
            )
            INTO expected_audit_evidence
            FROM location_eligibility_reconciliation_run audit
            WHERE audit.id = NEW.source_audit_id;
            WITH actual AS (
              SELECT task.adapter_id,
                     count(*) FILTER (
                       WHERE task.request_payload ? '_provider_request_contract'
                     )::integer AS frozen_task_count,
                     count(*) FILTER (
                       WHERE NOT task.request_payload ? '_provider_request_contract'
                     )::integer AS reconstructed_task_count,
                     COALESCE(
                       jsonb_agg(
                         jsonb_build_object(
                           'task_id', task.id::text,
                           'artifact_id', artifact.id::text,
                           'artifact_checksum', artifact.checksum,
                           'body_checksum', artifact.metadata->>'body_checksum',
                           'http_status', task.http_status
                         ) ORDER BY task.id::text COLLATE "C"
                       ) FILTER (
                         WHERE NOT task.request_payload ? '_provider_request_contract'
                           AND task.raw_artifact_id IS NOT NULL
                       ),
                       '[]'::jsonb
                     ) AS called_artifacts
              FROM collection_task task
              LEFT JOIN dataset_artifact artifact ON artifact.id = task.raw_artifact_id
              WHERE task.collection_run_id = NEW.base_collection_run_id
                AND task.retailer_id = NEW.retailer_id
              GROUP BY task.adapter_id
            ), sealed AS (
              SELECT entry.key AS adapter_id, entry.value AS evidence
              FROM jsonb_each(
                NEW.manifest->'source_evidence'->'request_identity'->'contracts'
              ) AS entry(key, value)
            )
            SELECT count(*)::integer
            INTO identity_inventory_mismatch_count
            FROM actual
            FULL JOIN sealed USING (adapter_id)
            WHERE actual.adapter_id IS NULL
               OR sealed.adapter_id IS NULL
               OR sealed.evidence->>'retailer_id' IS DISTINCT FROM NEW.retailer_id
               OR sealed.evidence->>'adapter_id' IS DISTINCT FROM actual.adapter_id
               OR jsonb_typeof(sealed.evidence->'contract') IS DISTINCT FROM 'object'
               OR sealed.evidence->>'sealed_contract_checksum' IS DISTINCT FROM encode(
                    digest(
                      convert_to(
                        scope_projection_canonical_jsonb(sealed.evidence->'contract'),
                        'UTF8'
                      ),
                      'sha256'
                    ),
                    'hex'
                  )
               OR (sealed.evidence->>'frozen_task_count')::integer
                    IS DISTINCT FROM actual.frozen_task_count
               OR (sealed.evidence->>'reconstructed_task_count')::integer
                    IS DISTINCT FROM actual.reconstructed_task_count
               OR (sealed.evidence->>'called_artifact_count')::integer
                    IS DISTINCT FROM jsonb_array_length(actual.called_artifacts)
               OR sealed.evidence->'called_artifacts' IS DISTINCT FROM actual.called_artifacts
               OR sealed.evidence->>'called_artifacts_checksum' IS DISTINCT FROM encode(
                    digest(
                      convert_to(
                        scope_projection_canonical_jsonb(
                          jsonb_build_object('artifacts', actual.called_artifacts)
                        ),
                        'UTF8'
                      ),
                      'sha256'
                    ),
                    'hex'
                  )
               OR (
                 actual.reconstructed_task_count > 0
                 AND jsonb_array_length(actual.called_artifacts) = 0
               );
            SELECT count(*)::integer INTO conflicting_location_count
            FROM (
              SELECT task.retailer_location_id
              FROM collection_scope_projection_task item
              JOIN collection_task task ON task.id = item.source_task_id
              WHERE item.scope_projection_id = NEW.id AND item.disposition = 'excluded'
              GROUP BY task.retailer_location_id
              HAVING bool_or(item.reason = 'audited_alias_of_provider_safe_canonical_scope')
                 AND bool_or(item.reason = 'audited_provider_unsafe_unpaired_scope_gap')
            ) conflicts;
            SELECT count(*)::integer INTO source_multi_target_count
            FROM (
              SELECT source_task.retailer_location_id
              FROM collection_scope_projection_task item
              JOIN collection_task source_task ON source_task.id = item.source_task_id
              JOIN collection_task target_task ON target_task.id = item.mapped_retained_task_id
              WHERE item.scope_projection_id = NEW.id
                AND item.reason = 'audited_alias_of_provider_safe_canonical_scope'
              GROUP BY source_task.retailer_location_id
              HAVING count(DISTINCT target_task.retailer_location_id) > 1
            ) conflicts;
            SELECT count(*)::integer INTO target_multi_source_count
            FROM (
              SELECT target_task.retailer_location_id
              FROM collection_scope_projection_task item
              JOIN collection_task source_task ON source_task.id = item.source_task_id
              JOIN collection_task target_task ON target_task.id = item.mapped_retained_task_id
              WHERE item.scope_projection_id = NEW.id
                AND item.reason = 'audited_alias_of_provider_safe_canonical_scope'
              GROUP BY target_task.retailer_location_id
              HAVING count(DISTINCT source_task.retailer_location_id) > 1
            ) conflicts;
            SELECT count(*)::integer INTO paired_gap_count
            FROM collection_scope_projection_task gap
            JOIN collection_task source_task ON source_task.id = gap.source_task_id
            WHERE gap.scope_projection_id = NEW.id
              AND gap.reason = 'audited_provider_unsafe_unpaired_scope_gap'
              AND EXISTS (
                SELECT 1
                FROM collection_scope_projection_task retained_item
                JOIN collection_task retained_task
                  ON retained_task.id = retained_item.source_task_id
                WHERE retained_item.scope_projection_id = NEW.id
                  AND retained_item.disposition = 'retained'
                  AND source_task.adapter_id = retained_task.adapter_id
                  AND source_task.zipcode = retained_task.zipcode
                  AND source_task.page_number = retained_task.page_number
                  AND retained_task.store_number = lpad(source_task.store_number, 8, '0')
                  AND length(source_task.store_number) = 7
                  AND length(retained_task.store_number) = 8
                  AND (
                    source_task.request_payload
                      - '_provider_request_contract' - 'store_number'
                  ) = (
                    retained_task.request_payload
                      - '_provider_request_contract' - 'store_number'
                  )
              );
            WITH reviewed_change AS MATERIALIZED (
              SELECT change
              FROM location_eligibility_reconciliation_run audit
              CROSS JOIN LATERAL jsonb_array_elements(audit.changes) change
              WHERE audit.id = NEW.source_audit_id AND audit.status = 'completed'
            )
            SELECT count(*)::integer INTO audit_mismatch_count
            FROM collection_scope_projection_task item
            JOIN collection_task task ON task.id = item.source_task_id
            LEFT JOIN reviewed_change reviewed
              ON reviewed.change->>'id' = task.retailer_location_id::text
             AND reviewed.change->>'retailer_id' = NEW.retailer_id
             AND COALESCE((reviewed.change->>'before_eligible')::boolean, false)
             AND NOT COALESCE((reviewed.change->>'after_eligible')::boolean, true)
             AND reviewed.change->>'store_number' = task.store_number
             AND reviewed.change->>'after_reason' = 'store_number_not_provider_safe'
            WHERE item.scope_projection_id = NEW.id
              AND item.disposition = 'excluded'
              AND reviewed.change IS NULL;
            IF invalid_reason_count <> 0
               OR actual_inventory_checksum IS DISTINCT FROM NEW.manifest->>'inventory_checksum'
               OR expected_audit_evidence IS DISTINCT FROM (
                    NEW.manifest->'source_evidence'->'location_audit'
                  )
               OR NEW.manifest->'source_evidence'->'request_identity'
                    ->'reconstructed_current_catalog_unverified'
                    IS DISTINCT FROM jsonb_build_array(
                      'historical_parameter_values', 'historical_catalog_defaults'
                    )
               OR identity_inventory_mismatch_count <> 0
               OR conflicting_location_count <> 0
               OR source_multi_target_count <> 0
               OR target_multi_source_count <> 0
               OR paired_gap_count <> 0
               OR audit_mismatch_count <> 0
               OR gap_locations <> NEW.denominator_gap_location_count
               OR NEW.raw_task_retention_ratio <> ROUND(
                    retained_count::numeric / inventory_count, 6
                  )
               OR NEW.governed_coverage_ratio <> ROUND(
                    retained_locations::numeric / (retained_locations + gap_locations), 6
                  )
               OR (
                 NEW.governed_coverage_ratio >= NEW.minimum_scoreable_coverage
                 AND NEW.scorecard_disposition <> 'scoreable'
               )
               OR (
                 NEW.governed_coverage_ratio < NEW.minimum_scoreable_coverage
                 AND NEW.scorecard_disposition <> 'unavailable'
               ) THEN
              RAISE EXCEPTION
                'audited reconciliation denominator or disposition does not reconcile';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER collection_scope_projection_complete_validate_trg
        AFTER INSERT ON collection_scope_projection
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION validate_collection_scope_projection_complete()
        """
    )
    op.execute(
        """
        CREATE FUNCTION serialize_audited_scope_projection_source()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_TABLE_NAME = 'collection_task'
             AND TG_OP = 'UPDATE'
             AND (
               OLD.collection_run_id IS DISTINCT FROM NEW.collection_run_id
               OR OLD.retailer_id IS DISTINCT FROM NEW.retailer_id
             ) THEN
            PERFORM 1 FROM collection_run
            WHERE id = NEW.collection_run_id FOR KEY SHARE;
          ELSIF TG_TABLE_NAME = 'collection_geography_location'
                AND TG_OP IN ('UPDATE', 'DELETE') THEN
            PERFORM 1 FROM collection_geography_resolution
            WHERE id = OLD.resolution_id FOR KEY SHARE;
            IF TG_OP = 'UPDATE'
               AND OLD.resolution_id IS DISTINCT FROM NEW.resolution_id THEN
              PERFORM 1 FROM collection_geography_resolution
              WHERE id = NEW.resolution_id FOR KEY SHARE;
            END IF;
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_audited_scope_projection_source()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          protected boolean := false;
        BEGIN
          IF TG_TABLE_NAME = 'collection_task' THEN
            IF TG_OP = 'INSERT' THEN
              SELECT EXISTS (
                SELECT 1 FROM collection_scope_projection projection
                WHERE projection.projection_kind = 'audited_alias_reconciliation'
                  AND projection.base_collection_run_id = NEW.collection_run_id
                  AND projection.retailer_id = NEW.retailer_id
              ) INTO protected;
            ELSIF TG_OP = 'UPDATE' THEN
              SELECT EXISTS (
                SELECT 1
                FROM collection_scope_projection_task item
                JOIN collection_scope_projection projection
                  ON projection.id = item.scope_projection_id
                WHERE projection.projection_kind = 'audited_alias_reconciliation'
                  AND item.source_task_id = OLD.id
              ) OR (
                (
                  OLD.collection_run_id IS DISTINCT FROM NEW.collection_run_id
                  OR OLD.retailer_id IS DISTINCT FROM NEW.retailer_id
                ) AND EXISTS (
                SELECT 1 FROM collection_scope_projection projection
                WHERE projection.projection_kind = 'audited_alias_reconciliation'
                  AND projection.base_collection_run_id = NEW.collection_run_id
                  AND projection.retailer_id = NEW.retailer_id
                )
              ) INTO protected;
            ELSE
              SELECT EXISTS (
                SELECT 1
                FROM collection_scope_projection_task item
                JOIN collection_scope_projection projection
                  ON projection.id = item.scope_projection_id
                WHERE projection.projection_kind = 'audited_alias_reconciliation'
                  AND item.source_task_id = OLD.id
              ) INTO protected;
            END IF;
          ELSIF TG_TABLE_NAME = 'dataset_artifact' THEN
            SELECT EXISTS (
              SELECT 1
              FROM collection_task task
              JOIN collection_scope_projection_task item
                ON item.source_task_id = task.id
              JOIN collection_scope_projection projection
                ON projection.id = item.scope_projection_id
              WHERE projection.projection_kind = 'audited_alias_reconciliation'
                AND task.raw_artifact_id = OLD.id
            ) INTO protected;
          ELSIF TG_TABLE_NAME = 'collection_geography_location' THEN
            IF TG_OP = 'INSERT' THEN
              SELECT EXISTS (
                SELECT 1 FROM collection_scope_projection projection
                JOIN collection_scope_projection_task item
                  ON item.scope_projection_id = projection.id
                JOIN collection_task task ON task.id = item.source_task_id
                JOIN collection_run run ON run.id = projection.base_collection_run_id
                JOIN collection_definition_version version
                  ON version.id = run.definition_version_id
                WHERE projection.projection_kind = 'audited_alias_reconciliation'
                  AND version.geography_resolution_id = NEW.resolution_id
                  AND task.retailer_id = NEW.retailer_id
                  AND task.location_scope_key = NEW.scope_key
              ) INTO protected;
            ELSIF TG_OP = 'UPDATE' THEN
              SELECT EXISTS (
                SELECT 1 FROM collection_scope_projection projection
                JOIN collection_scope_projection_task item
                  ON item.scope_projection_id = projection.id
                JOIN collection_task task ON task.id = item.source_task_id
                JOIN collection_run run ON run.id = projection.base_collection_run_id
                JOIN collection_definition_version version
                  ON version.id = run.definition_version_id
                WHERE projection.projection_kind = 'audited_alias_reconciliation'
                  AND (
                    (
                      version.geography_resolution_id = OLD.resolution_id
                      AND task.retailer_id = OLD.retailer_id
                      AND task.location_scope_key = OLD.scope_key
                    ) OR (
                      version.geography_resolution_id = NEW.resolution_id
                      AND task.retailer_id = NEW.retailer_id
                      AND task.location_scope_key = NEW.scope_key
                    )
                  )
              ) INTO protected;
            ELSE
              SELECT EXISTS (
                SELECT 1 FROM collection_scope_projection projection
                JOIN collection_scope_projection_task item
                  ON item.scope_projection_id = projection.id
                JOIN collection_task task ON task.id = item.source_task_id
                JOIN collection_run run ON run.id = projection.base_collection_run_id
                JOIN collection_definition_version version
                  ON version.id = run.definition_version_id
                WHERE projection.projection_kind = 'audited_alias_reconciliation'
                  AND version.geography_resolution_id = OLD.resolution_id
                  AND task.retailer_id = OLD.retailer_id
                  AND task.location_scope_key = OLD.scope_key
              ) INTO protected;
            END IF;
          ELSIF TG_TABLE_NAME = 'collection_definition_version' THEN
            SELECT EXISTS (
              SELECT 1
              FROM collection_run run
              JOIN collection_scope_projection projection
                ON projection.base_collection_run_id = run.id
              WHERE projection.projection_kind = 'audited_alias_reconciliation'
                AND run.definition_version_id = OLD.id
            ) INTO protected;
          ELSIF TG_TABLE_NAME = 'collection_run' THEN
            SELECT EXISTS (
              SELECT 1
              FROM collection_scope_projection projection
              WHERE projection.projection_kind = 'audited_alias_reconciliation'
                AND projection.base_collection_run_id = OLD.id
            ) INTO protected;
          END IF;
          IF protected THEN
            RAISE EXCEPTION
              'audited reconciliation source evidence is immutable after approval';
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER collection_task_audited_projection_source_serialize_trg "
        "BEFORE UPDATE ON collection_task "
        "FOR EACH ROW EXECUTE FUNCTION serialize_audited_scope_projection_source()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER collection_task_audited_projection_source_protect_trg "
        "AFTER INSERT OR UPDATE OR DELETE ON collection_task "
        "DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION protect_audited_scope_projection_source()"
    )
    op.execute(
        "CREATE TRIGGER collection_geography_location_audited_projection_source_serialize_trg "
        "BEFORE UPDATE OR DELETE ON collection_geography_location "
        "FOR EACH ROW EXECUTE FUNCTION serialize_audited_scope_projection_source()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER "
        "collection_geography_location_audited_projection_source_protect_trg "
        "AFTER INSERT OR UPDATE OR DELETE ON collection_geography_location "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION protect_audited_scope_projection_source()"
    )
    for table_name in (
        "dataset_artifact",
        "collection_definition_version",
        "collection_run",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table_name}_audited_projection_source_protect_trg "
            f"AFTER UPDATE OR DELETE ON {table_name} DEFERRABLE INITIALLY DEFERRED "
            "FOR EACH ROW EXECUTE FUNCTION protect_audited_scope_projection_source()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    if int(
        connection.scalar(
            sa.text(
                "SELECT count(*) FROM collection_scope_projection "
                "WHERE projection_kind = 'audited_alias_reconciliation' "
                "OR denominator_gap_location_count <> 0"
            )
        )
        or 0
    ):
        raise RuntimeError(
            "cannot downgrade 0054 while audited alias reconciliation history exists"
        )

    op.execute(
        "DROP TRIGGER collection_task_audited_projection_source_serialize_trg ON collection_task"
    )
    op.execute(
        "DROP TRIGGER collection_geography_location_audited_projection_source_serialize_trg "
        "ON collection_geography_location"
    )
    for table_name in (
        "collection_task",
        "dataset_artifact",
        "collection_geography_location",
        "collection_definition_version",
        "collection_run",
    ):
        op.execute(
            f"DROP TRIGGER {table_name}_audited_projection_source_protect_trg ON {table_name}"
        )
    op.execute("DROP FUNCTION protect_audited_scope_projection_source()")
    op.execute("DROP FUNCTION serialize_audited_scope_projection_source()")
    op.drop_index(
        "collection_scope_projection_task_source_idx",
        table_name="collection_scope_projection_task",
    )
    op.execute(
        "DROP TRIGGER collection_scope_projection_complete_validate_trg "
        "ON collection_scope_projection"
    )
    op.execute("DROP FUNCTION validate_collection_scope_projection_complete()")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_collection_scope_projection_header()
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
               SELECT 1 FROM jsonb_array_elements(
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
        CREATE OR REPLACE FUNCTION validate_collection_scope_projection_task()
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
          FROM collection_scope_projection WHERE id = NEW.scope_projection_id;
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
        CREATE OR REPLACE FUNCTION validate_collection_scope_projection_mapping()
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
    op.execute("DROP FUNCTION scope_projection_task_request_identity(uuid, jsonb)")
    op.execute("DROP FUNCTION scope_projection_quote_plus(text)")
    op.execute("DROP FUNCTION scope_projection_canonical_jsonb(jsonb)")

    op.drop_constraint(
        "collection_scope_projection_scoreability_ck",
        "collection_scope_projection",
        type_="check",
    )
    op.create_check_constraint(
        "collection_scope_projection_scoreability_ck",
        "collection_scope_projection",
        "(projection_kind = 'canonical_alias_collapse' "
        " AND governed_coverage_ratio = 1 AND scorecard_disposition = 'scoreable') OR "
        "(projection_kind = 'limited_provider_footprint' "
        " AND ((governed_coverage_ratio >= minimum_scoreable_coverage "
        "       AND scorecard_disposition = 'scoreable') "
        "      OR (governed_coverage_ratio < minimum_scoreable_coverage "
        "          AND scorecard_disposition = 'unavailable')))",
    )
    op.drop_constraint(
        "collection_scope_projection_audit_ck",
        "collection_scope_projection",
        type_="check",
    )
    op.create_check_constraint(
        "collection_scope_projection_audit_ck",
        "collection_scope_projection",
        "(projection_kind = 'canonical_alias_collapse' AND source_audit_id IS NOT NULL) OR "
        "(projection_kind = 'limited_provider_footprint' AND source_audit_id IS NULL)",
    )
    op.drop_constraint(
        "collection_scope_projection_kind_ck",
        "collection_scope_projection",
        type_="check",
    )
    op.create_check_constraint(
        "collection_scope_projection_kind_ck",
        "collection_scope_projection",
        "projection_kind IN ('canonical_alias_collapse','limited_provider_footprint')",
    )
    op.drop_constraint(
        "collection_scope_projection_denominator_gap_ck",
        "collection_scope_projection",
        type_="check",
    )
    op.drop_column("collection_scope_projection", "denominator_gap_location_count")
