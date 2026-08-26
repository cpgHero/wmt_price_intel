"""Release-grade reconciliation for competitive portfolio materializations.

The reporting UI reads six immutable portfolio documents for each publication:
every configured comparison basis at 1, 3, and 5 miles.  JSON Schema validation
proves shape, but it does not prove that the displayed denominators, status
counts, rates, product totals, or radius behavior agree.  This module supplies
that semantic acceptance boundary without changing the underlying evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from itertools import pairwise
from typing import Any

SUMMARY_COUNT_FIELDS = (
    "benchmark_product_locations",
    "scored_product_locations",
    "leader_product_locations",
    "tied_product_locations",
    "at_risk_product_locations",
    "losing_product_locations",
    "unscored_product_locations",
)
RATE_FIELDS = (
    "coverage_rate",
    "leader_rate",
    "benchmark_lower_rate",
    "competitor_lower_rate",
    "parity_rate",
)


def _integer(value: Any) -> int:
    return int(value or 0)


def _expected_rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _matches_rate(actual: Any, expected: float | None) -> bool:
    if expected is None:
        return actual is None
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    return abs(float(actual) - expected) <= 0.00005


def _matches_number(actual: Any, expected: float | None, *, tolerance: float = 0.00015) -> bool:
    if expected is None:
        return actual is None
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    return abs(float(actual) - expected) <= tolerance


def audit_competitive_portfolio_set(
    documents: Sequence[Mapping[str, Any]],
    *,
    expected_profiles: Iterable[str] | None = None,
    expected_radii: Iterable[int] = (1, 3, 5),
) -> dict[str, Any]:
    """Reconcile a complete publication-scoped portfolio read-model set.

    Errors mean the materialization set is unsafe to release.  Warnings identify
    honest evidence limitations (for example, a certified relationship with no
    geographically scorable observations) and remain visible for acceptance.
    """

    findings: list[dict[str, Any]] = []

    def finding(
        severity: str,
        code: str,
        message: str,
        **context: Any,
    ) -> None:
        findings.append(
            {
                "severity": severity,
                "code": code,
                "message": message,
                "context": context,
            }
        )

    def audit_summary(row: Mapping[str, Any], path: str) -> None:
        values = {field: _integer(row.get(field)) for field in SUMMARY_COUNT_FIELDS}
        benchmark = values["benchmark_product_locations"]
        scored = values["scored_product_locations"]
        leader = values["leader_product_locations"]
        tied = values["tied_product_locations"]
        at_risk = values["at_risk_product_locations"]
        losing = values["losing_product_locations"]
        unscored = values["unscored_product_locations"]
        if benchmark != scored + unscored:
            finding(
                "error",
                "benchmark_denominator_mismatch",
                "Benchmark product-locations must equal scored plus unscored locations.",
                path=path,
                benchmark=benchmark,
                scored=scored,
                unscored=unscored,
            )
        if scored != leader + tied + at_risk + losing:
            finding(
                "error",
                "status_partition_mismatch",
                "Scored product-locations must equal the four mutually exclusive outcomes.",
                path=path,
                scored=scored,
                leader=leader,
                tied=tied,
                at_risk=at_risk,
                losing=losing,
            )
        expected = {
            "coverage_rate": _expected_rate(scored, benchmark),
            "leader_rate": _expected_rate(leader, scored),
            "benchmark_lower_rate": _expected_rate(leader + at_risk, scored),
            "competitor_lower_rate": _expected_rate(losing, scored),
            "parity_rate": _expected_rate(tied, scored),
        }
        for field in RATE_FIELDS:
            if not _matches_rate(row.get(field), expected[field]):
                finding(
                    "error",
                    "rate_mismatch",
                    "A displayed rate does not reconcile to its governed count denominator.",
                    path=path,
                    field=field,
                    actual=row.get(field),
                    expected=expected[field],
                )

    def audit_product_rows(
        rows: Any,
        parent: Mapping[str, Any],
        path: str,
    ) -> None:
        products = [row for row in rows or [] if isinstance(row, Mapping)]
        for index, product in enumerate(products):
            audit_summary(product, f"{path}.products[{index}]")
        ordered = sorted(
            products,
            key=lambda row: (
                -_integer(row.get("scored_product_locations")),
                -_integer(row.get("benchmark_product_locations")),
                str(row.get("product_name") or "").casefold(),
            ),
        )
        if products != ordered:
            finding(
                "error",
                "product_order_mismatch",
                "Products must be ordered by decision evidence, then footprint, then name.",
                path=path,
            )
        for field in SUMMARY_COUNT_FIELDS:
            product_total = sum(_integer(row.get(field)) for row in products)
            if product_total != _integer(parent.get(field)):
                finding(
                    "error",
                    "product_rollup_mismatch",
                    "Product summaries must add exactly to their parent scorecard.",
                    path=path,
                    field=field,
                    product_total=product_total,
                    parent_total=_integer(parent.get(field)),
                )
        audit_weighted_average(products, parent, path, "product")

    def audit_weighted_average(
        rows: Sequence[Mapping[str, Any]],
        parent: Mapping[str, Any],
        path: str,
        grain: str,
    ) -> None:
        scored_rows = [row for row in rows if _integer(row.get("scored_product_locations"))]
        total_scored = sum(_integer(row.get("scored_product_locations")) for row in scored_rows)
        missing = [
            index
            for index, row in enumerate(scored_rows)
            if not isinstance(row.get("average_gap"), (int, float))
            or isinstance(row.get("average_gap"), bool)
        ]
        if missing:
            finding(
                "error",
                "average_gap_missing",
                "Every scored child row must retain its average local price gap.",
                path=path,
                grain=grain,
                missing_indexes=missing,
            )
            return
        expected = (
            round(
                sum(
                    float(row["average_gap"]) * _integer(row.get("scored_product_locations"))
                    for row in scored_rows
                )
                / total_scored,
                4,
            )
            if total_scored
            else None
        )
        if not _matches_number(parent.get("average_gap"), expected):
            finding(
                "error",
                "average_gap_rollup_mismatch",
                "The displayed average gap must be the scored-evidence-weighted child average.",
                path=path,
                grain=grain,
                actual=parent.get("average_gap"),
                expected=expected,
            )

    keys: dict[tuple[str, int], Mapping[str, Any]] = {}
    analysis_ids: set[str] = set()
    benchmark_ids: set[str] = set()
    competitor_sets: dict[tuple[str, int], set[str]] = {}
    for document_index, document in enumerate(documents):
        path = f"documents[{document_index}]"
        filters = document.get("filters")
        if not isinstance(filters, Mapping):
            finding("error", "filters_missing", "Portfolio filters are missing.", path=path)
            continue
        profile = str(filters.get("profile_id") or "")
        radius = _integer(filters.get("radius_miles"))
        key = (profile, radius)
        if key in keys:
            finding(
                "error",
                "duplicate_materialization_scope",
                "A comparison-basis/radius materialization occurs more than once.",
                path=path,
                profile=profile,
                radius=radius,
            )
        keys[key] = document
        analysis_ids.add(str(document.get("analysis_id") or ""))
        benchmark = document.get("benchmark_retailer")
        benchmark_ids.add(str(benchmark.get("id") or "") if isinstance(benchmark, Mapping) else "")
        if (
            filters.get("competitor_id") != "all"
            or filters.get("state") is not None
            or filters.get("city") is not None
        ):
            finding(
                "error",
                "materialization_scope_not_global",
                "Release materializations must retain the complete retailer and geography scope.",
                path=path,
                filters=dict(filters),
            )
        policy = document.get("policy")
        if (
            not isinstance(policy, Mapping)
            or policy.get("physical_store_rule") != "within selected radius"
            or policy.get("service_area_rule") != "same delivery ZIP"
        ):
            finding(
                "error",
                "geography_policy_mismatch",
                "The physical-store radius and service-area exception must be explicit.",
                path=path,
            )
        scorecards = [row for row in document.get("scorecards", []) if isinstance(row, Mapping)]
        competitor_sets[key] = {str(row.get("competitor_id") or "") for row in scorecards}
        scorecard_order = sorted(
            scorecards,
            key=lambda row: (
                -_integer(row.get("scored_product_locations")),
                str(row.get("competitor") or "").casefold(),
            ),
        )
        if scorecards != scorecard_order:
            finding(
                "error",
                "scorecard_order_mismatch",
                "Retailer scorecards must be ordered by scored evidence, then retailer.",
                path=path,
            )
        scorecards_by_retailer: dict[str, Mapping[str, Any]] = {}
        for scorecard_index, scorecard in enumerate(scorecards):
            scorecard_path = f"{path}.scorecards[{scorecard_index}]"
            retailer_id = str(scorecard.get("competitor_id") or "")
            scorecards_by_retailer[retailer_id] = scorecard
            audit_summary(scorecard, scorecard_path)
            products = scorecard.get("products")
            audit_product_rows(products, scorecard, scorecard_path)
            product_rows = [row for row in products or [] if isinstance(row, Mapping)]
            if len(product_rows) != _integer(scorecard.get("benchmark_products")):
                finding(
                    "error",
                    "benchmark_product_count_mismatch",
                    "The distinct benchmark-product count must equal the product summaries.",
                    path=scorecard_path,
                )
            relationships = [
                row
                for row in scorecard.get("product_relationships", [])
                if isinstance(row, Mapping)
            ]
            for relationship_index, relationship in enumerate(relationships):
                audit_summary(
                    relationship,
                    f"{scorecard_path}.product_relationships[{relationship_index}]",
                )
            for field in (
                "scored_product_locations",
                "leader_product_locations",
                "tied_product_locations",
                "at_risk_product_locations",
                "losing_product_locations",
            ):
                relationship_total = sum(_integer(row.get(field)) for row in relationships)
                if relationship_total != _integer(scorecard.get(field)):
                    finding(
                        "error",
                        "relationship_rollup_mismatch",
                        "Selected relationship evidence must add exactly to the "
                        "retailer scorecard.",
                        path=scorecard_path,
                        field=field,
                        relationship_total=relationship_total,
                        parent_total=_integer(scorecard.get(field)),
                    )
            audit_weighted_average(
                relationships, scorecard, scorecard_path, "certified relationship"
            )
            if len({str(row.get("relationship_id") or "") for row in relationships}) != _integer(
                scorecard.get("relationships")
            ):
                finding(
                    "error",
                    "relationship_count_mismatch",
                    "The relationship count must equal the distinct relationship evidence rows.",
                    path=scorecard_path,
                )
            if len(
                {str(row.get("competitor_product_id") or "") for row in relationships}
            ) != _integer(scorecard.get("competitor_products")):
                finding(
                    "error",
                    "competitor_product_count_mismatch",
                    "The competitor-product count must equal distinct products in relationships.",
                    path=scorecard_path,
                )
            relationship_order = sorted(
                relationships,
                key=lambda row: (
                    -_integer(row.get("scored_product_locations")),
                    str(row.get("benchmark_product_name") or "").casefold(),
                    str(row.get("competitor_product_name") or "").casefold(),
                ),
            )
            if relationships != relationship_order:
                finding(
                    "error",
                    "relationship_order_mismatch",
                    "Relationships must be ordered by scored evidence and product identity.",
                    path=scorecard_path,
                )
            if _integer(scorecard.get("relationships")) == 0:
                finding(
                    "warning",
                    "no_certified_relationships",
                    "This retailer has no certified relationship in the selected comparison basis.",
                    path=scorecard_path,
                    retailer_id=retailer_id,
                    profile=profile,
                    radius=radius,
                )
            elif _integer(scorecard.get("scored_product_locations")) == 0:
                finding(
                    "warning",
                    "no_scored_evidence",
                    "Certified relationships exist, but no product-location is "
                    "scorable in this radius.",
                    path=scorecard_path,
                    retailer_id=retailer_id,
                    profile=profile,
                    radius=radius,
                )

        cohorts = [row for row in document.get("cohorts", []) if isinstance(row, Mapping)]
        requires_cohort_lineage = str(document.get("schema_version") or "") == "1.3.0"
        for cohort_index, cohort in enumerate(cohorts):
            cohort_path = f"{path}.cohorts[{cohort_index}]"
            audit_summary(cohort, cohort_path)
            audit_product_rows(cohort.get("products"), cohort, cohort_path)
            if len(
                [row for row in cohort.get("products", []) if isinstance(row, Mapping)]
            ) != _integer(cohort.get("benchmark_products")):
                finding(
                    "error",
                    "cohort_product_count_mismatch",
                    "A cohort benchmark-product count must equal its product summaries.",
                    path=cohort_path,
                )
            relationships = [
                row for row in cohort.get("product_relationships", []) if isinstance(row, Mapping)
            ]
            for relationship_index, relationship in enumerate(relationships):
                audit_summary(
                    relationship,
                    f"{cohort_path}.product_relationships[{relationship_index}]",
                )
            if requires_cohort_lineage and len(
                {str(row.get("relationship_id") or "") for row in relationships}
            ) != _integer(cohort.get("relationships")):
                finding(
                    "error",
                    "cohort_relationship_count_mismatch",
                    "The cohort relationship count must equal its radius-native lineage rows.",
                    path=cohort_path,
                )
            for field in (
                "scored_product_locations",
                "leader_product_locations",
                "tied_product_locations",
                "at_risk_product_locations",
                "losing_product_locations",
            ):
                if not requires_cohort_lineage:
                    continue
                relationship_total = sum(_integer(row.get(field)) for row in relationships)
                if relationship_total != _integer(cohort.get(field)):
                    finding(
                        "error",
                        "cohort_relationship_rollup_mismatch",
                        "Cohort relationship evidence must add exactly to the cohort scorecard.",
                        path=cohort_path,
                        field=field,
                        relationship_total=relationship_total,
                        parent_total=_integer(cohort.get(field)),
                    )
            if requires_cohort_lineage:
                audit_weighted_average(
                    relationships, cohort, cohort_path, "cohort relationship"
                )
        cohort_relationships_by_retailer: dict[str, int] = {}
        for cohort in cohorts:
            retailer_id = str(cohort.get("competitor_id") or "")
            cohort_relationships_by_retailer[retailer_id] = cohort_relationships_by_retailer.get(
                retailer_id, 0
            ) + _integer(cohort.get("relationships"))
        for retailer_id, scorecard in scorecards_by_retailer.items():
            certified = _integer(scorecard.get("relationships"))
            cohorted = cohort_relationships_by_retailer.get(retailer_id, 0)
            if cohorted > certified:
                finding(
                    "error",
                    "cohort_relationship_overcount",
                    "Comparable cohorts cannot contain more relationships than the "
                    "certified ledger.",
                    path=path,
                    retailer_id=retailer_id,
                    certified=certified,
                    cohorted=cohorted,
                )
            elif cohorted < certified:
                finding(
                    "warning",
                    "cohort_attribute_coverage_gap",
                    "Certified relationships without complete cohort attributes are "
                    "excluded from cohort rows.",
                    path=path,
                    retailer_id=retailer_id,
                    certified=certified,
                    cohorted=cohorted,
                    excluded=certified - cohorted,
                )

        assortment = [
            row for row in document.get("assortment_scorecards", []) if isinstance(row, Mapping)
        ]
        assortment_by_retailer = {str(row.get("competitor_id") or ""): row for row in assortment}
        if set(assortment_by_retailer) != set(scorecards_by_retailer):
            finding(
                "error",
                "assortment_retailer_scope_mismatch",
                "Assortment and price scorecards must cover the same retailers.",
                path=path,
            )
        for retailer_id, assortment_row in assortment_by_retailer.items():
            assortment_path = f"{path}.assortment_scorecards[{retailer_id}]"
            audit_summary(assortment_row, assortment_path)
            matching_scorecard = scorecards_by_retailer.get(retailer_id)
            if matching_scorecard is not None:
                for field in SUMMARY_COUNT_FIELDS:
                    if _integer(assortment_row.get(field)) != _integer(
                        matching_scorecard.get(field)
                    ):
                        finding(
                            "error",
                            "assortment_summary_mismatch",
                            "Assortment and price scorecards must share the same "
                            "governed price evidence.",
                            path=assortment_path,
                            field=field,
                        )

    if len(analysis_ids) != 1 or "" in analysis_ids:
        finding(
            "error",
            "analysis_identity_mismatch",
            "All materializations must belong to one named analysis.",
            analysis_ids=sorted(analysis_ids),
        )
    if len(benchmark_ids) != 1 or "" in benchmark_ids:
        finding(
            "error",
            "benchmark_identity_mismatch",
            "All materializations must use one named benchmark retailer.",
            benchmark_ids=sorted(benchmark_ids),
        )

    profiles = sorted(
        set(expected_profiles)
        if expected_profiles is not None
        else {profile for profile, _ in keys}
    )
    radii = sorted(set(int(radius) for radius in expected_radii))
    expected_keys = {(profile, radius) for profile in profiles for radius in radii}
    if set(keys) != expected_keys:
        finding(
            "error",
            "materialization_matrix_incomplete",
            "Every configured comparison basis must be materialized at 1, 3, and 5 miles.",
            expected=sorted(expected_keys),
            actual=sorted(keys),
        )
    scope_sets = list(competitor_sets.values())
    if scope_sets and any(scope != scope_sets[0] for scope in scope_sets[1:]):
        finding(
            "error",
            "retailer_scope_drift",
            "Every materialization must contain the same configured competitor set.",
        )

    for profile in profiles:
        profile_documents = [
            (radius, keys[(profile, radius)]) for radius in radii if (profile, radius) in keys
        ]
        retailer_rows: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
        for radius, document in profile_documents:
            for scorecard in document.get("scorecards", []):
                if isinstance(scorecard, Mapping):
                    retailer_rows.setdefault(str(scorecard.get("competitor_id") or ""), []).append(
                        (radius, scorecard)
                    )
        for retailer_id, rows in retailer_rows.items():
            rows.sort(key=lambda item: item[0])
            stable_fields = (
                "benchmark_product_locations",
                "benchmark_products",
                "competitor_products",
                "relationships",
            )
            for field in stable_fields:
                values = [_integer(row.get(field)) for _, row in rows]
                if len(set(values)) > 1:
                    finding(
                        "error",
                        "radius_scope_drift",
                        "Changing radius must not change products, relationships, "
                        "or the benchmark denominator.",
                        profile=profile,
                        retailer_id=retailer_id,
                        field=field,
                        values=values,
                    )
            scored_values = [_integer(row.get("scored_product_locations")) for _, row in rows]
            unscored_values = [_integer(row.get("unscored_product_locations")) for _, row in rows]
            if any(right < left for left, right in pairwise(scored_values)):
                finding(
                    "error",
                    "radius_scored_evidence_regression",
                    "A wider physical-store radius cannot remove scorable evidence.",
                    profile=profile,
                    retailer_id=retailer_id,
                    values=scored_values,
                )
            if any(right > left for left, right in pairwise(unscored_values)):
                finding(
                    "error",
                    "radius_unscored_evidence_growth",
                    "A wider physical-store radius cannot add unscored benchmark locations.",
                    profile=profile,
                    retailer_id=retailer_id,
                    values=unscored_values,
                )

    errors = sum(row["severity"] == "error" for row in findings)
    warnings = sum(row["severity"] == "warning" for row in findings)
    return {
        "schema_version": "1.0.0-competitive-release-audit",
        "status": "passed" if errors == 0 else "failed",
        "analysis_id": next(iter(analysis_ids), None),
        "document_count": len(documents),
        "profiles": profiles,
        "radii": radii,
        "error_count": errors,
        "warning_count": warnings,
        "findings": findings,
    }


def require_competitive_portfolio_set(
    documents: Sequence[Mapping[str, Any]],
    *,
    expected_profiles: Iterable[str],
) -> dict[str, Any]:
    """Raise when semantic reconciliation finds a release-blocking defect."""

    audit = audit_competitive_portfolio_set(
        documents,
        expected_profiles=expected_profiles,
    )
    if audit["status"] != "passed":
        codes = sorted(
            {str(row["code"]) for row in audit["findings"] if row["severity"] == "error"}
        )
        raise ValueError("competitive portfolio release audit failed: " + ", ".join(codes))
    return audit
