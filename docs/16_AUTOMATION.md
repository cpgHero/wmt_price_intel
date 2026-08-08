# Scheduling, Alerts, Delivery, and Budgets

## Scheduled collections

Collection-definition versions carry a five-field cron expression and IANA timezone. The scheduler
synchronizes active definitions into `collection_schedule`, claims due rows with
`FOR UPDATE SKIP LOCKED`, and advances each row to the next timezone-aware instant. The unique
`(schedule_id, scheduled_for)` run constraint makes retries and multiple scheduler replicas safe.
Manual and scheduled runs share the same planner, budget checks, task identities, cancellation, and
collection worker path.

## Run budgets

Definitions may set `max_credits_per_day` and/or `max_credits_per_month`. Run creation takes a
transaction-scoped advisory lock per definition, calculates the UTC period usage, and atomically
rejects a run whose estimate would cross either limit. Completed runs count actual credits; queued
and running runs reserve their estimate. No task is created when admission fails.

## Historical comparison and alerts

History compares successful AnalysisResults for the same Product Pack and collection definition.
The generic comparator walks numeric metrics in source summary, coverage, comparisons, data quality,
and validation. Each change contains current/baseline values, absolute and optional percent change,
and JSON evidence references.

Alert definitions are JSON-Schema-validated, versioned, checksummed configurations. A selector
chooses one AnalysisResult metric by object path or filtered list row. Generic operators cover:

- a competitor becoming more than a configured percentage-point or percent-change amount lower;
- coverage expansion;
- parity-rate changes;
- data-quality degradation below a threshold;
- direct numeric comparisons and absolute changes for future Product Packs.

Core alert code contains no product-category branches. Definitions scope rules by Product Pack and
collection definition. Every evaluation stores a `triggered`, `suppressed`, or `not_triggered`
status plus the alert checksum, selector/condition, current analysis ID/checksum/pointer/value,
optional baseline equivalents, and computed change. Cooldown suppression is decided atomically from
shared Postgres event state.

## Email delivery

Triggered alerts and configured leadership reports enqueue immutable email jobs with unique
idempotency keys. Scheduler replicas claim jobs with `FOR UPDATE SKIP LOCKED` leases. Failure uses
bounded exponential retry; expired leases are reclaimable; sent and exhausted jobs are terminal.
SMTP credentials come only from environment variables. Delivery rows retain analysis/event evidence
and provider message IDs without persisting credentials.
