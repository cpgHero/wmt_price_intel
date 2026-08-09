# Phase 9.6 — Decision-Grade Narrative Parity

## Purpose

Phase 9.6 closes the gap between a numerically correct application result and the decision-grade
competitive story demonstrated by the five reference analyses for ground beef, eggs, milk,
bananas, and strawberries. It does not move metric authority to an AI model. Deterministic code
still owns every number, match, denominator, segment, comparison mode, and evidence reference.

The recovered master analysis prompt is treated as benchmark methodology, not as an executable
runtime prompt. Its reusable reporting grammar is represented by versioned schemas, Product Pack
configuration, and narrative regression fixtures.

## Reference benchmark contract

`fixtures/golden/narrative-benchmarks.json` records the source checksums, required leadership
topics, category-specific story patterns, and weighted quality rubric for all five benchmark
categories. `schemas/narrative-benchmarks.schema.json` makes the fixture machine-validatable.

The common reporting grammar is:

1. establish the complete source and qualifying retailer footprint;
2. distinguish competitor, comparison-mode, package, segment, brand, and geography findings;
3. call out reversals between exact package and normalized unit-price conclusions;
4. name evidence-backed watchlists and operating actions; and
5. disclose match rules, fulfillment distinctions, small samples, data-quality limits, and other
   caveats.

Category behavior remains configuration. Each Product Pack's `reporting.narrative_playbook`
declares its leadership objective, required topics, decision lenses, action principles, forbidden
claims, and small-sample threshold. Core analytics and agent code contain no category switch.

## Governed reporting pipeline

### 1. Deterministic facts and semantic brief

The analytics engine now persists richer comparison statistics, including benchmark median,
competitor median, median gap, and mean gap. It also persists answer-first deterministic narrative
sections for scope, coverage, exact price, normalized price, segment drivers, nearby-store
sensitivity, product interpretation, actions, quality, and methodology.

`AnalysisBriefBuilder` converts an immutable AnalysisResult and Product Pack into a bounded
`analysis-brief.schema.json` document. The brief contains only references to stored metrics and
evidence, plus deterministic classifications such as risk, strength, mixed position, reversal,
geographic sensitivity, quality limitation, and action. It does not calculate new business
metrics.

### 2. Governed strategist and writer

The governed insight role selects and interprets an existing deterministic insight candidate. The
governed narrative role receives the semantic brief and writes every requested report section.
Numeric language is possible only through metric placeholders, which are resolved from the
persisted metric registry after generation.

Both roles use strict structured output, explicit prompt versions, auditable task envelopes,
idempotent task caching, bounded metric/evidence context, and `store=false`. If either role fails,
times out, or violates a contract, the deterministic result remains available.

### 3. Deterministic critic and claim verifier

The critic rejects a narrative when it:

- omits a required section or leadership topic;
- cites an undeclared storyline, metric, or evidence set;
- cites evidence that is not linked to the selected metric;
- contains an unsupported numeric literal; or
- is structurally too thin for leadership use.

The final AnalysisResult retains byte-identical authoritative metrics. AI output may replace only
interpretive insight and narrative fields, and provenance records the final checksum and agent task
IDs.

## Presentation projection

HTML, leadership email, XLSX, audit ZIP, and the web analysis workspace all project the same stored
narratives and metrics. The renderer does not recalculate analytical facts. Renderer version
`2.2.0` creates new immutable artifact keys while preserving prior artifacts.

Leadership email now carries the complete decision story rather than only an executive-summary
stub. XLSX adds a Leadership Narrative worksheet. The web workspace renders paragraph structure
inside a visually distinct narrative callout.

## Quality gates

Run the local contract and focused Phase 9.6 gates with:

```bash
.venv/bin/python scripts/validate_handoff.py
.venv/bin/python -m pytest \
  packages/python/rci-analytics/tests/test_product_pack.py \
  packages/python/rci-analytics/tests/test_result_v2.py \
  packages/python/rci-agents/tests/test_governance.py \
  packages/python/rci-results/tests/test_blueprints.py \
  packages/python/rci-results/tests/test_results.py
```

The full repository gates remain:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy apps packages/python
uv run pytest
pnpm contracts:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## Paid model bake-off

No paid OpenAI or MetricsCart calls are required for contract, analytics, projection, or fallback
testing. A separate, explicitly authorized bake-off should run only after local and deployment
gates pass. It should use fixed analysis inputs, one or more explicitly pinned model IDs, a hard
request/token cap, and the narrative benchmark rubric. The bake-off must score numerical fidelity
as a hard gate before competitive story, reversals, actionability, methodology, and readability.

Model selection, prompts, and maximum output tokens must be pinned through Railway variables only
after the capped bake-off is approved. No live collection should be triggered solely to test prose;
persisted full-source results are the correct test inputs.

The first controlled candidate uses `gpt-5.4-mini-2026-03-17` for bounded insight selection and
`gpt-5.4-2026-03-05` for leadership narrative. `OPENAI_MAX_REQUEST_COST_USD=1.00` fails closed before
either request when its conservative maximum would exceed policy, so the two-role run is capped at
$2. Actual token counts and list-price estimates are retained in the governed task audit. Model
pricing is pinned in code and an unpriced model cannot run while the cost guard is enabled.
The output ceiling is 8,000 tokens so the full multi-section leadership contract can complete; the
cost guard evaluates that ceiling before each request and remains authoritative.

The production acceptance command operates on a previously persisted full-source result, writes a
temporary content-addressed HTML artifact, and returns a short-lived private download URL. It does
not publish or mutate the source result, call a retailer, or enable AI for normal worker jobs:

```bash
rci-narrative-bakeoff \
  --analysis-id <full-source-analysis-id> \
  --max-request-cost-usd 1.00 \
  --confirm-paid-call
```

The explicit confirmation flag is mandatory. The command fails closed if authoritative metrics
change, the governed critic rejects the narrative, the result contract fails, model pricing is
unknown, or a request would breach its cap.

## Acceptance criteria

Phase 9.6 is ready for production acceptance when:

- all five Product Packs load with narrative playbooks and no category branches in core code;
- every generated semantic brief validates and is reproducible from the same immutable result;
- every quantitative model statement resolves to an authoritative stored metric;
- omitted topics, undeclared references, thin prose, and unsupported numbers fail closed;
- deterministic fallback reports remain complete and useful with AI disabled;
- the five numerical golden suites remain unchanged;
- HTML, email, XLSX, and web views project the same narrative contract; and
- a capped model bake-off demonstrates material quality parity against the supplied benchmarks.
