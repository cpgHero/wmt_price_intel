"""Versioned report-blueprint loading and analytics-free presentation projection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from rci_contracts import ContractError, validate_instance
from rci_results.models import ArtifactType, JsonObject


@dataclass(frozen=True, slots=True)
class ReportBlueprint:
    id: str
    version: str
    product_pack_id: str
    product_pack_version: str
    document: JsonObject

    @property
    def sections(self) -> tuple[JsonObject, ...]:
        return tuple(dict(section) for section in self.document["sections"])

    def artifact_profile(self, artifact_type: ArtifactType) -> JsonObject:
        try:
            return next(
                dict(profile)
                for profile in self.document["artifact_profiles"]
                if profile["artifact_type"] == artifact_type
            )
        except StopIteration as exc:
            raise ValueError(
                f"report blueprint {self.id!r} does not define {artifact_type!r}"
            ) from exc


class ReportBlueprintLoader:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def load(self, blueprint_id: str) -> ReportBlueprint:
        path = self._root / "report-blueprints" / f"{blueprint_id}.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"could not read report blueprint {path}: {exc}") from exc
        validate_instance(
            self._root,
            "report-blueprint.schema.json",
            document,
            label=str(path),
        )
        self._validate_semantics(document)
        product_pack = document["product_pack"]
        return ReportBlueprint(
            id=str(document["id"]),
            version=str(document["version"]),
            product_pack_id=str(product_pack["id"]),
            product_pack_version=str(product_pack["version"]),
            document=document,
        )

    def load_for_result(self, result: JsonObject) -> tuple[ReportBlueprint, JsonObject]:
        product_pack_ref = result.get("product_pack")
        if not isinstance(product_pack_ref, dict):
            raise ContractError("AnalysisResult has no Product Pack reference")
        blueprint_ref = product_pack_ref.get("report_blueprint")
        if not isinstance(blueprint_ref, dict):
            raise ContractError("AnalysisResult V2 has no report blueprint reference")
        blueprint = self.load(str(blueprint_ref["id"]))
        if blueprint.version != str(blueprint_ref["version"]):
            raise ContractError("AnalysisResult report blueprint version does not match")
        if (blueprint.product_pack_id, blueprint.product_pack_version) != (
            str(product_pack_ref["id"]),
            str(product_pack_ref["version"]),
        ):
            raise ContractError(
                "report blueprint does not belong to the AnalysisResult Product Pack"
            )
        pack_path = self._root / "product-packs" / f"{blueprint.product_pack_id}.json"
        try:
            product_pack = json.loads(pack_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"could not read Product Pack {pack_path}: {exc}") from exc
        if str(product_pack.get("version")) != blueprint.product_pack_version:
            raise ContractError("report blueprint Product Pack version does not match runtime data")
        return blueprint, product_pack

    @staticmethod
    def _validate_semantics(document: JsonObject) -> None:
        sections = document["sections"]
        section_ids = [str(section["id"]) for section in sections]
        if len(section_ids) != len(set(section_ids)):
            raise ContractError("report blueprint section IDs must be unique")
        known = set(section_ids)
        artifact_types: list[str] = []
        for profile in document["artifact_profiles"]:
            artifact_types.append(str(profile["artifact_type"]))
            unknown = set(str(value) for value in profile["section_ids"]) - known
            if unknown:
                raise ContractError(
                    f"report artifact {profile['artifact_type']} references unknown sections "
                    f"{sorted(unknown)}"
                )
        if len(artifact_types) != len(set(artifact_types)):
            raise ContractError("report blueprint artifact types must be unique")
        required = {"html", "xlsx", "leadership_email", "audit_zip"}
        if set(artifact_types) != required:
            raise ContractError("report blueprint must define all four artifact profiles")


class ReportProjector:
    """Resolve references into display records without computing analytical facts."""

    def project(
        self,
        result: JsonObject,
        blueprint: ReportBlueprint,
        product_pack: JsonObject,
        *,
        artifact_type: ArtifactType | None = None,
    ) -> JsonObject:
        selected_ids = (
            set(str(value) for value in blueprint.artifact_profile(artifact_type)["section_ids"])
            if artifact_type is not None
            else {str(section["id"]) for section in blueprint.sections}
        )
        metric_index = {
            str(metric["metric_id"]): dict(metric) for metric in self._rows(result.get("metrics"))
        }
        evidence_sets = self._rows(result.get("evidence_sets"))
        sections = [
            self._section(result, section, product_pack, metric_index, evidence_sets)
            for section in blueprint.sections
            if str(section["id"]) in selected_ids
        ]
        return {
            "analysis_id": result["analysis_id"],
            "generated_at": result["generated_at"],
            "benchmark_retailer": result["benchmark_retailer"],
            "competitors": result["competitors"],
            "product_pack": {
                "id": product_pack["id"],
                "name": product_pack["name"],
                "version": product_pack["version"],
            },
            "blueprint": {"id": blueprint.id, "version": blueprint.version},
            "sections": sections,
        }

    def worksheet_rows(
        self,
        result: JsonObject,
        source: str,
        product_pack: JsonObject,
    ) -> list[JsonObject]:
        value = result.get(source)
        if isinstance(value, list):
            return self._rows(value)
        if isinstance(value, dict):
            return [dict(value)]
        if source == "methodology":
            return [
                {
                    "source": result.get("source", {}),
                    "provenance": result.get("provenance", {}),
                    "required_caveats": product_pack.get("reporting", {}).get(
                        "required_caveats", []
                    ),
                }
            ]
        return [
            evidence
            for evidence in self._rows(result.get("evidence_sets"))
            if evidence.get("kind") == source
        ]

    def _section(
        self,
        result: JsonObject,
        section: JsonObject,
        product_pack: JsonObject,
        metric_index: dict[str, JsonObject],
        evidence_sets: list[JsonObject],
    ) -> JsonObject:
        selectors = [str(value) for value in section["metric_selectors"]]
        selected_metrics = [
            metric
            for metric_id, metric in metric_index.items()
            if any(fnmatchcase(metric_id, selector) for selector in selectors)
        ]
        evidence_kinds = set(str(value) for value in section["evidence_kinds"])
        selected_evidence = [
            evidence for evidence in evidence_sets if str(evidence.get("kind")) in evidence_kinds
        ]
        kind = str(section["kind"])
        records = self._records_for_kind(
            result, kind, {str(m["metric_id"]) for m in selected_metrics}
        )
        narrative = None
        narrative_id = section.get("narrative_section_id")
        narratives = result.get("narratives", {})
        if narrative_id and isinstance(narratives, dict):
            narrative = next(
                (
                    dict(value)
                    for value in self._rows(narratives.get("sections"))
                    if value.get("id") == narrative_id
                ),
                None,
            )
        if kind == "methodology":
            records = [
                {
                    "source": result.get("source", {}),
                    "required_caveats": product_pack.get("reporting", {}).get(
                        "required_caveats", []
                    ),
                    "provenance": result.get("provenance", {}),
                }
            ]
        empty = not (records or selected_metrics or narrative)
        return {
            "id": section["id"],
            "title": section["title"],
            "kind": kind,
            "visualization": section.get("visualization", "none"),
            "required": section["required"],
            "empty": empty,
            "empty_state": section.get("empty_state"),
            "metrics": selected_metrics,
            "records": records,
            "evidence_sets": selected_evidence,
            "narrative": narrative,
        }

    def _records_for_kind(
        self,
        result: JsonObject,
        kind: str,
        selected_metric_ids: set[str],
    ) -> list[JsonObject]:
        sources = {
            "executive_summary": "insights",
            "kpi_strip": "metrics",
            "coverage": "coverage",
            "price_position": "comparisons",
            "segment_analysis": "segments",
            "geographic_sensitivity": "geographic_sensitivity",
            "assortment": "assortment",
            "product_table": "evidence_sets",
            "recommendations": "recommendations",
        }
        if kind == "data_quality":
            return [
                {
                    "data_quality": result.get("data_quality", {}),
                    "validation": result.get("validation", {}),
                }
            ]
        source = sources.get(kind)
        if source is None:
            return []
        rows = self._rows(result.get(source))
        if kind == "kpi_strip":
            return [row for row in rows if str(row.get("metric_id")) in selected_metric_ids]
        if kind in {"price_position", "segment_analysis", "coverage"} and selected_metric_ids:
            return [
                row
                for row in rows
                if selected_metric_ids.intersection(
                    str(value) for value in row.get("metric_refs", [])
                )
            ]
        return rows

    @staticmethod
    def _rows(value: object) -> list[JsonObject]:
        if not isinstance(value, list):
            return []
        return [dict(row) for row in value if isinstance(row, dict)]
