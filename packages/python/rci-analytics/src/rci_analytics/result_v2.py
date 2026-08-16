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
_SUMMARY_FIELDS = (
    "matches",
    "unique_geographies",
    "benchmark_lower",
    "competitor_lower",
    "parity",
    "benchmark_lower_rate",
    "competitor_lower_rate",
    "parity_rate",
    "benchmark_median",
    "competitor_median",
    "median_gap",
    "mean_gap",
)


def _id(value: object) -> str:
    return _SAFE_ID.sub("-", str(value).casefold()).strip("-") or "unknown"


def _checksum(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def _display_id(value: object) -> str:
    return str(value).replace("_", " ").replace("-", " ").strip().title()


def _metric_field(metric_id: str) -> str | None:
    normalized = metric_id.replace("-", "_").casefold()
    return next(
        (
            field
            for field in sorted(_SUMMARY_FIELDS, key=len, reverse=True)
            if normalized.endswith(field)
        ),
        None,
    )


def _metric_display(metric: JsonObject) -> str:
    value = metric["value"]
    unit = str(metric["unit"])
    if not isinstance(value, int | float) or isinstance(value, bool):
        return str(value)
    if unit == "rate":
        return f"{float(value):.1%}"
    if unit.startswith("USD"):
        amount = f"-${abs(float(value)):,.2f}" if float(value) < 0 else f"${float(value):,.2f}"
        suffix = unit.removeprefix("USD_per_").replace("_", " ")
        return f"{amount} per {suffix}" if unit.startswith("USD_per_") else amount
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}"
    return f"{float(value):,.2f}"


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
        retailer_packs: list[JsonObject] | None = None,
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
            source=source,
            benchmark_retailer=benchmark_retailer,
            coverage=coverage,
            comparison_modes=comparison_modes,
            comparisons=comparisons,
            segments=segments,
            geographic_sensitivity=geography,
            metrics=registry.documents,
            data_quality_facts=data_quality_facts,
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
            "retailer_packs": list(retailer_packs or []),
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
                (
                    "seller_verified_first_party_offers",
                    "First-party seller verified offers",
                    "offers",
                ),
                ("seller_unverified_offers", "Seller-unverified retained offers", "offers"),
                ("third_party_excluded_offers", "Third-party excluded offers", "offers"),
            ):
                if field not in fact:
                    continue
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

    def _comparison_modes(self, facts: list[ComparisonFact]) -> list[JsonObject]:
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
                    "relationship_scope_policy": dict(
                        self._pack.profile(fact.profile_id).get(
                            "relationship_scope_policy",
                            {
                                "default_scope_mode": "global",
                                "allow_scoped_reuse": False,
                                "relationship_role": "primary",
                                "conflict_behavior": "exclude_from_price_comparison",
                                "comparison_context_grain": "benchmark_location",
                                "future_location_policy": "require_review",
                            },
                        )
                    ),
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
                elif field in {
                    "benchmark_median",
                    "competitor_median",
                    "median_gap",
                    "mean_gap",
                }:
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

    def _deterministic_narratives(
        self,
        insights: list[JsonObject],
        recommendations: list[JsonObject],
        fallback_refs: list[str],
        fallback_evidence: list[str],
        *,
        source: JsonObject,
        benchmark_retailer: str,
        coverage: list[JsonObject],
        comparison_modes: list[JsonObject],
        comparisons: list[JsonObject],
        segments: list[JsonObject],
        geographic_sensitivity: list[JsonObject],
        metrics: list[JsonObject],
        data_quality_facts: JsonObject,
    ) -> JsonObject:
        metric_index = {str(metric["metric_id"]): metric for metric in metrics}
        mode_index = {str(mode["profile_id"]): mode for mode in comparison_modes}
        segment_index = {str(segment["segment_id"]): segment for segment in segments}

        def refs_for(rows: list[JsonObject]) -> tuple[list[str], list[str]]:
            metric_refs = (
                list(dict.fromkeys(str(ref) for row in rows for ref in row.get("metric_refs", [])))
                or fallback_refs
            )
            evidence_refs = (
                list(
                    dict.fromkeys(
                        str(ref)
                        for metric_ref in metric_refs
                        for ref in metric_index.get(metric_ref, {}).get("evidence_refs", [])
                    )
                )
                or fallback_evidence
            )
            return metric_refs, evidence_refs

        def values_for(row: JsonObject) -> dict[str, JsonObject]:
            return {
                field: metric_index[str(ref)]
                for ref in row.get("metric_refs", [])
                if str(ref) in metric_index and (field := _metric_field(str(ref))) is not None
            }

        def comparison_sentence(row: JsonObject) -> str:
            values = values_for(row)
            competitor = _display_id(row["competitor_id"])
            mode = mode_index.get(str(row["profile_id"]), {})
            profile = str(mode.get("label", "validated comparison"))
            segment = segment_index.get(str(row["segment_id"]), {})
            segment_label = str(segment.get("label", "all comparable items"))
            benchmark_rate = float(values.get("benchmark_lower_rate", {}).get("value", 0))
            competitor_rate = float(values.get("competitor_lower_rate", {}).get("value", 0))
            parity_rate = float(values.get("parity_rate", {}).get("value", 0))
            if parity_rate >= benchmark_rate and parity_rate >= competitor_rate:
                rate = values.get("parity_rate")
                outcome = "Prices are at parity"
            elif benchmark_rate >= competitor_rate:
                winner = _display_id(benchmark_retailer)
                rate = values.get("benchmark_lower_rate")
                outcome = f"{winner} is lower"
            else:
                winner = competitor
                rate = values.get("competitor_lower_rate")
                outcome = f"{winner} is lower"
            matches = values.get("matches")
            if rate is None or matches is None:
                return f"{profile} evidence is available for {competitor} in {segment_label}."
            sentence = (
                f"{outcome} in {_metric_display(rate)} of "
                f"{_metric_display(matches)} {profile.lower()} matches for {segment_label}."
            )
            median_gap = values.get("median_gap")
            if median_gap is not None:
                gap_value = float(median_gap["value"])
                if gap_value < 0:
                    sentence += (
                        f" {competitor} was ${abs(gap_value):,.2f} lower at the paired median."
                    )
                elif gap_value > 0:
                    sentence += (
                        f" {_display_id(benchmark_retailer)} was ${gap_value:,.2f} lower "
                        "at the paired median."
                    )
                else:
                    sentence += " The paired median price difference was $0.00."
            return sentence

        overall = [row for row in comparisons if str(row["segment_id"]) == "all"]
        segment_rows = [row for row in comparisons if str(row["segment_id"]) != "all"]

        def row_score(row: JsonObject) -> tuple[float, float, str]:
            values = values_for(row)
            matches = float(values.get("matches", {}).get("value", 0))
            benchmark_rate = float(values.get("benchmark_lower_rate", {}).get("value", 0))
            competitor_rate = float(values.get("competitor_lower_rate", {}).get("value", 0))
            return matches, abs(benchmark_rate - competitor_rate), str(row["comparison_id"])

        decision_rules = self._pack.reporting.get("decision_rules", {})
        preferred_profile = str(decision_rules.get("preferred_scorecard_profile_id", ""))
        profile_priority = {
            str(profile_id): index
            for index, profile_id in enumerate(decision_rules.get("profile_priority", []))
        }

        def headline_rank(row: JsonObject) -> tuple[int, int, int, float, float, str]:
            profile_id = str(row["profile_id"])
            mode = mode_index.get(profile_id, {})
            values = values_for(row)
            matches = float(values.get("matches", {}).get("value", 0))
            benchmark_rate = float(values.get("benchmark_lower_rate", {}).get("value", 0))
            competitor_rate = float(values.get("competitor_lower_rate", {}).get("value", 0))
            return (
                0 if profile_id == preferred_profile else 1,
                profile_priority.get(profile_id, len(profile_priority)),
                0 if str(mode.get("geography")) == "exact_zip" else 1,
                -matches,
                -abs(benchmark_rate - competitor_rate),
                str(row["comparison_id"]),
            )

        overall_by_competitor: dict[str, list[JsonObject]] = {}
        for competitor in sorted({str(row["competitor_id"]) for row in overall}):
            rows = [row for row in overall if str(row["competitor_id"]) == competitor]
            overall_by_competitor[competitor] = sorted(rows, key=headline_rank)
        headline_rows = [rows[0] for rows in overall_by_competitor.values() if rows]
        headline_profiles = {
            (str(row["competitor_id"]), str(row["profile_id"])) for row in headline_rows
        }
        headline_segment_rows = [
            row
            for row in segment_rows
            if (str(row["competitor_id"]), str(row["profile_id"])) in headline_profiles
        ]
        ranked_segments = sorted(headline_segment_rows or segment_rows, key=row_score, reverse=True)
        high_signal_segments = ranked_segments[:4]

        source_metric = metric_index.get("source.total_rows")
        source_sentence = (
            f"The analysis processed {_metric_display(source_metric)} source rows"
            if source_metric is not None
            else "The analysis processed the complete contracted source set"
        )
        source_sentence += (
            " without intentional sampling."
            if not bool(source.get("sampling"))
            else " using the explicitly recorded sampling configuration."
        )
        summary_parts = [source_sentence]
        summary_parts.extend(comparison_sentence(row) for row in headline_rows[:3])
        if high_signal_segments:
            summary_parts.append(
                "The most decision-relevant segment evidence includes "
                + "; ".join(comparison_sentence(row) for row in high_signal_segments[:2])
            )
        elif insights:
            headline_evidence = {
                str(ref) for row in headline_rows for ref in row.get("evidence_refs", [])
            }
            summary_parts.extend(
                str(value["summary"])
                for value in insights
                if headline_evidence.intersection(
                    str(ref) for ref in value.get("evidence_refs", [])
                )
            )
        summary_rows = [*headline_rows[:3], *high_signal_segments[:2]]
        summary_refs, summary_evidence = refs_for(summary_rows)
        if source_metric is not None:
            summary_refs = list(dict.fromkeys(["source.total_rows", *summary_refs]))
            summary_evidence = list(
                dict.fromkeys([*source_metric.get("evidence_refs", []), *summary_evidence])
            )

        coverage_parts = [source_sentence]
        for row in coverage:
            retailer = _display_id(row["retailer_id"])
            selected = [
                metric_index[str(ref)]
                for ref in row["metric_refs"]
                if str(ref) in metric_index
                and (str(ref).endswith("qualifying_zips") or str(ref).endswith("qualifying_stores"))
            ]
            if selected:
                details = ", ".join(
                    f"{_metric_display(metric)} {str(metric['unit']).replace('zipcodes', 'ZIPs')}"
                    for metric in selected
                )
                coverage_parts.append(
                    f"{retailer} contributes {details} to the qualifying footprint."
                )
        coverage_refs, coverage_evidence = refs_for(coverage)

        exact_rows = [
            row
            for row in comparisons
            if mode_index.get(str(row["profile_id"]), {}).get("comparison_metric")
            == "package_price"
            and mode_index.get(str(row["profile_id"]), {}).get("geography") != "radius"
        ]
        normalized_rows = [
            row
            for row in comparisons
            if mode_index.get(str(row["profile_id"]), {}).get("comparison_metric")
            != "package_price"
            and mode_index.get(str(row["profile_id"]), {}).get("geography") != "radius"
        ]
        exact_selected = sorted(exact_rows, key=row_score, reverse=True)[:5]
        normalized_selected = sorted(normalized_rows, key=row_score, reverse=True)[:5]
        exact_body = " ".join(comparison_sentence(row) for row in exact_selected) or (
            "No exact-package comparison met the configured reporting requirements."
        )
        normalized_body = (
            " ".join(comparison_sentence(row) for row in normalized_selected)
            or "No defensible normalized-unit comparison was available."
        )
        exact_refs, exact_evidence = refs_for(exact_selected)
        normalized_refs, normalized_evidence = refs_for(normalized_selected)

        reversal_parts: list[str] = []
        reversal_rows: list[JsonObject] = []
        grouped: dict[tuple[str, str], list[JsonObject]] = {}
        for row in segment_rows:
            grouped.setdefault((str(row["competitor_id"]), str(row["segment_id"])), []).append(row)
        for (competitor, segment_id), rows in grouped.items():
            directions = set()
            metrics_seen = set()
            for row in rows:
                values = values_for(row)
                benchmark_rate = float(values.get("benchmark_lower_rate", {}).get("value", 0))
                competitor_rate = float(values.get("competitor_lower_rate", {}).get("value", 0))
                parity_rate = float(values.get("parity_rate", {}).get("value", 0))
                directions.add(
                    "parity"
                    if parity_rate >= benchmark_rate and parity_rate >= competitor_rate
                    else "benchmark"
                    if benchmark_rate >= competitor_rate
                    else "competitor"
                )
                metrics_seen.add(
                    str(
                        mode_index.get(str(row["profile_id"]), {}).get(
                            "comparison_metric", "unknown"
                        )
                    )
                )
            if len(directions) > 1 and len(metrics_seen) > 1:
                segment = str(segment_index.get(segment_id, {}).get("label", segment_id))
                reversal_parts.append(
                    f"The price winner changes by comparison lens for {segment} against "
                    f"{_display_id(competitor)}; keep package and normalized conclusions separate."
                )
                reversal_rows.extend(rows)
        segment_body = (
            " ".join(
                [
                    *(comparison_sentence(row) for row in high_signal_segments),
                    *reversal_parts[:3],
                ]
            )
            or "No segment-specific signal met the configured reporting threshold."
        )
        segment_refs, segment_evidence = refs_for([*high_signal_segments, *reversal_rows[:6]])

        proximity_ids = {str(row["id"]) for row in geographic_sensitivity}
        proximity_rows = [row for row in comparisons if str(row["comparison_id"]) in proximity_ids]
        proximity_body = (
            " ".join(comparison_sentence(row) for row in proximity_rows[:4])
            or "No configured proximity sensitivity result was available."
        )
        proximity_refs, proximity_evidence = refs_for(proximity_rows[:4])

        recommendation_body = (
            " ".join(
                f"{index}. {value['action']} {value.get('rationale', '')}".strip()
                for index, value in enumerate(recommendations[:5], start=1)
            )
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
        quality_refs = [metric_id for metric_id in metric_index if metric_id.startswith("quality.")]
        quality_evidence = (
            list(
                dict.fromkeys(
                    str(ref)
                    for metric_id in quality_refs
                    for ref in metric_index[metric_id]["evidence_refs"]
                )
            )
            or fallback_evidence
        )
        issue_total = sum(int(value) for value in data_quality_facts.values())
        quality_body = (
            "The deterministic quality checks recorded no normalization, review, or price-capture "
            "exceptions in the configured issue set."
            if issue_total == 0
            else (
                "The deterministic quality checks recorded "
                f"{issue_total:,} issues across the configured validation categories. "
                "Review the cited issue metrics before acting on affected segments."
            )
        )
        headline_attributes = [
            str(value).replace("_", " ")
            for value in self._pack.reporting.get("headline_segments", [])
        ]
        products_body = (
            "Product interpretation preserves "
            + ", ".join(headline_attributes)
            + " so unlike items are not blended into a category average."
            if headline_attributes
            else (
                "Product interpretation follows the Product Pack's configured comparison "
                "attributes."
            )
        )
        methodology_body = (
            source_sentence
            + " Comparison modes remain separate: "
            + "; ".join(
                f"{mode['label']} ({str(mode['comparison_metric']).replace('_', ' ')}, "
                f"{str(mode['geography']).replace('_', ' ')})"
                for mode in comparison_modes
            )
            + ". Required caveats: "
            + "; ".join(str(value) for value in self._pack.reporting["required_caveats"])
            + "."
        )

        def section(
            section_id: str,
            heading: str,
            body: str,
            metric_refs: list[str],
            evidence_refs: list[str],
            topics: list[str],
        ) -> JsonObject:
            return {
                "id": section_id,
                "heading": heading,
                "body": body,
                "topic_refs": topics,
                "storyline_refs": [f"deterministic.{section_id}"],
                "metric_refs": metric_refs or fallback_refs,
                "evidence_refs": evidence_refs or fallback_evidence,
            }

        return {
            "generation_mode": "deterministic",
            "agent_task_ids": [],
            "sections": [
                section(
                    "executive_summary",
                    "Executive Summary",
                    " ".join(summary_parts),
                    summary_refs,
                    summary_evidence,
                    ["data_scope", "exact_price", "normalized_price", "segment_drivers"],
                ),
                section(
                    "coverage",
                    "Geographic Footprint",
                    " ".join(coverage_parts),
                    coverage_refs,
                    coverage_evidence,
                    ["data_scope", "footprint", "geography", "fulfillment"],
                ),
                section(
                    "exact_price",
                    "Exact Package Price Position",
                    exact_body,
                    exact_refs,
                    exact_evidence,
                    ["exact_price", "segment_drivers"],
                ),
                section(
                    "price_position",
                    "Price Position",
                    exact_body,
                    exact_refs,
                    exact_evidence,
                    ["exact_price", "segment_drivers"],
                ),
                section(
                    "normalized_price",
                    "Normalized Unit-Price Position",
                    normalized_body,
                    normalized_refs,
                    normalized_evidence,
                    ["normalized_price", "segment_drivers", "segment_reversals"],
                ),
                section(
                    "segments",
                    "Segment Drivers and Reversals",
                    segment_body,
                    segment_refs,
                    segment_evidence,
                    ["normalized_price", "segment_drivers", "segment_reversals"],
                ),
                section(
                    "proximity",
                    "Geographic Sensitivity",
                    proximity_body,
                    proximity_refs,
                    proximity_evidence,
                    ["geography"],
                ),
                section(
                    "products",
                    "Products and Assortment",
                    products_body,
                    coverage_refs,
                    coverage_evidence,
                    ["brand_assortment", "segment_drivers"],
                ),
                section(
                    "recommendations",
                    "Recommended Actions",
                    recommendation_body,
                    recommendation_refs,
                    recommendation_evidence,
                    ["actions"],
                ),
                section(
                    "quality",
                    "Data Quality",
                    quality_body,
                    quality_refs,
                    quality_evidence,
                    ["caveats"],
                ),
                section(
                    "methodology",
                    "Methodology and Required Caveats",
                    methodology_body,
                    list(dict.fromkeys([*fallback_refs, *quality_refs])),
                    list(dict.fromkeys([*fallback_evidence, *quality_evidence])),
                    ["data_scope", "caveats"],
                ),
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
