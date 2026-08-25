"""Advisory, human-gated AI review for Matching v2 evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI, BadRequestError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_agents.models import JsonObject, ProviderResponse
from rci_agents.provider import PINNED_MODEL_PRICING, ModelPricing
from rci_contracts import validate_instance

logger = logging.getLogger(__name__)

_ALLOWED_TIERS = {
    "exact_item",
    "exact_specification",
    "equivalent_product",
    "comparable_substitute",
    "custom_approved",
}

_RESULT_SCHEMA: JsonObject = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "verdict_proposal",
        "tier_proposal",
        "comparison_basis_proposal",
        "rationale",
        "attribute_proposals",
        "conflicts",
        "requires_human_review",
    ],
    "properties": {
        "verdict_proposal": {
            "type": "string",
            "enum": ["comparable", "not_comparable", "insufficient_evidence"],
        },
        "tier_proposal": {
            "anyOf": [
                {"type": "string", "enum": sorted(_ALLOWED_TIERS)},
                {"type": "null"},
            ]
        },
        "comparison_basis_proposal": {
            "type": "array",
            "maxItems": 2,
            "items": {
                "type": "string",
                "enum": ["package_price", "normalized_unit_price"],
            },
        },
        "rationale": {"type": "string", "minLength": 1, "maxLength": 4000},
        "attribute_proposals": {
            "type": "array",
            "maxItems": 24,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "attribute",
                    "value",
                    "evidence_source",
                    "confidence",
                    "visible_text",
                    "source_image_url",
                ],
                "properties": {
                    "attribute": {"type": "string", "minLength": 1, "maxLength": 120},
                    "value": {"type": "string", "minLength": 1, "maxLength": 500},
                    "evidence_source": {
                        "type": "string",
                        "enum": ["structured", "image"],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "visible_text": {
                        "anyOf": [{"type": "string", "maxLength": 500}, {"type": "null"}]
                    },
                    "source_image_url": {
                        "anyOf": [{"type": "string", "maxLength": 4000}, {"type": "null"}]
                    },
                },
            },
        },
        "conflicts": {
            "type": "array",
            "maxItems": 24,
            "items": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
        "requires_human_review": {"type": "boolean", "const": True},
    },
}


def _deterministic_tier(case_document: JsonObject) -> str | None:
    engine = case_document.get("engine_proposal")
    if not isinstance(engine, dict):
        return None
    tier = str(engine.get("tier") or "")
    return tier if tier in _ALLOWED_TIERS else None


def _deterministic_comparison_bases(case_document: JsonObject) -> list[str]:
    edge = case_document.get("edge")
    if not isinstance(edge, dict):
        return []
    eligible = edge.get("eligible_price_bases")
    eligible = set(str(value) for value in eligible) if isinstance(eligible, list) else set()
    result: list[str] = []
    if "exact_package" in eligible:
        result.append("package_price")
    if "normalized_unit" in eligible:
        result.append("normalized_unit_price")
    return result


def _result_schema(image_urls: list[str], case_document: JsonObject) -> JsonObject:
    """Bind image-derived proposals to the exact images sent to the model.

    The prior static schema allowed ``evidence_source=image`` even when no image
    was in the request, then rejected that otherwise structured response after
    the paid call.  A request-specific schema makes the invalid state
    unrepresentable while retaining the post-response integrity check.
    """

    schema = json.loads(json.dumps(_RESULT_SCHEMA))
    deterministic_tier = _deterministic_tier(case_document)
    if deterministic_tier is None:
        schema["properties"]["tier_proposal"] = {"type": "null"}
    else:
        schema["properties"]["tier_proposal"]["anyOf"][0]["enum"] = [deterministic_tier]
    comparison_bases = _deterministic_comparison_bases(case_document)
    comparison_basis_schema = schema["properties"]["comparison_basis_proposal"]
    comparison_basis_schema["maxItems"] = len(comparison_bases)
    if comparison_bases:
        comparison_basis_schema["items"]["enum"] = comparison_bases
    proposals = schema["properties"]["attribute_proposals"]
    if not image_urls:
        proposals["items"]["properties"]["evidence_source"] = {
            "type": "string",
            "enum": ["structured"],
        }
        proposals["items"]["properties"]["visible_text"] = {"type": "null"}
        proposals["items"]["properties"]["source_image_url"] = {"type": "null"}
        return schema

    common_properties: JsonObject = {
        "attribute": {"type": "string", "minLength": 1, "maxLength": 120},
        "value": {"type": "string", "minLength": 1, "maxLength": 500},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }
    required = [
        "attribute",
        "value",
        "evidence_source",
        "confidence",
        "visible_text",
        "source_image_url",
    ]
    proposals["items"] = {
        "anyOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": {
                    **common_properties,
                    "evidence_source": {"type": "string", "enum": ["structured"]},
                    "visible_text": {"type": "null"},
                    "source_image_url": {"type": "null"},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": {
                    **common_properties,
                    "evidence_source": {"type": "string", "enum": ["image"]},
                    "visible_text": {"type": "string", "minLength": 1, "maxLength": 500},
                    "source_image_url": {
                        "type": "string",
                        "enum": list(image_urls),
                    },
                },
            },
        ]
    }
    return schema


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MatchingReviewPrompt:
    id: str
    version: str
    instructions: str
    checksum: str


def load_matching_review_prompt(repository_root: Path) -> MatchingReviewPrompt:
    path = repository_root / "agent-prompts" / "matching_v2_evidence_review.json"
    body = path.read_bytes()
    document = json.loads(body)
    validate_instance(repository_root, "agent-prompt.schema.json", document, label=str(path))
    if document["role"] != "matching_review":
        raise ValueError("matching review prompt has the wrong role")
    return MatchingReviewPrompt(
        id=str(document["id"]),
        version=str(document["version"]),
        instructions=str(document["instructions"]),
        checksum=hashlib.sha256(body).hexdigest(),
    )


class OpenAIMatchingReviewProvider:
    """Generate a non-authoritative draft, optionally using missing label evidence."""

    provider_id = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        max_output_tokens: int,
        max_request_cost_usd: float | None,
        reasoning_effort: str = "high",
        client: Any | None = None,
        model_pricing: dict[str, ModelPricing] | None = None,
    ) -> None:
        if not api_key.strip() and client is None:
            raise ValueError("OPENAI_API_KEY is required for AI matching review")
        if timeout_seconds <= 0 or max_output_tokens <= 0:
            raise ValueError("OpenAI timeout and output-token limit must be positive")
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._max_output_tokens = max_output_tokens
        self._max_request_cost_usd = max_request_cost_usd
        self._reasoning_effort = reasoning_effort
        self._model_pricing = dict(model_pricing or PINNED_MODEL_PRICING)

    async def generate(
        self,
        prompt: MatchingReviewPrompt,
        case_document: JsonObject,
        *,
        model_id: str,
    ) -> ProviderResponse:
        image_urls = _vision_image_urls(case_document)
        pricing = self._model_pricing.get(model_id)
        input_upper_bound = (
            len(_canonical(case_document).encode()) + 2_048 + len(image_urls) * 8_000
        )
        if self._max_request_cost_usd is not None:
            if pricing is None:
                raise ValueError(f"model {model_id!r} has no pinned pricing")
            maximum_cost = pricing.estimate(
                input_tokens=input_upper_bound,
                output_tokens=self._max_output_tokens,
            )
            if maximum_cost > self._max_request_cost_usd:
                raise ValueError(
                    f"AI matching review maximum cost ${maximum_cost:.4f} exceeds "
                    f"${self._max_request_cost_usd:.4f} policy"
                )

        def request_content(urls: list[str]) -> list[JsonObject]:
            content: list[JsonObject] = [
                {
                    "type": "input_text",
                    "text": _canonical(
                        {
                            "authoritative": False,
                            "human_review_required": True,
                            "image_evidence_policy": {
                                "images_provided": bool(urls),
                                "allowed_source_image_urls": urls,
                                "image_proposals_require_exact_source_url": True,
                                "image_proposals_require_visible_text": True,
                                "structured_proposals_require_null_image_fields": True,
                            },
                            "case": case_document,
                        }
                    ),
                }
            ]
            content.extend(
                {"type": "input_image", "image_url": image_url, "detail": "high"}
                for image_url in urls
            )
            return content

        async def request(urls: list[str]) -> Any:
            return await client.responses.create(
                model=model_id,
                instructions=prompt.instructions,
                input=[{"role": "user", "content": request_content(urls)}],
                max_output_tokens=self._max_output_tokens,
                store=False,
                reasoning={"effort": self._reasoning_effort},
                text={
                    "verbosity": "medium",
                    "format": {
                        "type": "json_schema",
                        "name": "rci_matching_review_draft",
                        "strict": True,
                        "schema": _result_schema(urls, case_document),
                    },
                },
            )

        started_at = perf_counter()
        client: Any = self._client
        warnings: tuple[str, ...] = ()
        try:
            response = await request(image_urls)
        except BadRequestError as exc:
            message = str(exc).lower()
            image_download_failed = any(
                marker in message
                for marker in (
                    "error while downloading file",
                    "failed to download file",
                )
            )
            if not image_urls or not image_download_failed:
                raise
            warnings = ("vision_image_download_unavailable",)
            logger.warning(
                "AI matching review image retrieval unavailable; retrying with structured evidence",
                extra={
                    "event": "matching_review_vision_fallback",
                    "image_count": len(image_urls),
                    "error_type": type(exc).__name__,
                },
            )
            image_urls = []
            response = await request(image_urls)
        result = json.loads(str(response.output_text))
        _validate_matching_review_result(
            result,
            image_urls=image_urls,
            case_document=case_document,
        )
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
            warnings=warnings,
        )


def _vision_image_urls(case_document: JsonObject) -> list[str]:
    coverage = (
        case_document.get("engine_proposal", {})
        .get("evidence_coverage", {})
        .get("critical_coverage", 0)
    )
    attribute_rows = case_document.get("edge", {}).get("attribute_evidence", [])
    incomplete = not isinstance(coverage, (int, float)) or coverage < 1
    if isinstance(attribute_rows, list):
        incomplete = incomplete or any(
            isinstance(row, dict)
            and (
                row.get("benchmark_value") in (None, "", "unknown")
                or row.get("competitor_value") in (None, "", "unknown")
                or row.get("outcome") in {"unknown", "conflict"}
            )
            for row in attribute_rows
        )
    if not incomplete:
        return []
    # Secondary PDP images commonly contain the package side/back label and are
    # often more useful than the hero image for governed package attributes.
    # Bound the request while preserving both sides of the proposed relationship.
    per_listing_urls: list[list[str]] = []
    for side in ("benchmark_listing", "competitor_listing"):
        listing = case_document.get(side)
        if not isinstance(listing, dict):
            continue
        candidates = listing.get("image_urls")
        values = list(candidates) if isinstance(candidates, list) else []
        values.insert(0, listing.get("image_url"))
        listing_urls: list[str] = []
        for candidate in values:
            value = str(candidate or "").strip()
            if value.startswith(("https://", "http://")) and value not in listing_urls:
                listing_urls.append(value)
        per_listing_urls.append(listing_urls[:6])
    urls: list[str] = []
    for index in range(6):
        for listing_urls in per_listing_urls:
            if index < len(listing_urls) and listing_urls[index] not in urls:
                urls.append(listing_urls[index])
    return urls[:12]


def _validate_matching_review_result(
    result: object, *, image_urls: list[str], case_document: JsonObject
) -> None:
    if not isinstance(result, dict) or result.get("requires_human_review") is not True:
        raise ValueError("AI matching result did not preserve mandatory human review")
    verdict = str(result.get("verdict_proposal") or "")
    tier = result.get("tier_proposal")
    comparison_bases = result.get("comparison_basis_proposal")
    if verdict == "comparable" and tier not in _ALLOWED_TIERS:
        raise ValueError("comparable AI draft requires a governed tier")
    deterministic_tier = _deterministic_tier(case_document)
    if verdict == "comparable" and tier != deterministic_tier:
        raise ValueError("comparable AI draft must use the deterministic engine tier")
    if verdict != "comparable" and tier is not None:
        raise ValueError("non-comparable AI draft cannot propose a tier")
    if not isinstance(comparison_bases, list):
        raise ValueError("AI matching result must propose governed price-comparison bases")
    allowed_comparison_bases = {"package_price", "normalized_unit_price"}
    if any(value not in allowed_comparison_bases for value in comparison_bases):
        raise ValueError("AI matching result proposed an unsupported price-comparison basis")
    if len(comparison_bases) != len(set(comparison_bases)):
        raise ValueError("AI matching result proposed duplicate price-comparison bases")
    if len(comparison_bases) > len(allowed_comparison_bases):
        raise ValueError("AI matching result proposed too many price-comparison bases")
    deterministic_comparison_bases = set(_deterministic_comparison_bases(case_document))
    if any(value not in deterministic_comparison_bases for value in comparison_bases):
        raise ValueError(
            "AI matching result proposed a price-comparison basis absent from "
            "deterministic evidence"
        )
    if verdict == "comparable" and not comparison_bases:
        raise ValueError("comparable AI draft requires at least one price-comparison basis")
    if verdict != "comparable" and comparison_bases:
        raise ValueError("non-comparable AI draft cannot propose a price-comparison basis")
    for row in result.get("attribute_proposals", []):
        if not isinstance(row, dict):
            raise ValueError("AI attribute proposal must be an object")
        if row.get("evidence_source") == "image" and (
            not row.get("visible_text") or row.get("source_image_url") not in image_urls
        ):
            raise ValueError("image evidence must cite visible evidence and an input image")


@dataclass(frozen=True, slots=True)
class MatchingReviewTask:
    task_id: str
    batch_id: str
    model_id: str
    prompt_id: str
    prompt_version: str
    prompt_checksum: str
    input_checksum: str
    input_document: JsonObject
    attempt_count: int
    max_attempts: int


class PostgresMatchingReviewTaskRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(self, *, worker_id: str, lease_seconds: int) -> MatchingReviewTask | None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            WITH candidate AS (
                              SELECT id
                              FROM matching_v2_ai_review_task
                              WHERE attempt_count < max_attempts
                                AND (
                                  status = 'queued'
                                  OR (status = 'running' AND lease_expires_at <= now())
                                )
                              ORDER BY created_at, id
                              FOR UPDATE SKIP LOCKED
                              LIMIT 1
                            )
                            UPDATE matching_v2_ai_review_task task
                            SET status = 'running', attempt_count = task.attempt_count + 1,
                                locked_by = :worker_id, locked_at = now(),
                                lease_expires_at = now() + make_interval(secs => :lease_seconds),
                                last_error_type = NULL, last_error_message = NULL,
                                updated_at = now()
                            FROM candidate
                            WHERE task.id = candidate.id
                            RETURNING task.id::text, task.model_id, task.prompt_id,
                                      task.batch_id::text,
                                      task.prompt_version, task.prompt_checksum,
                                      task.input_checksum, task.input_document,
                                      task.attempt_count, task.max_attempts
                            """
                        ),
                        {"worker_id": worker_id, "lease_seconds": lease_seconds},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return MatchingReviewTask(
            task_id=str(row["id"]),
            batch_id=str(row["batch_id"]),
            model_id=str(row["model_id"]),
            prompt_id=str(row["prompt_id"]),
            prompt_version=str(row["prompt_version"]),
            prompt_checksum=str(row["prompt_checksum"]),
            input_checksum=str(row["input_checksum"]),
            input_document=dict(row["input_document"]),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
        )

    async def succeed(
        self,
        task_id: str,
        *,
        worker_id: str,
        output: JsonObject,
        usage: JsonObject,
    ) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE matching_v2_ai_review_task
                    SET status = 'succeeded', output_checksum = :checksum,
                        output_document = CAST(:output AS jsonb), usage = CAST(:usage AS jsonb),
                        completed_at = now(), locked_by = NULL, locked_at = NULL,
                        lease_expires_at = NULL, updated_at = now()
                    WHERE id::text = :task_id AND status = 'running'
                      AND locked_by = :worker_id AND lease_expires_at > now()
                    """
                ),
                {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "checksum": _checksum(output),
                    "output": _canonical(output),
                    "usage": _canonical(usage),
                },
            )
            if result.rowcount != 1:
                raise RuntimeError("AI matching review lease is no longer owned")

    async def fail(
        self,
        task_id: str,
        *,
        worker_id: str,
        error_type: str,
        error_message: str,
    ) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE matching_v2_ai_review_task
                    SET status = CASE WHEN attempt_count >= max_attempts
                                      THEN 'needs_review' ELSE 'queued' END,
                        last_error_type = :error_type,
                        last_error_message = :error_message,
                        locked_by = NULL, locked_at = NULL, lease_expires_at = NULL,
                        updated_at = now()
                    WHERE id::text = :task_id AND status = 'running'
                      AND locked_by = :worker_id
                    """
                ),
                {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "error_type": error_type[:200],
                    "error_message": error_message[:2000],
                },
            )
            if result.rowcount != 1:
                raise RuntimeError("AI matching review lease is no longer owned")


