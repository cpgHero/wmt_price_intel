# Phase 9.9 — Report surface parity and category certification

## Outcome

The analysis workspace, downloadable HTML report, and shareable report now project the same
publication through one ordered presentation contract. An export can no longer retain obsolete
cards, map treatments, or section ordering after the application has moved forward.

## Shared presentation contract

`rci-results` assigns every report section to the same eight presentation groups used by the web
workspace: Summary, Geography, Price, Segments, Products, Opportunities, Quality, and Methodology.
The API exposes that ordering. The web workspace and HTML renderer consume it without
recalculating analytics.

Renderer `2.11.0` adds:

- the product-pair decision cards used by the application, including both product identities and
  images when PDP evidence exists;
- product and outcome filters on the geographic footprint;
- state geometry and marker clustering derived from the same bundled US topology used by web;
- the segment decision matrix;
- exact store/ZIP evidence behind product decisions;
- representative source rows behind quality exclusions;
- the same omission of low-value aggregate KPI cards used by the application.

Search evidence remains authoritative for price and location. PDP data remains identity-only.
The renderer consumes deterministic `AnalysisResult` evidence and does not calculate new findings.

## Consolidated historical sources

A consolidated source artifact may contain multiple retailer payloads. Historical normalization
preserves the retailer carried by each row rather than replacing it with the artifact-level hint.
This is required for the supplied 14-retailer fresh-shell-eggs source and remains a generic source
format capability rather than a category branch.

Pinned manifests now cover the full supplied Strawberries, Eggs, Milk, and Bananas corpora. Every
manifest records checksums, row counts, adapters, source formats, and Product Pack versions.

## Obsolete report cleanup

Migration `0016_analysis_archival` adds a reversible `archived_at` lifecycle field. The analysis
index hides archived rows by default. Obsolete single-product development runs are archived with
an audit record after the new release is deployed; the certified ground-beef publication and new
full-category publications remain active.

## Acceptance gates

Before a category is published:

1. Its full-source golden benchmark must pass.
2. Its pinned historical-input manifest must validate against the source files.
3. The import must complete through the durable historical analysis queue.
4. Selective PDP enrichment may target analysis-admitted products only, using one representative
   location per product unless distinct observed price states require additional locations.
5. Narrative publication must pass deterministic claim validation.
6. The app and renderer-versioned export must pass live visual and evidence checks.

The full supplied certification corpus contains 1,201,752 source rows: 297,443 Strawberries,
386,889 Eggs, 348,980 Milk, and 168,440 Bananas.
