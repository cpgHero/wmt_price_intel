# Phase 13.94 - Canonical report empty dataset fail-closed

Date: 2026-09-10

Parent plan: `docs/139_PHASE_13_85_REPORTING_SIMPLIFICATION_AND_APP_FIRST_REDESIGN.md`

## Objective

Prevent a canonical buyer-facing report from presenting as ready when no product-level relationships are reportable.

## Trigger

Production read-only checks of the active canonical report dataset endpoints showed that bananas had reportable product relationships, while milk and eggs could return canonical datasets with zero included relationships and no audit blockers. That was internally consistent but misleading for the report workflow: a buyer-facing report with no product-level wins or losses is not ready for executive review or PDF export.

## Scope

- Mark canonical datasets as `blocked` when zero product relationships pass the canonical guardrails.
- Add blocking reason `no_reportable_product_relationships`.
- Include a next action that points operators back to Product Pack coverage, match certification, positive prices, governed distribution evidence, and retained-evidence rebuild.
- Mark product-pack and retailer coverage QA statuses as blocked when no product relationships are reportable.
- Display readiness next actions in the Evidence & QA checklist.
- Make the canonical dataset audit command fail when readiness is blocked or zero product relationships are reportable.

## Non-goals

This phase does not invent product relationships, change price calculations, change distribution rules, change seller governance, call providers, call PDP, call AI, recollect data, reprocess data, publish reports, export PDFs, or delete historical artifacts.

## Acceptance criteria

- A canonical dataset with no reportable product relationships has `readiness.status = blocked`.
- The first blocking reason tells the operator why the buyer-facing report is not ready.
- The blocking reason includes a retained-evidence rebuild next action.
- The Evidence & QA readiness card displays the next action.
- The canonical audit command fails for blocked readiness and zero product relationships.
- Existing clean datasets with product relationships continue to pass focused canonical report tests.
