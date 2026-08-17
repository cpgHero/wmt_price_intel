# Phase 13.13.3 — Egg PDP 404 Remediation

## Purpose

Diagnose the 404-heavy Egg Product Details subsets without paying to repeat requests that are
already known to be wrong. Correct only the demonstrated retailer contract, identifier, and
Product Pack scope defects; preserve Search as the authority for store price and availability.

## Evidence from the completed run

Production run `11d33dad-0658-457d-8bdd-b72d2f45a212` produced 117 billable HTTP 404 responses.
The heavy subsets were not equivalent:

- Target returned the same plain `404 page not found` response for all 41 requests, including
  legitimate shell-Egg URLs that currently resolve on Target. This is a route signature, not
  evidence that all products disappeared.
- Sam's Club returned `no Route matched with those values` for all 21 requests, including a
  currently resolving shell-Egg URL. This is a request-contract signature.
- Trader Joe's Search identities lost leading zeros (`62124` instead of `062124`, for example),
  while the provider catalog defines six-digit identifiers.
- ALDI and Walmart have extensive prior HTTP 200 coverage. Their small uncached 404 subsets are
  therefore product/location/current-availability cases and must not be swept into a contract
  retry.
- Every attempted context came from a positive-price Search observation. Target, ALDI, and
  Walmart store/ZIP pairs reconciled to the location master; Sam's Club and Trader Joe's are not
  represented in the current master and retain Search-observed location provenance.
- The earlier Egg scope admitted non-shell-Egg noise. That waste is a Product Pack admission
  defect, separate from endpoint behavior.

## Configuration-driven corrections

- Target uses `/mc/target/pdp/zipcode/`, URL identity only, observed ZIP/store, and pickup.
- Sam's Club uses `/mc/samsclub/pdp/zipcode/`, URL identity only, observed ZIP/store, and pickup.
- Trader Joe's uses `/mc/traderjoes/pdp/zipcode/`, product-ID identity, observed ZIP/store, and a
  generic catalog-configured six-character left pad for numeric IDs.
- The generic request adapter applies the endpoint's configured identity policy and optional
  identifier normalization. No retailer or Egg branch was added to the core engine.
- The same normalized request parameters govern request construction and cache identity, so an
  obsolete contract cannot be reused silently.
- Product Pack `fresh_shell_eggs` 1.2.1 rejects known Egg search noise such as egg nog, hard-cooked
  eggs, egg replacers/bites/rolls, decorative/nonfood items, pet food, books, and serum before PDP
  planning. Regression tests preserve true shell-Egg admission.

## Bounded paid preflight

Deployment alone does not authorize a broad retry. The controlled preflight ceiling is nine
credits / **$0.018** and uses no secret in source or output:

1. The owner-provided Target catalog example (three credits).
2. A real Target shell-Egg URL at its positive-price observed ZIP/store (three credits).
3. The owner-provided Sam's Club Egg example (two credits).
4. One real Trader Joe's Egg with the restored six-digit ID (one credit).

The preflight records only request metadata, HTTP status, response content type, and a minimal
identity check. Response bodies remain out of Git and user-visible logs.

## Retry gate

A corrected subset may be replanned only when its preflight proves the contract. The new plan must
be read-only first, use Product Pack 1.2.1, reuse fresh cache, admit one positive-price observed
context per distinct in-scope product, and state exact calls/credits. ALDI and Walmart 404s remain
excluded unless a separate product/location investigation identifies a correct alternate context.

## Verification checklist

- [x] Target and Sam's Club owner-provided CURLs are encoded exactly, without API keys.
- [x] URL-only endpoints never send a conflicting `product_id`.
- [x] Trader Joe's leading-zero normalization is configuration, not retailer code.
- [x] Request and cache identities use the same normalized parameters.
- [x] Egg noise and true-shell-Egg regression fixtures pass.
- [ ] CI and Railway deployment pass.
- [ ] The bounded paid preflight is complete and its outcomes are recorded.
- [ ] Any retry estimate is reviewed before a durable paid run is created.

## Explicitly deferred

- Broad retry of any 404 subset.
- Retrying ALDI or Walmart just to improve coverage.
- Replaying Egg analysis/reporting until corrected PDP evidence is collected and Matching v2 is
  ready for the separately governed reporting cutover.
