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


def _segment_display_label(segment: JsonObject, product_pack: JsonObject) -> str:
    """Render segment attributes as a compact merchant-facing label."""

    if str(segment.get("segment_id", "")).casefold() == "all":
        return "All comparable items"
    values = segment.get("attributes")
    if not isinstance(values, dict) or not values:
        return str(segment.get("label") or segment.get("segment_id") or "Comparable items")
    definitions = {
        str(attribute.get("name")): attribute
        for attribute in product_pack.get("attributes", [])
        if isinstance(attribute, dict) and attribute.get("name")
    }
    names = [name for name in definitions if name in values]
    names.extend(sorted(str(name) for name in values if str(name) not in definitions))
    percentages: list[str] = []
    measurements: list[str] = []
    descriptors: list[str] = []
    baseline_values = {"", "default", "none", "not applicable", "standard", "unknown"}
    for name in names:
        value = values.get(name)
        if value is None:
            continue
        definition = definitions.get(name, {})
        label = str(definition.get("label") or name.replace("_", " ")).strip().casefold()
        unit = str(definition.get("unit", "")).strip().casefold()
        if not unit and name.casefold().endswith("_pct"):
            unit = "percent"
            label = name.removesuffix("_pct").replace("_", " ")
        if not unit and (name.casefold().endswith("_lb") or "weight" in name.casefold()):
            unit = "lb"
        if isinstance(value, bool):
            descriptors.append(label if value else f"non-{label.replace(' ', '-')}")
        elif isinstance(value, int | float):
            rendered = f"{float(value):g}"
            if unit == "percent":
                percentages.append(f"{rendered}% {label.removesuffix(' percentage')}")
            else:
                display_unit = unit.replace("_", " ") if unit else label
                measurements.append(f"{rendered} {display_unit}".strip())
        else:
            rendered = str(value).replace("_", " ").strip().casefold()
            if rendered not in baseline_values:
                descriptors.append(rendered)
    parts: list[str] = []
    if percentages:
        parts.append(" / ".join(percentages))
    parts.extend(measurements)
    parts.extend(descriptors)
    return " · ".join(parts) or str(segment.get("label") or "Comparable items")


_COMPARISON_FIELDS = (
    "unique_geographies",
    "benchmark_lower_rate",
    "competitor_lower_rate",
    "parity_rate",
    "benchmark_lower",
    "competitor_lower",
    "benchmark_median",
    "competitor_median",
    "matches",
    "parity",
    "median_gap",
)

