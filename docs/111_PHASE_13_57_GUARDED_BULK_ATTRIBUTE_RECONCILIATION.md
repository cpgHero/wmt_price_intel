# Phase 13.57 — Guarded Bulk Attribute Reconciliation

## Objective

Remove the requirement to manually decide more than one thousand consistent product-attribute
claims while preserving the evidence and authority boundaries that protect match accuracy. The
system identifies the complete safe population, an administrator confirms it once, and only true
exceptions remain unresolved.

## Production evidence profile

The Vitamin queue contains 1,880 product-level claims across 941 products. Of these, 1,753 propose
one value and 127 contain conflicting values. A read-only production audit identified 1,415 claims
across 837 products that satisfy every policy gate. The excluded population consists of 127
conflicts, 303 attempts to refine or contradict an existing value, and 35 claims below the 95%
confidence floor. A claim may have more than one exclusion reason; summary counts remain explicit.

## Automatic safe-consensus policy

A claim is safe only when all of the following are true:

1. it has no existing final claim decision;
2. every eligible observation proposes the same normalized value;
3. the proposal fills an unknown Product Pack attribute and does not refine or replace evidence;
4. the minimum confidence across its source observations is at least 95%;
5. every citation retains an exact source image and non-empty visible label text; and
6. the complete queue, lineage, policy, claim membership, selected value, representative case, and
   proposal population still match the preview checksum at commit time.

AI remains an evidence producer. A deterministic versioned policy selects the safe population.
The administrator confirms the complete checksum-bound population in one action; there is no
per-claim clerical review.

## Transaction and audit behavior

The API recomputes the preview immediately before commit. It locks every representative review
case, revalidates the latest AI proposal under the active Product Pack, rejects stale or previously
decided proposals, and inserts the complete decision population in one Postgres transaction. A
failure rolls back the entire action. Every append-only evidence decision retains the policy,
confirmation checksum, selected source proposal, image, visible text, and complete claim context.

Product evidence may be reconciled after a case received a match verdict because the two records
have independent authority. The evidence decision does not reopen, replace, or silently change the
certified relationship. Any effect on matching or reporting requires a later, separately governed
recomputation and publication.

Raw Search, PDP, product images, AI responses, and review queues are immutable. The action updates
derived governed evidence only. It does not certify a product relationship, trigger reanalysis, or
publish reporting. Weak, conflicting, or value-changing claims remain unresolved and are not a
mandatory manual workload unless they are needed to resolve a specific high-value match later.

## Administrator experience

**Product Evidence Claims** now includes **Auto-reconcile safe claims**. The preview shows the safe
claim/product counts, attribute distribution, exception reasons, and a 25-claim sample. One
identified administrator confirmation applies the safe population and reports exactly how many
exceptions remain. Match Certification is still the next separate gate.

## Validation

- pure policy tests cover consensus, conflicts, and attempts to change existing evidence;
- service tests prove checksum binding, one-action persistence, and stale-preview rejection;
- browser coverage exercises preview, administrator confirmation, and the explicit no-match/no-
  reporting boundary;
- Ruff, mypy, API tests, TypeScript, lint, formatting, production build, and Playwright remain
  release gates.
