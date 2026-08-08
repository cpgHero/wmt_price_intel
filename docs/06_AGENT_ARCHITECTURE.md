# AI Agent Architecture

AI is a bounded reasoning layer around deterministic analytics, not the source of truth.

## 1. Classification Fallback Agent
Input: Product Pack, title, URL, brand, provider fields, deterministic extraction result.
Output: structured attribute proposal + include/exclude + confidence + evidence snippets.
Authority: may fill unresolved fields only when schema/rules allow. Does not calculate price metrics.

## 2. Comparison QA Agent
Input: suspicious match pairs and already-computed evidence.
Output: approve/reject/review recommendation with reason such as unit mismatch, specialty mismatch, likely search noise, or ambiguous package size.
Authority: cannot alter price; accepted actions are explicit review decisions persisted separately.

## 3. Insight Agent
Input: validated segment metrics, coverage metrics, QA summary, and evidence references.
Output: ranked findings with breadth, magnitude, confidence, and suggested action.
Authority: narrative interpretation only.

## 4. Narrative/Report Agent
Input: immutable AnalysisResult.
Output: leadership summary/email/report prose.
Authority: must cite existing metrics; cannot create new authoritative statistics.

## Governance

Store model identifier, prompt version, schema version, input checksum, output, confidence, latency, and token/cost metadata. AI output that changes classification/match state must be traceable and reversible.

## Feature flag

`AI_ENABLED` and per-definition `enable_ai_fallback` allow deterministic-only operation. Human review remains the safe fallback.
