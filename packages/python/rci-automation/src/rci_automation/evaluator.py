"""Historical metric comparison and evidence-backed alert evaluation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from rci_automation.models import (
    AlertDefinitionRecord,
    AlertEvaluation,
    AnalysisContext,
    HistoricalComparison,
    MetricChange,
    MetricValue,
)


class MetricSelectionError(ValueError):
    pass


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise MetricSelectionError("boolean values are not numeric metrics")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MetricSelectionError(f"metric value {value!r} is not numeric") from exc


def select_metric(document: dict[str, Any], selector: dict[str, Any]) -> MetricValue:
    value: Any = document
    pointer: list[str] = []
    for component in selector["path"]:
        if isinstance(component, int):
            if not isinstance(value, list) or component >= len(value):
                raise MetricSelectionError(f"metric path component {component!r} was not found")
            value = value[component]
        else:
            if not isinstance(value, dict) or component not in value:
                raise MetricSelectionError(f"metric path component {component!r} was not found")
            value = value[component]
        pointer.append(str(component))
    where = selector.get("where", {})
    if where:
        if not isinstance(value, list):
            raise MetricSelectionError("metric where filter requires a list path")
        matches = [
            (index, row)
            for index, row in enumerate(value)
            if isinstance(row, dict)
            and all(row.get(key) == expected for key, expected in where.items())
        ]
        if len(matches) != 1:
            raise MetricSelectionError(f"metric selector matched {len(matches)} rows; expected one")
        index, value = matches[0]
        pointer.append(str(index))
    field = str(selector["field"])
    if not isinstance(value, dict) or field not in value:
        raise MetricSelectionError(f"metric field {field!r} was not found")
    pointer.append(field)
    return MetricValue(
        value=_decimal(value[field]),
        json_pointer="/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in pointer),
    )


def _change(current: Decimal, baseline: Decimal, mode: str) -> Decimal:
    difference = current - baseline
    if mode == "percentage_points":
        return difference * 100
    if mode == "percent_change":
        if baseline == 0:
            raise MetricSelectionError("percent change is undefined for a zero baseline")
        return difference * 100 / abs(baseline)
    return difference


class AlertEvaluator:
    def applies(self, definition: AlertDefinitionRecord, context: AnalysisContext) -> bool:
        scope = definition.config.get("scope", {})
        product_packs = scope.get("product_pack_ids", [])
        collection_definitions = scope.get("collection_definition_ids", [])
        return (not product_packs or context.analysis.product_pack_id in product_packs) and (
            not collection_definitions
            or context.collection_definition_key in collection_definitions
            or context.collection_definition_id in collection_definitions
        )

    def evaluate(
        self,
        definition: AlertDefinitionRecord,
        current: AnalysisContext,
        baseline: AnalysisContext | None,
    ) -> AlertEvaluation:
        selector = definition.config["metric"]
        condition = definition.config["condition"]
        operator = str(condition["operator"])
        current_metric = select_metric(current.analysis.result, selector)
        baseline_metric = (
            select_metric(baseline.analysis.result, selector) if baseline is not None else None
        )
        change_value = None
        comparison_value = current_metric.value
        if operator.startswith("change_") or operator == "absolute_change_gte":
            if baseline_metric is None:
                raise MetricSelectionError("change alert requires a comparable baseline analysis")
            change_value = _change(
                current_metric.value,
                baseline_metric.value,
                str(condition.get("change_mode", "absolute")),
            )
            comparison_value = (
                abs(change_value) if operator == "absolute_change_gte" else change_value
            )
        threshold = _decimal(condition["threshold"])
        comparisons = {
            "gt": comparison_value > threshold,
            "gte": comparison_value >= threshold,
            "lt": comparison_value < threshold,
            "lte": comparison_value <= threshold,
            "change_gt": comparison_value > threshold,
            "change_gte": comparison_value >= threshold,
            "change_lt": comparison_value < threshold,
            "change_lte": comparison_value <= threshold,
            "absolute_change_gte": comparison_value >= threshold,
        }
        evidence: dict[str, Any] = {
            "alert_definition": {
                "id": definition.stable_key,
                "version": definition.version,
                "checksum": definition.checksum,
            },
            "selector": selector,
            "condition": condition,
            "current": {
                "analysis_id": current.analysis.analysis_id,
                "analysis_checksum": current.analysis.checksum,
                "json_pointer": current_metric.json_pointer,
                "value": float(current_metric.value),
            },
        }
        if baseline is not None and baseline_metric is not None:
            evidence["baseline"] = {
                "analysis_id": baseline.analysis.analysis_id,
                "analysis_checksum": baseline.analysis.checksum,
                "json_pointer": baseline_metric.json_pointer,
                "value": float(baseline_metric.value),
            }
        if change_value is not None:
            evidence["change_value"] = float(change_value)
        return AlertEvaluation(
            triggered=comparisons[operator],
            current_value=current_metric.value,
            baseline_value=baseline_metric.value if baseline_metric is not None else None,
            change_value=change_value,
            evidence=evidence,
        )


class HistoricalComparator:
    _sections = ("source_summary", "coverage", "comparisons", "data_quality", "validation")
    _identity_fields = ("competitor_id", "retailer_id", "segment_id", "profile_id", "type", "id")

    def compare(self, current: AnalysisContext, baseline: AnalysisContext) -> HistoricalComparison:
        current_values = self._numeric_values(current.analysis.result)
        baseline_values = self._numeric_values(baseline.analysis.result)
        changes = []
        for key in sorted(current_values.keys() & baseline_values.keys()):
            current_value, current_ref = current_values[key]
            baseline_value, baseline_ref = baseline_values[key]
            difference = current_value - baseline_value
            percent = difference * 100 / abs(baseline_value) if baseline_value else None
            changes.append(
                MetricChange(
                    metric_key=key,
                    current_value=current_value,
                    baseline_value=baseline_value,
                    change_value=difference,
                    percent_change=percent,
                    current_evidence_ref=current_ref,
                    baseline_evidence_ref=baseline_ref,
                )
            )
        return HistoricalComparison(
            current_analysis_id=current.analysis.analysis_id,
            baseline_analysis_id=baseline.analysis.analysis_id,
            product_pack_id=current.analysis.product_pack_id,
            collection_definition_key=current.collection_definition_key,
            changes=tuple(changes),
        )

    def _numeric_values(self, document: dict[str, Any]) -> dict[str, tuple[Decimal, str]]:
        values: dict[str, tuple[Decimal, str]] = {}
        for section in self._sections:
            if section in document:
                self._walk(document[section], section, f"/{section}", values)
        return values

    def _walk(
        self,
        value: Any,
        key: str,
        pointer: str,
        output: dict[str, tuple[Decimal, str]],
    ) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, int | float | Decimal):
            output[key] = (_decimal(value), pointer)
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                self._walk(child, f"{key}.{child_key}", f"{pointer}/{child_key}", output)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                identity = self._identity(child, index)
                self._walk(child, f"{key}[{identity}]", f"{pointer}/{index}", output)

    def _identity(self, value: Any, index: int) -> str:
        if not isinstance(value, dict):
            return str(index)
        fields = [f"{field}={value[field]}" for field in self._identity_fields if field in value]
        return ",".join(fields) if fields else str(index)