_REPORT_GROUPS = (
    ("overview", "Overview", ("executive_summary", "kpi_strip")),
    ("price-segments", "Price & Segments", ("price_position", "segment_analysis")),
    ("products", "Products", ("product_table",)),
    ("geography", "Geography", ("coverage", "geographic_sensitivity")),
    ("assortment", "Assortment", ("assortment",)),
    ("match-review", "Match Review", ()),
    (
        "quality-methodology",
        "Quality & Methodology",
        ("recommendations", "data_quality", "methodology"),
    ),
    ("exports", "Exports", ()),
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
        return self.load_document(document, label=str(path))

    def load_document(
        self,
        document: JsonObject,
        *,
        label: str = "<report blueprint>",
    ) -> ReportBlueprint:
        validate_instance(
            self._root,
            "report-blueprint.schema.json",
            document,
            label=label,
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

    def load_for_documents(
        self,
        result: JsonObject,
        blueprint_document: JsonObject,
        product_pack: JsonObject,
    ) -> tuple[ReportBlueprint, JsonObject]:
        blueprint = self.load_document(
            blueprint_document,
            label="runtime report blueprint",
        )
        self._validate_result_references(result, blueprint, product_pack)
        return blueprint, product_pack

    def load_for_result(self, result: JsonObject) -> tuple[ReportBlueprint, JsonObject]:
        product_pack_ref = result.get("product_pack")
        if not isinstance(product_pack_ref, dict):
            raise ContractError("AnalysisResult has no Product Pack reference")
        blueprint_ref = product_pack_ref.get("report_blueprint")
        if not isinstance(blueprint_ref, dict):
            raise ContractError("AnalysisResult V2 has no report blueprint reference")
        blueprint = self.load(str(blueprint_ref["id"]))
        pack_path = self._root / "product-packs" / f"{blueprint.product_pack_id}.json"
        try:
            product_pack = json.loads(pack_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"could not read Product Pack {pack_path}: {exc}") from exc
        self._validate_result_references(result, blueprint, product_pack)
        return blueprint, product_pack

    @staticmethod
    def _validate_result_references(
        result: JsonObject,
        blueprint: ReportBlueprint,
        product_pack: JsonObject,
    ) -> None:
        product_pack_ref = result["product_pack"]
        assert isinstance(product_pack_ref, dict)
        blueprint_ref = product_pack_ref["report_blueprint"]
        assert isinstance(blueprint_ref, dict)
        if blueprint.version != str(blueprint_ref["version"]):
            raise ContractError("AnalysisResult report blueprint version does not match")
        if (blueprint.product_pack_id, blueprint.product_pack_version) != (
            str(product_pack_ref["id"]),
            str(product_pack_ref["version"]),
        ):
            raise ContractError(
                "report blueprint does not belong to the AnalysisResult Product Pack"
            )
        if str(product_pack.get("version")) != blueprint.product_pack_version:
            raise ContractError("report blueprint Product Pack version does not match runtime data")

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
            "schema_version": "1.1.0",
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
            "retailer_scope": {
                "benchmark": {
                    "id": str(result["benchmark_retailer"]),
                    "name": self._retailer_name(result["benchmark_retailer"]),
                },
                "competitors": [
                    {"id": str(value), "name": self._retailer_name(value)}
                    for value in result["competitors"]
                ],
            },
            "retailer_scorecards": self.retailer_scorecards(result, product_pack),
            "comparison_bases": self.comparison_bases(result, product_pack),
            "match_governance": self._base_match_governance(result),
            "report_readiness": self._base_report_readiness(result),
            "product_pack": {
                "id": product_pack["id"],
                "name": product_pack["name"],
                "version": product_pack["version"],
                "recommended_charts": product_pack.get("reporting", {}).get(
                    "recommended_charts", []
                ),
                "cohort_dimensions": [
                    str(value).replace("_", " ").title()
                    for value in product_pack.get("reporting", {}).get("headline_segments", [])
                ],
                "minimum_cohort_geographies": int(
                    product_pack.get("reporting", {})
                    .get("decision_rules", {})
                    .get("minimum_geographies", 1)
                ),
            },
            "blueprint": {"id": blueprint.id, "version": blueprint.version},
            "groups": groups,
            "sections": sections,
        }

    def comparison_bases(
        self,
        result: JsonObject,
        product_pack: JsonObject,
    ) -> list[JsonObject]:
        profile_index = {
            str(profile["id"]): profile for profile in product_pack.get("matching_profiles", [])
        }
        decision_rules = product_pack.get("reporting", {}).get("decision_rules", {})
        preferred = str(decision_rules.get("preferred_scorecard_profile_id", ""))
        bases: list[JsonObject] = []
        for mode in self._rows(result.get("comparison_modes")):
            profile_id = str(mode.get("profile_id", ""))
            profile = profile_index.get(profile_id, {})
            comparison_metric = str(mode.get("comparison_metric", "package_price"))
            package_basis = self._package_basis(comparison_metric, profile)
            price_unit = self._price_unit(comparison_metric)
            bases.append(
                {
                    "profile_id": profile_id,
                    "label": str(mode.get("label") or profile.get("label") or profile_id),
                    "geography": str(
                        mode.get("geography") or profile.get("geography") or "unknown"
                    ),
                    "comparison_metric": comparison_metric,
                    "price_unit": price_unit,
                    "package_basis": package_basis,
                    "availability_policy": str(
                        profile.get("availability_policy", "search_presence")
                    ),
                    "population_basis": "relationship_resolved_products",
                    "scorecard_role": "preferred" if profile_id == preferred else "fallback",
                }
            )
        priority = {
            str(value): index
            for index, value in enumerate(decision_rules.get("profile_priority", []))
        }
        return sorted(
            bases,
            key=lambda row: (
                priority.get(
                    str(row["profile_id"]),
                    len(priority)
                    + (
                        0
                        if row["geography"] == "exact_zip"
                        and row["comparison_metric"] == "package_price"
                        else 1
                        if row["geography"] == "exact_zip"
                        else 2
                    ),
                ),
                str(row["profile_id"]),
            ),
        )

    @staticmethod
    def _package_basis(comparison_metric: str, profile: Mapping[str, object]) -> str:
        if comparison_metric == "package_price":
            return "exact_package"
        if profile.get("comparison_interval"):
            return "configured_interval"
        return "normalized_unit"

    @staticmethod
    def _price_unit(comparison_metric: str) -> str:
        if comparison_metric == "package_price":
            return "USD/package"
        return f"USD/{comparison_metric.removeprefix('price_per_').replace('_', ' ')}"

    @staticmethod
    def _base_match_governance(result: JsonObject) -> JsonObject:
        source = result.get("source", {})
        revision_id = source.get("match_revision_id") if isinstance(source, dict) else None
        return {
            "mode": "governed" if revision_id else "ungoverned",
            "match_revision_id": revision_id,
            "applied_policy_revision_id": None,
            "staged_revision_id": None,
            "suggested": 0,
            "confirmed": 0,
            "rejected": 0,
            "ambiguous": 0,
        }

    @staticmethod
    def _base_report_readiness(result: JsonObject) -> JsonObject:
        validation = result.get("validation", {})
        ready = isinstance(validation, dict) and validation.get("status") == "ready_to_share"
        return {
            "status": "ready" if ready else "limited",
            "blocking_reasons": [],
            "warnings": [],
            "suppressed_decisions": 0,
        }

    def worksheet_rows(
        self,
        result: JsonObject,
        source: str,
        product_pack: JsonObject,
    ) -> list[JsonObject]:
        if source == "retailer_scorecards":
            return [
                {
                    "reference_retailer": row.get("benchmark_retailer"),
                    "competitor": row.get("competitor"),
                    "comparison_lens": row.get("comparison_lens"),
                    "matched_observations": row.get("matches"),
                    "matched_zip_markets": row.get("matched_geographies"),
                    "qualifying_geographies": row.get("qualifying_geographies"),
                    "reference_lower_share": row.get("benchmark_lower_rate"),
                    "competitor_lower_share": row.get("competitor_lower_rate"),
                    "parity_share": row.get("parity_rate"),
                    "reference_marginal_median_price": row.get("benchmark_median"),
                    "competitor_marginal_median_price": row.get("competitor_median"),
                    "paired_median_competitor_minus_reference_gap": row.get("median_gap"),
                    "paired_median_price_position": row.get("price_position"),
                    "comparison_metric": row.get("comparison_metric"),
                    "price_unit": row.get("price_unit"),
                    "comparison_geography": row.get("geography"),
                    "readiness_reason": row.get("readiness_reason"),
                    "evidence_status": str(row.get("status", "limited_evidence"))
                    .replace("_", " ")
                    .title(),
                }
                for row in self.retailer_scorecards(result, product_pack)
            ]
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
            self._annotate_evidence_retailer(result, evidence)
            for evidence in evidence_sets
            if str(evidence.get("kind")) in evidence_kinds
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
            source_records = records
            records = [_merchant_record(row, self._retailer_names, product_pack) for row in records]
            if kind == "coverage":
                for rendered, source_record in zip(records, source_records, strict=True):
                    retailer_id = source_record.get("retailer_id")
                    if retailer_id is not None:
                        rendered["_retailer_id"] = str(retailer_id)
            elif kind == "product_table":
                for rendered, source_record in zip(records, source_records, strict=True):
                    retailer_id = self._evidence_retailer_id(result, source_record)
                    if retailer_id == str(result["benchmark_retailer"]):
                        rendered["_retailer_id"] = retailer_id
                    elif retailer_id is not None:
                        rendered["_competitor_id"] = retailer_id
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

    @staticmethod
    def _evidence_retailer_id(result: JsonObject, evidence: JsonObject) -> str | None:
        retailer_ids = [
            str(result["benchmark_retailer"]),
            *(str(value) for value in result["competitors"]),
        ]
        evidence_token = re.sub(
            r"[^a-z0-9]",
            "",
            " ".join(
                str(value).casefold() for value in evidence.values() if isinstance(value, str)
            ),
        )
        for retailer_id in sorted(retailer_ids, key=len, reverse=True):
            retailer_token = re.sub(r"[^a-z0-9]", "", retailer_id.casefold())
            if retailer_token and retailer_token in evidence_token:
                return retailer_id
        retailer_roots: dict[str, list[str]] = {}
        for retailer_id in retailer_ids:
            root = retailer_id.casefold().split("_", 1)[0]
            retailer_roots.setdefault(root, []).append(retailer_id)
        for root, matching_ids in retailer_roots.items():
            if len(matching_ids) == 1 and root in evidence_token:
                return matching_ids[0]
        return None

    def _annotate_evidence_retailer(self, result: JsonObject, evidence: JsonObject) -> JsonObject:
        rendered = dict(evidence)
        retailer_id = self._evidence_retailer_id(result, evidence)
        if retailer_id == str(result["benchmark_retailer"]):
            rendered["_retailer_id"] = retailer_id
        elif retailer_id is not None:
            rendered["_competitor_id"] = retailer_id
        return rendered

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
            values = self._comparison_metric_values(
                comparison,
                metric_index,
                benchmark_id=str(result.get("benchmark_retailer", "benchmark")),
            )
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
            segment_label = _segment_display_label(
                {**segment, "segment_id": segment_id},
                product_pack,
            )
            benchmark_lower_rate = self._numeric_metric(values.get("benchmark_lower_rate"))
            competitor_lower_rate = self._numeric_metric(values.get("competitor_lower_rate"))
            parity_rate = self._numeric_metric(values.get("parity_rate"))
            dominant_outcome = self._dominant_outcome(
                benchmark_lower_rate,
                competitor_lower_rate,
                parity_rate,
            )
            rows.append(
                {
                    "_competitor_id": competitor_id,
                    "_profile_id": str(comparison.get("profile_id", "")),
                    "_segment_id": segment_id,
                    "competitor": competitor,
                    "comparison lens": _merchant_text(
                        mode.get("label", comparison.get("profile_id", "Comparison")),
                        self._retailer_names,
                        product_pack,
                    ),
                    "comparison metric": str(
                        mode.get("comparison_metric", "package_price")
                    ).replace("_", " "),
                    "segment": _merchant_text(
                        segment_label,
                        self._retailer_names,
                        product_pack,
                    ),
                    "_matches": self._numeric_metric(values.get("matches")),
                    "_matched_geographies": self._numeric_metric(values.get("unique_geographies")),
                    "_benchmark_lower_rate": benchmark_lower_rate,
                    "_competitor_lower_rate": competitor_lower_rate,
                    "_parity_rate": parity_rate,
                    "_benchmark_median": self._numeric_metric(values.get("benchmark_median")),
                    "_competitor_median": self._numeric_metric(values.get("competitor_median")),
                    "_median_gap": self._numeric_metric(values.get("median_gap")),
                    "_dominant_outcome": dominant_outcome,
                    "matches": _formatted_metric(values.get("matches")),
                    "matched geographies": _formatted_metric(values.get("unique_geographies")),
                    "benchmark lower": _formatted_metric(values.get("benchmark_lower_rate")),
                    "competitor lower": _formatted_metric(values.get("competitor_lower_rate")),
                    "parity": _formatted_metric(values.get("parity_rate")),
                    "benchmark marginal median": _formatted_metric(values.get("benchmark_median")),
                    "competitor marginal median": _formatted_metric(
                        values.get("competitor_median")
                    ),
                    "paired median gap": _formatted_metric(values.get("median_gap")),
                    "dominant outcome": dominant_outcome.replace("_", " ").title(),
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

    def retailer_scorecards(
        self,
        result: JsonObject,
        product_pack: JsonObject,
    ) -> list[JsonObject]:
        """Project one governed comparison scorecard per competitor."""

        metric_index = {
            str(metric["metric_id"]): metric for metric in self._rows(result.get("metrics"))
        }
        modes = {
            str(row.get("profile_id")): row for row in self._rows(result.get("comparison_modes"))
        }
        coverage_by_retailer = {
            str(row.get("retailer_id")): row for row in self._rows(result.get("coverage"))
        }
        comparisons = self._rows(result.get("comparisons"))
        benchmark_id = str(result.get("benchmark_retailer", "benchmark"))
        benchmark_name = self._retailer_name(benchmark_id)
        decision_rules = product_pack.get("reporting", {}).get("decision_rules", {})
        minimum_observations = max(1, int(decision_rules.get("minimum_observations", 1)))
        minimum_geographies = max(1, int(decision_rules.get("minimum_geographies", 1)))
        preferred_profile = str(decision_rules.get("preferred_scorecard_profile_id", ""))
        preferred_profile_available = preferred_profile in modes
        configured_priority = {
            str(value): index
            for index, value in enumerate(decision_rules.get("profile_priority", []))
        }
        scorecards: list[JsonObject] = []
        for competitor_value in result.get("competitors", []):
            competitor_id = str(competitor_value)
            candidates = [
                row for row in comparisons if str(row.get("competitor_id")) == competitor_id
            ]
            candidates.sort(
                key=lambda row: self._scorecard_priority(
                    row,
                    modes,
                    configured_priority=configured_priority,
                )
            )
            comparison = candidates[0] if candidates else {}
            values = self._comparison_metric_values(
                comparison,
                metric_index,
                benchmark_id=benchmark_id,
            )
            mode = modes.get(str(comparison.get("profile_id")), {})
            benchmark_rate = self._numeric_metric(values.get("benchmark_lower_rate"))
            competitor_rate = self._numeric_metric(values.get("competitor_lower_rate"))
            parity_rate = self._numeric_metric(values.get("parity_rate"))
            if parity_rate is None and benchmark_rate is not None and competitor_rate is not None:
                parity_rate = max(0.0, 1.0 - benchmark_rate - competitor_rate)
            outcome_rates = (benchmark_rate, competitor_rate, parity_rate)
            rates_available = all(value is not None for value in outcome_rates)
            rates_reconcile = (
                rates_available
                and abs(sum(float(value) for value in outcome_rates if value is not None) - 1.0)
                <= 0.001
            )
            matches = self._numeric_metric(values.get("matches"))
            matched_geographies = self._numeric_metric(values.get("unique_geographies"))
            coverage_geographies = self._coverage_value(
                coverage_by_retailer.get(competitor_id, {}), metric_index
            )
            median_gap = self._numeric_metric(values.get("median_gap"))
            profile: JsonObject = next(
                (
                    row
                    for row in product_pack.get("matching_profiles", [])
                    if str(row.get("id")) == str(comparison.get("profile_id", ""))
                ),
                {},
            )
            comparison_metric = str(mode.get("comparison_metric", "package_price"))
            evidence_ready = (
                matches is not None
                and matches >= minimum_observations
                and matched_geographies is not None
                and matched_geographies >= minimum_geographies
                and rates_reconcile
            )
            if evidence_ready:
                readiness_reason = (
                    f"Meets the Product Pack minimum of {minimum_observations:,} "
                    f"observations across {minimum_geographies:,} geographies"
                )
            else:
                shortfalls: list[str] = []
                if matches is None or matches < minimum_observations:
                    shortfalls.append(
                        f"{self._whole_number(matches) or 0:,} of "
                        f"{minimum_observations:,} required observations"
                    )
                if matched_geographies is None or matched_geographies < minimum_geographies:
                    shortfalls.append(
                        f"{self._whole_number(matched_geographies) or 0:,} of "
                        f"{minimum_geographies:,} required geographies"
                    )
                if not rates_available:
                    shortfalls.append(
                        "complete benchmark, competitor, and parity shares unavailable"
                    )
                elif not rates_reconcile:
                    rate_total = sum(float(value) for value in outcome_rates if value is not None)
                    shortfalls.append(f"outcome shares total {rate_total:.1%}; expected 100.0%")
                readiness_reason = "Limited evidence: " + "; ".join(shortfalls)
            scorecards.append(
                {
                    "competitor_id": competitor_id,
                    "competitor": self._retailer_name(competitor_id),
                    "benchmark_retailer_id": benchmark_id,
                    "benchmark_retailer": benchmark_name,
                    "profile_id": str(comparison.get("profile_id", "")),
                    "comparison_lens": _merchant_text(
                        mode.get("label", comparison.get("profile_id", "Comparison")),
                        self._retailer_names,
                        product_pack,
                    ),
                    "comparison_metric": comparison_metric,
                    "price_unit": self._price_unit(comparison_metric),
                    "package_basis": self._package_basis(comparison_metric, profile),
                    "geography": str(mode.get("geography", "unknown")),
                    "basis_status": (
                        "preferred"
                        if str(comparison.get("profile_id", "")) == preferred_profile
                        or (comparison and not preferred_profile_available)
                        else "fallback"
                        if comparison
                        else "unavailable"
                    ),
                    "matches": self._whole_number(matches),
                    "matched_geographies": self._whole_number(matched_geographies),
                    "qualifying_geographies": self._whole_number(coverage_geographies),
                    "benchmark_lower_rate": benchmark_rate,
                    "competitor_lower_rate": competitor_rate,
                    "parity_rate": parity_rate,
                    "benchmark_median": self._numeric_metric(values.get("benchmark_median")),
                    "competitor_median": self._numeric_metric(values.get("competitor_median")),
                    "median_gap": median_gap,
                    "benchmark_median_statistic": "marginal_median",
                    "competitor_median_statistic": "marginal_median",
                    "median_gap_statistic": "paired_median_gap",
                    "minimum_observations": minimum_observations,
                    "minimum_geographies": minimum_geographies,
                    "readiness_reason": readiness_reason,
                    "dominant_outcome": self._dominant_outcome(
                        benchmark_rate,
                        competitor_rate,
                        parity_rate,
                    ),
                    "price_position": self._price_position(
                        benchmark_name,
                        self._retailer_name(competitor_id),
                        median_gap,
                    ),
                    "status": "ready" if evidence_ready else "limited_evidence",
                }
            )
        return scorecards

    def _retailer_name(self, value: object) -> str:
        retailer_id = str(value)
        return self._retailer_names.get(retailer_id, retailer_id.replace("_", " ").title())

    @staticmethod
    def _scorecard_priority(
        comparison: JsonObject,
        modes: Mapping[str, JsonObject],
        *,
        configured_priority: Mapping[str, int] | None = None,
    ) -> tuple[int, str]:
        mode = modes.get(str(comparison.get("profile_id")), {})
        strict_exact = (
            str(mode.get("geography")) == "exact_zip"
            and str(mode.get("comparison_metric")) == "package_price"
        )
        exact_zip = str(mode.get("geography")) == "exact_zip"
        overall = str(comparison.get("segment_id", "all")) == "all"
        configured = (configured_priority or {}).get(str(comparison.get("profile_id")))
        priority = (
            configured * 2 + (0 if overall else 1)
            if configured is not None
            else 0
            if strict_exact and overall
            else 1
            if exact_zip and overall
            else 2
            if overall
            else 3
            if strict_exact
            else 4
        )
        return (priority, str(comparison.get("comparison_id")))

    @staticmethod
    def _comparison_metric_values(
        comparison: JsonObject,
        metric_index: Mapping[str, JsonObject],
        *,
        benchmark_id: str,
    ) -> dict[str, JsonObject]:
        values: dict[str, JsonObject] = {}
        benchmark_tokens = {
            "benchmark",
            benchmark_id.casefold(),
            benchmark_id.casefold().removesuffix("_us"),
            benchmark_id.casefold().split("_")[0],
        }
        competitor_id = str(comparison.get("competitor_id", "competitor")).casefold()
        competitor_tokens = {
            "competitor",
            competitor_id,
            competitor_id.removesuffix("_us"),
            competitor_id.split("_")[0],
        }
        for reference in comparison.get("metric_refs", []):
            metric = metric_index.get(str(reference))
            if metric is None:
                continue
            field = _metric_field(str(reference))
            normalized = re.sub(
                r"[^a-z0-9]+",
                "_",
                f"{reference} {metric.get('name', '')}".casefold(),
            )
            if field is None:
                suffix = next(
                    (
                        value
                        for value in ("lower_rate", "lower", "median")
                        if normalized.endswith(value) or f"_{value}_" in normalized
                    ),
                    None,
                )
                if suffix and any(token and token in normalized for token in benchmark_tokens):
                    field = f"benchmark_{suffix}"
                elif suffix and any(token and token in normalized for token in competitor_tokens):
                    field = f"competitor_{suffix}"
            if field is not None:
                values[field] = metric
        return values

    @staticmethod
    def _numeric_metric(metric: JsonObject | None) -> float | None:
        value = metric.get("value") if metric is not None else None
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        return None

    @staticmethod
    def _dominant_outcome(
        benchmark_rate: float | None,
        competitor_rate: float | None,
        parity_rate: float | None,
    ) -> str:
        if benchmark_rate is None and competitor_rate is None and parity_rate is None:
            return "unavailable"
        values = {
            "benchmark_lower": benchmark_rate or 0.0,
            "competitor_lower": competitor_rate or 0.0,
            "parity": parity_rate or 0.0,
        }
        return max(
            values,
            key=lambda key: (values[key], key == "parity", key),
        )

    @classmethod
    def _coverage_value(
        cls,
        coverage: JsonObject,
        metric_index: Mapping[str, JsonObject],
    ) -> float | None:
        metrics = [
            metric_index[str(reference)]
            for reference in coverage.get("metric_refs", [])
            if str(reference) in metric_index
        ]
        preferred = next(
            (
                metric
                for metric in metrics
                if any(
                    token in str(metric.get("metric_id", "")).casefold()
                    for token in ("qualifying", "zip", "geograph")
                )
            ),
            metrics[0] if metrics else None,
        )
        return cls._numeric_metric(preferred)

    @staticmethod
    def _whole_number(value: float | None) -> int | float | None:
        return int(value) if value is not None and value.is_integer() else value

    @staticmethod
    def _price_position(
        benchmark: str,
        competitor: str,
        median_gap: float | None,
    ) -> str:
        if median_gap is None:
            return "Paired median price difference unavailable"
        if median_gap < 0:
            return f"{competitor} was ${abs(median_gap):,.2f} lower at the paired median"
        if median_gap > 0:
            return f"{benchmark} was ${median_gap:,.2f} lower at the paired median"
        return "The paired median price difference was $0.00"

    @staticmethod
    def _rows(value: object) -> list[JsonObject]:
        if not isinstance(value, list):
            return []
        return [dict(row) for row in value if isinstance(row, dict)]
