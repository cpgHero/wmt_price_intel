"""Typed records for governed model execution and durable audit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

JsonObject = dict[str, Any]
AgentRole = Literal["insight", "narrative"]


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    id: str
    version: str
    role: AgentRole
    instructions: str
    checksum: str


@dataclass(frozen=True, slots=True)
class AgentTaskSpec:
    analysis_run_id: str
    analysis_id: str
    role: AgentRole
    prompt: PromptTemplate
    provider: str
    model_id: str
    input_checksum: str
    input_document: JsonObject
    max_attempts: int


@dataclass(frozen=True, slots=True)
class AgentTaskReservation:
    task_id: str
    acquired: bool
    cached_output: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    result: JsonObject
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    estimated_cost_usd: float | None = None
    warnings: tuple[str, ...] = ()
