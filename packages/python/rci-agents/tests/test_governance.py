from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rci_agents import (
    AgentGovernanceError,
    AnalysisBriefBuilder,
    GovernedAnalysisAssistant,
    InMemoryAgentTaskRepository,
    MetricCitationRenderer,
    OpenAIResponsesProvider,
    PromptTemplateLoader,
    ProviderResponse,
)
from rci_agents.governance import NarrativeQualityCritic, canonical_bytes

from rci_contracts import validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class FakeProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(self, prompt, payload, *, model_id):  # type: ignore[no-untyped-def]
        self.calls.append(prompt.role)
        if prompt.role == "insight":
            return ProviderResponse(
                result={
                    "insights": [
                        {
                            "id": "aldi-segmented-pressure",
                            "title": "ALDI pressure warrants a focused response",
                            "summary": (
                                "ALDI is lower in "
                                "{{metric:aldi-competitor-lower-rate|percent_1}} of exact matches."
                            ),
                            "business_impact": (
                                "A targeted response protects stronger positions elsewhere."
                            ),
                        }
                    ]
                },
                input_tokens=300,
                output_tokens=90,
            )
        metrics = {str(row["metric_id"]): row for row in payload["metrics"]}
        sections = []
        for requested in payload["requested_sections"]:
            allowed = list(requested["allowed_metric_refs"])
            if requested["id"] == "executive_summary" and {
                "aldi-competitor-lower-rate",
                "amazon-walmart-lower-rate",
            }.issubset(allowed):
                refs = ["aldi-competitor-lower-rate", "amazon-walmart-lower-rate"]
                body = (
                    "ALDI is lower in "
                    "{{metric:aldi-competitor-lower-rate|percent_1}} of exact matches, "
                    "while Walmart is lower in "
                    "{{metric:amazon-walmart-lower-rate|percent_1}} versus Amazon, which "
                    "supports separate competitor-specific actions."
                )
            elif (
                requested["id"] == "recommendations"
                and "metric-aldi-organic-85-15-gap-per-lb" in allowed
            ):
                refs = ["metric-aldi-organic-85-15-gap-per-lb"]
                body = (
                    "Prioritize the segment with a median gap of "
                    "{{metric:metric-aldi-organic-85-15-gap-per-lb|currency_2}} and "
                    "keep the response bounded to the cited product specification."
                )
            else:
                refs = allowed[:1]
                metric = metrics[refs[0]]
                format_name = _format_name(metric)
                body = (
                    "The governed evidence for this section is anchored in "
                    f"{{{{metric:{refs[0]}|{format_name}}}}}; interpret it only within "
                    "the cited comparison mode and Product Pack guardrails."
                )
            evidence_refs = list(
                dict.fromkeys(
                    str(evidence) for ref in refs for evidence in metrics[ref]["evidence_refs"]
                )
            )
            sections.append(
                {
                    "id": requested["id"],
                    "body_template": body,
                    "topic_refs": list(requested["required_topics"]),
                    "storyline_refs": list(requested["storyline_refs"][:1]),
                    "metric_refs": refs,
                    "evidence_refs": evidence_refs[:1],
                }
            )
        return ProviderResponse(
            result={"sections": sections},
            input_tokens=450,
            output_tokens=140,
        )


class InvalidNumericProvider:
    provider_id = "fake-invalid"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate(self, prompt, payload, *, model_id):  # type: ignore[no-untyped-def]
        self.calls.append(prompt.role)
        if prompt.role == "insight":
            return ProviderResponse(
                result={
                    "insights": [
                        {
                            "id": "aldi-segmented-pressure",
                            "title": "ALDI pressure warrants a focused response",
                            "summary": "ALDI is lower in 84.1% of exact matches.",
                            "business_impact": "A targeted response protects stronger positions.",
                        }
                    ]
                }
            )
        metrics = {str(row["metric_id"]): row for row in payload["metrics"]}
        sections = []
        for requested in payload["requested_sections"]:
            refs = list(requested["allowed_metric_refs"][:1])
            body = (
                "Walmart leads by 12.5% in the cited evidence and leadership should act "
                "on that unsupported direct numeric claim."
                if requested["id"] == "executive_summary"
                else (
                    "This section remains grounded in the requested evidence but is long "
                    "enough to reach the structural quality check."
                )
            )
            sections.append(
                {
                    "id": requested["id"],
                    "body_template": body,
                    "topic_refs": list(requested["required_topics"]),
                    "storyline_refs": list(requested["storyline_refs"][:1]),
                    "metric_refs": refs,
                    "evidence_refs": list(metrics[refs[0]]["evidence_refs"][:1]),
                }
            )
        return ProviderResponse(result={"sections": sections})


