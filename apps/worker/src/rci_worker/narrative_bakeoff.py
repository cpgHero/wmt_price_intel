"""Run a governed, zero-retailer-credit narrative bake-off on a persisted result."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from rci_agents import (
    AgentProvider,
    GovernedAnalysisAssistant,
    OpenAIResponsesProvider,
    PostgresAgentTaskRepository,
    PromptTemplate,
    ProviderResponse,
)

from rci_core import AppSettings
from rci_db import DatabaseProbe
from rci_results import (
    AnalysisResultValidator,
    ArtifactRenderer,
    PostgresResultsRepository,
    ReportBlueprintLoader,
    S3ReportObjectStore,
)


def _enabled(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(slots=True)
class RecordingProvider:
    delegate: AgentProvider
    responses: list[tuple[str, str, ProviderResponse]] = field(default_factory=list)
    provider_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.provider_id = self.delegate.provider_id

    async def generate(
        self,
        prompt: PromptTemplate,
        payload: dict[str, Any],
        *,
        model_id: str,
    ) -> ProviderResponse:
        response = await self.delegate.generate(prompt, payload, model_id=model_id)
        self.responses.append((prompt.role, model_id, response))
        return response


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a temporary leadership HTML bake-off from an existing deterministic "
            "AnalysisResult. This command never calls MetricsCart or publishes a new result."
        )
    )
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())),
    )
    parser.add_argument(
        "--insight-model",
        default=os.getenv("OPENAI_MODEL_INSIGHT", "gpt-5.4-mini-2026-03-17"),
    )
    parser.add_argument(
        "--narrative-model",
        default=os.getenv("OPENAI_MODEL_NARRATIVE", "gpt-5.4-2026-03-05"),
    )
    parser.add_argument(
        "--max-request-cost-usd",
        type=float,
        default=float(os.getenv("OPENAI_MAX_REQUEST_COST_USD", "1.00")),
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "3000")),
    )
    parser.add_argument(
        "--max-metrics",
        type=int,
        default=int(os.getenv("AI_MAX_METRICS", "160")),
    )
    parser.add_argument("--expires-in-seconds", type=int, default=86_400)
    parser.add_argument(
        "--confirm-paid-call",
        action="store_true",
        help="Required acknowledgement that up to two capped OpenAI calls may be billed.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict[str, object]:
    settings = AppSettings.from_env()
    database = DatabaseProbe(settings.database_url)
    repository_root = args.repository_root.resolve(strict=True)
    results = PostgresResultsRepository(database.engine)
    try:
        record = await results.get(args.analysis_id)
        if record is None:
            raise LookupError(f"analysis {args.analysis_id!r} was not found")
        deterministic_result = AnalysisResultValidator(repository_root).validate(record.result)
        if deterministic_result.get("schema_version") != "2.0.0":
            raise ValueError("narrative bake-off requires AnalysisResult V2")
        blueprint, product_pack = ReportBlueprintLoader(repository_root).load_for_result(
            deterministic_result
        )
        provider = RecordingProvider(
            OpenAIResponsesProvider(
                api_key=os.environ["OPENAI_API_KEY"],
                timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
                max_output_tokens=args.max_output_tokens,
                max_request_cost_usd=args.max_request_cost_usd,
            )
        )
        assistant = GovernedAnalysisAssistant(
            repository_root=repository_root,
            provider=provider,
            repository=PostgresAgentTaskRepository(database.engine),
            worker_id=f"narrative-bakeoff-{uuid4()}",
            insight_model=args.insight_model,
            narrative_model=args.narrative_model,
            max_metrics=args.max_metrics,
            max_attempts=1,
            lease_seconds=int(os.getenv("AI_LEASE_SECONDS", "180")),
        )
        enriched = await assistant.enrich(
            deepcopy(deterministic_result),
            product_pack=product_pack,
            report_blueprint=blueprint.document,
        )
        if _digest(enriched.get("metrics")) != _digest(deterministic_result.get("metrics")):
            raise RuntimeError("bake-off changed authoritative metrics")
        narratives = enriched.get("narratives")
        if not isinstance(narratives, dict) or narratives.get("generation_mode") != "ai_assisted":
            raise RuntimeError("governed narrative was rejected; no bake-off artifact was created")
        validated = AnalysisResultValidator(repository_root).validate(enriched)
        renderer = ArtifactRenderer(repository_root)
        payload = renderer.render(validated, "html")
        store = S3ReportObjectStore.create(
            bucket=os.environ["OBJECT_STORAGE_BUCKET"],
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT"),
            region_name=os.getenv("OBJECT_STORAGE_REGION"),
            access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
            force_path_style=_enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE")),
        )
        storage_uri = await store.put(f"bakeoff-{record.analysis_id}", payload)
        download_url = await store.presign(
            storage_uri,
            expires_in_seconds=args.expires_in_seconds,
        )
        usage = [
            {
                "role": role,
                "model_id": model_id,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "estimated_cost_usd": response.estimated_cost_usd,
            }
            for role, model_id, response in provider.responses
        ]
        return {
            "status": "ready",
            "analysis_id": record.analysis_id,
            "source_result_checksum_sha256": record.checksum,
            "authoritative_metrics_unchanged": True,
            "retailer_api_calls": 0,
            "model_calls_charged_this_execution": len(provider.responses),
            "maximum_model_calls": 2,
            "maximum_cost_usd": round(2 * args.max_request_cost_usd, 4),
            "estimated_cost_usd": round(
                sum(response.estimated_cost_usd or 0 for _, _, response in provider.responses),
                6,
            ),
            "usage": usage,
            "validation": validated["validation"],
            "download_url": download_url,
            "expires_in_seconds": args.expires_in_seconds,
        }
    finally:
        await database.dispose()


def main() -> None:
    args = _arguments()
    if not args.confirm_paid_call:
        raise SystemExit(
            "Refusing paid model calls without --confirm-paid-call. "
            f"Maximum policy exposure would be ${2 * args.max_request_cost_usd:.2f}."
        )
    if args.max_request_cost_usd <= 0:
        raise ValueError("--max-request-cost-usd must be positive")
    if args.max_output_tokens <= 0 or args.max_metrics <= 0:
        raise ValueError("token and metric limits must be positive")
    if not 60 <= args.expires_in_seconds <= 604_800:
        raise ValueError("--expires-in-seconds must be between 60 and 604800")
    print(json.dumps(asyncio.run(_run(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
