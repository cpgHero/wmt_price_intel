"""Structured-output model provider boundary."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Protocol

from openai import AsyncOpenAI

from rci_agents.models import AgentRole, JsonObject, PromptTemplate, ProviderResponse


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
                    "required": ["id", "body_template", "metric_refs", "evidence_refs"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "body_template": {"type": "string", "minLength": 1},
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
    ) -> None:
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when AI is enabled")
        if timeout_seconds <= 0 or max_output_tokens <= 0:
            raise ValueError("OpenAI timeout and output-token limit must be positive")
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._max_output_tokens = max_output_tokens

    async def generate(
        self,
        prompt: PromptTemplate,
        payload: JsonObject,
        *,
        model_id: str,
    ) -> ProviderResponse:
        client: Any = self._client
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
                    "schema": _result_schema(prompt.role),
                }
            },
        )
        result = json.loads(str(response.output_text))
        if not isinstance(result, dict):
            raise ValueError("model response was not a JSON object")
        usage = getattr(response, "usage", None)
        return ProviderResponse(
            result=result,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            latency_ms=round((perf_counter() - started_at) * 1000),
        )
