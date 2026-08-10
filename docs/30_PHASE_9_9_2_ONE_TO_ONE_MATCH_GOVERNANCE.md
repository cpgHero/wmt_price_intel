# Phase 9.9.2 — One-to-One Match Governance

## Outcome

Give analysts a retailer-tabbed Match Review Workbench where they can confirm, reject,
replace, or manually create product matches and then queue a deterministic reanalysis from the
existing immutable inputs. No MetricsCart or PDP call is required merely because match decisions
changed.

## Integrity contract

- An active price match is one reference-retailer product to one competitor product per
  organization, Product Pack version, and competitor retailer. Phase 9.9.2a makes the
  relationship independent of the display lens and records the exact comparison profiles for
  which deterministic Product Pack evidence makes it eligible.
- A reference-retailer product and competitor product may each participate in at most one
  confirmed match in that scope, across all comparison profiles. Database partial unique indexes
  enforce both sides of the relationship.
- A benchmark product may be matched separately in different competitor-retailer tabs.
- Confirmed user decisions take precedence over automated candidates. Rejected pairs are removed
  from automated output. New products remain eligible for generic Product Pack matching.
- Related products, substitutes, and alternate package sizes are not price matches and do not feed
  report metrics.
- Duplicate listings must be consolidated to stable retailer product identities before review.
- Search observations remain authoritative for store-specific price. PDP enrichment supplies
  identity, attributes, descriptions, URLs, and imagery.

## Persistence and subsequent runs

Match decisions are immutable revision snapshots keyed by stable string product IDs. Saving a
decision creates a new revision by copying the previous snapshot and applying one change. A
confirmed replacement requires explicit replacement approval and atomically removes the displaced
confirmed edge. Rejections persist until reset.

An analysis run stores the exact match-revision ID it consumed. Attribute drift or missing product
identity never silently rewrites a decision; it produces a review status. Previously published
AnalysisResults and report artifacts remain immutable.

## Deterministic precedence

1. Remove explicitly rejected pairs.
2. Apply confirmed one-to-one pairs at the configured geography and price metric.
3. Exclude automated pairs that conflict with either side of a confirmed pair.
4. Admit remaining Product Pack matches.
5. Surface newly observed or uncertain products as review candidates.

The LLM may explain or rank candidates but cannot create authoritative matches or calculate prices,
counts, medians, rates, conversions, or geographic outcomes.

## User experience

- The named reference-retailer products appear on the left and competitor products on the right.
- Each competitor retailer has a tab; the comparison lens filters profile eligibility but does
  not require the same relationship to be reviewed repeatedly.
- Product cards show retailer, product ID, PDP-backed identity and image, current match state, and
  retained price-evidence counts.
- Analysts can drag or select two products to connect them, confirm an automated suggestion, reject
  a pair, disconnect/reset a decision, or replace a conflicting connection after confirmation.
- The workbench distinguishes suggested, confirmed, rejected, new, and unmatched products.
- Reanalysis shows that it uses existing inputs, the selected decision revision, and no provider
  credits. Completion creates a new immutable AnalysisResult linked to its source analysis.

## Acceptance tests

1. Database constraints prevent two confirmed products from sharing either side of a match.
2. Concurrent edits with a stale expected revision return a conflict rather than losing work.
3. Confirmed and rejected decisions survive subsequent runs by stable string product ID.
4. A confirmed pair displaces conflicting automated pairs and produces store/ZIP facts without
   bypassing price, availability, or geography validation.
5. A rejected pair never appears in governed match output.
6. Newly observed products remain eligible for automated matching and review.
7. Reanalysis reuses the existing input set and makes no MetricsCart, PDP, or OpenAI call.
8. The new analysis and every report artifact record the consumed match revision.
9. Existing publications remain byte-for-byte immutable.
10. Product Pack and core matching code remain category-neutral.
