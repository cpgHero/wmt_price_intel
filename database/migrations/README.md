# Database migrations

Alembic owns the executable migration history. The supplied `database/001_control_plane.sql`,
`002_seed_retailers.sql`, and `003_queue_claim_reference.sql` remain immutable design references.
Later phases translate those references into reviewable, reversible Alembic revisions.

The foundation revision intentionally creates no domain tables. `0002_location_master` implements
the retailer, alias, location, and import-status portion of the supplied control-plane reference.
`0003_collection_control_plane` adds versioned collection definitions, collection runs, and the
durable leased task queue. `0004_metricscart_data_plane` adds shared provider-limit state and
immutable object-artifact metadata. Later gated phases translate the remaining tables in dependency
order. `0005_product_packs` adds immutable, schema-validated Product Pack versions.
`0006_results_delivery` adds immutable AnalysisResult records, validation issues, report
artifact links, and audit events.
`0007_automation` adds durable schedules, alert evaluation, and email delivery. `0008` corrects
MetricsCart 404 billing, `0009` adds analysis orchestration, and `0010`/`0011` add immutable
historical/live input sets with safe artifact cascades. `0012_product_details` adds canonical
product identity, contextual provenance, separately budgeted PDP runs, a leased `SKIP LOCKED` PDP
queue, and immutable cached PDP snapshots. `0013_governed_ai` adds idempotent, leased, auditable
insight and narrative tasks without granting model output authority over analytical metrics.
`0014` through `0019` add renderer-version policy, immutable publications, safe historical
archival, and one-to-one match governance/application policy. `0020_provider_permit_pacing`
replaces fixed-window provider bursts with a database-coordinated next-permit timestamp so rolling
per-second and per-minute limits remain safe across worker replicas.