def _format_name(metric: dict[str, object]) -> str:
    unit = str(metric["unit"])
    value = float(metric["value"])
    if unit == "rate":
        return "percent_1"
    if unit.startswith("USD"):
        return "currency_2"
    return "integer" if value.is_integer() else "decimal_2"


class FakeResponsesEndpoint:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            output_text=json.dumps({"insights": []}),
            usage=SimpleNamespace(input_tokens=17, output_tokens=9),
        )


def _document(path: str) -> dict[str, object]:
    return json.loads((REPOSITORY_ROOT / path).read_text())


def test_metric_citations_reject_direct_numbers_and_unknown_metrics() -> None:
    renderer = MetricCitationRenderer(
        [
            {
                "metric_id": "win-rate",
                "value": 0.8414,
                "unit": "rate",
            }
        ]
    )
    with pytest.raises(AgentGovernanceError, match="unsupported numeric literals"):
        renderer.render("The rate is 84.1%.", allowed_metric_refs={"win-rate"})
    with pytest.raises(AgentGovernanceError, match="undeclared metric"):
        renderer.render(
            "The rate is {{metric:win-rate|percent_1}}.",
            allowed_metric_refs={"another-rate"},
        )


def test_storyline_placeholder_preserves_governed_numeric_product_descriptors() -> None:
    renderer = MetricCitationRenderer([])

    body, claims = renderer.render(
        "{{storyline:story.segment|headline}} Protect the cited segment.",
        allowed_metric_refs=set(),
        allowed_storyline_refs={"story.segment"},
        storylines={
            "story.segment": {
                "id": "story.segment",
                "headline": "The 85/15 organic one-pound segment is the priority watchlist.",
            }
        },
    )

    assert body.startswith("The 85/15 organic one-pound segment")
    assert claims == []
    with pytest.raises(AgentGovernanceError, match="unsupported numeric literals"):
        renderer.render(
            "The 85/15 segment is the priority watchlist.",
            allowed_metric_refs=set(),
            allowed_storyline_refs={"story.segment"},
            storylines={},
        )


def test_analysis_brief_is_deterministic_complete_and_evidence_bounded() -> None:
    result = _document("examples/analysis-result-v2.ground-beef.json")
    product_pack = _document("product-packs/fresh_ground_beef.json")
    blueprint = _document("report-blueprints/fresh_ground_beef_leadership.json")
    builder = AnalysisBriefBuilder(REPOSITORY_ROOT)

    first = builder.build(
        result,
        product_pack=product_pack,
        report_blueprint=blueprint,
    )
    second = builder.build(
        result,
        product_pack=product_pack,
        report_blueprint=blueprint,
    )

    assert first == second
    metric_ids = {str(metric["metric_id"]) for metric in result["metrics"]}
    evidence_ids = {str(evidence["evidence_set_id"]) for evidence in result["evidence_sets"]}
    brief_metric_ids = {str(ref) for fact in first["facts"] for ref in fact["metric_refs"]}
    brief_evidence_ids = {str(ref) for fact in first["facts"] for ref in fact["evidence_refs"]}
    covered_topics = {
        str(topic)
        for section in first["requested_sections"]
        for topic in section["required_topics"]
    }
    assert brief_metric_ids <= metric_ids
    assert brief_evidence_ids <= evidence_ids
    assert len(brief_metric_ids) <= 160
    assert set(first["required_topics"]) <= covered_topics


def test_narrative_critic_rejects_omitted_required_topic() -> None:
    requested = {
        "executive_summary": {
            "required_topics": ["data_scope", "actions"],
            "storyline_refs": ["story.scope"],
        }
    }
    rows = [
        {
            "id": "executive_summary",
            "body_template": (
                "This otherwise complete leadership summary remains grounded in its "
                "declared storyline and evidence references."
            ),
            "topic_refs": ["data_scope"],
            "storyline_refs": ["story.scope"],
        }
    ]

    with pytest.raises(AgentGovernanceError, match="omits required topics"):
        NarrativeQualityCritic().validate(rows, requested)


