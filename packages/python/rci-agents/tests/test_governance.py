from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rci_agents import (
    AgentCostLimitError,
    AgentGovernanceError,
    AnalysisBriefBuilder,
    GovernedAnalysisAssistant,
    GovernedOutputBuilder,
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
            sections.append(
                {
                    "id": requested["id"],
                    "body_template": body,
                    "topic_refs": list(requested["required_topics"]),
                    "storyline_refs": list(requested["storyline_refs"][:1]),
                    "metric_refs": refs,
                    "evidence_refs": ["model-cannot-select-evidence"],
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


def test_governed_product_placeholders_preserve_exact_pdp_identity_and_zip() -> None:
    renderer = MetricCitationRenderer(
        [{"metric_id": "gap", "value": -0.22, "unit": "USD_per_package"}]
    )
    rendered, claims = renderer.render(
        "{{product:product-a|benchmark_name}} needs attention in "
        "{{product:product-a|locations}} because ALDI is typically "
        "{{metric:gap|currency_abs_2}} cheaper.",
        allowed_metric_refs={"gap"},
        allowed_product_refs={"product-a"},
        products={
            "product-a": {
                "benchmark_name": "All Natural 80/20 Ground Beef, 1 lb",
                "locations": "ZIP 72712",
            }
        },
    )

    assert "All Natural 80/20 Ground Beef, 1 lb" in rendered
    assert "ZIP 72712" in rendered
    assert "$0.22 cheaper" in rendered
    assert claims == [{"metric_ref": "gap", "rendered_value": "$0.22", "format": "currency_abs_2"}]


def test_structured_narrative_renders_headline_bullets_action_and_product() -> None:
    builder = GovernedOutputBuilder(REPOSITORY_ROOT)
    result = builder.narrative_result(
        {
            "sections": [
                {
                    "id": "executive_summary",
                    "headline_template": "Focus the first move on the clearest product loss",
                    "subtitle_template": (
                        "{{product:product-a|benchmark_name}} is the most actionable item in the "
                        "governed product evidence."
                    ),
                    "bullet_templates": [
                        "ALDI is typically {{metric:gap|currency_abs_2}} cheaper in the cited "
                        "comparable observations.",
                        "The evidence is concentrated in {{product:product-a|locations}}, so the "
                        "decision can remain targeted rather than category wide.",
                    ],
                    "implication_template": (
                        "Review the opening price point for {{product:product-a|benchmark_name}} "
                        "in the cited locations and monitor the same comparison after the test."
                    ),
                    "topic_refs": ["exact_price", "actions"],
                    "storyline_refs": ["story.action"],
                    "product_refs": ["product-a"],
                    "metric_refs": ["gap"],
                }
            ]
        },
        [
            {
                "id": "executive_summary",
                "heading": "Executive Summary",
                "required_topics": ["exact_price", "actions"],
                "storyline_refs": ["story.action"],
                "required_storyline_refs": ["story.action"],
                "allowed_metric_refs": ["gap"],
                "allowed_evidence_refs": ["evidence.exact"],
                "allowed_product_refs": ["product-a"],
            }
        ],
        [
            {
                "metric_id": "gap",
                "value": -0.22,
                "unit": "USD_per_package",
                "evidence_refs": ["evidence.exact"],
            }
        ],
        {"evidence.exact"},
        [{"id": "story.action", "headline": "Target the opening price point"}],
        [
            {
                "id": "product-a",
                "benchmark_name": "All Natural 80/20 Ground Beef, 1 lb",
                "competitor_name": "Fresh 80/20 Ground Beef, 1 lb",
                "locations": "ZIP 72712",
            }
        ],
    )

    section = result["sections"][0]
    assert section["heading"] == "Focus the first move on the clearest product loss"
    assert len(section["bullets"]) == 2
    assert "$0.22 cheaper" in section["bullets"][0]
    assert "All Natural 80/20 Ground Beef, 1 lb" in section["implication"]
    envelope = _document("examples/agent-output.ground-beef-insight.json")
    envelope["role"] = "narrative"
    prompt_template = envelope["prompt_template"]
    assert isinstance(prompt_template, dict)
    prompt_template["id"] = "governed_narrative"
    envelope["result"] = result
    envelope["evidence_refs"] = ["evidence.exact"]
    validate_instance(
        REPOSITORY_ROOT,
        "agent-output.schema.json",
        envelope,
        label="structured narrative output",
    )


@pytest.mark.parametrize(
    "prose",
    [
        "The signed median gap requires action.",
        "Use ALDI response for this segment.",
        "Treat ALDI response for the priority item.",
    ],
)
def test_narrative_critic_rejects_unclear_merchant_jargon(prose: str) -> None:
    with pytest.raises(AgentGovernanceError, match="unclear merchant jargon"):
        NarrativeQualityCritic.validate_prose(prose)


@pytest.mark.parametrize(
    ("position", "prose"),
    [
        (
            "attention",
            "Walmart also wins the named pack {{product:pair-1|benchmark_name}}.",
        ),
        (
            "protect",
            "ALDI wins the named pack {{product:pair-1|benchmark_name}}.",
        ),
    ],
)
def test_narrative_critic_rejects_product_direction_reversal(
    position: str,
    prose: str,
) -> None:
    with pytest.raises(AgentGovernanceError, match=r"reverses .* product direction"):
        NarrativeQualityCritic.validate_product_direction(prose, {"pair-1": position})


def test_narrative_critic_allows_aggregate_product_distinction() -> None:
    NarrativeQualityCritic.validate_product_direction(
        "ALDI wins the visible price on {{product:pair-1|benchmark_name}}, but Walmart is lower "
        "across the broader segment.",
        {"pair-1": "attention"},
    )


def test_metric_citations_accept_only_source_backed_numeric_descriptors() -> None:
    renderer = MetricCitationRenderer([])

    body, claims = renderer.render(
        "Keep the 80/20 segment on the merchant watchlist.",
        allowed_metric_refs=set(),
        trusted_numeric_literals={"80", "20"},
    )

    assert body == "Keep the 80/20 segment on the merchant watchlist."
    assert claims == []
    with pytest.raises(AgentGovernanceError, match=r"unsupported numeric literals.*85"):
        renderer.render(
            "Keep the 85/15 segment on the merchant watchlist.",
            allowed_metric_refs=set(),
            trusted_numeric_literals={"80", "20"},
        )


def test_insight_builder_carries_source_numeric_descriptors_into_governed_copy() -> None:
    builder = GovernedOutputBuilder(REPOSITORY_ROOT)
    candidate = {
        "id": "lean-ratio-segment",
        "title": "The 80/20 segment needs attention",
        "summary": "The 80/20 segment is a governed product descriptor.",
        "severity": "high",
        "business_impact": "Protect the 80/20 segment.",
        "metric_refs": [],
        "evidence_refs": [],
        "confidence": "high",
    }

    result = builder.insight_result(
        {
            "insights": [
                {
                    "id": "lean-ratio-segment",
                    "title": "The 80/20 segment needs a focused response",
                    "summary": "Keep the 80/20 segment on the merchant watchlist.",
                    "business_impact": "Protect the 80/20 segment.",
                }
            ]
        },
        [candidate],
        [],
    )

    assert result["insights"][0]["title"].startswith("The 80/20 segment")
    with pytest.raises(AgentGovernanceError, match=r"unsupported numeric literals.*85"):
        builder.insight_result(
            {
                "insights": [
                    {
                        "id": "lean-ratio-segment",
                        "title": "The 85/15 segment needs a focused response",
                        "summary": "Keep the cited segment on the merchant watchlist.",
                        "business_impact": "Protect the cited segment.",
                    }
                ]
            },
            [candidate],
            [],
        )


def test_insight_builder_humanizes_explicit_percent_descriptors_without_changing_digits() -> None:
    builder = GovernedOutputBuilder(REPOSITORY_ROOT)
    candidate = {
        "id": "lean-ratio-segment",
        "title": "Lean Pct: 80 / Fat Pct: 20",
        "summary": "The source explicitly declares both fields as percentages.",
        "severity": "high",
        "business_impact": "Protect the governed product segment.",
        "metric_refs": [],
        "evidence_refs": [],
        "confidence": "high",
    }

    result = builder.insight_result(
        {
            "insights": [
                {
                    "id": "lean-ratio-segment",
                    "title": "The 80% lean / 20% fat segment needs attention",
                    "summary": "Keep the governed segment on the merchant watchlist.",
                    "business_impact": "Protect the governed product segment.",
                }
            ]
        },
        [candidate],
        [],
    )

    assert result["insights"][0]["title"].startswith("The 80% lean / 20% fat segment")


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
    assert len(brief_metric_ids) <= 360
    assert set(first["required_topics"]) <= covered_topics


def test_analysis_brief_preserves_configured_priorities_and_cross_profile_reversals() -> None:
    result = _document("examples/analysis-result-v2.ground-beef.json")
    result["comparison_modes"].extend(
        [
            {
                "profile_id": "strict",
                "label": "Strict same-ZIP and exact-package comparison",
                "geography": "exact_zip",
                "comparison_metric": "package_price",
                "dimensions": [
                    "lean_pct",
                    "fat_pct",
                    "weight_lb",
                    "organic",
                    "grass_fed",
                    "premium_tier",
                ],
            },
            {
                "profile_id": "unit_price",
                "label": "Best available price per pound",
                "geography": "exact_zip",
                "comparison_metric": "price_per_lb",
                "dimensions": [
                    "lean_pct",
                    "fat_pct",
                    "organic",
                    "grass_fed",
                    "premium_tier",
                ],
            },
        ]
    )
    result["segments"].extend(
        [
            {
                "segment_id": "exact-80-20-225",
                "label": "80/20 conventional — 2.25 lb",
                "attributes": {
                    "lean_pct": 80,
                    "fat_pct": 20,
                    "weight_lb": 2.25,
                    "organic": False,
                    "grass_fed": False,
                    "premium_tier": "standard",
                },
                "metric_refs": [],
                "evidence_refs": ["evidence-exact-aldi"],
            },
            {
                "segment_id": "normalized-80-20",
                "label": "80/20 conventional",
                "attributes": {
                    "lean_pct": 80,
                    "fat_pct": 20,
                    "organic": False,
                    "grass_fed": False,
                    "premium_tier": "standard",
                },
                "metric_refs": [],
                "evidence_refs": ["evidence-exact-aldi"],
            },
        ]
    )

    def add_comparison(
        comparison_id: str,
        profile_id: str,
        segment_id: str,
        values: dict[str, float],
    ) -> None:
        refs = []
        for field, value in values.items():
            metric_id = f"comparison.aldi_us.{profile_id}.{segment_id}.{field}"
            result["metrics"].append(
                {
                    "metric_id": metric_id,
                    "name": f"ALDI {field}",
                    "value": value,
                    "unit": "rate" if field.endswith("_rate") else "matches",
                    "method": "deterministic test fixture",
                    "source": "deterministic",
                    "evidence_refs": ["evidence-exact-aldi"],
                }
            )
            refs.append(metric_id)
        result["comparisons"].append(
            {
                "comparison_id": comparison_id,
                "competitor_id": "aldi_us",
                "profile_id": profile_id,
                "segment_id": segment_id,
                "metric_refs": refs,
                "evidence_refs": ["evidence-exact-aldi"],
            }
        )

    add_comparison(
        "aldi-exact-80-20-225",
        "strict",
        "exact-80-20-225",
        {"matches": 1456, "benchmark_lower_rate": 0.0, "competitor_lower_rate": 1.0},
    )
    add_comparison(
        "aldi-normalized-80-20",
        "unit_price",
        "normalized-80-20",
        {"matches": 1438, "benchmark_lower_rate": 0.861, "competitor_lower_rate": 0.139},
    )
    product_pack = _document("product-packs/fresh_ground_beef.json")
    blueprint = _document("report-blueprints/fresh_ground_beef_leadership.json")

    brief = AnalysisBriefBuilder(REPOSITORY_ROOT).build(
        result,
        product_pack=product_pack,
        report_blueprint=blueprint,
    )

    storyline_ids = {str(row["id"]) for row in brief["storylines"]}
    assert "story.priority.aldi_80_20_package_reversal" in storyline_ids
    assert any(value.startswith("story.reversal.aldi_us") for value in storyline_ids)
    executive = next(row for row in brief["requested_sections"] if row["id"] == "executive_summary")
    assert "story.priority.aldi_80_20_package_reversal" in executive["required_storyline_refs"]
    assert "_attributes" not in json.dumps(brief)


def test_analysis_brief_uses_merchant_facing_retailer_and_segment_names() -> None:
    result = _document("examples/analysis-result-v2.ground-beef.json")
    result["comparisons"].append(
        {
            **result["comparisons"][0],
            "comparison_id": "aldi-organic-segment",
            "segment_id": "organic_grass_fed_85_15_1lb",
        }
    )
    product_pack = _document("product-packs/fresh_ground_beef.json")
    blueprint = _document("report-blueprints/fresh_ground_beef_leadership.json")
    brief = AnalysisBriefBuilder(REPOSITORY_ROOT).build(
        result,
        product_pack=product_pack,
        report_blueprint=blueprint,
    )

    text = " ".join(
        f"{storyline['headline']} {storyline['interpretation']}"
        for storyline in brief["storylines"]
    )
    assert "aldi_us" not in text
    assert "amazon_us_same_day" not in text
    assert "ALDI" in text
    comparison_labels = [
        str(fact["label"]) for fact in brief["facts"] if str(fact["kind"]).startswith("comparison")
    ]
    assert any("85% lean · 1 lb · organic · grass fed" in label for label in comparison_labels)

    model_view = AnalysisBriefBuilder(REPOSITORY_ROOT).model_view(brief)
    model_text = json.dumps(model_view, ensure_ascii=False)
    assert "aldi_us" not in model_text
    assert "amazon_us_same_day" not in model_text
    assert '"fact_refs"' not in model_text


def test_narrative_critic_rejects_machine_oriented_labels() -> None:
    with pytest.raises(AgentGovernanceError, match="machine-oriented"):
        NarrativeQualityCritic.validate_prose(
            "Prioritize aldi_us losses in Lean Pct: eighty and Organic: False."
        )
    NarrativeQualityCritic.validate_prose(
        "ALDI is lower in "
        "{{metric:comparison.aldi_us.exact.package_price.lower_rate|percent_1}} "
        "of governed comparisons."
    )
    NarrativeQualityCritic.validate_prose(
        "The merchant decision differs for grass fed: protect the premium tier while "
        "monitoring conventional value."
    )
    with pytest.raises(AgentGovernanceError, match="machine-oriented"):
        NarrativeQualityCritic.validate_prose("The raw flag is Grass Fed: True.")


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


def test_narrative_critic_rejects_omitted_configured_priority() -> None:
    requested = {
        "executive_summary": {
            "required_topics": ["data_scope"],
            "storyline_refs": ["story.scope", "story.priority"],
            "required_storyline_refs": ["story.priority"],
        }
    }
    rows = [
        {
            "id": "executive_summary",
            "body_template": (
                "The governed scope is complete, but this intentionally long leadership "
                "summary omits the configured merchant-priority storyline. It remains long "
                "enough to prove that required strategic coverage, rather than character "
                "count alone, controls acceptance of the result."
            ),
            "topic_refs": ["data_scope"],
            "storyline_refs": ["story.scope"],
        }
    ]

    with pytest.raises(AgentGovernanceError, match="omits required storylines"):
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
    assert "model-cannot-select-evidence" not in executive_summary["evidence_refs"]
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
        {
            "analysis_id": "analysis-1",
            "deterministic_insights": [{"id": "known-insight"}],
        },
        model_id="explicit-test-model",
    )

    assert endpoint.kwargs["model"] == "explicit-test-model"
    assert endpoint.kwargs["store"] is False
    assert endpoint.kwargs["max_output_tokens"] == 321
    assert endpoint.kwargs["reasoning"] == {"effort": "high"}
    assert endpoint.kwargs["text"]["verbosity"] == "high"
    response_format = endpoint.kwargs["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    assert response_format["schema"]["additionalProperties"] is False
    insight_schema = response_format["schema"]["properties"]["insights"]["items"]["anyOf"][0]
    insight_id = insight_schema["properties"]["id"]
    assert insight_id["enum"] == ["known-insight"]
    governed_pattern = insight_schema["properties"]["title"]["pattern"]
    assert re.fullmatch(governed_pattern, "Leadership action is required")
    assert re.fullmatch(governed_pattern, "Leadership action 3 is required") is None
    assert re.fullmatch(
        governed_pattern,
        "Gap is {{metric:segment-3.median_gap|currency_2}}",
    )
    assert response.input_tokens == 17
    assert response.output_tokens == 9


async def test_narrative_response_schema_uses_supported_keywords_and_known_section_ids() -> None:
    endpoint = FakeResponsesEndpoint()
    endpoint_output = {
        "sections": [
            {
                "id": "executive_summary",
                "body_template": "Evidence-backed leadership narrative.",
                "topic_refs": ["data_scope"],
                "storyline_refs": ["story.scope"],
                "metric_refs": ["source.total_rows"],
            }
        ]
    }

    async def create(**kwargs: Any) -> object:
        endpoint.kwargs = kwargs
        return SimpleNamespace(
            output_text=json.dumps(endpoint_output),
            usage=SimpleNamespace(input_tokens=17, output_tokens=9),
        )

    endpoint.create = create  # type: ignore[method-assign]
    provider = OpenAIResponsesProvider(
        api_key="test-only-key",
        timeout_seconds=10,
        max_output_tokens=321,
    )
    provider._client = SimpleNamespace(responses=endpoint)  # type: ignore[attr-defined]
    prompt = PromptTemplateLoader(REPOSITORY_ROOT).load("governed_narrative")

    await provider.generate(
        prompt,
        {
            "analysis_id": "analysis-1",
            "requested_sections": [
                {
                    "id": "executive_summary",
                    "required_topics": ["data_scope"],
                    "storyline_refs": ["story.scope"],
                    "allowed_metric_refs": ["source.total_rows"],
                    "allowed_evidence_refs": ["evidence.source"],
                }
            ],
        },
        model_id="explicit-test-model",
    )

    schema = endpoint.kwargs["text"]["format"]["schema"]
    item_schema = schema["properties"]["sections"]["items"]["anyOf"][0]
    assert item_schema["properties"]["id"]["enum"] == ["executive_summary"]
    assert item_schema["properties"]["topic_refs"]["items"]["enum"] == ["data_scope"]
    assert item_schema["properties"]["storyline_refs"]["items"]["enum"] == ["story.scope"]
    assert item_schema["properties"]["metric_refs"]["items"]["enum"] == ["source.total_rows"]
    assert "evidence_refs" not in item_schema["properties"]
    assert "evidence_refs" not in item_schema["required"]
    assert "uniqueItems" not in json.dumps(schema)


async def test_openai_provider_records_pinned_cost_and_rejects_over_budget_request() -> None:
    endpoint = FakeResponsesEndpoint()
    provider = OpenAIResponsesProvider(
        api_key="test-only-key",
        timeout_seconds=10,
        max_output_tokens=321,
        max_request_cost_usd=1,
    )
    provider._client = SimpleNamespace(responses=endpoint)  # type: ignore[attr-defined]
    prompt = PromptTemplateLoader(REPOSITORY_ROOT).load("governed_insight")

    response = await provider.generate(
        prompt,
        {"analysis_id": "analysis-1"},
        model_id="gpt-5.4-mini-2026-03-17",
    )

    assert response.estimated_cost_usd == pytest.approx(0.00005325)

    sol_response = await provider.generate(
        prompt,
        {"analysis_id": "analysis-1"},
        model_id="gpt-5.6-sol",
    )
    assert sol_response.estimated_cost_usd == pytest.approx(0.000355)

    blocked_endpoint = FakeResponsesEndpoint()
    blocked = OpenAIResponsesProvider(
        api_key="test-only-key",
        timeout_seconds=10,
        max_output_tokens=3_000,
        max_request_cost_usd=0.000001,
    )
    blocked._client = SimpleNamespace(responses=blocked_endpoint)  # type: ignore[attr-defined]
    with pytest.raises(AgentCostLimitError, match="exceeds"):
        await blocked.generate(
            prompt,
            {"analysis_id": "analysis-1"},
            model_id="gpt-5.4-mini-2026-03-17",
        )
    assert blocked_endpoint.kwargs == {}


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
