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
`0021_collection_geography_resolution` adds immutable, approved geography snapshots for the
dynamic Collection Builder. `0022_product_pack_runtime_catalog` makes exact Product Pack and
report-blueprint versions first-class runtime records. `0023_product_pack_authoring` adds
revisioned drafts, immutable evidence manifests, leased validation work, certification links,
and review events for the governed administrator builder.
`0024_scoped_match_brand` preserves the global one-to-one default while adding
location-scoped relationship metadata, conflict-safe comparison resolution, and immutable brand
classification revisions/application policy for the Brand Workbench.
`0025_retailer_pack_brand` adds immutable Retailer Pack and brand-foundation runtime tables plus
the fail-closed unknown-brand discovery queue. Repository bundles remain the reviewed seed source;
application analyses record exact checksums for reproducibility.
`0026_study_discovery_control_plane` adds governed query discovery, candidate profiling, and paid
work approvals. `0027_price_intelligence_foundation` adds nullable, source-governed retailer
location hierarchy fields plus immutable single-retailer product-price snapshots, exact-product
store observations, deterministic aggregates, and an auditable exception-review foundation.
`0028_pdp_renormalization` adds a leased, replica-safe, zero-credit queue of append-only
normalization revisions over immutable PDP raw snapshots. It permits schema upgrades and historical
seller/attribute recovery without mutating raw or previously published snapshot evidence.
