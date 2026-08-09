"""Governed AI orchestration around immutable deterministic AnalysisResult facts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from rci_agents.brief import AnalysisBriefBuilder
from rci_agents.governance import (
    GovernedOutputBuilder,
    apply_governed_outputs,
    checksum,
)
from rci_agents.models import AgentRole, AgentTaskSpec, JsonObject, PromptTemplate
from rci_agents.prompts import PromptTemplateLoader
from rci_agents.provider import AgentProvider
from rci_agents.repository import AgentTaskRepository

logger = logging.getLogger(__name__)


class GovernedAnalysisAssistant:
    """Use models only for bounded interpretation; deterministic output is always the fallback."""

    def __init__(
        self,
        *,
        repository_root: Path,
        provider: AgentProvider,
        repository: AgentTaskRepository,
        worker_id: str,
        insight_model: str,
        narrative_model: str,
        max_metrics: int = 360,
        max_attempts: int = 2,
        lease_seconds: int = 180,
    ) -> None:
        if not insight_model.strip() or not narrative_model.strip():
            raise ValueError("explicit insight and narrative model IDs are required")
        if max_metrics < 1:
            raise ValueError("AI_MAX_METRICS must be positive")
        if not 1 <= max_attempts <= 5:
            raise ValueError("AI_MAX_ATTEMPTS must be between 1 and 5")
        if lease_seconds < 1:
            raise ValueError("AI_LEASE_SECONDS must be positive")
        self._root = repository_root
        self._provider = provider
        self._repository = repository
        self._worker_id = worker_id
        self._models: dict[AgentRole, str] = {
            "insight": insight_model,
            "narrative": narrative_model,
        }
        self._max_metrics = max_metrics
        self._max_attempts = max_attempts
        self._lease_seconds = lease_seconds
        self._prompts = PromptTemplateLoader(repository_root)
        self._builder = GovernedOutputBuilder(repository_root)
        self._briefs = AnalysisBriefBuilder(repository_root, max_metrics=max_metrics)

    async def enrich(
        self,
        result: JsonObject,
        *,
        product_pack: JsonObject,
        report_blueprint: JsonObject,
    ) -> JsonObject:
        deterministic_insights = _rows(result.get("insights"))
        recommendations = _rows(result.get("recommendations"))
        all_metrics = _rows(result.get("metrics"))
        analysis_brief = self._briefs.build(
            result,
            product_pack=product_pack,
            report_blueprint=report_blueprint,
        )
        brief_metric_refs = list(
            dict.fromkeys(
                str(ref)
                for section in _rows(analysis_brief.get("requested_sections"))
                for ref in section.get("allowed_metric_refs", [])
            )
        )
        selected_metrics = self._select_metrics(
            all_metrics,
            [*deterministic_insights, *recommendations],
            priority_refs=brief_metric_refs,
        )
        selected_metric_ids = {str(metric["metric_id"]) for metric in selected_metrics}
        deterministic_insights = _eligible_rows(deterministic_insights, selected_metric_ids)
        recommendations = _eligible_rows(recommendations, selected_metric_ids)
        selected_evidence_ids = {
            str(ref)
            for row in [*selected_metrics, *deterministic_insights, *recommendations]
            for ref in row.get("evidence_refs", [])
        }
        evidence_sets = [
            evidence
            for evidence in _rows(result.get("evidence_sets"))
            if str(evidence.get("evidence_set_id")) in selected_evidence_ids
        ]
        evidence_ids = {str(value["evidence_set_id"]) for value in evidence_sets}
        task_ids: list[str] = []
        insight_output: JsonObject | None = None
        if deterministic_insights:
            insight_payload: JsonObject = {
                "analysis_id": result["analysis_id"],
                "product_pack": _product_pack_context(product_pack),
                "analysis_brief": analysis_brief,
                "deterministic_insights": deterministic_insights,
                "metrics": selected_metrics,
                "evidence_sets": evidence_sets,
                "required_caveats": product_pack.get("reporting", {}).get("required_caveats", []),
            }
            insight_output = await self._run(
                result,
                self._prompts.load("governed_insight"),
                insight_payload,
                build=lambda response: self._builder.insight_result(
                    response,
                    deterministic_insights,
                    selected_metrics,
                ),
            )
            if insight_output is not None:
                task_ids.append(str(insight_output["task_id"]))

        narrative_sections = _rows(analysis_brief.get("requested_sections"))
        narrative_output: JsonObject | None = None
        if narrative_sections:
            interpreted_insights = (
                _rows(insight_output["result"].get("insights"))
                if insight_output is not None
                else deterministic_insights
            )
            narrative_payload: JsonObject = {
                "analysis_id": result["analysis_id"],
                "product_pack": _product_pack_context(product_pack),
                "analysis_brief": self._briefs.model_view(analysis_brief),
                "requested_sections": narrative_sections,
                "required_questions": report_blueprint.get("narrative_policy", {}).get(
                    "required_questions", []
                ),
                "insights": interpreted_insights,
                "recommendations": recommendations,
                "metrics": selected_metrics,
                "evidence_sets": evidence_sets,
                "required_caveats": product_pack.get("reporting", {}).get("required_caveats", []),
            }
            narrative_output = await self._run(
                result,
                self._prompts.load("governed_narrative"),
                narrative_payload,
                build=lambda response: self._builder.narrative_result(
                    response,
                    narrative_sections,
                    selected_metrics,
                    evidence_ids,
                    _rows(analysis_brief.get("storylines")),
                ),
            )
            if narrative_output is not None:
                task_ids.append(str(narrative_output["task_id"]))
        if insight_output is None and narrative_output is None:
            return result
        return apply_governed_outputs(
            result,
            insight_output=insight_output,
            narrative_output=narrative_output,
            task_ids=task_ids,
        )

    async def _run(
        self,
        result: JsonObject,
        prompt: PromptTemplate,
        payload: JsonObject,
        *,
        build: Callable[[JsonObject], JsonObject],
    ) -> JsonObject | None:
        input_checksum = checksum(payload)
        model_id = self._models[prompt.role]
        spec = AgentTaskSpec(
            analysis_run_id=str(result["analysis_run_id"]),
            analysis_id=str(result["analysis_id"]),
            role=prompt.role,
            prompt=prompt,
            provider=self._provider.provider_id,
            model_id=model_id,
            input_checksum=input_checksum,
            input_document=payload,
            max_attempts=self._max_attempts,
        )
        reservation = await self._repository.reserve(
            spec,
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
        )
        if reservation.cached_output is not None:
            try:
                self._builder.validate_envelope(
                    reservation.cached_output,
                    expected_input_checksum=input_checksum,
                )
            except Exception as exc:
                logger.warning(
                    "cached governed AI task rejected",
                    extra={
                        "event": "agent_cache_rejected",
                        "analysis_id": result["analysis_id"],
                        "role": prompt.role,
                        "error_type": type(exc).__name__,
                    },
                )
                return None
            return reservation.cached_output
        if not reservation.acquired:
            return None
        try:
            response = await self._provider.generate(prompt, payload, model_id=model_id)
            governed_result = build(response.result)
            evidence_refs = sorted(_collect_refs(governed_result, "evidence_refs"))
            envelope = self._builder.envelope(
                task_id=reservation.task_id,
                analysis_id=str(result["analysis_id"]),
                prompt=prompt,
                provider_id=self._provider.provider_id,
                model_id=model_id,
                input_checksum=input_checksum,
                evidence_refs=evidence_refs,
                result=governed_result,
                response=response,
            )
            await self._repository.succeed(reservation.task_id, self._worker_id, envelope)
            return envelope
        except Exception as exc:
            error_type = type(exc).__name__
            issue = str(exc).strip()[:1_000] or (
                "governed output was rejected; deterministic fallback retained"
            )
            try:
                await self._repository.fail(
                    reservation.task_id,
                    self._worker_id,
                    error_type,
                    [issue],
                )
            except RuntimeError:
                logger.warning(
                    "governed AI task lease was lost before failure audit",
                    extra={
                        "event": "agent_task_lease_lost",
                        "analysis_id": result["analysis_id"],
                        "role": prompt.role,
                    },
                )
            logger.warning(
                "governed AI task rejected",
                extra={
                    "event": "agent_task_rejected",
                    "analysis_id": result["analysis_id"],
                    "role": prompt.role,
                    "error_type": error_type,
                },
            )
            return None

    def _select_metrics(
        self,
        metrics: list[JsonObject],
        interpreted_rows: list[JsonObject],
        *,
        priority_refs: list[str] | None = None,
    ) -> list[JsonObject]:
        priority = list(
            dict.fromkeys(
                [
                    *(priority_refs or []),
                    *(str(ref) for row in interpreted_rows for ref in row.get("metric_refs", [])),
                ]
            )
        )
        metric_index = {str(metric["metric_id"]): metric for metric in metrics}
        selected = [metric_index[ref] for ref in priority if ref in metric_index]
        selected_ids = {str(metric["metric_id"]) for metric in selected}
        for metric in metrics:
            if len(selected) >= self._max_metrics:
                break
            if str(metric["metric_id"]) not in selected_ids:
                selected.append(metric)
        return selected[: self._max_metrics]


def _rows(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def _collect_refs(value: object, key: str) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key and isinstance(child, list):
                refs.update(str(item) for item in child)
            refs.update(_collect_refs(child, key))
    elif isinstance(value, list):
        for child in value:
            refs.update(_collect_refs(child, key))
    return refs


def _eligible_rows(rows: list[JsonObject], selected_metric_ids: set[str]) -> list[JsonObject]:
    return [
        row
        for row in rows
        if {str(ref) for ref in row.get("metric_refs", [])}.issubset(selected_metric_ids)
    ]


def _product_pack_context(product_pack: JsonObject) -> JsonObject:
    return {
        "id": product_pack["id"],
        "name": product_pack["name"],
        "version": product_pack["version"],
    }
