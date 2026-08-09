"""Structured-output model provider boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from openai import AsyncOpenAI

from rci_agents.models import AgentRole, JsonObject, PromptTemplate, ProviderResponse


class AgentCostLimitError(RuntimeError):
    """Raised before a model request whose conservative maximum cost exceeds policy."""


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Pinned public list pricing in USD per one million tokens."""

    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float

    def estimate(self, *, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_usd_per_million_tokens
            + output_tokens * self.output_usd_per_million_tokens
        ) / 1_000_000


PINNED_MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-5.4-2026-03-05": ModelPricing(
        input_usd_per_million_tokens=2.50,
        output_usd_per_million_tokens=15.00,
    ),
    "gpt-5.4-mini-2026-03-17": ModelPricing(
        input_usd_per_million_tokens=0.75,
        output_usd_per_million_tokens=4.50,
    ),
}


class AgentProvider(Protocol):
    provider_id: str

    async def generate(
        self,
        prompt: PromptTemplate,
        payload: JsonObject,
        *,
        model_id: str,
    ) -> ProviderResponse: ...


def _refs() -> JsonObject:
    return {
        "type": "array",
        "minItems": 1,
        "uniqueItems": True,
        "items": {"type": "string", "minLength": 1},
    }


def _result_schema(role: AgentRole) -> JsonObject:
    if role == "insight":
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["insights"],
            "properties": {
                "insights": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "title", "summary", "business_impact"],
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "title": {"type": "string", "minLength": 1},
                            "summary": {"type": "string", "minLength": 1},
                            "business_impact": {"type": "string", "minLength": 1},
                        },
                    },
                }
            },
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["sections"],
        "properties": {
            "sections": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "id",
                        "body_template",
                        "topic_refs",
                        "storyline_refs",
                        "metric_refs",
                        "evidence_refs",
                    ],
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "body_template": {"type": "string", "minLength": 1},
                        "topic_refs": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {
                                "type": "string",
                                "enum": [
                                    "data_scope",
                                    "footprint",
                                    "exact_price",
                                    "normalized_price",
                                    "segment_drivers",
                                    "segment_reversals",
                                    "geography",
                                    "fulfillment",
                                    "brand_assortment",
                                    "actions",
                                    "caveats",
                                ],
                            },
                        },
                        "storyline_refs": _refs(),
                        "metric_refs": _refs(),
                        "evidence_refs": _refs(),
                    },
                },
            }
        },
    }


class OpenAIResponsesProvider:
    """Call the Responses API with a strict JSON Schema response format."""

    provider_id = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        max_output_tokens: int,
        max_request_cost_usd: float | None = None,
        model_pricing: Mapping[str, ModelPricing] | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when AI is enabled")
        if timeout_seconds <= 0 or max_output_tokens <= 0:
            raise ValueError("OpenAI timeout and output-token limit must be positive")
        if max_request_cost_usd is not None and max_request_cost_usd <= 0:
            raise ValueError("OpenAI request cost limit must be positive")
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._max_output_tokens = max_output_tokens
        self._max_request_cost_usd = max_request_cost_usd
        self._model_pricing = dict(model_pricing or PINNED_MODEL_PRICING)

    async def generate(
        self,
        prompt: PromptTemplate,
        payload: JsonObject,
        *,
        model_id: str,
    ) -> ProviderResponse:
        client: Any = self._client
        response_schema = _result_schema(prompt.role)
        pricing = self._model_pricing.get(model_id)
        if self._max_request_cost_usd is not None:
            if pricing is None:
                raise AgentCostLimitError(
                    f"model {model_id!r} has no pinned pricing for the request cost guard"
                )
            maximum_cost = pricing.estimate(
                input_tokens=_input_token_upper_bound(prompt, payload, response_schema),
                output_tokens=self._max_output_tokens,
            )
            if maximum_cost > self._max_request_cost_usd:
                raise AgentCostLimitError(
                    "model request conservative maximum cost "
                    f"${maximum_cost:.4f} exceeds ${self._max_request_cost_usd:.4f} policy"
                )
        started_at = perf_counter()
        response = await client.responses.create(
            model=model_id,
            instructions=prompt.instructions,
            input=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
            max_output_tokens=self._max_output_tokens,
            store=False,
            text={
                "format": {
                    "type": "json_schema",
                    "name": f"rci_{prompt.role}_result",
                    "strict": True,
                    "schema": response_schema,
                }
            },
        )
        result = json.loads(str(response.output_text))
        if not isinstance(result, dict):
            raise ValueError("model response was not a JSON object")
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return ProviderResponse(
            result=result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round((perf_counter() - started_at) * 1000),
            estimated_cost_usd=(
                pricing.estimate(input_tokens=input_tokens, output_tokens=output_tokens)
                if pricing is not None
                else None
            ),
        )


def _input_token_upper_bound(
    prompt: PromptTemplate,
    payload: JsonObject,
    response_schema: JsonObject,
) -> int:
    """Bound request tokens by serialized UTF-8 bytes plus fixed protocol headroom."""

    request_material = {
        "instructions": prompt.instructions,
        "input": payload,
        "response_schema": response_schema,
    }
    serialized = json.dumps(
        request_material,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return len(serialized) + 2_048
