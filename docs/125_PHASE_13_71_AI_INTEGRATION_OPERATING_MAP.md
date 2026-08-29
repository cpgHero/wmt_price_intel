# Phase 13.71 — AI Integration Operating Map

## Outcome

Platform Docs now contains one consolidated, maintained guide for every implemented AI-assisted
workflow and the boundaries around it. The guide is written for the platform owner, platform
administrators, and engineering lead and is available under **Trust & governance → AI integration
& operating boundaries**.

## Current production inventory

The deployed runtime has three OpenAI-assisted lanes:

1. governed interpretation of deterministic insight candidates;
2. governed drafting of report narrative sections; and
3. administrator-requested Matching v2 evidence review.

Product-image vision is conditional evidence inside the third lane rather than a separate agent.
The repository also contains an explicit, engineering-only narrative bake-off command. It is not
part of the normal application workflow and cannot activate a report.

Production non-secret configuration was verified on August 29, 2026:

- AI and Matching v2 review are enabled;
- insight and narrative use `gpt-5.6-sol`, high reasoning, at most 12,000 output tokens, a $3.00
  conservative per-request ceiling, and at most two attempts;
- Matching v2 review uses `gpt-5.6-luna`, medium reasoning, at most 6,000 output tokens, a $0.35
  conservative per-case ceiling, at most two automatic attempts, and four-case worker concurrency;
- Matching v2 terminal failures may receive up to four separately administrator-confirmed retry
  rounds.

The OpenAI credential was not read, printed, or added to documentation.

## Authority boundary

AI may interpret supplied facts, improve prose, propose match verdicts, and propose exact-image,
visible-text-backed attribute evidence. It never owns Search price, availability, location,
sponsorship, identifiers, package rules, distances, unit conversions, counts, medians, rates,
cohorts, price ladders, scorecards, publication readiness, or report activation.

Matching proposals remain advisory. Product Pack policy and deterministic evidence constrain the
tier and price bases. Human review is mandatory. Guarded bulk certification still requires one
identified administrator to confirm a checksum-bound preview.

## Explicit non-AI areas

The maintained guide records that collection, retailer adapters, raw preservation, normalization,
noise removal, seller policy, Product Pack admission, PDP acquisition, brand governance,
candidate generation, hard blockers, analytics, materialization, trust audits, context filtering,
export, schedules, alerts, and runtime web research are not AI-powered today.

`OPENAI_MODEL_CLASSIFICATION` remains an unused environment-template placeholder. It must not be
described as assisted brand classification until a governed runtime consumer, tests, audit
lineage, and administrator workflow exist.

## Maintenance contract

Any model, provider, prompt, prompt version, schema, reasoning level, token/cost limit,
concurrency, retry rule, model input, image policy, authority boundary, trigger, fallback, or
administrator action change must update the guide and append a dated Platform Docs change order
in the same release. Paid acceptance work must record its approval, scope, model, usage/cost,
outcomes, and downstream effects.

## Verification

- Platform Docs unit tests require the consolidated guide and all three current AI lanes.
- Tests require the current production model families, `store=false`, the unused classification
  placeholder disclosure, deterministic authority, human authority, and the maintenance contract.
- The implementation changes documentation only. It makes no provider call and changes no source
  evidence, certified relationship, metric, materialization, report, or historical audit record.
