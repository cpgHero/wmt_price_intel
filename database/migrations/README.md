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
`0042_price_arch_matrix` persists parameter-scoped Price Architecture Matrix
read models beside the immutable AnalysisResult. Default Walmart-anchored, fixed-$0.50, and
fixed-$1.00 matrices can be built during publication and served without rereading every classified
Parquet artifact; rebuilding the derivative never queues a paid provider call.
`0043_comp_portfolio_mat` persists the complete configured comparison-basis × 1/3/5-mile
Competitive Portfolio set. `0044_report_pub_gate` makes new AnalysisResults pending by default and
adds a leased `SKIP LOCKED` publication job plus idempotent staging documents. Existing certified
results are backfilled as ready. A replacement becomes ready only when the complete staged set
passes the semantic trust audit and one transaction installs every read model while recoverably
archiving the prior ready report in the same Product Pack lineage.
`0045_location_eligibility` preserves every imported location row while allowing collection
planning to use only active, provider-safe store identifiers.
`0046_retailer_gates` makes availability decisions durable per retailer, releases healthy retailer
work independently, stops an unrecoverable retailer sample early, and records mixed run outcomes as
partial without discarding task or billing evidence.
`0048_price_catalog` adds one compact Price Intelligence retailer catalog per immutable
AnalysisResult. Catalogs join the leased report-publication staging and atomic activation flow,
support server-side product search/facets/paging, and remain derived, reversible, and free of paid
provider or AI work.
`0049_gate_resilience` adds nullable, run-scoped successful-sample quorum and transient-nonbillable
failure ceilings to retailer availability gates. Null preserves the legacy strict gate. The revision
does not alter frozen tasks, raw evidence, 404 accounting, budgets, or historical gate decisions.
`0050_location_reconcile` adds a durable audit run for catalog-driven location-eligibility
corrections. The administrator command defaults to a read-only dry run; an explicit apply records
the reviewed-plan, catalog, and location-snapshot checksums, operator, reason, before/after counts,
and exact row changes. Apply must consume the reviewed dry-run artifact, shares a whole-operation
advisory lock with location import, rejects a stale snapshot, and commits all changes plus audit
completion atomically. Downgrade is refused after audit history exists so a schema rollback cannot
silently destroy the record of an applied eligibility decision.
`0051_composite_evidence` adds an offline-created immutable spend authorization consumed by exactly
one aggregate recovery batch; checksum-bound, failure-only recovery plans; versioned retailer
unavailability approvals; immutable base/recovery input components; one canonical selected task
per provider request; and downstream composite-analysis lineage. The Search credit rate is pinned
at $0.002 USD, and the HTTP API can create a batch only from an existing authorization UUID. It
permits multiple immutable input generations for one base run without rewriting source tasks or
artifacts. Downgrade is refused after any spend authorization, recovery batch, recovery plan,
unavailability approval, composite input set, or incompatible duplicate input generation exists.
`0052_recovery_continuations` adds a bounded, non-branching parent/child lineage for exact
unresolved-only recovery plans. A continuation may reuse the same canonical request only through
its explicit ancestor chain, reserves only incremental credits still available in the immutable
batch, and preserves every ancestor component during materialization. Its downgrade refuses to
discard any persisted continuation lineage. The separate audit-bound Kroger scope-projection work
is a follow-on schema revision (0053 if it requires a migration), not part of 0052.
