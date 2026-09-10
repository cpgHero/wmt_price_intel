# Phase 13.88 - Hidden Canonical Report Preview

Date: 2026-09-09

Parent plan: `docs/139_PHASE_13_85_REPORTING_SIMPLIFICATION_AND_APP_FIRST_REDESIGN.md`

## Objective

Create a safe, non-default app preview of the simplified report experience so the bananas pilot can be reviewed without changing the current reporting route or published report behavior.

## Implemented files

- `apps/web/src/app/analyses/[analysisId]/canonical-report-workspace.tsx`
- `apps/web/src/app/api/analyses/[analysisId]/canonical-report-dataset/route.ts`
- `apps/web/src/lib/canonical-report-preview.ts`
- `apps/web/src/lib/canonical-report-preview.test.ts`
- `apps/web/src/app/analyses/[analysisId]/page.tsx`
- `apps/web/src/app/analyses/[analysisId]/workspace.tsx`
- `apps/web/src/app/styles.css`
- `apps/web/src/lib/canonical-report-focus.ts`
- `apps/web/src/lib/canonical-report-focus.test.ts`
- `apps/web/src/lib/canonical-report-dataset-route.ts`
- `apps/web/src/lib/canonical-report-dataset-route.test.ts`
- `apps/web/src/lib/canonical-report-qa.ts`
- `apps/web/src/lib/canonical-report-qa.test.ts`
- `apps/web/src/lib/canonical-report-workspace-source.test.ts`
- `apps/web/src/lib/analyses-library-source.test.ts`
- `apps/web/src/lib/platform-docs.ts`
- `apps/web/src/lib/platform-docs.test.ts`
- `scripts/audit_canonical_report_dataset.mjs`
- `package.json`

## Preview flags

The simplified shell is hidden unless one of these query parameters is present:

- `?experience=canonical`
- `?experience=simplified`
- `?reportExperience=canonical`
- `?reportExperience=simplified`
- `?canonical=1`
- `?canonical=true`

For staging or local runtime QA, the web process can set `RCI_CANONICAL_REPORT_DEFAULT=1`, `true`, or `enabled` to make the canonical preview the default report experience without changing the code path again.

Explicit URL overrides still force the current report when needed for side-by-side comparison:

- `?experience=legacy`
- `?experience=current`
- `?reportExperience=legacy`
- `?reportExperience=current`
- `?canonical=0`
- `?canonical=false`

The reports library exposes `Open current report` as the primary action and `Open simplified preview` as a secondary action for AnalysisResult v2 reports only. The simplified preview header includes a `Current report` comparison link.

The reports library empty state identifies whether the API was unavailable or whether no published AnalysisResults were returned, names the source endpoint checked, and links operators to Collections, Report Publishing/materialization, and Data Quality for follow-up.

The app navigation has a hidden simplified model controlled by `NEXT_PUBLIC_RCI_SIMPLIFIED_NAV`. When enabled, Reports becomes the only primary Analytics entry, Report Publishing is presented as Pipeline Status under Operations, and Price Intelligence/Data Quality are removed from primary navigation without deleting their routes.

## Current preview shape

Tabs:

1. Executive Summary
2. Product Wins & Losses
3. Distribution & Assortment
4. Price Architecture
5. Evidence & QA

The preview renders product relationships as image-first comparison cards. The Product Wins & Losses tab lists all included Walmart wins, all included Walmart losses, and parity/unscored relationships separately. It does not mix a few image examples with table-only rows.

The Product Wins & Losses tab now includes a product action board. By default it still shows every included relationship, but reviewers can filter the same governed image cards by product text, outcome, Walmart brand type, competitor, and Walmart positive-price store footprint. The default sort puts Walmart losses first, then broader Walmart distribution, then larger percentage price gaps.

The sort control names percentage-gap sorting explicitly, and each product card states in plain language whether Walmart's displayed reporting price is above or below the competitor on the displayed comparison basis.

The Executive Summary includes fact-only brand-role focus cards for private label, national, regional, and unclassified Walmart products. These cards summarize only included governed product relationships, Walmart wins, Walmart losses, and broad-footprint Walmart losses.

The preview header links to a hidden JSON endpoint at `/api/analyses/{analysisId}/canonical-report-dataset`. The endpoint performs no analysis or publication work; it reads the existing analysis and report view, applies the canonical adapter, and returns the same canonical dataset consumed by the preview.

The repository now also includes an offline audit command:

```bash
pnpm reports:audit-canonical -- --input examples/canonical-report-dataset.bananas.json --output /tmp/canonical-bananas-audit.md
```

