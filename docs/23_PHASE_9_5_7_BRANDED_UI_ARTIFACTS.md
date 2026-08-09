# Phase 9.5.7: Branded UI and Artifacts

Status: implemented and locally accepted on 2026-08-09. Railway acceptance is recorded after the
production deployment in this document.

## Outcome

The application and its leadership artifacts now share a CPGHero presentation system based on the
verified public-site light and dark themes. The report workspace is organized around stable,
category-neutral decision areas, and every artifact carries the same immutable AnalysisResult
checksum.

The changes are presentation-only. Renderers do not import the analytics engine, and neither the
web workspace nor any artifact renderer recalculates authoritative analytical facts.

## Application shell

- Shared light tokens use white and `#f6f7fb` surfaces, near-black text, cyan `#58d2f8` highlights,
  and `#0082c8` strong accents.
- Shared dark tokens use `#0b0b0d`, `#0f0f11`, `#1a1a1d`, and `#222228` surfaces with the same cyan
  brand family.
- A compact CPGHero wordmark identifies the standalone Retail Competitive Intelligence product.
- The accessible theme control persists a user choice in `localStorage`.
- A `beforeInteractive` theme initializer applies the saved or system preference before hydration,
  preventing a light-theme flash when dark mode is selected.
- The shell remains responsive and retains the existing operational navigation.

## Decision workspace

Report-blueprint section `kind` values map into nine stable workspace destinations:

1. Summary
2. Geography
3. Price
4. Segments
5. Products
6. Opportunities
7. Quality
8. Methodology
9. Exports

The mapping is generic and contains no Product Pack or category identifiers. Blueprint-selected
metrics receive unit-aware presentation formatting, `ranked_cards` sections receive decision
cards, and `bar` sections receive display-only relative bars. Underlying values, references, and
records are unchanged. A trust strip exposes deterministic authority, linked evidence, and the
persisted result checksum.

## Artifact reconciliation

The shared artifact identity is `provenance.final_result_checksum_sha256` for AnalysisResult V2. A
canonical-result SHA-256 fallback preserves the same guarantee for V1 results.

- Leadership HTML includes the checksum in a data attribute, trust pill, and footer.
- Excel includes a branded `Artifact Manifest` worksheet with the checksum, schema, Product Pack,
  and report-blueprint versions.
- Leadership email includes an `X-RCI-Result-Checksum` header and a visible checksum line.
- Audit ZIP `manifest.json` includes the same top-level `result_checksum_sha256` while retaining
  per-file hashes.

The Excel writer disables string-to-formula and string-to-URL conversion, preventing source text
from becoming an executable workbook formula or unintended hyperlink.

## Local acceptance evidence

```text
Python:       194 passed, 10 environment-gated skips
Web:          8 passed
TS contracts: 1 passed
Browser:      2 passed
Mypy:         103 source files, no issues
Ruff:         164 Python files linted and format-checked
ESLint:       web and contracts passed
Prettier:     all repository files passed
Next.js:      production build passed
Contracts:    26 normative JSON documents validated
Goldens:      all configured benchmark assertions passed
Alembic:      offline upgrade through 0013 passed
```

Focused artifact tests prove that HTML, Excel, email, and audit ZIP all contain the identical V2
checksum. Local in-app browser inspection confirmed the branded shell, persisted theme toggle,
light and dark computed colors, and the self-contained leadership HTML. No MetricsCart or model
requests were made.

## Railway acceptance evidence

Pending production deployment and post-deploy health/browser checks.

## Remaining acceptance work

Phase 9.5.8 runs the available full-source regressions and performs the final Railway health,
artifact, browser, migration, concurrency, and explicitly budgeted live-smoke gates.