class MatchingReviewAIWorker:
    """Process durable drafts; results remain separate from human submissions."""

    def __init__(
        self,
        repository: PostgresMatchingReviewTaskRepository,
        provider: OpenAIMatchingReviewProvider,
        *,
        repository_root: Path,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._prompt = load_matching_review_prompt(repository_root)

    async def run_once(self) -> int:
        return await self.run_many(1)

    async def run_many(self, concurrency: int) -> int:
        """Claim and process a bounded number of independent review tasks."""

        limit = max(1, min(int(concurrency), 4))
        tasks: list[MatchingReviewTask] = []
        for _ in range(limit):
            task = await self._repository.claim(
                worker_id=self._worker_id,
                lease_seconds=self._lease_seconds,
            )
            if task is None:
                break
            tasks.append(task)
        if not tasks:
            return 0
        await asyncio.gather(*(self._process_task(task) for task in tasks))
        return len(tasks)

    async def _process_task(self, task: MatchingReviewTask) -> None:
        started_at = perf_counter()
        logger.info(
            "AI matching review started",
            extra={
                "event": "matching_review_started",
                "task_id": task.task_id,
                "batch_id": task.batch_id,
                "model_id": task.model_id,
                "attempt_count": task.attempt_count,
                "max_attempts": task.max_attempts,
            },
        )
        try:
            if (
                task.prompt_id != self._prompt.id
                or task.prompt_version != self._prompt.version
                or task.prompt_checksum != self._prompt.checksum
                or task.input_checksum != _checksum(task.input_document)
            ):
                raise ValueError("AI matching review task does not match governed input or prompt")
            response = await self._provider.generate(
                self._prompt,
                task.input_document,
                model_id=task.model_id,
            )
            output: JsonObject = {
                "authoritative": False,
                "human_review_required": True,
                "prompt": {
                    "id": self._prompt.id,
                    "version": self._prompt.version,
                    "checksum_sha256": self._prompt.checksum,
                },
                "provider": self._provider.provider_id,
                "model_id": task.model_id,
                "input_checksum_sha256": task.input_checksum,
                "result": response.result,
            }
            usage: JsonObject = {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "latency_ms": response.latency_ms,
                "estimated_cost_usd": response.estimated_cost_usd,
                "warnings": list(response.warnings),
            }
            await self._repository.succeed(
                task.task_id,
                worker_id=self._worker_id,
                output=output,
                usage=usage,
            )
            logger.info(
                "AI matching review succeeded",
                extra={
                    "event": "matching_review_succeeded",
                    "task_id": task.task_id,
                    "batch_id": task.batch_id,
                    "model_id": task.model_id,
                    "attempt_count": task.attempt_count,
                    "latency_ms": round((perf_counter() - started_at) * 1000),
                    "estimated_cost_usd": response.estimated_cost_usd,
                },
            )
        except Exception as exc:
            await self._repository.fail(
                task.task_id,
                worker_id=self._worker_id,
                error_type=type(exc).__name__,
                error_message=str(exc) or "AI matching review failed",
            )
            terminal = task.attempt_count >= task.max_attempts
            logger.warning(
                (
                    "AI matching review needs attention"
                    if terminal
                    else "AI matching review retry queued"
                ),
                extra={
                    "event": (
                        "matching_review_needs_attention"
                        if terminal
                        else "matching_review_retry_queued"
                    ),
                    "task_id": task.task_id,
                    "batch_id": task.batch_id,
                    "model_id": task.model_id,
                    "attempt_count": task.attempt_count,
                    "max_attempts": task.max_attempts,
                    "latency_ms": round((perf_counter() - started_at) * 1000),
                    "error_type": type(exc).__name__,
                },
            )
