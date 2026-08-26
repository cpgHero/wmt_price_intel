# Phase 13.56 — Product Attribute Claim Reconciliation

## Objective

Turn repeated, pair-level AI image observations into a safe product-level administrator workflow.
One retailer product and one Product Pack attribute appear once, with every source citation and
conflicting value available for review. This removes duplicate work without allowing repetition to
be mistaken for independent proof.

## Governing identity and scope

A claim is identified by the current immutable review queue, retailer listing identity, Product
Pack attribute, batch scope, and the complete set of eligible source proposal checksums. The claim
checksum changes whenever that evidence membership or queue context changes. A decision against an
older checksum is rejected as stale.

The default administrator view includes all current AI batch lineages for the queue. It can be
filtered by attribute and by awaiting-review, conflict, verified, or rejected status. Conflict
claims are ranked first, followed by unresolved claims and then finalized history; products with
the largest observed footprint rank first within a status.

## Evidence presentation

Each claim displays:

- retailer product identity, brand, image, listing ID, and observed store/location count;
- the current governed value and source authority;
- the number of affected candidate relationships and distinct counterpart products/retailers;
- every distinct proposed normalized value and its confidence range;
- every distinct cited PDP image and visible label excerpt; and
- the number of underlying pair-level observations for audit context.

Repeated proposals across candidate pairs are supporting context only. They do not increase source
authority or independently verify a value. Multiple normalized values remain a visible conflict and
require the administrator to choose the supported citation or reject the claim.

## Decision and authority boundary

An identified administrator must provide a rationale. Verification selects one exact,
source-attributable proposal. Rejection rejects the complete product-attribute claim. The append-only
decision stores the full claim membership and selected evidence in the existing evidence-decision
audit record; no destructive schema rewrite is required.

The derived deterministic evidence layer may reuse a verified value anywhere the same governed
retailer listing participates in a candidate relationship. Raw Search, PDP, images, AI output, and
immutable queue evidence never change. A verified evidence claim does not certify any relationship,
start a replay, or change reporting. Match Certification and governed publication remain separate,
explicit gates.

## Validation

- The pure projection test proves that three pair proposals for one listing and attribute collapse
  to one claim and that two values fail closed as a conflict.
- The service test proves stale-checksum protection, product-level affected-case context, and no
  automatic relationship certification.
- The browser test covers the administrator selecting one conflict variant, supplying rationale,
  and posting the checksum-bound verification.
- Ruff, mypy, API tests, TypeScript type checking, lint, formatting, and production build remain
  release gates.

## Operational next step

Open Match Certification, select the Vitamin queue, and choose **Product evidence claims**. Work
conflicts first, then high-footprint consensus claims. After reconciliation is complete, recompute
the deterministic relationship view and assess guarded match certification. Do not replay or
publish Vitamin reporting until relationship certification and the Product Pack release gates pass.
