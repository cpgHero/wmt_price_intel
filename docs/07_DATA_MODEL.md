# Data Model

## Design principle

PostgreSQL is the control plane. High-volume immutable datasets are stored as objects/Parquet and referenced by metadata rows.

## Core entities

- organization / user / role (lightweight V1, future multi-tenant ready)
- retailer
- retailer_alias
- retailer_location
- product_pack
- product_pack_version
- collection_definition
- collection_definition_version
- collection_run
- collection_task
- provider_rate_limit_state
- dataset_artifact
- canonical_product / canonical_product_context
- product_detail_enrichment_run / product_detail_job / product_detail_snapshot
- analysis_input_set / analysis_input_artifact
- analysis_run
- analysis_result
- validation_issue
- report_artifact
- collection_schedule
- alert_definition / alert_definition_version / alert_event
- analysis_automation_state
- email_delivery
- audit_event

## Heavy analytical artifacts

Normalized offers, classified offers, candidates, match detail, and supporting row-level output should default to Parquet in object storage. Store counts/checksums/schema versions and object URIs in `dataset_artifact`.

## Historical reproducibility

`analysis_input_set` is the source boundary shared by live collection and historical replay. Its
manifest is canonical JSON with a SHA-256, source kind, Product Pack reference, analysis config,
and total rows. Ordered `analysis_input_artifact` rows link that manifest to immutable bucket
objects. The same realized manifest is unique per organization and source kind.

## Product identity and PDP evidence

`canonical_product` has one stable record per organization, retailer, and retailer product ID.
Alternate identifiers remain a JSON object of strings, while stable PDP identity fields are stored
separately from `canonical_product_context` rows that preserve SERP/PDP ZIP, store, fulfillment,
source-artifact, and observation-time provenance.

`product_detail_enrichment_run` owns a hard planned-credit ceiling and separate actual-credit
ledger. `product_detail_job` is a durable leased queue with a request checksum idempotency key;
claims use `FOR UPDATE SKIP LOCKED`. `product_detail_snapshot` is immutable attempt evidence with a
raw-object checksum and optional cache expiry. The cache key includes retailer, product ID, ZIP,
store, fulfillment, and endpoint contract version. PDP identity may enrich every linked SERP
observation, but PDP price and availability never replace the SERP snapshot fields.

An analysis result records:
- collection definition version,
- Product Pack version,
- retailer adapter versions,
- normalized dataset checksums,
- analytics code build SHA,
- AI prompt/model metadata where applicable.

## Automation state

`collection_schedule` materializes versioned collection definitions into idempotent scheduled run
slots. `analysis_automation_state` and `email_delivery` are durable leased work queues; claims use
`FOR UPDATE SKIP LOCKED`, expired leases are reclaimable, and unique keys prevent repeat evaluation
or delivery. Alert events retain the current and baseline metric values plus JSON evidence pointers
to the immutable AnalysisResults used in the decision.

Collection budgets remain configuration on the immutable collection definition version. Run
creation serializes budget reservations with a transaction-scoped advisory lock, counting actual
credits for terminal runs and the original estimate for in-flight runs in UTC daily/monthly windows.