The audit validates the dataset contract and writes a Markdown QA readout covering included relationships, excluded relationships, summary reconciliation, win/loss counts, brand-type mix, top Walmart wins/losses by product footprint, price sentinels, seller governance, distribution evidence, and service-area separation.

The Evidence & QA tab includes a validation checklist that summarizes report readiness, seller governance, price normalization, distribution evidence, match certification, and product image coverage. The checklist is derived from canonical dataset status fields and QA counts; it does not recompute authoritative metrics.

The Evidence & QA tab also surfaces canonical dataset integrity blockers. The same shared checker guards the hidden dataset endpoint, which returns HTTP 422 when the projected dataset has summary drift, win/loss sign contradictions, invalid prices, invalid distribution contracts, service-area/store-count confusion, duplicate relationships, seller qualification failures, or negative distribution counts.

The command resolves `ajv` and `ajv-formats` from `packages/typescript/contracts/node_modules` first, then root `node_modules`. In a degraded checkout where dependencies are available only elsewhere, set `RCI_NODE_MODULES_FALLBACK` to one or more `node_modules` search paths separated by `:`.

## Trust rules carried into the preview

- Store distribution is positive-price store Search presence.
- Store distribution is not an in-stock claim.
- Service-area presence is separate and is never shown as a store count.
- Zero or missing reportable prices are excluded by the canonical adapter.
- Walmart benchmark products must be seller-qualified or explicitly not applicable.
- Benchmark and competitor products must both carry governed distribution evidence before a relationship can render as an included card.
- `price_delta` is benchmark/Walmart reporting price minus competitor reporting price; product-card outcomes are derived from that displayed delta, and the audit blocks any future sign/outcome contradiction.
- Regional brand content is fact-only through governed relationship cards.
- The preview contains no commentary about changes versus prior report versions.

## Validation performed

- Focused Vitest suite passed:
  - `apps/web/src/lib/canonical-report-dataset.test.ts`
  - `apps/web/src/lib/canonical-report-preview.test.ts`
  - `apps/web/src/lib/platform-docs.test.ts`
  - `apps/web/src/lib/public-availability-cache.test.ts`
- Result: 3 test files passed, 13 tests passed.
- After the endpoint and audit utility additions: 4 test files passed, 33 tests passed.
- After audit-command portability coverage: 5 test files passed, 35 tests passed.
- After endpoint-helper and evidence-timestamp coverage: 6 test files passed, 41 tests passed.
- After product action-board filtering and sorting coverage: 7 test files passed, 47 tests passed.
- After validation-checklist coverage: 8 test files passed, 50 tests passed.
- After staging rollout flag coverage: 8 test files passed, 52 tests passed.
- After preview source-contract coverage: 9 test files passed, 58 tests passed.
- After library preview-affordance coverage: 10 test files passed, 62 tests passed.
- After card-outcome/price-delta alignment coverage: 10 test files passed, 63 tests passed.
- After card delta-wording coverage: 10 test files passed, 64 tests passed.
- After report-library empty-state diagnostics coverage: 10 test files passed, 65 tests passed.
- After brand-role focus coverage: 10 test files passed, 67 tests passed.
- After report-library empty-state follow-up link coverage: 10 test files passed, 68 tests passed.
- After canonical dataset integrity guard coverage: 10 test files passed, 72 tests passed.
- After simplified navigation model coverage: 11 test files passed, 76 tests passed.
- `scripts/audit_canonical_report_dataset.mjs --input examples/canonical-report-dataset.bananas.json` passed and wrote `/private/tmp/canonical-bananas-audit.md`.
- TypeScript contract generation completed and produced no additional canonical report dataset type diff.
- `packages/python/rci-contracts/tests/test_validator.py` passed with 18 tests.

## Known limits

- Full web typecheck was not completed because this checkout started dependency linking/install work and stalled before compile execution. The command was interrupted cleanly after focused tests had passed.
- Local browser/runtime validation was attempted on 2026-09-09, but pnpm repeatedly entered workspace dependency linking and did not reach `next` or the app server within the bounded probe window. A second offline frozen install using `--package-import-method=hardlink` progressed further, but still did not complete within the bounded probe window. No browser QA should be claimed until a single clean workspace install/link completes and the web app can start against a reachable API or mocked API.
- PDF/export remains intentionally pending until the app preview is accepted.
- Production/default report behavior is unchanged.

## Next step

Run the bananas pilot through the preview, compare the included and excluded product relationships against the current report and raw evidence, then decide whether to replace the default app report shell.
