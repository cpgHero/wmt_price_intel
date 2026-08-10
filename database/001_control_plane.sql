-- PostgreSQL V1 control plane for Retail Competitive Intelligence.
-- IDs are UUIDs except provider-facing identifiers, which remain TEXT.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE organization (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organization(id),
  email text NOT NULL UNIQUE,
  display_name text,
  role text NOT NULL CHECK (role IN ('admin','analyst','viewer')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE retailer (
  id text PRIMARY KEY,
  display_name text NOT NULL,
  country text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE retailer_alias (
  alias text PRIMARY KEY,
  retailer_id text NOT NULL REFERENCES retailer(id)
);

CREATE TABLE retailer_location (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  retailer_id text NOT NULL REFERENCES retailer(id),
  provider text NOT NULL,
  provider_location_id text,
  store_number text NOT NULL,
  store_name text,
  raw_zipcode text,
  zipcode text,
  street text,
  address text,
  city text,
  state text,
  county text,
  country text NOT NULL,
  latitude double precision,
  longitude double precision,
  status text,
  source_created_at text,
  imported_at timestamptz NOT NULL DEFAULT now(),
  raw_row jsonb,
  UNIQUE(retailer_id, provider, store_number, country)
);
CREATE INDEX retailer_location_zip_idx ON retailer_location(retailer_id, country, zipcode);
CREATE INDEX retailer_location_latlon_idx ON retailer_location(latitude, longitude);

CREATE TABLE product_pack (
  id text PRIMARY KEY,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE product_pack_version (
  product_pack_id text NOT NULL REFERENCES product_pack(id),
  version text NOT NULL,
  schema_version text NOT NULL,
  config jsonb NOT NULL,
  checksum text NOT NULL,
  published_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(product_pack_id, version)
);

CREATE TABLE collection_definition (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organization(id),
  stable_key text NOT NULL,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_by uuid REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(organization_id, stable_key)
);
CREATE TABLE collection_definition_version (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  definition_id uuid NOT NULL REFERENCES collection_definition(id),
  version integer NOT NULL,
  config jsonb NOT NULL,
  checksum text NOT NULL,
  created_by uuid REFERENCES app_user(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(definition_id, version)
);

CREATE TABLE collection_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organization(id),
  definition_version_id uuid NOT NULL REFERENCES collection_definition_version(id),
  status text NOT NULL,
  estimated_pages integer,
  estimated_credits integer,
  actual_success_pages integer NOT NULL DEFAULT 0,
  actual_credits integer NOT NULL DEFAULT 0,
  trigger_type text NOT NULL DEFAULT 'manual'
    CHECK(trigger_type IN ('manual','scheduled','historical_import')),
  requested_by uuid REFERENCES app_user(id),
  started_at timestamptz,
  completed_at timestamptz,
  cancel_requested_at timestamptz,
  error_summary text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX collection_run_status_idx ON collection_run(status, created_at);

CREATE TABLE collection_task (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_run_id uuid NOT NULL REFERENCES collection_run(id) ON DELETE CASCADE,
  retailer_id text NOT NULL REFERENCES retailer(id),
  retailer_location_id uuid REFERENCES retailer_location(id),
  location_scope_key text NOT NULL,
  zipcode text NOT NULL,
  store_number text,
  page_number integer NOT NULL CHECK(page_number BETWEEN 1 AND 10),
  request_fingerprint text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  priority integer NOT NULL DEFAULT 100,
  attempt_count integer NOT NULL DEFAULT 0,
  available_at timestamptz NOT NULL DEFAULT now(),
  locked_by text,
  locked_at timestamptz,
  lease_expires_at timestamptz,
  http_status integer,
  failure_class text,
  raw_artifact_id uuid,
  billable_credits integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  UNIQUE(collection_run_id, retailer_id, location_scope_key, page_number, request_fingerprint)
);
CREATE INDEX collection_task_claim_idx ON collection_task(status, available_at, priority, created_at);
CREATE INDEX collection_task_run_idx ON collection_task(collection_run_id, retailer_id, status);

CREATE TABLE provider_rate_limit_state (
  provider text NOT NULL,
  budget_key text NOT NULL,
  second_window_start timestamptz,
  second_count integer NOT NULL DEFAULT 0,
  minute_window_start timestamptz,
  minute_count integer NOT NULL DEFAULT 0,
  paused_until timestamptz,
  last_429_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(provider, budget_key)
);

CREATE TABLE dataset_artifact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_run_id uuid REFERENCES collection_run(id) ON DELETE CASCADE,
  artifact_type text NOT NULL,
  storage_uri text NOT NULL,
  content_type text,
  row_count bigint,
  byte_size bigint,
  checksum text NOT NULL,
  schema_version text,
  metadata jsonb NOT NULL DEFAULT '{}',
  immutable boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(storage_uri)
);

ALTER TABLE collection_task ADD CONSTRAINT collection_task_raw_artifact_fk FOREIGN KEY(raw_artifact_id) REFERENCES dataset_artifact(id);

CREATE TABLE analysis_input_set (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organization(id),
  source_kind text NOT NULL CHECK(source_kind IN ('live_collection','historical_import')),
  stable_key text NOT NULL,
  collection_run_id uuid NOT NULL UNIQUE REFERENCES collection_run(id) ON DELETE CASCADE,
  product_pack_id text NOT NULL,
  product_pack_version text NOT NULL,
  analysis_config jsonb NOT NULL,
  manifest jsonb NOT NULL,
  manifest_checksum text NOT NULL,
  total_rows bigint NOT NULL CHECK(total_rows >= 0),
  status text NOT NULL CHECK(status IN ('preparing','ready','failed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  UNIQUE(organization_id, source_kind, manifest_checksum)
);
CREATE INDEX analysis_input_set_ready_idx
  ON analysis_input_set(status, source_kind, created_at);

CREATE TABLE analysis_input_artifact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_set_id uuid NOT NULL REFERENCES analysis_input_set(id) ON DELETE CASCADE,
  dataset_artifact_id uuid NOT NULL REFERENCES dataset_artifact(id) ON DELETE CASCADE,
  ordinal integer NOT NULL CHECK(ordinal >= 0),
  retailer_id text NOT NULL REFERENCES retailer(id),
  adapter_id text NOT NULL,
  source_name text NOT NULL,
  source_format text NOT NULL,
  row_count bigint NOT NULL CHECK(row_count >= 0),
  checksum text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}',
  UNIQUE(input_set_id, ordinal),
  UNIQUE(input_set_id, dataset_artifact_id)
);

CREATE TABLE analysis_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_run_id uuid NOT NULL REFERENCES collection_run(id) ON DELETE CASCADE,
  input_set_id uuid REFERENCES analysis_input_set(id),
  product_pack_id text NOT NULL,
  product_pack_version text NOT NULL,
  status text NOT NULL,
  code_version text,
  available_at timestamptz NOT NULL DEFAULT now(),
  locked_by text,
  locked_at timestamptz,
  lease_expires_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 3,
  last_error text,
  started_at timestamptz,
  completed_at timestamptz,
  match_revision_id uuid,
  source_analysis_result_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX analysis_run_queue_claim_idx
  ON analysis_run(status, available_at, lease_expires_at, created_at);

CREATE TABLE analysis_result (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL UNIQUE REFERENCES analysis_run(id),
  schema_version text NOT NULL,
  result jsonb NOT NULL,
  checksum text NOT NULL,
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX analysis_result_active_created_idx
  ON analysis_result(created_at) WHERE archived_at IS NULL;

CREATE TABLE product_match_revision (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  product_pack_id text NOT NULL,
  product_pack_version text NOT NULL,
  benchmark_retailer_id text NOT NULL REFERENCES retailer(id),
  source_analysis_result_id uuid NOT NULL REFERENCES analysis_result(id),
  revision integer NOT NULL,
  status text NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'superseded')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(product_pack_id, product_pack_version)
    REFERENCES product_pack_version(product_pack_id, version),
  UNIQUE(organization_id, product_pack_id, product_pack_version,
    benchmark_retailer_id, revision)
);
CREATE UNIQUE INDEX product_match_revision_current_uq
  ON product_match_revision(
    organization_id, product_pack_id, product_pack_version, benchmark_retailer_id
  ) WHERE status = 'current';

CREATE TABLE product_match_rule (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  revision_id uuid NOT NULL REFERENCES product_match_revision(id) ON DELETE CASCADE,
  competitor_retailer_id text NOT NULL REFERENCES retailer(id),
  profile_id text NOT NULL,
  eligible_profile_ids text[] NOT NULL CHECK (cardinality(eligible_profile_ids) > 0),
  benchmark_product_id text NOT NULL,
  competitor_product_id text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('confirmed', 'rejected')),
  origin text NOT NULL DEFAULT 'user' CHECK (origin IN ('user', 'automatic')),
  reason text,
  benchmark_snapshot jsonb NOT NULL DEFAULT '{}',
  competitor_snapshot jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(revision_id, competitor_retailer_id,
    benchmark_product_id, competitor_product_id)
);
CREATE UNIQUE INDEX product_match_rule_confirmed_benchmark_uq
  ON product_match_rule(revision_id, competitor_retailer_id,
    benchmark_product_id) WHERE decision = 'confirmed';
CREATE UNIQUE INDEX product_match_rule_confirmed_competitor_uq
  ON product_match_rule(revision_id, competitor_retailer_id,
    competitor_product_id) WHERE decision = 'confirmed';

CREATE TABLE product_match_application_policy (
  organization_id uuid NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  product_pack_id text NOT NULL,
  product_pack_version text NOT NULL,
  benchmark_retailer_id text NOT NULL REFERENCES retailer(id),
  revision_id uuid NOT NULL REFERENCES product_match_revision(id) ON DELETE CASCADE,
  updated_by text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(organization_id, product_pack_id, product_pack_version,
    benchmark_retailer_id),
  FOREIGN KEY(product_pack_id, product_pack_version)
    REFERENCES product_pack_version(product_pack_id, version)
);
CREATE INDEX product_match_application_policy_revision_idx
  ON product_match_application_policy(revision_id);

CREATE TABLE product_match_review_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  revision_id uuid NOT NULL REFERENCES product_match_revision(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  actor text NOT NULL,
  details jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE analysis_run
  ADD CONSTRAINT analysis_run_match_revision_fk
    FOREIGN KEY(match_revision_id) REFERENCES product_match_revision(id),
  ADD CONSTRAINT analysis_run_source_result_fk
    FOREIGN KEY(source_analysis_result_id) REFERENCES analysis_result(id),
  ADD CONSTRAINT analysis_run_collection_pack_match_revision_uq
    UNIQUE NULLS NOT DISTINCT (
      collection_run_id, product_pack_id, product_pack_version, match_revision_id
    );
CREATE INDEX analysis_run_match_revision_idx ON analysis_run(match_revision_id);

CREATE TABLE agent_task (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  idempotency_key text NOT NULL UNIQUE,
  analysis_run_id uuid NOT NULL REFERENCES analysis_run(id) ON DELETE CASCADE,
  analysis_id text NOT NULL,
  role text NOT NULL CHECK(role IN ('insight','narrative')),
  status text NOT NULL CHECK(status IN ('running','succeeded','needs_review')),
  prompt_template_id text NOT NULL,
  prompt_template_version text NOT NULL,
  prompt_template_checksum text NOT NULL,
  model_provider text NOT NULL,
  model_id text NOT NULL,
  input_checksum text NOT NULL,
  input_document jsonb NOT NULL,
  output_checksum text,
  output_document jsonb,
  validation jsonb NOT NULL DEFAULT '{}',
  usage jsonb NOT NULL DEFAULT '{}',
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 2,
  locked_by text,
  locked_at timestamptz,
  lease_expires_at timestamptz,
  last_error_type text,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5)
);
CREATE INDEX agent_task_analysis_idx
  ON agent_task(analysis_run_id, role, created_at);
CREATE INDEX agent_task_lease_idx
  ON agent_task(status, lease_expires_at);

CREATE TABLE validation_issue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES analysis_run(id),
  severity text NOT NULL CHECK(severity IN ('info','warning','blocker')),
  issue_type text NOT NULL,
  entity_ref jsonb,
  message text NOT NULL,
  evidence jsonb,
  status text NOT NULL DEFAULT 'open',
  resolution jsonb,
  resolved_by uuid REFERENCES app_user(id),
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE report_artifact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL REFERENCES analysis_run(id),
  artifact_type text NOT NULL CHECK(artifact_type IN ('html','xlsx','leadership_email','audit_zip','csv','parquet')),
  renderer_version text NOT NULL DEFAULT 'legacy',
  dataset_artifact_id uuid REFERENCES dataset_artifact(id),
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (analysis_run_id, artifact_type, renderer_version)
);

CREATE TABLE audit_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid REFERENCES organization(id),
  user_id uuid REFERENCES app_user(id),
  event_type text NOT NULL,
  entity_type text,
  entity_id text,
  details jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
