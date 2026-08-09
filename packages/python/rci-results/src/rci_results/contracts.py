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
