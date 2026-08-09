"""Structured-output model provider boundary."""

from __future__ import annotations

import json
import re
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
    "gpt-5.6-sol": ModelPricing(
        input_usd_per_million_tokens=5.00,
        output_usd_per_million_tokens=30.00,
    ),
    "gpt-5.4-2026-03-05": ModelPricing(
        input_usd_per_million_tokens=2.50,
        output_usd_per_million_tokens=15.00,
    ),
    "gpt-5.4-mini-2026-03-17": ModelPricing(
        input_usd_per_million_tokens=0.75,
        output_usd_per_million_tokens=4.50,
    ),
}

_NUMERIC_LITERAL = re.compile(
    r"(?<![A-Za-z0-9_.])(?:-\$?|\$-?)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
)
_METRIC_PLACEHOLDER_PATTERN = (
    r"\{\{metric:[A-Za-z0-9_.-]+\|"
    r"(?:integer|decimal_1|decimal_2|percent_1|percent_2|currency_2)\}\}"
)


class AgentProvider(Protocol):
    provider_id: str

    async def generate(
        self,
        prompt: PromptTemplate,
        payload: JsonObject,
        *,
        model_id: str,
    ) -> ProviderResponse: ...


def _refs(allowed_values: list[str] | None = None) -> JsonObject:
    item_schema: JsonObject = {"type": "string", "minLength": 1}
    if allowed_values:
        item_schema["enum"] = allowed_values
    return {
        "type": "array",
        "minItems": 1,
        "items": item_schema,
    }


def _narrative_section_schema(section: JsonObject) -> JsonObject:
    section_id = str(section.get("id", "")).strip()
    required_topics = [str(value) for value in section.get("required_topics", [])]
    storyline_refs = [str(value) for value in section.get("storyline_refs", [])]
    metric_refs = [str(value) for value in section.get("allowed_metric_refs", [])]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "id",
            "body_template",
            "topic_refs",
            "storyline_refs",
            "metric_refs",
        ],
        "properties": {
            "id": {
                "type": "string",
                "minLength": 1,
                **({"enum": [section_id]} if section_id else {}),
            },
            "body_template": {"type": "string", "minLength": 1},
            "topic_refs": _refs(required_topics),
            "storyline_refs": _refs(storyline_refs),
            "metric_refs": _refs(metric_refs),
        },
    }


def _governed_insight_text_schema(candidate: JsonObject) -> JsonObject:
    trusted_numbers = sorted(
        {
            numeric_literal
            for field in ("title", "summary", "business_impact")
            for numeric_literal in _NUMERIC_LITERAL.findall(str(candidate.get(field, "")))
        },
        key=lambda value: (-len(value), value),
    )
    alternatives = [r"[^0-9]", _METRIC_PLACEHOLDER_PATTERN]
    alternatives.extend(re.escape(value) for value in trusted_numbers)
    return {
        "type": "string",
        "minLength": 1,
        "pattern": rf"^(?:{'|'.join(alternatives)})+$",
    }


def _insight_schema(candidate: JsonObject) -> JsonObject:
    candidate_id = str(candidate.get("id", "")).strip()
    text_schema = _governed_insight_text_schema(candidate)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "title", "summary", "business_impact"],
        "properties": {
            "id": {
                "type": "string",
                "minLength": 1,
                **({"enum": [candidate_id]} if candidate_id else {}),
            },
            "title": dict(text_schema),
            "summary": dict(text_schema),
            "business_impact": dict(text_schema),
        },
    }


def _result_schema(role: AgentRole, payload: JsonObject) -> JsonObject:
    if role == "insight":
        candidates = [
            row
            for row in payload.get("deterministic_insights", [])
            if isinstance(row, dict) and row.get("id")
        ]
        insight_branches = [_insight_schema(candidate) for candidate in candidates] or [
            _insight_schema({})
        ]
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["insights"],
            "properties": {
                "insights": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"anyOf": insight_branches},
                }
            },
        }
    requested_sections = [
        row
        for row in payload.get("requested_sections", [])
        if isinstance(row, dict) and row.get("id")
    ]
    section_branches = [_narrative_section_schema(section) for section in requested_sections] or [
        _narrative_section_schema({})
    ]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["sections"],
        "properties": {
            "sections": {
                "type": "array",
                "minItems": 1,
                "items": {"anyOf": section_branches},
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
        reasoning_effort: str = "high",
        text_verbosity: str = "high",
    ) -> None:
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when AI is enabled")
        if timeout_seconds <= 0 or max_output_tokens <= 0:
            raise ValueError("OpenAI timeout and output-token limit must be positive")
        if max_request_cost_usd is not None and max_request_cost_usd <= 0:
            raise ValueError("OpenAI request cost limit must be positive")
        if reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported OpenAI reasoning effort")
        if text_verbosity not in {"low", "medium", "high"}:
            raise ValueError("unsupported OpenAI text verbosity")
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._max_output_tokens = max_output_tokens
        self._max_request_cost_usd = max_request_cost_usd
        self._model_pricing = dict(model_pricing or PINNED_MODEL_PRICING)
        self._reasoning_effort = reasoning_effort
        self._text_verbosity = text_verbosity

    async def generate(
        self,
        prompt: PromptTemplate,
        payload: JsonObject,
        *,
        model_id: str,
    ) -> ProviderResponse:
        client: Any = self._client
        response_schema = _result_schema(prompt.role, payload)
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
            reasoning={"effort": self._reasoning_effort},
            text={
                "verbosity": self._text_verbosity,
                "format": {
                    "type": "json_schema",
                    "name": f"rci_{prompt.role}_result",
                    "strict": True,
                    "schema": response_schema,
                },
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
