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

## Matching Architecture v2 shadow model

Phase 13 adds an additive evidence and comparison model while the existing matcher remains
authoritative:

- `retailer_listing_v2` explicitly represents the retailer-specific product identity currently
  carried by `canonical_product`.
- `trade_item_v2` represents a verified physical package when identifier and package evidence are
  sufficient; listings may remain unlinked rather than being guessed into a trade item.
- `product_attribute_fact_v2` stores immutable raw/normalized attribute evidence, source,
  reliability, extraction method, review state, and Product Pack version.
- `match_policy_version_v2`, `product_match_candidate_v2`, `product_match_edge_v2`, and
  `product_match_attribute_evidence_v2` separate candidate recall, pairwise semantic claims, match
  tiers, price-basis eligibility, and attribute provenance.
- `match_group_v2` and `match_group_member_v2` are derived business groupings; they never replace
  pairwise edge evidence.
- `store_catchment_policy_v2` and `store_catchment_v2` version physical-store and service-area
  applicability.
- `local_comparison_observation_v2` stores every local candidate and the one policy-selected
  controlling offer. Partial unique indexes enforce one selected result per policy, competitor,
  price basis, benchmark product, and benchmark location.
- decision and revalidation events preserve immutable human/rule history and drift triggers.

The v2 tables are shadow-only until a Product Pack passes the Phase 13 certification gates.
Historical `product_match_revision`, `product_match_rule`, AnalysisResults, and publications are
not rewritten.

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
