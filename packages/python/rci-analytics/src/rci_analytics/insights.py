"""Configuration-driven deterministic insight candidate ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rci_analytics.models import JsonObject
from rci_analytics.product_pack import ProductPack

_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(*parts: str) -> str:
    return "-".join(
        value for part in parts if (value := _SLUG.sub("-", part.casefold()).strip("-"))
    )


def _score(value: float, scale: float) -> float:
    return min(max(value / scale, 0.0), 1.0)


@dataclass(frozen=True, slots=True)
class ComparisonInsightInput:
    benchmark_id: str
    competitor_id: str
    profile_id: str
    profile_label: str
    segment_id: str
    segment_label: str
    values: dict[str, float]
    metric_refs: dict[str, str]
    evidence_refs: tuple[str, ...]

    @property
    def is_segment(self) -> bool:
        return self.segment_id != "all"


@dataclass(frozen=True, slots=True)
class RankedInsightCandidate:
    id: str
    score: float
    breadth: float
    magnitude: float
    confidence: float
    actionability: float
    insight: JsonObject
    recommendation: JsonObject | None


class DeterministicInsightEngine:
    """Evaluate Product Pack rules and rank only deterministic comparison signals."""

    def __init__(self, product_pack: ProductPack) -> None:
        reporting = product_pack.reporting
        self._rules = tuple(dict(rule) for rule in reporting["insight_rules"])
        ranking = reporting["insight_ranking"]
        self._weights = {key: float(value) for key, value in ranking["weights"].items()}
        self._weight_total = sum(self._weights.values())
        self._minimum_score = float(ranking["minimum_score"])
        self._max_candidates = int(ranking["max_candidates"])

    def rank(self, inputs: list[ComparisonInsightInput]) -> list[RankedInsightCandidate]:
        candidates = [
            candidate
            for value in inputs
            for rule in self._rules
            if (candidate := self._evaluate(value, rule)) is not None
            and candidate.score >= self._minimum_score
        ]
        candidates.sort(
            key=lambda candidate: (
                -candidate.score,
                -candidate.breadth,
                -candidate.magnitude,
                candidate.id,
            )
        )
        selected = candidates[: self._max_candidates]
        return [
            RankedInsightCandidate(
                id=candidate.id,
                score=candidate.score,
                breadth=candidate.breadth,
                magnitude=candidate.magnitude,
                confidence=candidate.confidence,
                actionability=candidate.actionability,
                insight=candidate.insight,
                recommendation=(
                    {**candidate.recommendation, "priority": index}
                    if candidate.recommendation is not None
                    else None
                ),
            )
            for index, candidate in enumerate(selected, start=1)
        ]

    def _evaluate(
        self,
        value: ComparisonInsightInput,
        rule: JsonObject,
    ) -> RankedInsightCandidate | None:
        scope = str(rule["scope"])
        if scope == "overall" and value.is_segment:
            return None
        if scope == "segment" and not value.is_segment:
            return None
        matches = value.values.get("matches", 0.0)
        if matches < float(rule.get("minimum_matches", 1)):
            return None
        condition = rule["condition"]
        assert isinstance(condition, dict)
        field = str(condition["field"])
        observed = value.values.get(field)
        if observed is None or not self._compare(
            observed,
            str(condition["operator"]),
            float(condition["threshold"]),
        ):
            return None
        threshold = float(condition["threshold"])
        breadth = _score(matches, float(rule["breadth_scale"]))
        magnitude = _score(abs(observed - threshold), float(rule["magnitude_scale"]))
        confidence_basis = value.values.get("unique_geographies", matches)
        confidence = _score(confidence_basis, float(rule["confidence_scale"]))
        actionability = float(rule["actionability"])
        components = {
            "breadth": breadth,
            "magnitude": magnitude,
            "confidence": confidence,
            "actionability": actionability,
        }
        score = sum(components[key] * self._weights[key] for key in components) / self._weight_total
        context = {
            "benchmark": value.benchmark_id,
            "competitor": value.competitor_id,
            "profile": value.profile_label,
            "segment": value.segment_label,
        }
        metric_fields = (field, "matches", "unique_geographies")
        metric_refs = tuple(
            dict.fromkeys(
                value.metric_refs[name] for name in metric_fields if name in value.metric_refs
            )
        )
        if not metric_refs or not value.evidence_refs:
            return None
        candidate_id = _slug(
            str(rule["id"]),
            value.competitor_id,
            value.profile_id,
            value.segment_id,
        )
        insight: JsonObject = {
            "id": candidate_id,
            "title": str(rule["title_template"]).format_map(context),
            "summary": str(rule["summary_template"]).format_map(context),
            "severity": str(rule["severity"]),
            "business_impact": str(rule["business_impact"]),
            "metric_refs": list(metric_refs),
            "evidence_refs": list(value.evidence_refs),
            "confidence": round(confidence, 8),
            "generated_by": "deterministic",
        }
        limitations = rule.get("limitations")
        if isinstance(limitations, list) and limitations:
            insight["limitations"] = [str(item) for item in limitations]
        recommendation_config = rule.get("recommendation")
        recommendation: JsonObject | None = None
        if isinstance(recommendation_config, dict):
            recommendation = {
                "id": f"recommend-{candidate_id}",
                "priority": 1,
                "action": str(recommendation_config["action_template"]).format_map(context),
                "owner": str(recommendation_config["owner"]),
                "rationale": str(recommendation_config["rationale_template"]).format_map(context),
                "metric_refs": list(metric_refs),
                "evidence_refs": list(value.evidence_refs),
            }
        return RankedInsightCandidate(
            id=candidate_id,
            score=round(score, 8),
            breadth=round(breadth, 8),
            magnitude=round(magnitude, 8),
            confidence=round(confidence, 8),
            actionability=round(actionability, 8),
            insight=insight,
            recommendation=recommendation,
        )

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        operations: dict[str, Any] = {
            "gt": value > threshold,
            "gte": value >= threshold,
            "lt": value < threshold,
            "lte": value <= threshold,
        }
        return bool(operations[operator])
