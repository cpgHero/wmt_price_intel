"""Normative AnalysisResult validation and canonical serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rci_contracts import validate_instance
from rci_results.models import JsonObject


def canonical_result_bytes(document: JsonObject) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def result_checksum(document: JsonObject) -> str:
    return hashlib.sha256(canonical_result_bytes(document)).hexdigest()


def has_verified_local_availability_contract(document: JsonObject) -> bool:
    """Return whether a V2 result has a complete local-availability trust contract.

    JSON Schema establishes the shape of AnalysisResult V2, but the public trust
    boundary also depends on relationships between retailer scope, coverage
    metrics, validation evidence, and governed unavailability.  Keep that
    fail-closed predicate next to the canonical result validator so publication
    and API delivery paths use exactly the same definition.
    """

    if document.get("schema_version") != "2.0.0":
        return False
    validation = document.get("validation")
    if not isinstance(validation, dict) or validation.get("status") != "ready_to_share":
        return False
    checks = validation.get("checks")
    if not isinstance(checks, list):
        return False
    availability_checks = [
        check
        for check in checks
        if isinstance(check, dict) and check.get("id") == "verified-local-availability"
    ]
    if len(availability_checks) != 1 or availability_checks[0].get("status") != "passed":
        return False
    availability_evidence_refs = availability_checks[0].get("evidence_refs")
    if not isinstance(availability_evidence_refs, list) or not availability_evidence_refs:
        return False
    availability_evidence = {str(ref) for ref in availability_evidence_refs}

    evidence_sets = document.get("evidence_sets")
    if not isinstance(evidence_sets, list):
        return False
    evidence_id_values = [
        str(row.get("evidence_set_id"))
        for row in evidence_sets
        if isinstance(row, dict) and row.get("evidence_set_id")
    ]
    if len(evidence_id_values) != len(evidence_sets) or len(evidence_id_values) != len(
        set(evidence_id_values)
    ):
        return False
    evidence_ids = set(evidence_id_values)
    if not availability_evidence <= evidence_ids:
        return False

    benchmark = document.get("benchmark_retailer")
    competitors = document.get("competitors")
    source = document.get("source")
    if (
        not isinstance(benchmark, str)
        or not benchmark
        or not isinstance(competitors, list)
        or not isinstance(source, dict)
    ):
        return False
    competitor_values = [value for value in competitors if isinstance(value, str) and value]
    if (
        len(competitor_values) != len(competitors)
        or len(competitor_values) != len(set(competitor_values))
        or benchmark in competitor_values
    ):
        return False
    unavailable_value = source.get("unavailable_retailers", [])
    if not isinstance(unavailable_value, list):
        return False
    unavailable_values = [value for value in unavailable_value if isinstance(value, str) and value]
    unavailable = set(unavailable_values)
    competitor_ids = set(competitor_values)
    if (
        len(unavailable_values) != len(unavailable_value)
        or len(unavailable_values) != len(unavailable)
        or benchmark in unavailable
        or not unavailable <= competitor_ids
    ):
        return False
    required_retailers = {benchmark, *(competitor_ids - unavailable)}

    coverage = document.get("coverage")
    metrics = document.get("metrics")
    if not isinstance(coverage, list) or not isinstance(metrics, list):
        return False
    coverage_ids = [
        str(row.get("retailer_id"))
        for row in coverage
        if isinstance(row, dict) and row.get("retailer_id")
    ]
    if (
        len(coverage_ids) != len(coverage)
        or len(coverage_ids) != len(set(coverage_ids))
        or set(coverage_ids) != required_retailers
    ):
        return False
    coverage_by_retailer = {
        str(row["retailer_id"]): row for row in coverage if isinstance(row, dict)
    }
    metric_ids = [
        str(row.get("metric_id"))
        for row in metrics
        if isinstance(row, dict) and row.get("metric_id")
    ]
    if len(metric_ids) != len(metrics) or len(metric_ids) != len(set(metric_ids)):
        return False
    metrics_by_id = {str(row["metric_id"]): row for row in metrics if isinstance(row, dict)}

    covered_evidence: set[str] = set()
    required_fields = {
        "verified_available_offers": "offers",
        "verified_available_zips": "zipcodes",
        "verified_available_stores": "stores",
    }
    for retailer in required_retailers:
        coverage_row = coverage_by_retailer[retailer]
        coverage_evidence_refs = coverage_row.get("evidence_refs")
        if not isinstance(coverage_evidence_refs, list) or not coverage_evidence_refs:
            return False
        coverage_evidence = {str(ref) for ref in coverage_evidence_refs}
        if not coverage_evidence <= evidence_ids:
            return False
        covered_evidence.update(coverage_evidence)
        metric_refs = coverage_row.get("metric_refs")
        if not isinstance(metric_refs, list):
            return False
        metric_ref_ids = {str(ref) for ref in metric_refs}
        if len(metric_ref_ids) != len(metric_refs):
            return False
        for field, expected_unit in required_fields.items():
            metric_id = f"coverage.{retailer}.{field}"
            if metric_id not in metric_ref_ids:
                return False
            metric = metrics_by_id.get(metric_id)
            if not isinstance(metric, dict) or metric.get("unit") != expected_unit:
                return False
            metric_evidence_refs = metric.get("evidence_refs")
            if not isinstance(metric_evidence_refs, list) or not metric_evidence_refs:
                return False
            metric_evidence = {str(ref) for ref in metric_evidence_refs}
            if not coverage_evidence <= metric_evidence or not metric_evidence <= evidence_ids:
                return False
            value = metric.get("value")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False
            if field == "verified_available_offers" and value == 0:
                return False
    return covered_evidence <= availability_evidence


class AnalysisResultValidator:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def validate(self, document: dict[str, Any]) -> JsonObject:
        schema_version = str(document.get("schema_version", ""))
        schema_name = (
            "analysis-result-v2.schema.json"
            if schema_version == "2.0.0"
            else "analysis-result.schema.json"
        )
        validate_instance(
            self._root,
            schema_name,
            document,
            label="AnalysisResult",
        )
        if schema_version == "2.0.0":
            self._validate_v2_references(document)
        canonical = json.loads(canonical_result_bytes(document))
        assert isinstance(canonical, dict)
        return canonical

    @staticmethod
    def _validate_v2_references(document: dict[str, Any]) -> None:
        metrics = document["metrics"]
        evidence_sets = document["evidence_sets"]
        metric_ids = [str(metric["metric_id"]) for metric in metrics]
        evidence_ids = [str(evidence["evidence_set_id"]) for evidence in evidence_sets]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("AnalysisResult V2 metric IDs must be unique")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("AnalysisResult V2 evidence-set IDs must be unique")
        known_metrics = set(metric_ids)
        known_evidence = set(evidence_ids)
        metric_references: list[str] = []
        evidence_references: list[str] = []

        def collect(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "metric_refs" and isinstance(child, list):
                        metric_references.extend(str(item) for item in child)
                    elif key == "evidence_refs" and isinstance(child, list):
                        evidence_references.extend(str(item) for item in child)
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(document)
        unknown_metrics = set(metric_references) - known_metrics
        unknown_evidence = set(evidence_references) - known_evidence
        if unknown_metrics:
            raise ValueError(
                f"AnalysisResult V2 references unknown metrics {sorted(unknown_metrics)}"
            )
        if unknown_evidence:
            raise ValueError(
                f"AnalysisResult V2 references unknown evidence sets {sorted(unknown_evidence)}"
            )


class ReportViewValidator:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def validate(self, document: dict[str, Any]) -> JsonObject:
        validate_instance(
            self._root,
            "report-view.schema.json",
            document,
            label="ReportView",
        )
        canonical = json.loads(canonical_result_bytes(document))
        assert isinstance(canonical, dict)
        return canonical
