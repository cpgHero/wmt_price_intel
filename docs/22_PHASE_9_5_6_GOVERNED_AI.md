# Phase 9.5.6: Governed AI Interpretation

Status: implemented and Railway-accepted on 2026-08-09.

## Outcome

The worker can now add model-assisted insight wording and leadership narrative to an otherwise
complete AnalysisResult V2. The deterministic engine remains the only authority for price,
availability, comparisons, counts, rates, gaps, rankings, classification, and recommendations.
If model execution, validation, persistence, or lease ownership fails, the deterministic result is
published unchanged.

The implementation is generic. It receives the active Product Pack, report blueprint,
deterministic metrics, insights, recommendations, and evidence manifest. There are no
product-category branches in the governed AI package or worker integration.

## Model authority boundary

- Models receive a capped, checksummed evidence packet rather than raw SERP/PDP payloads.
- Product Pack context is limited to ID, name, version, and configured caveats.
- Raw source files, object-storage locations, secrets, credentials, and personal data are not sent.
- Insight output may select and rewrite configured deterministic insight candidates, but cannot
  change their severity, confidence, metric references, or evidence references.
- Narrative output must return every requested report section exactly once and cite known metrics
  and evidence linked to those metrics.
- Models cannot emit numeric literals. Numeric prose uses a metric placeholder that the
  deterministic renderer resolves after validating metric ID, declared references, unit, and
  format.
- Authoritative metric bytes are compared before and after the AI overlay. Any mutation is rejected.
- Invalid output is recorded as `needs_review` on the agent task while the analysis retains its
  deterministic fallback.

## Provider and contract implementation

`rci-agents` pins `openai==2.53.0` and uses the Responses API with strict JSON Schema structured
output. Requests set `store=false`, use an explicitly configured model ID, cap output tokens, and
disable hidden SDK retries. Two versioned prompt contracts are validated from `agent-prompts/`:
`governed_insight` and `governed_narrative`.

The normative agent-output contract records prompt ID/version/checksum, provider/model, input and
output checksums, evidence references, token usage, latency, validation coverage, and the invariant
`authoritative_metrics_computed=false`. Python and TypeScript contract generators validate the same
prompt and output schemas.

The structured-output request follows the official OpenAI Responses API pattern for strict JSON
Schema output: <https://developers.openai.com/api/docs/guides/structured-outputs>.

## Durable audit and replica safety

Migration `0013_governed_ai` adds the `agent_task` audit table. Its idempotency key combines the
analysis run, role, prompt checksum, provider/model, and input checksum. Postgres advisory locking
serializes identical reservations. Running tasks have bounded leases and attempt limits; completed
outputs are reused rather than billed twice.

Completion and failure updates require the current worker ID and an unexpired lease. A slow worker
therefore cannot overwrite a task after another replica reclaims it. Successful records persist the
sanitized input, governed output, checksums, validation, usage, and task timing. Failure records keep
only the error type and a generic issue message; provider bodies and secrets are not logged.

## Runtime controls

The capability is off by default and remains off in Railway:

```text
AI_ENABLED=false
```

Enabling it requires a sealed worker-only `OPENAI_API_KEY` plus explicit insight and narrative model
IDs. Timeouts, output-token limits, input metric caps, attempts, and leases are independently
configured. Product Details enrichment remains separately gated and disabled.

## Local acceptance evidence

```text
Python:       193 passed, 10 environment-gated skips
Agent focus:  21 passed, 1 Postgres-gated skip
Web:          5 passed
TS contracts: 1 passed
Mypy:         103 source files, no issues
Ruff:         163 Python files linted and format-checked
ESLint:       web and contracts passed
Next.js:      production build passed
Contracts:    26 normative JSON documents validated
Goldens:      all configured benchmark assertions passed
Alembic:      offline upgrade through 0013 passed
Lockfile:     uv frozen-lock validation passed
```

The tests prove strict ephemeral provider configuration, deterministic metric immutability,
placeholder rendering, rejection of direct/unknown numeric claims, exact narrative section
coverage, idempotent result reuse, and full deterministic fallback after invalid model output.

## Railway acceptance evidence

- Commit `4fdbaff` deployed successfully to web, API, worker, and scheduler.
- The API pre-deploy migration advanced Postgres through `0013_governed_ai`.
- A production-Postgres acceptance run simulated two replicas reserving one identical agent task.
  Exactly one acquired the lease; the non-owner completion was rejected; the owner completed the
  task; and a third reservation reused the cached audited output.
- Temporary acceptance rows, the temporary Railway SSH key, and all local key material were removed.
- Public `/health/ready` returned `ready` with the API dependency `ok`.
- `AI_ENABLED` remained unset/false. No OpenAI or MetricsCart calls were made and no paid credits
  were used.

## Remaining acceptance work

Phase 9.5.7 applies final CPGHero presentation and branding. Phase 9.5.8 performs the full-source,
browser, artifact, concurrency, and live governed-output acceptance. A live model-backed quality
comparison against the supplied ground-beef and egg reference reports has not yet been run; that
requires an explicitly selected model and sealed worker key, and it will not grant the model metric
authority.
