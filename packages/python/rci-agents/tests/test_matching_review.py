from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rci_agents import OpenAIMatchingReviewProvider, load_matching_review_prompt

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class FakeResponsesEndpoint:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            output_text=json.dumps(self.result),
            usage=SimpleNamespace(input_tokens=200, output_tokens=80),
        )


def _case(*, coverage: float = 0.5) -> dict[str, Any]:
    return {
        "case_id": "case-1",
        "benchmark_listing": {
            "retailer_id": "walmart_us",
            "image_url": "https://example.com/walmart.jpg",
        },
        "competitor_listing": {
            "retailer_id": "aldi_us",
            "image_url": "https://example.com/aldi.jpg",
        },
        "engine_proposal": {"evidence_coverage": {"critical_coverage": coverage}},
        "edge": {
            "attribute_evidence": [
                {
                    "attribute": "fat_content",
                    "benchmark_value": "2%",
                    "competitor_value": None,
                    "outcome": "unknown",
                }
            ]
        },
    }


async def test_matching_review_is_ephemeral_structured_and_human_gated() -> None:
    endpoint = FakeResponsesEndpoint(
        {
            "verdict_proposal": "insufficient_evidence",
            "tier_proposal": None,
            "rationale": "The competitor fat content needs human confirmation.",
            "attribute_proposals": [
                {
                    "attribute": "fat_content",
                    "value": "2%",
                    "evidence_source": "image",
                    "confidence": 0.91,
                    "visible_text": "2% Reduced Fat Milk",
                    "source_image_url": "https://example.com/aldi.jpg",
                }
            ],
            "conflicts": [],
            "requires_human_review": True,
        }
    )
    provider = OpenAIMatchingReviewProvider(
        api_key="test-key",
        timeout_seconds=10,
        max_output_tokens=1000,
        max_request_cost_usd=1,
        client=SimpleNamespace(responses=endpoint),
    )

    response = await provider.generate(
        load_matching_review_prompt(REPOSITORY_ROOT),
        _case(),
        model_id="gpt-5.6-terra",
    )

    assert response.result["requires_human_review"] is True
    assert endpoint.kwargs["store"] is False
    assert endpoint.kwargs["text"]["format"]["strict"] is True
    result_schema = endpoint.kwargs["text"]["format"]["schema"]
    assert result_schema["properties"]["verdict_proposal"]["type"] == "string"
    assert result_schema["properties"]["tier_proposal"]["anyOf"][0]["type"] == "string"
    assert result_schema["properties"]["requires_human_review"] == {
        "type": "boolean",
        "const": True,
    }
    content = endpoint.kwargs["input"][0]["content"]
    assert [item["type"] for item in content] == [
        "input_text",
        "input_image",
        "input_image",
    ]


async def test_matching_review_rejects_uncited_image_claim() -> None:
    endpoint = FakeResponsesEndpoint(
        {
            "verdict_proposal": "comparable",
            "tier_proposal": "equivalent_product",
            "rationale": "The products appear compatible.",
            "attribute_proposals": [
                {
                    "attribute": "fat_content",
                    "value": "2%",
                    "evidence_source": "image",
                    "confidence": 0.91,
                    "visible_text": None,
                    "source_image_url": "https://example.com/aldi.jpg",
                }
            ],
            "conflicts": [],
            "requires_human_review": True,
        }
    )
    provider = OpenAIMatchingReviewProvider(
        api_key="test-key",
        timeout_seconds=10,
        max_output_tokens=1000,
        max_request_cost_usd=1,
        client=SimpleNamespace(responses=endpoint),
    )

    with pytest.raises(ValueError, match="visible evidence"):
        await provider.generate(
            load_matching_review_prompt(REPOSITORY_ROOT),
            _case(),
            model_id="gpt-5.6-terra",
        )
