"""Versioned report-blueprint loading and analytics-free presentation projection."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from rci_contracts import ContractError, validate_instance
from rci_results.models import ArtifactType, JsonObject


def _attribute_aliases(attribute: JsonObject) -> set[str]:
    name = str(attribute.get("name", "")).replace("_", " ").strip()
    label = str(attribute.get("label", "")).strip()
    aliases = {value.casefold() for value in (name, label) if value}
    aliases.update(value.replace("percentage", "pct") for value in tuple(aliases))
    return aliases


def _attribute_pattern(attribute: JsonObject, alias: str) -> re.Pattern[str]:
    data_type = str(attribute.get("data_type", "string"))
    if data_type == "number":
        value_pattern = r"-?(?:\d+(?:\.\d+)?|\.\d+)"
    elif data_type == "boolean":
        value_pattern = r"(?:true|false)"
    elif data_type == "enum":
        allowed = sorted(
            (
                re.escape(str(value).replace("_", " "))
                for value in attribute.get("allowed_values", [])
            ),
            key=len,
            reverse=True,
        )
        value_pattern = rf"(?:{'|'.join(allowed)})" if allowed else r"[^/]+"
    else:
        value_pattern = r"[^/]+"
    return re.compile(rf"\b{re.escape(alias)}\s*:\s*({value_pattern})", flags=re.IGNORECASE)


def _format_attribute(attribute: JsonObject, raw_value: str) -> str:
    value = raw_value.strip()
    label = str(attribute.get("label") or attribute.get("name") or "attribute").casefold()
    unit = str(attribute.get("unit", "")).casefold()
    data_type = str(attribute.get("data_type", "string"))
    if data_type == "boolean":
        return label if value.casefold() == "true" else f"non-{label.replace(' ', '-')}"
    if data_type == "number":
        rendered = f"{float(value):g}"
        if unit == "percent":
            return f"{rendered}% {label.removesuffix(' percentage')}"
        return f"{rendered} {unit or label}".strip()
    return value.replace("_", " ").casefold()


def _merchant_text(
    value: object,
    retailer_names: Mapping[str, str],
    product_pack: JsonObject,
) -> object:
    if not isinstance(value, str):
        return value
    rendered = value
    for retailer_id, display_name in sorted(retailer_names.items(), key=lambda row: -len(row[0])):
        rendered = rendered.replace(retailer_id, display_name)
    for attribute in product_pack.get("attributes", []):
        if not isinstance(attribute, dict):
            continue
        for alias in sorted(_attribute_aliases(attribute), key=len, reverse=True):
            pattern = _attribute_pattern(attribute, alias)

            def replace_attribute(match: re.Match[str], definition: JsonObject = attribute) -> str:
                return _format_attribute(definition, match.group(1))

            rendered = pattern.sub(replace_attribute, rendered)
    return re.sub(r"\s+", " ", rendered).strip()


def _merchant_record(
    row: JsonObject,
    retailer_names: Mapping[str, str],
    product_pack: JsonObject,
) -> JsonObject:
    def merchant_value(value: object) -> object:
        if isinstance(value, dict):
            return {key: merchant_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [merchant_value(item) for item in value]
        return _merchant_text(value, retailer_names, product_pack)

    return {key: merchant_value(value) for key, value in row.items()}


_COMPARISON_FIELDS = (
    "matches",
    "unique_geographies",
    "benchmark_lower_rate",
    "competitor_lower_rate",
    "benchmark_median",
    "competitor_median",
    "median_gap",
)

_REPORT_GROUPS = (
    ("summary", "Summary", ("executive_summary", "kpi_strip")),
    ("geography", "Geography", ("coverage", "geographic_sensitivity")),
    ("price", "Price", ("price_position",)),
    ("segments", "Segments", ("segment_analysis",)),
    ("products", "Products", ("product_table", "assortment")),
    ("opportunities", "Opportunities", ("recommendations",)),
    ("quality", "Quality", ("data_quality",)),
    ("methodology", "Methodology", ("methodology",)),
)


def _metric_field(metric_id: str) -> str | None:
    normalized = metric_id.replace("-", "_").casefold()
    for field in sorted(_COMPARISON_FIELDS, key=len, reverse=True):
        if normalized.endswith(field):
            return field
    return None


def _formatted_metric(metric: JsonObject | None) -> str:
    if metric is None:
        return "—"
    value = metric.get("value")
    if not isinstance(value, int | float) or isinstance(value, bool):
        return "—"
    unit = str(metric.get("unit", ""))
    if unit == "rate":
        return f"{value:.1%}"
    if unit.startswith("USD"):
        rendered = f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"
        return rendered
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


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

    def __init__(self, retailer_names: Mapping[str, str] | None = None) -> None:
        self._retailer_names = dict(retailer_names or {})

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
        groups = [
            {
                "id": group_id,
                "label": label,
                "section_ids": [
                    str(section["id"]) for section in sections if str(section["kind"]) in kinds
                ],
            }
            for group_id, label, kinds in _REPORT_GROUPS
        ]
        return {
            "analysis_id": result["analysis_id"],
            "generated_at": result["generated_at"],
            "benchmark_retailer": self._retailer_names.get(
                str(result["benchmark_retailer"]),
                str(result["benchmark_retailer"]).replace("_", " ").title(),
            ),
            "competitors": [
                self._retailer_names.get(str(value), str(value).replace("_", " ").title())
                for value in result["competitors"]
            ],
            "product_pack": {
                "id": product_pack["id"],
                "name": product_pack["name"],
                "version": product_pack["version"],
                "recommended_charts": product_pack.get("reporting", {}).get(
                    "recommended_charts", []
                ),
            },
            "blueprint": {"id": blueprint.id, "version": blueprint.version},
            "groups": groups,
            "sections": sections,
        }

    def worksheet_rows(
        self,
        result: JsonObject,
        source: str,
        product_pack: JsonObject,
    ) -> list[JsonObject]:
        if source == "narratives":
            narratives = result.get("narratives", {})
            return self._rows(narratives.get("sections")) if isinstance(narratives, dict) else []
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
        value = result.get(source)
        if isinstance(value, list):
            return self._rows(value)
        if isinstance(value, dict):
            return [dict(value)]
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
            {
                **metric,
                "name": _merchant_text(metric.get("name"), self._retailer_names, product_pack),
            }
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
        if kind in {"price_position", "segment_analysis", "geographic_sensitivity"}:
            records = self._comparison_records(
                result,
                records,
                metric_index,
                product_pack,
            )
        else:
            records = [_merchant_record(row, self._retailer_names, product_pack) for row in records]
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
        presentation_title = (
            str(narrative.get("heading"))
            if isinstance(narrative, dict) and narrative.get("heading")
            else str(section["title"])
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
            "title": presentation_title,
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
            "segment_analysis": "comparisons",
            "geographic_sensitivity": "comparisons",
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
        if (
            kind
            in {
                "price_position",
                "segment_analysis",
                "geographic_sensitivity",
                "coverage",
            }
            and selected_metric_ids
        ):
            return [
                row
                for row in rows
                if selected_metric_ids.intersection(
                    str(value) for value in row.get("metric_refs", [])
                )
            ]
        return rows

    def _comparison_records(
        self,
        result: JsonObject,
        comparisons: list[JsonObject],
        metric_index: dict[str, JsonObject],
        product_pack: JsonObject,
    ) -> list[JsonObject]:
        """Project stored comparison metrics into a merchant-facing table."""

        mode_index = {
            str(row.get("profile_id")): row for row in self._rows(result.get("comparison_modes"))
        }
        segment_index = {
            str(row.get("segment_id")): row for row in self._rows(result.get("segments"))
        }
        rows: list[JsonObject] = []
        for comparison in comparisons:
            values = {
                field: metric_index[str(ref)]
                for ref in comparison.get("metric_refs", [])
                if str(ref) in metric_index and (field := _metric_field(str(ref))) is not None
            }
            if not values:
                continue
            competitor_id = str(comparison.get("competitor_id", "unknown"))
            competitor = self._retailer_names.get(
                competitor_id,
                competitor_id.replace("_", " ").title(),
            )
            mode = mode_index.get(str(comparison.get("profile_id")), {})
            segment_id = str(comparison.get("segment_id", "all"))
            segment = segment_index.get(segment_id, {})
            segment_label = (
                "All comparable items" if segment_id == "all" else segment.get("label", segment_id)
            )
            rows.append(
                {
                    "competitor": competitor,
                    "comparison lens": _merchant_text(
                        mode.get("label", comparison.get("profile_id", "Comparison")),
                        self._retailer_names,
                        product_pack,
                    ),
                    "segment": _merchant_text(
                        segment_label,
                        self._retailer_names,
                        product_pack,
                    ),
                    "matches": _formatted_metric(values.get("matches")),
                    "matched geographies": _formatted_metric(values.get("unique_geographies")),
                    "benchmark lower": _formatted_metric(values.get("benchmark_lower_rate")),
                    "competitor lower": _formatted_metric(values.get("competitor_lower_rate")),
                    "benchmark median": _formatted_metric(values.get("benchmark_median")),
                    "competitor median": _formatted_metric(values.get("competitor_median")),
                    "competitor - benchmark gap": _formatted_metric(values.get("median_gap")),
                }
            )
        return sorted(
            rows,
            key=lambda row: (
                str(row["competitor"]),
                str(row["segment"]) != "All comparable items",
                str(row["segment"]),
            ),
        )

    @staticmethod
    def _rows(value: object) -> list[JsonObject]:
        if not isinstance(value, list):
            return []
        return [dict(row) for row in value if isinstance(row, dict)]
