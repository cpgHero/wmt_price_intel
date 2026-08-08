# Product Requirements Document

## 1. Product

Working name: **Retail Competitive Intelligence (RCI)**.

### Primary user
Retail pricing, merchandising, category management, competitive-intelligence, and leadership teams who need store/ZIP-level evidence of competitor assortment, availability, and price position.

### Initial benchmark
Walmart US.

### V1 competitors
ALDI US and Amazon Same Day US.

## 2. Jobs to be done

- Define a repeatable category collection across retailer/location universes.
- Know estimated API credits before running the collection.
- Collect every configured store/ZIP with visible progress, retries, and failures.
- Preserve raw evidence for audit/reprocessing.
- Convert heterogeneous retailer responses to one canonical offer model.
- Remove keyword noise and classify category-specific attributes.
- Match truly comparable products at the correct geography and unit.
- Compute price leadership, parity, coverage, segment, assortment, and fulfillment metrics deterministically.
- Investigate suspicious comparisons without allowing AI to change calculations silently.
- Deliver an interactive leadership report, Excel audit workbook, leadership email draft, and audit data.
- Save definitions and rerun/schedule them later.

## 3. V1 user workflow

1. Create Collection Definition.
2. Select Product Pack.
3. Choose Walmart benchmark and enabled competitors.
4. Choose geography strategy and max pages.
5. Review location/page/credit estimate.
6. Start Collection Run.
7. Monitor progress, retries, 429 cooldown, empty results, and failures.
8. Run normalization/classification/analysis.
9. Review Data Quality and unresolved classification issues.
10. Publish AnalysisResult and generated artifacts.
11. View historical runs and rerun the same definition.

## 4. Functional requirements

### Collection definitions
- Versioned and immutable after a run begins; editing creates a new version.
- Keyword plus retailer-specific request options.
- Geography: all retailer stores, benchmark ZIPs, union ZIPs, custom ZIPs, custom locations, states.
- Per-retailer page caps 1-10.
- Cost estimate by retailer and total.
- Optional run credit ceiling.

### Collection engine
- Per retailer/location/page durable tasks.
- Multi-worker safe claims.
- Shared provider RPS/RPM enforcement.
- Shared cooldown after 429.
- Retry classification by failure class.
- Stop pagination on empty results when configured.
- Actual credits tracked on successful 2xx pages.

### Location master
- Import/sync provider geography.
- Preserve raw provider values plus normalized ZIP/country/coordinates.
- String IDs.
- Country-aware retailer universe.
- Proximity queries using Haversine/PostGIS-compatible semantics; PostGIS optional in V1, Python vectorized distance acceptable for analysis.

### Analytics
- Product Pack classification.
- Exact, compatible, private-label, same-brand, normalized-unit, and proximity profiles as supported by each pack.
- Lowest qualifying price selection at the defined grain.
- Parity tolerance explicit per pack/profile.
- Match evidence retained.
- No unsupported derived metrics.

### Artifacts
- Interactive web result view.
- Self-contained leadership HTML export.
- Excel workbook.
- Leadership email draft.
- Audit CSV/Parquet package.

## 5. Non-functional requirements

- Reproducible: rerunning analytics from the same raw snapshot + same code/config version yields the same result.
- Auditable: every metric traces to run, Product Pack version, normalized dataset, and match evidence.
- Scalable: multiple collection workers without duplicate task execution or provider quota multiplication.
- Secure: provider/API secrets server-side only.
- Observable: run/task counters, provider latency, 429s, retries, failures, page credits, processing time, QA issue counts.
- Resumable: failed workers do not lose claimed work permanently; leases expire and tasks can be reclaimed.

## 6. Out of scope for first vertical slice

- Fully self-service visual Product Pack builder.
- General-purpose supplier/broker dashboards.
- Autonomous price changes or retailer actions.
- Real-time sub-minute alerting.
- Adding all nine MetricsCart retailer endpoints before the abstraction is proven.

## 7. Success criteria

- Strawberry end-to-end run completes from definition through report.
- Golden strawberry headline metrics reproduce within tolerances.
- No strawberry-specific branches in the core engine.
- Adding eggs is primarily Product Pack configuration + generic capabilities.
- Collection costs and actual credits reconcile by retailer/page.