async def test_governed_assistant_adds_interpretation_without_mutating_metrics() -> None:
    result = _document("examples/analysis-result-v2.ground-beef.json")
    product_pack = _document("product-packs/fresh_ground_beef.json")
    blueprint = _document("report-blueprints/fresh_ground_beef_leadership.json")
    original_metrics = canonical_bytes(result["metrics"])
    provider = FakeProvider()
    repository = InMemoryAgentTaskRepository()
    assistant = GovernedAnalysisAssistant(
        repository_root=REPOSITORY_ROOT,
        provider=provider,
        repository=repository,
        worker_id="test-worker",
        insight_model="test-insight-model",
        narrative_model="test-narrative-model",
    )

    enriched = await assistant.enrich(
        deepcopy(result),
        product_pack=product_pack,
        report_blueprint=blueprint,
    )

    assert provider.calls == ["insight", "narrative"]
    assert canonical_bytes(enriched["metrics"]) == original_metrics
    assert enriched["insights"][0]["generated_by"] == "ai_assisted"
    assert "84.1%" in enriched["insights"][0]["summary"]
    assert enriched["narratives"]["generation_mode"] == "ai_assisted"
    executive_summary = next(
        section
        for section in enriched["narratives"]["sections"]
        if section["id"] == "executive_summary"
    )
    assert "while Walmart is lower" in executive_summary["body"]
    assert len(enriched["narratives"]["agent_task_ids"]) == 2
    assert enriched["validation"]["unsupported_numeric_claims"] == 0
    assert enriched["validation"]["metric_reference_coverage"] == 1
    assert (
        enriched["provenance"]["deterministic_result_checksum_sha256"]
        == (result["provenance"]["deterministic_result_checksum_sha256"])
    )
    validate_instance(
        REPOSITORY_ROOT,
        "analysis-result-v2.schema.json",
        enriched,
        label="AI-assisted AnalysisResult",
    )


async def test_identical_governed_task_reuses_audited_output() -> None:
    result = _document("examples/analysis-result-v2.ground-beef.json")
    product_pack = _document("product-packs/fresh_ground_beef.json")
    blueprint = _document("report-blueprints/fresh_ground_beef_leadership.json")
    provider = FakeProvider()
    assistant = GovernedAnalysisAssistant(
        repository_root=REPOSITORY_ROOT,
        provider=provider,
        repository=InMemoryAgentTaskRepository(),
        worker_id="test-worker",
        insight_model="test-insight-model",
        narrative_model="test-narrative-model",
    )

    first = await assistant.enrich(
        deepcopy(result), product_pack=product_pack, report_blueprint=blueprint
    )
    second = await assistant.enrich(
        deepcopy(result), product_pack=product_pack, report_blueprint=blueprint
    )

    assert provider.calls == ["insight", "narrative"]
    assert first["insights"] == second["insights"]
    assert first["narratives"] == second["narratives"]


async def test_openai_provider_uses_strict_ephemeral_structured_output() -> None:
    endpoint = FakeResponsesEndpoint()
    provider = OpenAIResponsesProvider(
        api_key="test-only-key",
        timeout_seconds=10,
        max_output_tokens=321,
    )
    assert provider._client.max_retries == 0  # type: ignore[attr-defined]
    provider._client = SimpleNamespace(responses=endpoint)  # type: ignore[attr-defined]
    prompt = PromptTemplateLoader(REPOSITORY_ROOT).load("governed_insight")

    response = await provider.generate(
        prompt,
        {"analysis_id": "analysis-1"},
        model_id="explicit-test-model",
    )

    assert endpoint.kwargs["model"] == "explicit-test-model"
    assert endpoint.kwargs["store"] is False
    assert endpoint.kwargs["max_output_tokens"] == 321
    response_format = endpoint.kwargs["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    assert response_format["schema"]["additionalProperties"] is False
    assert response.input_tokens == 17
    assert response.output_tokens == 9


async def test_invalid_model_numbers_leave_deterministic_result_unchanged() -> None:
    result = _document("examples/analysis-result-v2.ground-beef.json")
    product_pack = _document("product-packs/fresh_ground_beef.json")
    blueprint = _document("report-blueprints/fresh_ground_beef_leadership.json")
    provider = InvalidNumericProvider()
    assistant = GovernedAnalysisAssistant(
        repository_root=REPOSITORY_ROOT,
        provider=provider,
        repository=InMemoryAgentTaskRepository(),
        worker_id="test-worker",
        insight_model="test-insight-model",
        narrative_model="test-narrative-model",
    )

    enriched = await assistant.enrich(
        deepcopy(result), product_pack=product_pack, report_blueprint=blueprint
    )

    assert provider.calls == ["insight", "narrative"]
    assert enriched == result
