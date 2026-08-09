# Phase 9.6 — Analysis Publications and Unified Reports

## Outcome

The application, leadership HTML, email attachment, workbook, and audit package now resolve
the same governed analysis publication. The immutable deterministic `AnalysisResult` remains
the analytical system of record.

## Publication contract

`analysis_publication` is an immutable, versioned presentation record linked to one
`analysis_result`.

- `source_result_checksum` pins the deterministic source.
- `publication_checksum` covers the governed result and presentation context.
- authoritative `source`, `metrics`, and `evidence_sets` must remain byte-equivalent to the
  deterministic result before a publication is accepted;
- a repeated publication is idempotent;
- a new publication supersedes the prior display version without deleting it; and
- report artifacts are keyed by publication and renderer version.

The app falls back to the deterministic result when no governed publication exists.

## Presentation behavior

- `/analyses` remains the stable route; the user-facing navigation label is **Reports**.
- The report workspace leads with governed narrative and a limited decision scorecard.
- Product Pack `reporting.recommended_charts` selects generic chart capabilities. No product
  category branches were introduced in the report engine.
- Comparison charts keep matched-observation counts visible and retain the detailed table in
  a disclosure.
- Maps render only when analysis-linked coordinates are present in the publication context.
  Location-master coverage is not presented as price-opportunity evidence.
- PDP product cards are optional. PDP identity and imagery can enrich presentation, while
  SERP price and availability remain authoritative.

## Delivery behavior

- The HTML export is the shareable report represented in the app.
- The leadership `.eml` includes that same HTML report as an attachment.
- The audit package contains the canonical published result and the publication-aware exports.
- All report objects remain private and are opened through short-lived signed URLs.

## Railway sequence

1. Deploy migration `0015_analysis_publications`.
2. Deploy API, worker, web, and scheduler from the same commit.
3. Publish the approved governed ground-beef result from the cached agent tasks.
4. Generate and validate the publication-aware report artifacts.
5. Confirm the live app report, email attachment, light mode, dark mode, and mobile layout.

No MetricsCart calls are required to publish the already-approved governed narrative.
