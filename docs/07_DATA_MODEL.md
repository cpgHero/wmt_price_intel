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
