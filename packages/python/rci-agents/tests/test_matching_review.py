from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openai import BadRequestError
from rci_agents import (
    MatchingReviewAIWorker,
    OpenAIMatchingReviewProvider,
    ProviderResponse,
    load_matching_review_prompt,
)
from rci_agents.matching_review import MatchingReviewTask

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


class ImageDownloadFallbackEndpoint:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            request = SimpleNamespace(method="POST", url="https://api.openai.com/v1/responses")
            response = SimpleNamespace(status_code=400, request=request, headers={})
            raise BadRequestError(
                "Error while downloading file. Upstream status code: 403.",
                response=response,  # type: ignore[arg-type]
                body={"error": {"code": "invalid_value"}},
            )
        return SimpleNamespace(
            output_text=json.dumps(self.result),
            usage=SimpleNamespace(input_tokens=180, output_tokens=60),
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


def test_matching_review_prompt_obeys_non_decisive_brand_roles() -> None:
    prompt = load_matching_review_prompt(REPOSITORY_ROOT)

    assert prompt.version == "1.0.4"
    assert "Product Pack attribute roles" in prompt.instructions
    assert "different or unknown brands do not independently prevent" in prompt.instructions
    assert "Brand agreement never overrides" in prompt.instructions
    assert "gallon, half-gallon, quart, pint" in prompt.instructions
    assert "unit-price normalization never creates a product match" in prompt.instructions


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
    request_document = json.loads(content[0]["text"])
    assert request_document["image_evidence_policy"] == {
        "images_provided": True,
        "allowed_source_image_urls": [
            "https://example.com/walmart.jpg",
            "https://example.com/aldi.jpg",
        ],
        "image_proposals_require_exact_source_url": True,
        "image_proposals_require_visible_text": True,
        "structured_proposals_require_null_image_fields": True,
    }
    proposal_variants = result_schema["properties"]["attribute_proposals"]["items"]["anyOf"]
    assert proposal_variants[1]["properties"]["source_image_url"]["enum"] == [
        "https://example.com/walmart.jpg",
        "https://example.com/aldi.jpg",
    ]


async def test_matching_review_schema_disallows_image_claims_without_input_images() -> None:
    endpoint = FakeResponsesEndpoint(
        {
            "verdict_proposal": "comparable",
            "tier_proposal": "equivalent_product",
            "rationale": "The governed structured attributes agree.",
            "attribute_proposals": [
                {
                    "attribute": "fat_content",
                    "value": "2%",
                    "evidence_source": "structured",
                    "confidence": 0.99,
                    "visible_text": None,
                    "source_image_url": None,
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
    case_document = _case(coverage=1)
    case_document["edge"]["attribute_evidence"][0].update(
        {"competitor_value": "2%", "outcome": "match"}
    )

    await provider.generate(
        load_matching_review_prompt(REPOSITORY_ROOT),
        case_document,
        model_id="gpt-5.6-terra",
    )

    content = endpoint.kwargs["input"][0]["content"]
    assert [item["type"] for item in content] == ["input_text"]
    schema = endpoint.kwargs["text"]["format"]["schema"]
    proposal = schema["properties"]["attribute_proposals"]["items"]
    assert proposal["properties"]["evidence_source"]["enum"] == ["structured"]
    assert proposal["properties"]["visible_text"] == {"type": "null"}
    assert proposal["properties"]["source_image_url"] == {"type": "null"}


async def test_matching_review_falls_back_when_retailer_image_download_is_blocked() -> None:
    endpoint = ImageDownloadFallbackEndpoint(
        {
            "verdict_proposal": "insufficient_evidence",
            "tier_proposal": None,
            "rationale": "Structured evidence is not sufficient for an automatic proposal.",
            "attribute_proposals": [],
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

    assert response.warnings == ("vision_image_download_unavailable",)
    assert len(endpoint.calls) == 2
    assert [item["type"] for item in endpoint.calls[0]["input"][0]["content"]] == [
        "input_text",
        "input_image",
        "input_image",
    ]
    assert [item["type"] for item in endpoint.calls[1]["input"][0]["content"]] == ["input_text"]
    assert endpoint.calls[1]["text"]["format"]["schema"]["properties"]["attribute_proposals"][
        "items"
    ]["properties"]["evidence_source"]["enum"] == ["structured"]


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


async def test_matching_review_worker_processes_a_bounded_concurrent_batch() -> None:
    prompt = load_matching_review_prompt(REPOSITORY_ROOT)

    class Repository:
        def __init__(self) -> None:
            input_document = _case()
            input_checksum = hashlib.sha256(
                json.dumps(
                    input_document,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            self.tasks = [
                MatchingReviewTask(
                    task_id=f"task-{index}",
                    batch_id="batch-1",
                    model_id="gpt-5.6-terra",
                    prompt_id=prompt.id,
                    prompt_version=prompt.version,
                    prompt_checksum=prompt.checksum,
                    input_checksum=input_checksum,
                    input_document=input_document,
                    attempt_count=1,
                    max_attempts=2,
                )
                for index in range(4)
            ]
            self.succeeded: list[str] = []

        async def claim(self, **_: Any) -> MatchingReviewTask | None:
            return self.tasks.pop(0) if self.tasks else None

        async def succeed(self, task_id: str, **_: Any) -> None:
            self.succeeded.append(task_id)

        async def fail(self, *_: Any, **__: Any) -> None:
            raise AssertionError("the fixture provider should not fail")

    class Provider:
        provider_id = "openai"

        def __init__(self) -> None:
            self.active = 0
            self.maximum_active = 0

        async def generate(self, *_: Any, **__: Any) -> ProviderResponse:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return ProviderResponse(
                result={
                    "verdict_proposal": "insufficient_evidence",
                    "tier_proposal": None,
                    "rationale": "Human confirmation is required.",
                    "attribute_proposals": [],
                    "conflicts": [],
                    "requires_human_review": True,
                }
            )

    repository = Repository()
    provider = Provider()
    worker = MatchingReviewAIWorker(
        repository,  # type: ignore[arg-type]
        provider,  # type: ignore[arg-type]
        repository_root=REPOSITORY_ROOT,
        worker_id="test-worker",
        lease_seconds=900,
    )

    assert await worker.run_many(2) == 2
    assert provider.maximum_active == 2
    assert repository.succeeded == ["task-0", "task-1"]
    assert len(repository.tasks) == 2
