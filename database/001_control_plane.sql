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
  collection_run_id uuid REFERENCES collection_run(id),
  artifact_type text NOT NULL,
  storage_uri text NOT NULL,
  content_type text,
  row_count bigint,
  byte_size bigint,
  checksum text NOT NULL,
  schema_version text,
  metadata jsonb,
  immutable boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE collection_task ADD CONSTRAINT collection_task_raw_artifact_fk FOREIGN KEY(raw_artifact_id) REFERENCES dataset_artifact(id);

CREATE TABLE analysis_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_run_id uuid NOT NULL REFERENCES collection_run(id),
  product_pack_id text NOT NULL,
  product_pack_version text NOT NULL,
  status text NOT NULL,
  code_version text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analysis_result (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_run_id uuid NOT NULL UNIQUE REFERENCES analysis_run(id),
  schema_version text NOT NULL,
  result jsonb NOT NULL,
  checksum text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

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
  dataset_artifact_id uuid REFERENCES dataset_artifact(id),
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
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
