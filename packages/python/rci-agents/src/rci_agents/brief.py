"""Deterministic semantic brief construction for leadership narrative generation."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from rci_agents.models import JsonObject
from rci_contracts import validate_instance

_SAFE_ID = re.compile(r"[^a-z0-9_.-]+")
_KEY_FIELDS = (
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
_SECTION_TOPICS: dict[str, tuple[str, ...]] = {
    "executive_summary": (
        "data_scope",
        "exact_price",
        "normalized_price",
        "segment_drivers",
        "segment_reversals",
        "actions",
    ),
    "kpi_strip": ("data_scope", "footprint"),
    "coverage": ("data_scope", "footprint", "geography", "fulfillment"),
    "price_position": ("exact_price", "segment_drivers"),
    "segment_analysis": ("normalized_price", "segment_drivers", "segment_reversals"),
    "geographic_sensitivity": ("geography",),
    "assortment": ("brand_assortment", "segment_drivers"),
    "product_table": ("brand_assortment", "segment_drivers"),
    "recommendations": ("actions",),
    "data_quality": ("caveats",),
    "methodology": ("data_scope", "caveats"),
}


def _rows(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def _slug(value: object) -> str:
    return _SAFE_ID.sub("-", str(value).casefold()).strip("-") or "unknown"


def _checksum(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def _metric_field(metric: JsonObject, benchmark_retailer: str) -> str | None:
    metric_id = str(metric.get("metric_id", "")).replace("-", "_").casefold()
    name = str(metric.get("name", "")).replace("-", "_").casefold()
    for field in sorted(_KEY_FIELDS, key=len, reverse=True):
        if metric_id.endswith(field):
            return field
    benchmark_tokens = {
        benchmark_retailer.replace("-", "_").casefold(),
        benchmark_retailer.replace("-", "_").casefold().split("_")[0],
    }
    for token in benchmark_tokens:
        if metric_id.endswith(f"{token}_lower_rate"):
            return "benchmark_lower_rate"
        if metric_id.endswith(f"{token}_lower"):
            return "benchmark_lower"
    for field in sorted(_KEY_FIELDS, key=len, reverse=True):
        phrase = field.replace("_", " ")
        if phrase in name and not (field == "matches" and "lower" in name):
            return field
    return None


def _display_identifier(value: object) -> str:
    return str(value).replace("_", " ").replace("-", " ").strip().title()


def _display_number(value: int | float) -> str:
    return f"{float(value):g}"


def _attribute_label(attribute: JsonObject, name: str) -> str:
    label = str(attribute.get("label") or _display_identifier(name)).strip()
    if str(attribute.get("unit", "")).casefold() == "percent":
        label = re.sub(r"\s+percentage$", "", label, flags=re.IGNORECASE)
    return label.casefold()


def _segment_display_label(segment: JsonObject, product_pack: JsonObject) -> str:
    """Render Product Pack segment attributes as a compact merchant-facing label."""

    if str(segment.get("segment_id", "")).casefold() == "all":
        return "all comparable items"
    values = segment.get("attributes")
    if not isinstance(values, dict) or not values:
        return str(segment.get("label") or "comparable items")
    definitions = {
        str(attribute.get("name")): attribute
        for attribute in _rows(product_pack.get("attributes"))
        if attribute.get("name")
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
        label = _attribute_label(definition, name)
        unit = str(definition.get("unit", "")).strip().casefold()
        if not unit and name.casefold().endswith("_pct"):
            unit = "percent"
            label = name.removesuffix("_pct").replace("_", " ")
        if not unit and (name.casefold().endswith("_lb") or "weight" in name.casefold()):
            unit = "lb"
        if isinstance(value, bool):
            descriptors.append(label if value else f"non-{label.replace(' ', '-')}")
        elif isinstance(value, int | float):
            rendered = _display_number(value)
            if unit == "percent":
                percentages.append(f"{rendered}% {label}")
            else:
                measurements.append(f"{rendered} {unit or label}".strip())
        else:
            rendered = str(value).replace("_", " ").strip().casefold()
            if rendered not in baseline_values:
                descriptors.append(rendered)
    parts: list[str] = []
    if percentages:
        parts.append(" / ".join(percentages))
    parts.extend(measurements)
    parts.extend(descriptors)
    return " · ".join(parts) or str(segment.get("label") or "comparable items")


class AnalysisBriefBuilder:
    """Create a bounded, evidence-linked business-fact packet without category branches."""

    def __init__(self, repository_root: Path, *, max_metrics: int = 160) -> None:
        if max_metrics < 24:
            raise ValueError("analysis brief requires at least 24 metrics")
        self._root = repository_root
        self._max_metrics = max_metrics
        catalog = json.loads((repository_root / "config/retailer-catalog.json").read_text())
        catalog_rows = [
            *_rows(catalog.get("retailers")),
            *_rows(catalog.get("normalization_only_retailers")),
        ]
        self._retailer_names = {
            str(row["id"]): str(row["display_name"])
            for row in catalog_rows
            if row.get("id") and row.get("display_name")
        }

    def build(
        self,
        result: JsonObject,
        *,
        product_pack: JsonObject,
        report_blueprint: JsonObject,
    ) -> JsonObject:
        metrics = _rows(result.get("metrics"))
        metric_index = {str(metric["metric_id"]): metric for metric in metrics}
        evidence_ids = {str(row["evidence_set_id"]) for row in _rows(result.get("evidence_sets"))}
        playbook = product_pack.get("reporting", {}).get("narrative_playbook")
        if not isinstance(playbook, dict):
            raise ValueError("Product Pack has no narrative playbook")
        required_topics = [str(value) for value in playbook["required_topics"]]
        small_sample_threshold = int(playbook["small_sample_threshold"])

        facts = self._base_facts(result, metric_index)
        comparison_facts = self._comparison_facts(
            result,
            metric_index,
            product_pack=product_pack,
            small_sample_threshold=small_sample_threshold,
        )
        facts.extend(self._bounded_comparisons(comparison_facts, facts))
        facts.extend(self._quality_facts(result, metric_index))
        fact_index = {str(fact["id"]): fact for fact in facts}
        selected_metric_refs = list(
            dict.fromkeys(str(ref) for fact in facts for ref in fact.get("metric_refs", []))
        )[: self._max_metrics]
        selected_metric_ids = set(selected_metric_refs)
        facts = [
            {
                **fact,
                "metric_refs": [
                    str(ref) for ref in fact["metric_refs"] if str(ref) in selected_metric_ids
                ],
            }
            for fact in facts
            if any(str(ref) in selected_metric_ids for ref in fact["metric_refs"])
        ]
        fact_index = {str(fact["id"]): fact for fact in facts}
        storylines = self._storylines(
            result,
            facts,
            benchmark_retailer=str(result["benchmark_retailer"]),
            small_sample_threshold=small_sample_threshold,
        )
        storylines = [
            storyline
            for storyline in storylines
            if set(str(ref) for ref in storyline["fact_refs"]).issubset(fact_index)
        ]
        lenses = self._decision_lenses(
            playbook,
            metric_index,
            selected_metric_ids,
            evidence_ids,
        )
        sections = self._sections(
            report_blueprint,
            required_topics,
            facts,
            storylines,
            lenses,
        )
        provenance = result.get("provenance", {})
        persisted_checksum = (
            provenance.get("final_result_checksum_sha256") if isinstance(provenance, dict) else None
        )
        document: JsonObject = {
            "schema_version": "1.0.0",
            "analysis_id": result["analysis_id"],
            "analysis_result_checksum_sha256": (
                str(persisted_checksum)
                if isinstance(persisted_checksum, str) and len(persisted_checksum) == 64
                else _checksum(result)
            ),
            "benchmark_retailer": result["benchmark_retailer"],
            "competitors": list(result["competitors"]),
            "product_pack": {
                "id": product_pack["id"],
                "name": product_pack["name"],
                "version": product_pack["version"],
            },
            "leadership_objective": playbook["leadership_objective"],
            "required_topics": required_topics,
            "decision_lenses": lenses,
            "facts": facts,
            "storylines": storylines,
            "requested_sections": sections,
            "guardrails": {
                "required_caveats": list(
                    product_pack.get("reporting", {}).get("required_caveats", [])
                ),
                "forbidden_claims": list(playbook["forbidden_claims"]),
                "action_principles": list(playbook["action_principles"]),
                "small_sample_threshold": small_sample_threshold,
                "numeric_claim_policy": "metric_placeholders_only",
            },
        }
        validate_instance(
            self._root,
            "analysis-brief.schema.json",
            document,
            label="analysis brief",
        )
        return document

    def model_view(self, document: JsonObject) -> JsonObject:
        """Return the same governed brief without machine identifiers irrelevant to prose."""

        view = deepcopy(document)
        view["benchmark_retailer"] = self._retailer_name(view.get("benchmark_retailer"))
        view["competitors"] = [
            self._retailer_name(retailer_id) for retailer_id in view.get("competitors", [])
        ]
        for fact in view.get("facts", []):
            if not isinstance(fact, dict):
                continue
            fact.pop("id", None)
            context = fact.get("context")
            if not isinstance(context, dict):
                continue
            for identifier_key in ("competitor_id", "retailer_id"):
                identifier = context.pop(identifier_key, None)
                if identifier is not None:
                    context.setdefault(
                        identifier_key.removesuffix("_id") + "_name",
                        self._retailer_name(identifier),
                    )
        for storyline in view.get("storylines", []):
            if not isinstance(storyline, dict):
                continue
            storyline.pop("fact_refs", None)
        return view

    def _base_facts(
        self,
        result: JsonObject,
        metric_index: dict[str, JsonObject],
    ) -> list[JsonObject]:
        facts: list[JsonObject] = []
        source_refs = [
            metric_id
            for metric_id, metric in metric_index.items()
            if metric_id == "source.total_rows"
            or str(metric.get("name", "")).casefold() == "source rows"
        ]
        if source_refs:
            evidence = AnalysisBriefBuilder._evidence_for(source_refs, metric_index)
            facts.append(
                {
                    "id": "fact.source.scope",
                    "kind": "source_scope",
                    "label": "Complete source scope",
                    "significance": "context",
                    "metric_refs": source_refs[:1],
                    "evidence_refs": evidence,
                    "context": {
                        "sampling": bool(result.get("source", {}).get("sampling", False))
                        if isinstance(result.get("source"), dict)
                        else False,
                        "source_kind": str(result.get("source", {}).get("kind", "unknown"))
                        if isinstance(result.get("source"), dict)
                        else "unknown",
                    },
                }
            )
        for row in _rows(result.get("coverage")):
            refs = [str(ref) for ref in row.get("metric_refs", []) if str(ref) in metric_index]
            if not refs:
                continue
            facts.append(
                {
                    "id": f"fact.coverage.{_slug(row.get('retailer_id'))}",
                    "kind": "coverage",
                    "label": f"{self._retailer_name(row.get('retailer_id'))} qualifying footprint",
                    "significance": "context",
                    "metric_refs": refs,
                    "evidence_refs": AnalysisBriefBuilder._evidence_for(refs, metric_index),
                    "context": {"retailer_id": str(row.get("retailer_id", "unknown"))},
                }
            )
        return facts

    def _comparison_facts(
        self,
        result: JsonObject,
        metric_index: dict[str, JsonObject],
        *,
        product_pack: JsonObject,
        small_sample_threshold: int,
    ) -> list[JsonObject]:
        mode_index = {str(row["profile_id"]): row for row in _rows(result.get("comparison_modes"))}
        segment_index = {str(row["segment_id"]): row for row in _rows(result.get("segments"))}
        facts: list[JsonObject] = []
        for comparison in _rows(result.get("comparisons")):
            refs = [
                str(ref) for ref in comparison.get("metric_refs", []) if str(ref) in metric_index
            ]
            fields = {
                field: ref
                for ref in refs
                if (
                    (
                        field := _metric_field(
                            metric_index[ref],
                            str(result["benchmark_retailer"]),
                        )
                    )
                    is not None
                )
            }
            key_refs = [fields[field] for field in _KEY_FIELDS if field in fields]
            if not key_refs:
                continue
            matches = AnalysisBriefBuilder._number(fields.get("matches"), metric_index)
            benchmark_rate = AnalysisBriefBuilder._number(
                fields.get("benchmark_lower_rate"), metric_index
            )
            competitor_rate = AnalysisBriefBuilder._number(
                fields.get("competitor_lower_rate"), metric_index
            )
            if matches is not None and matches < small_sample_threshold:
                significance = "caveat"
            elif competitor_rate is not None and competitor_rate > 0.5:
                significance = "risk"
            elif benchmark_rate is not None and benchmark_rate >= 0.75:
                significance = "strength"
            else:
                significance = "watch"
            segment_id = str(comparison.get("segment_id", "all"))
            segment = segment_index.get(segment_id, {})
            mode = mode_index.get(str(comparison.get("profile_id")), {})
            competitor_id = str(comparison.get("competitor_id", "unknown"))
            label = _segment_display_label(segment, product_pack)
            competitor_name = self._retailer_name(competitor_id)
            facts.append(
                {
                    "id": f"fact.comparison.{_slug(comparison.get('comparison_id'))}",
                    "kind": (
                        "geographic_validation"
                        if mode.get("geography") == "radius"
                        else ("comparison_overall" if segment_id == "all" else "comparison_segment")
                    ),
                    "label": f"{competitor_name} — {label}",
                    "significance": significance,
                    "metric_refs": key_refs,
                    "evidence_refs": AnalysisBriefBuilder._evidence_for(key_refs, metric_index),
                    "context": {
                        "competitor_id": competitor_id,
                        "competitor_name": competitor_name,
                        "profile_id": str(comparison.get("profile_id", "unknown")),
                        "profile_label": str(mode.get("label", "Comparison")),
                        "segment_id": segment_id,
                        "segment_label": label,
                        "geography": str(mode.get("geography", "unknown")),
                        "comparison_metric": str(mode.get("comparison_metric", "unknown")),
                        "sample_warning": bool(
                            matches is not None and matches < small_sample_threshold
                        ),
                    },
                }
            )
        return facts

    def _bounded_comparisons(
        self,
        comparison_facts: list[JsonObject],
        base_facts: list[JsonObject],
    ) -> list[JsonObject]:
        metric_budget = self._max_metrics - len(
            {str(ref) for fact in base_facts for ref in fact["metric_refs"]}
        )
        selected: list[JsonObject] = []
        used: set[str] = set()
        ordered = sorted(
            comparison_facts,
            key=lambda fact: (
                fact["kind"] != "comparison_overall",
                fact["significance"] == "caveat",
                0 if fact["significance"] == "risk" else 1,
                str(fact["id"]),
            ),
        )
        for fact in ordered:
            new_refs = {str(ref) for ref in fact["metric_refs"]} - used
            if len(new_refs) > metric_budget:
                continue
            selected.append(fact)
            used.update(new_refs)
            metric_budget -= len(new_refs)
            if len(selected) >= 28:
                break
        return selected

    @staticmethod
    def _quality_facts(
        result: JsonObject,
        metric_index: dict[str, JsonObject],
    ) -> list[JsonObject]:
        quality = result.get("data_quality")
        if not isinstance(quality, dict):
            return []
        refs = [str(ref) for ref in quality.get("metric_refs", []) if str(ref) in metric_index]
        if not refs:
            return []
        has_issues = any(int(value) > 0 for value in quality.get("issue_counts", {}).values())
        return [
            {
                "id": "fact.quality.summary",
                "kind": "data_quality",
                "label": "Data-quality status",
                "significance": "caveat" if has_issues else "context",
                "metric_refs": refs,
                "evidence_refs": AnalysisBriefBuilder._evidence_for(refs, metric_index),
                "context": {"status": str(quality.get("status", "unknown"))},
            }
        ]

    def _storylines(
        self,
        result: JsonObject,
        facts: list[JsonObject],
        *,
        benchmark_retailer: str,
        small_sample_threshold: int,
    ) -> list[JsonObject]:
        storylines: list[JsonObject] = []
        fact_index = {str(fact["id"]): fact for fact in facts}
        scope_fact = fact_index.get("fact.source.scope")
        coverage_facts = [fact for fact in facts if fact["kind"] == "coverage"]
        if scope_fact is not None:
            linked = [scope_fact, *coverage_facts]
            storylines.append(
                AnalysisBriefBuilder._storyline(
                    "story.scope",
                    "scope",
                    "complete contracted source scope",
                    "Lead with the observed retailer footprint and disclose whether "
                    "sampling occurred before interpreting price outcomes.",
                    ["data_scope", "footprint"],
                    linked,
                )
            )

        comparison_facts = [
            fact for fact in facts if fact["kind"] in {"comparison_overall", "comparison_segment"}
        ]
        chosen: list[JsonObject] = []
        by_competitor: dict[str, list[JsonObject]] = defaultdict(list)
        for fact in comparison_facts:
            by_competitor[str(fact["context"]["competitor_id"])].append(fact)
        for competitor_facts in by_competitor.values():
            overall = [fact for fact in competitor_facts if fact["kind"] == "comparison_overall"]
            chosen.extend(overall[:2])
            risks = [fact for fact in competitor_facts if fact["significance"] == "risk"]
            strengths = [fact for fact in competitor_facts if fact["significance"] == "strength"]
            chosen.extend(risks[:2])
            chosen.extend(strengths[:2])
        seen: set[str] = set()
        for fact in chosen:
            fact_id = str(fact["id"])
            if fact_id in seen:
                continue
            seen.add(fact_id)
            context = fact["context"]
            competitor = str(
                context.get("competitor_name") or _display_identifier(context["competitor_id"])
            )
            segment = str(context["segment_label"])
            profile = str(context["profile_label"])
            article = "an" if profile[:1].casefold() in "aeiou" else "a"
            if fact["significance"] == "risk":
                kind = "competitive_pressure"
                headline = f"{competitor} price pressure in {segment}"
                interpretation = (
                    f"Treat this as {article} {profile.casefold()} watchlist and keep the action "
                    "within the "
                    "matched product specification."
                )
            elif fact["significance"] == "strength":
                kind = "benchmark_strength"
                headline = (
                    f"{self._retailer_name(benchmark_retailer)} value strength against "
                    f"{competitor} in {segment}"
                )
                interpretation = (
                    f"Protect this {profile} value position while monitoring localized exceptions."
                )
            else:
                kind = "mixed_position"
                headline = f"mixed price position against {competitor} in {segment}"
                interpretation = (
                    f"Avoid a broad price conclusion; use the {profile} evidence and matched "
                    "denominator to guide monitoring."
                )
            topics = [
                "exact_price"
                if context["comparison_metric"] == "package_price"
                else "normalized_price",
                "segment_drivers",
            ]
            if fact["significance"] == "caveat":
                topics.append("caveats")
                interpretation += (
                    f" The match universe is below the configured small-sample threshold of "
                    f"{small_sample_threshold}; do not generalize it broadly."
                )
            storylines.append(
                AnalysisBriefBuilder._storyline(
                    f"story.{_slug(fact_id)}",
                    kind,
                    headline,
                    interpretation,
                    topics,
                    [fact],
                )
            )

        groups: dict[tuple[str, str], list[JsonObject]] = defaultdict(list)
        for fact in comparison_facts:
            context = fact["context"]
            if context["segment_id"] == "all":
                continue
            groups[(str(context["competitor_id"]), str(context["segment_id"]))].append(fact)
        for (competitor_id, _), grouped in groups.items():
            directions = {str(fact["significance"]) for fact in grouped}
            metrics = {str(fact["context"]["comparison_metric"]) for fact in grouped}
            if not ({"risk", "strength"}.issubset(directions) and len(metrics) > 1):
                continue
            segment = str(grouped[0]["context"]["segment_label"])
            competitor_name = grouped[0]["context"].get("competitor_name")
            competitor_name = competitor_name or _display_identifier(competitor_id)
            storylines.append(
                AnalysisBriefBuilder._storyline(
                    f"story.reversal.{_slug(competitor_id)}.{_slug(grouped[0]['context']['segment_id'])}",
                    "segment_reversal",
                    f"price-winner reversal against {competitor_name!s} in {segment}",
                    "Present the exact-package and normalized-unit conclusions separately; "
                    "both can be valid for different merchant decisions.",
                    ["segment_reversals", "exact_price", "normalized_price"],
                    grouped,
                )
            )

        for fact in [fact for fact in facts if fact["kind"] == "geographic_validation"][:3]:
            context = fact["context"]
            competitor_name = context.get("competitor_name")
            competitor_name = competitor_name or _display_identifier(context["competitor_id"])
            storylines.append(
                AnalysisBriefBuilder._storyline(
                    f"story.geography.{_slug(fact['id'])}",
                    "geographic_validation",
                    f"{competitor_name!s} nearby-store validation",
                    "State whether the directional result is consistent with the primary "
                    "comparison and keep the radius analysis labeled as a sensitivity test.",
                    ["geography"],
                    [fact],
                )
            )

        quality = fact_index.get("fact.quality.summary")
        if quality is not None and quality["significance"] == "caveat":
            storylines.append(
                AnalysisBriefBuilder._storyline(
                    "story.quality",
                    "quality_limitation",
                    "observed data-quality limitations",
                    "Disclose the affected metric and avoid turning incomplete product or "
                    "unit evidence into an automated alert.",
                    ["caveats"],
                    [quality],
                )
            )

        recommendations = _rows(result.get("recommendations"))
        for index, recommendation in enumerate(recommendations[:5], start=1):
            refs = {str(ref) for ref in recommendation.get("metric_refs", [])}
            linked = [
                fact
                for fact in facts
                if refs.intersection(str(ref) for ref in fact.get("metric_refs", []))
            ][:2]
            if not linked:
                continue
            primary_context = linked[0].get("context", {})
            if not isinstance(primary_context, dict):
                primary_context = {}
            competitor = str(
                primary_context.get("competitor_name")
                or self._retailer_name(primary_context.get("competitor_id"))
            )
            segment = str(primary_context.get("segment_label") or "the cited opportunity")
            storylines.append(
                AnalysisBriefBuilder._storyline(
                    f"story.action.{index}",
                    "action",
                    f"{competitor} response for {segment}",
                    str(
                        recommendation.get(
                            "rationale",
                            "Tie the operating response to the cited comparison evidence.",
                        )
                    ),
                    ["actions"],
                    linked,
                )
            )
        return [
            {**storyline, "priority": index}
            for index, storyline in enumerate(storylines[:20], start=1)
        ]

    def _retailer_name(self, retailer_id: object) -> str:
        key = str(retailer_id or "unknown")
        return self._retailer_names.get(key, _display_identifier(key))

    @staticmethod
    def _storyline(
        storyline_id: str,
        kind: str,
        headline: str,
        interpretation: str,
        topics: list[str],
        facts: list[JsonObject],
    ) -> JsonObject:
        return {
            "id": storyline_id,
            "kind": kind,
            "headline": headline,
            "interpretation": interpretation,
            "priority": 1,
            "topic_refs": list(dict.fromkeys(topics)),
            "fact_refs": list(dict.fromkeys(str(fact["id"]) for fact in facts)),
            "metric_refs": list(
                dict.fromkeys(str(ref) for fact in facts for ref in fact["metric_refs"])
            ),
            "evidence_refs": list(
                dict.fromkeys(str(ref) for fact in facts for ref in fact["evidence_refs"])
            ),
        }

    @staticmethod
    def _decision_lenses(
        playbook: JsonObject,
        metric_index: dict[str, JsonObject],
        selected_metric_ids: set[str],
        evidence_ids: set[str],
    ) -> list[JsonObject]:
        lenses: list[JsonObject] = []
        for lens in playbook["decision_lenses"]:
            selectors = [str(value) for value in lens["metric_selectors"]]
            refs = [
                metric_id
                for metric_id in sorted(selected_metric_ids)
                if any(fnmatchcase(metric_id, selector) for selector in selectors)
            ]
            if not refs:
                continue
            evidence = AnalysisBriefBuilder._evidence_for(refs, metric_index)
            evidence = [ref for ref in evidence if ref in evidence_ids]
            if not refs or not evidence:
                continue
            lenses.append(
                {
                    "id": lens["id"],
                    "label": lens["label"],
                    "question": lens["question"],
                    "metric_refs": refs,
                    "evidence_refs": evidence,
                }
            )
        return lenses

    @staticmethod
    def _sections(
        report_blueprint: JsonObject,
        required_topics: list[str],
        facts: list[JsonObject],
        storylines: list[JsonObject],
        lenses: list[JsonObject],
    ) -> list[JsonObject]:
        sections: list[JsonObject] = []
        all_metric_refs = list(
            dict.fromkeys(str(ref) for fact in facts for ref in fact["metric_refs"])
        )
        all_evidence_refs = list(
            dict.fromkeys(str(ref) for fact in facts for ref in fact["evidence_refs"])
        )
        lens_questions = " ".join(str(lens["question"]) for lens in lenses)
        for section in _rows(report_blueprint.get("sections")):
            narrative_id = section.get("narrative_section_id")
            if not narrative_id:
                continue
            kind = str(section["kind"])
            topics = [
                topic
                for topic in _SECTION_TOPICS.get(kind, ("caveats",))
                if topic in required_topics
            ] or [required_topics[0]]
            linked = [
                storyline
                for storyline in storylines
                if set(topics).intersection(str(value) for value in storyline["topic_refs"])
            ]
            if not linked:
                linked = storylines[:1]
            metric_refs = (
                list(dict.fromkeys(str(ref) for row in linked for ref in row["metric_refs"]))
                or all_metric_refs[:1]
            )
            evidence_refs = (
                list(dict.fromkeys(str(ref) for row in linked for ref in row["evidence_refs"]))
                or all_evidence_refs[:1]
            )
            objective = f"Answer the section's required leadership topics: {', '.join(topics)}."
            if lens_questions and kind in {
                "executive_summary",
                "price_position",
                "segment_analysis",
            }:
                objective = (
                    f"{objective} Use these decision questions where relevant: {lens_questions}"
                )
            sections.append(
                {
                    "id": str(narrative_id),
                    "heading": str(section["title"]),
                    "objective": objective,
                    "required_topics": topics,
                    "storyline_refs": [str(row["id"]) for row in linked],
                    "allowed_metric_refs": metric_refs,
                    "allowed_evidence_refs": evidence_refs,
                }
            )
        if not sections:
            raise ValueError("report blueprint has no narrative sections")
        return sections

    @staticmethod
    def _evidence_for(
        refs: list[str],
        metric_index: dict[str, JsonObject],
    ) -> list[str]:
        return list(
            dict.fromkeys(
                str(evidence)
                for ref in refs
                for evidence in metric_index.get(ref, {}).get("evidence_refs", [])
            )
        )

    @staticmethod
    def _number(
        metric_ref: str | None,
        metric_index: dict[str, JsonObject],
    ) -> float | None:
        if metric_ref is None:
            return None
        value: Any = metric_index.get(metric_ref, {}).get("value")
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)
