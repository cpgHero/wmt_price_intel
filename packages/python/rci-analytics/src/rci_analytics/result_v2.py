"""Category-neutral AnalysisResult V2 assembly from deterministic facts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from rci_analytics.insights import ComparisonInsightInput, DeterministicInsightEngine
from rci_analytics.models import JsonObject
from rci_analytics.product_pack import ProductPack

_SAFE_ID = re.compile(r"[^a-z0-9_.-]+")


def _id(value: object) -> str:
    return _SAFE_ID.sub("-", str(value).casefold()).strip("-") or "unknown"


def _checksum(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ComparisonFact:
    competitor_id: str
    profile_id: str
    profile_label: str
    geography: str
    comparison_metric: str
    dimensions: tuple[str, ...]
    evidence_ref: str
    values: dict[str, float | int | None]
    segment_id: str = "all"
    segment_label: str = "All comparable items"
    attributes: JsonObject | None = None
    radius_miles: float | None = None


class _MetricRegistry:
    def __init__(self) -> None:
        self.documents: list[JsonObject] = []
        self.ids: set[str] = set()

    def add(
        self,
        metric_id: str,
        name: str,
        value: float | int,
        unit: str,
        method: str,
        evidence_refs: list[str],
        *,
        numerator: float | int | None = None,
        denominator: float | int | None = None,
    ) -> str:
        if metric_id in self.ids:
            raise ValueError(f"duplicate deterministic metric {metric_id!r}")
        document: JsonObject = {
            "metric_id": metric_id,
            "name": name,
            "value": value,
            "unit": unit,
            "method": method,
            "source": "deterministic",
            "evidence_refs": list(dict.fromkeys(evidence_refs)),
        }
        if numerator is not None:
            document["numerator"] = numerator
        if denominator is not None and denominator > 0:
            document["denominator"] = denominator
        self.documents.append(document)
        self.ids.add(metric_id)
        return metric_id


class AnalysisResultV2Builder:
    def __init__(self, product_pack: ProductPack, *, code_version: str) -> None:
        self._pack = product_pack
        self._code_version = code_version

    def build(
        self,
        *,
        analysis_id: str,
        analysis_run_id: str,
        generated_at: str,
        source: JsonObject,
        benchmark_retailer: str,
        competitors: list[str],
        coverage_facts: list[JsonObject],
        comparison_facts: list[ComparisonFact],
        data_quality_facts: JsonObject,
        evidence_sets: list[JsonObject],
        raw_source_artifact_ids: list[str],
    ) -> JsonObject:
        evidence_ids = {str(value["evidence_set_id"]) for value in evidence_sets}
        if len(evidence_ids) != len(evidence_sets):
            raise ValueError("evidence-set IDs must be unique")
        registry = _MetricRegistry()
        source_evidence = self._source_evidence(evidence_sets)
        source_total_metric = registry.add(
            "source.total_rows",
            "Source rows",
            int(source["total_rows"]),
            "rows",
            "sum immutable source artifact row counts",
            [source_evidence],
        )
        coverage, assortment_refs = self._coverage(registry, coverage_facts, evidence_ids)
        comparison_modes = self._comparison_modes(comparison_facts)
        comparisons, segments, geography, insight_inputs = self._comparisons(
            registry,
            comparison_facts,
            benchmark_retailer,
        )
        quality_metric_refs = self._quality(
            registry,
            data_quality_facts,
            source_evidence,
        )
        ranked = DeterministicInsightEngine(self._pack).rank(insight_inputs)
        insights = [candidate.insight for candidate in ranked]
        recommendations = [
            candidate.recommendation for candidate in ranked if candidate.recommendation is not None
        ]
        fallback_refs = list(insights[0]["metric_refs"]) if insights else [source_total_metric]
        fallback_evidence = list(insights[0]["evidence_refs"]) if insights else [source_evidence]
        narratives = self._deterministic_narratives(
            insights,
            recommendations,
            fallback_refs,
            fallback_evidence,
        )
        matched_competitors = {
            fact.competitor_id for fact in comparison_facts if fact.segment_id == "all"
        }
        ready_to_share = bool(comparisons) and matched_competitors == set(competitors)
        result: JsonObject = {
            "schema_version": "2.0.0",
            "analysis_id": analysis_id,
            "analysis_run_id": analysis_run_id,
            "generated_at": generated_at,
            "source": source,
            "benchmark_retailer": benchmark_retailer,
            "competitors": competitors,
            "product_pack": {
                "id": self._pack.id,
                "version": self._pack.version,
                "checksum_sha256": self._pack.checksum,
                "report_blueprint": self._pack.report_blueprint,
            },
            "metrics": registry.documents,
            "coverage": coverage,
            "comparison_modes": comparison_modes,
            "segments": segments,
            "comparisons": comparisons,
            "geographic_sensitivity": geography,
            "assortment": {
                "metric_refs": assortment_refs,
                "evidence_refs": sorted({ref for row in coverage for ref in row["evidence_refs"]}),
            },
            "data_quality": {
                "status": (
                    "warning"
                    if any(int(value) > 0 for value in data_quality_facts.values())
                    else "ready"
                ),
                "metric_refs": quality_metric_refs,
                "issue_counts": {key: int(value) for key, value in data_quality_facts.items()},
                "evidence_refs": [source_evidence],
            },
            "validation": {
                "status": "ready_to_share" if ready_to_share else "needs_review",
                "golden_status": "not_applicable",
                "unsupported_numeric_claims": 0,
                "metric_reference_coverage": 1,
                "checks": [
                    {
                        "id": "authoritative-metrics-deterministic",
                        "status": "passed",
                        "evidence_refs": [source_evidence],
                    },
                    {
                        "id": "comparison-evidence-linked",
                        "status": "passed" if comparisons else "warning",
                        "evidence_refs": sorted(
                            {fact.evidence_ref for fact in comparison_facts} or {source_evidence}
                        ),
                    },
                ],
            },
            "insights": insights,
            "recommendations": recommendations,
            "narratives": narratives,
            "evidence_sets": evidence_sets,
            "artifacts": [],
            "provenance": {
                "analytics_code_version": self._code_version,
                "deterministic_result_checksum_sha256": "0" * 64,
                "final_result_checksum_sha256": "0" * 64,
                "raw_source_artifact_ids": sorted(set(raw_source_artifact_ids)),
            },
        }
        deterministic_checksum = _checksum(result)
        result["provenance"]["deterministic_result_checksum_sha256"] = deterministic_checksum
        result["provenance"]["final_result_checksum_sha256"] = _checksum(result)
        return result

    @staticmethod
    def _source_evidence(evidence_sets: list[JsonObject]) -> str:
        try:
            return str(
                next(value for value in evidence_sets if value["kind"] == "source_manifest")[
                    "evidence_set_id"
                ]
            )
        except StopIteration as exc:
            raise ValueError("AnalysisResult V2 requires a source_manifest evidence set") from exc

    @staticmethod
    def _coverage(
        registry: _MetricRegistry,
        facts: list[JsonObject],
        evidence_ids: set[str],
    ) -> tuple[list[JsonObject], list[str]]:
        rows: list[JsonObject] = []
        assortment_refs: list[str] = []
        for fact in facts:
            retailer = str(fact["retailer_id"])
            evidence_ref = str(fact["evidence_ref"])
            if evidence_ref not in evidence_ids:
                raise ValueError(f"coverage references unknown evidence {evidence_ref!r}")
            metric_refs = []
            for field, label, unit in (
                ("offers", "Observed offers", "offers"),
                ("in_scope_offers", "Qualifying offers", "offers"),
                ("in_scope_zips", "Qualifying ZIPs", "zipcodes"),
                ("in_scope_stores", "Qualifying stores", "stores"),
            ):
                metric_id = f"coverage.{_id(retailer)}.{field.replace('in_scope_', 'qualifying_')}"
                metric_refs.append(
                    registry.add(
                        metric_id,
                        f"{retailer} {label}",
                        int(fact[field]),
                        unit,
                        "distinct deterministic coverage aggregation",
                        [evidence_ref],
                    )
                )
                if field == "in_scope_offers":
                    assortment_refs.append(metric_id)
            rows.append(
                {
                    "retailer_id": retailer,
                    "metric_refs": metric_refs,
                    "evidence_refs": [evidence_ref],
                }
            )
        return rows, assortment_refs

    @staticmethod
    def _comparison_modes(facts: list[ComparisonFact]) -> list[JsonObject]:
        seen: set[str] = set()
        modes: list[JsonObject] = []
        for fact in facts:
            if fact.profile_id in seen:
                continue
            seen.add(fact.profile_id)
            modes.append(
                {
                    "profile_id": fact.profile_id,
                    "label": fact.profile_label,
                    "geography": fact.geography,
                    "comparison_metric": fact.comparison_metric,
                    "dimensions": list(fact.dimensions),
                }
            )
        return modes

    @staticmethod
    def _comparisons(
        registry: _MetricRegistry,
        facts: list[ComparisonFact],
        benchmark_retailer: str,
    ) -> tuple[list[JsonObject], list[JsonObject], list[JsonObject], list[ComparisonInsightInput]]:
        comparisons: list[JsonObject] = []
        segment_rows: dict[str, JsonObject] = {}
        geography: list[JsonObject] = []
        insight_inputs: list[ComparisonInsightInput] = []
        for fact in facts:
            prefix = ".".join(
                (
                    "comparison",
                    _id(fact.competitor_id),
                    _id(fact.geography),
                    _id(fact.comparison_metric),
                    _id(fact.profile_id),
                    _id(fact.segment_id),
                )
            )
            values = {key: value for key, value in fact.values.items() if value is not None}
            metric_refs: dict[str, str] = {}
            matches = int(values.get("matches", 0))
            for field, raw_value in values.items():
                value = float(raw_value) if isinstance(raw_value, float) else int(raw_value)
                if field.endswith("_rate"):
                    numerator_name = field.removesuffix("_rate")
                    numerator = values.get(numerator_name)
                    unit = "rate"
                    denominator = matches
                elif field == "median_gap":
                    numerator = denominator = None
                    unit = "USD" if fact.comparison_metric == "package_price" else "USD_per_unit"
                elif field == "unique_geographies":
                    numerator = denominator = None
                    unit = "geographies"
                else:
                    numerator = denominator = None
                    unit = "matches"
                metric_refs[field] = registry.add(
                    f"{prefix}.{field}",
                    f"{fact.competitor_id} {fact.profile_label} {fact.segment_label} {field}",
                    value,
                    unit,
                    f"deterministic {fact.profile_label} comparison summary",
                    [fact.evidence_ref],
                    numerator=numerator,
                    denominator=denominator,
                )
            comparison_id = _id(f"{fact.competitor_id}-{fact.profile_id}-{fact.segment_id}")
            comparisons.append(
                {
                    "comparison_id": comparison_id,
                    "competitor_id": fact.competitor_id,
                    "profile_id": fact.profile_id,
                    "segment_id": fact.segment_id,
                    "metric_refs": list(metric_refs.values()),
                    "evidence_refs": [fact.evidence_ref],
                }
            )
            if fact.segment_id != "all":
                segment = segment_rows.setdefault(
                    fact.segment_id,
                    {
                        "segment_id": fact.segment_id,
                        "label": fact.segment_label,
                        "attributes": fact.attributes or {},
                        "metric_refs": [],
                        "evidence_refs": [],
                    },
                )
                segment["metric_refs"] = list(
                    dict.fromkeys([*segment["metric_refs"], *metric_refs.values()])
                )
                segment["evidence_refs"] = list(
                    dict.fromkeys([*segment["evidence_refs"], fact.evidence_ref])
                )
            if fact.geography == "radius" and fact.segment_id == "all":
                geography.append(
                    {
                        "id": comparison_id,
                        "profile_id": fact.profile_id,
                        "radius_miles": fact.radius_miles,
                        "metric_refs": list(metric_refs.values()),
                        "evidence_refs": [fact.evidence_ref],
                    }
                )
            insight_inputs.append(
                ComparisonInsightInput(
                    benchmark_id=benchmark_retailer,
                    competitor_id=fact.competitor_id,
                    profile_id=fact.profile_id,
                    profile_label=fact.profile_label,
                    segment_id=fact.segment_id,
                    segment_label=fact.segment_label,
                    values={key: float(value) for key, value in values.items()},
                    metric_refs=metric_refs,
                    evidence_refs=(fact.evidence_ref,),
                )
            )
        return comparisons, list(segment_rows.values()), geography, insight_inputs

    @staticmethod
    def _quality(
        registry: _MetricRegistry,
        facts: JsonObject,
        evidence_ref: str,
    ) -> list[str]:
        return [
            registry.add(
                f"quality.{_id(key)}",
                str(key).replace("_", " ").title(),
                int(value),
                "offers",
                "deterministic data-quality count",
                [evidence_ref],
            )
            for key, value in facts.items()
        ]

    @staticmethod
    def _deterministic_narratives(
        insights: list[JsonObject],
        recommendations: list[JsonObject],
        fallback_refs: list[str],
        fallback_evidence: list[str],
    ) -> JsonObject:
        summary_body = (
            " ".join(str(value["summary"]) for value in insights[:3])
            if insights
            else "No comparison signal met the configured deterministic insight threshold."
        )
        recommendation_body = (
            " ".join(str(value["action"]) for value in recommendations[:3])
            if recommendations
            else (
                "Continue monitoring until an evidence-backed action meets the "
                "configured threshold."
            )
        )
        recommendation_refs = (
            list(dict.fromkeys(ref for row in recommendations for ref in row["metric_refs"]))
            or fallback_refs
        )
        recommendation_evidence = (
            list(dict.fromkeys(ref for row in recommendations for ref in row["evidence_refs"]))
            or fallback_evidence
        )
        insight_refs = (
            list(dict.fromkeys(ref for row in insights[:3] for ref in row["metric_refs"]))
            or fallback_refs
        )
        insight_evidence = (
            list(dict.fromkeys(ref for row in insights[:3] for ref in row["evidence_refs"]))
            or fallback_evidence
        )
        return {
            "generation_mode": "deterministic",
            "agent_task_ids": [],
            "sections": [
                {
                    "id": "executive_summary",
                    "heading": "Executive Summary",
                    "body": summary_body,
                    "metric_refs": insight_refs,
                    "evidence_refs": insight_evidence,
                },
                {
                    "id": "recommendations",
                    "heading": "Recommended Actions",
                    "body": recommendation_body,
                    "metric_refs": recommendation_refs,
                    "evidence_refs": recommendation_evidence,
                },
            ],
        }


def evidence_set(
    evidence_set_id: str,
    kind: str,
    artifacts: list[tuple[str, str, int]],
) -> JsonObject:
    """Create a stable evidence manifest from artifact ID, checksum, and row count tuples."""

    ordered = sorted(artifacts)
    return {
        "evidence_set_id": evidence_set_id,
        "kind": kind,
        "row_count": sum(row_count for _, _, row_count in ordered),
        "checksum_sha256": _checksum(ordered),
    }
