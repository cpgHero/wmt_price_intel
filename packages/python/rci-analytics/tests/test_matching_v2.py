from __future__ import annotations

import copy
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from rci_analytics.matching_v2 import (
    AttributePolicyV2,
    AttributeValue,
    DeterministicMatchEngineV2,
    IdentifierEvidence,
    ListingEvidence,
    LocalComparisonProjectorV2,
    LocalOfferV2,
    MatchingPolicyV2,
    compile_matching_policy_v2,
    reconcile_local_comparisons,
)
from rci_analytics.matching_v2_certification import GoldMatchLabelV2, certify_matching_v2
from rci_analytics.matching_v2_profile import (
    MatchingV2SourceInput,
    build_matching_v2_evidence_profile,
)
from rci_analytics.matching_v2_review import (
    MatchingV2ReviewSampling,
    build_matching_v2_review_queue,
)
from rci_analytics.matching_v2_shadow import (
    ListingEvidenceAccumulatorV2,
    MatchingShadowEvaluatorV2,
    build_listing_evidence_v2,
    shadow_result_checksum,
)
from rci_analytics.models import ClassifiedOffer, NormalizedOffer
from rci_analytics.product_pack import ProductPackLoader
from rci_contracts import validate_instance

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DECIDED_AT = "2026-08-15T12:00:00Z"


def _policy() -> MatchingPolicyV2:
    return MatchingPolicyV2(
        policy_id="milk:strict",
        version="2.0.0-shadow",
        product_pack_id="fresh_fluid_milk",
        product_pack_version="1.2.0",
        attributes=(
            AttributePolicyV2("product_form", "hard_blocker"),
            AttributePolicyV2("fat_percent", "required_exact"),
            AttributePolicyV2("volume_fl_oz", "required_exact"),
            AttributePolicyV2("organic", "required_exact"),
            AttributePolicyV2("container", "soft_comparator", weight=0.5),
        ),
        eligible_price_bases=("exact_package", "normalized_unit"),
        price_basis_requirements=(("exact_package", ("volume_fl_oz",)),),
        auto_approval_tiers=("exact_item", "exact_specification"),
        minimum_equivalent_coverage=0.75,
        equivalent_score_threshold=0.8,
    )


def _listing(
    retailer: str,
    product: str,
    *,
    fat: float | None = 2,
    volume: float | None = 128,
    organic: bool | None = False,
    form: str | None = "fluid_milk",
    container: str | None = "jug",
    brand: str | None = None,
    brand_type: str = "private_label",
    brand_verified: bool = False,
    identifier: IdentifierEvidence | None = None,
) -> ListingEvidence:
    def value(item: object, name: str) -> AttributeValue | None:
        return None if item is None else AttributeValue(item, f"pdp:{retailer}:{product}:{name}")

    attributes = {
        name: evidence
        for name, evidence in {
            "product_form": value(form, "product_form"),
            "fat_percent": value(fat, "fat_percent"),
            "volume_fl_oz": value(volume, "volume_fl_oz"),
            "organic": value(organic, "organic"),
            "container": value(container, "container"),
        }.items()
        if evidence is not None
    }
    return ListingEvidence(
        listing_id=f"listing-{retailer}-{product}",
        retailer_id=retailer,
        retailer_product_id=product,
        attributes=attributes,
        identifiers=(identifier,) if identifier else (),
        brand=brand,
        brand_type=brand_type,  # type: ignore[arg-type]
        brand_verified=brand_verified,
    )


def test_exact_specification_is_deterministic_and_contract_valid() -> None:
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1", brand="Great Value"),
        _listing("aldi_us", "a1", brand="Friendly Farms"),
        _policy(),
        decided_at=DECIDED_AT,
    )

    assert decision.tier == "exact_specification"
    assert decision.status == "auto_approved"
    assert decision.critical_coverage == 1
    assert decision.brand_relationship == "private_label_to_private_label"
    validate_instance(
        REPOSITORY_ROOT,
        "product-match-edge-v2.schema.json",
        decision.to_contract(),
        label="deterministic exact-spec edge",
    )


def test_product_pack_must_explicitly_authorize_automatic_approval() -> None:
    draft_policy = MatchingPolicyV2(
        policy_id="milk:draft",
        version="2.0.0-draft",
        product_pack_id="fresh_fluid_milk",
        product_pack_version="1.2.0",
        attributes=_policy().attributes,
        eligible_price_bases=_policy().eligible_price_bases,
        auto_approval_tiers=(),
    )
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1"),
        _listing("aldi_us", "a1"),
        draft_policy,
        decided_at=DECIDED_AT,
    )

    assert decision.tier == "exact_specification"
    assert decision.status == "candidate"
    assert "Product Pack review is required" in decision.decision_reason


def test_unknown_values_never_agree_and_prevent_exact_specification() -> None:
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1", volume=None),
        _listing("aldi_us", "a1", volume=None),
        _policy(),
        decided_at=DECIDED_AT,
    )

    volume = next(row for row in decision.evidence if row.attribute == "volume_fl_oz")
    assert volume.outcome == "unknown"
    assert decision.tier != "exact_specification"
    assert decision.status in {"candidate", "unresolved"}
    assert decision.critical_coverage < 1


def test_hard_conflict_is_not_comparable_and_price_never_enters_evidence() -> None:
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1", form="fluid_milk"),
        _listing("aldi_us", "a1", form="oat_beverage"),
        _policy(),
        decided_at=DECIDED_AT,
    )

    assert decision.tier is None
    assert decision.status == "not_comparable"
    assert decision.eligible_price_bases == ()
    assert "price" not in {row.attribute for row in decision.evidence}
    validate_instance(
        REPOSITORY_ROOT,
        "product-match-edge-v2.schema.json",
        decision.to_contract(),
        label="not-comparable v2 edge",
    )


def test_verified_identifier_establishes_exact_item_without_unknown_becoming_agreement() -> None:
    identifier = IdentifierEvidence(
        scheme="gtin", value="00012345678905", verification_status="verified", source="label"
    )
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1", container=None, identifier=identifier),
        _listing("target_us", "t1", container=None, identifier=identifier),
        _policy(),
        decided_at=DECIDED_AT,
    )

    assert decision.tier == "exact_item"
    assert decision.status == "auto_approved"
    assert (
        next(row for row in decision.evidence if row.attribute == "container").outcome == "unknown"
    )


def test_verified_identifier_does_not_override_conflicting_critical_evidence() -> None:
    identifier = IdentifierEvidence(
        scheme="gtin", value="00012345678905", verification_status="verified", source="label"
    )
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1", volume=128, identifier=identifier),
        _listing("target_us", "t1", volume=64, identifier=identifier),
        _policy(),
        decided_at=DECIDED_AT,
    )

    assert decision.tier != "exact_item"
    assert decision.status != "auto_approved"


def test_package_size_conflict_cannot_use_exact_package_price_basis() -> None:
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1", volume=128),
        _listing("aldi_us", "a1", volume=64),
        _policy(),
        decided_at=DECIDED_AT,
    )

    assert decision.tier == "comparable_substitute"
    assert "exact_package" not in decision.eligible_price_bases
    assert "normalized_unit" in decision.eligible_price_bases


def test_equal_unverified_brand_names_are_not_labeled_verified() -> None:
    decision = DeterministicMatchEngineV2().evaluate(
        _listing(
            "walmart_us", "w1", brand="Shared Name", brand_type="national", brand_verified=False
        ),
        _listing("aldi_us", "a1", brand="Shared Name", brand_type="national", brand_verified=False),
        _policy(),
        decided_at=DECIDED_AT,
    )

    assert decision.brand_relationship == "different_national_brands"


def test_equal_verified_brand_names_are_labeled_same_brand() -> None:
    decision = DeterministicMatchEngineV2().evaluate(
        _listing(
            "walmart_us", "w1", brand="Shared Name", brand_type="national", brand_verified=True
        ),
        _listing("aldi_us", "a1", brand="Shared Name", brand_type="national", brand_verified=True),
        _policy(),
        decided_at=DECIDED_AT,
    )

    assert decision.brand_relationship == "same_verified_brand"


def test_many_to_one_semantic_edges_are_retained_independently() -> None:
    engine = DeterministicMatchEngineV2()
    competitor = _listing("aldi_us", "a1", brand="Friendly Farms")
    decisions = [
        engine.evaluate(
            _listing("walmart_us", f"w{index}", brand=f"Regional Dairy {index}"),
            competitor,
            _policy(),
            decided_at=DECIDED_AT,
        )
        for index in range(1, 5)
    ]

    assert len({decision.edge_id for decision in decisions}) == 4
    assert {decision.competitor.listing_id for decision in decisions} == {competitor.listing_id}
    assert all(decision.status == "auto_approved" for decision in decisions)


def test_many_to_one_gold_certification_is_contract_valid() -> None:
    engine = DeterministicMatchEngineV2()
    competitor = _listing("aldi_us", "a1", brand="Friendly Farms")
    decisions = tuple(
        engine.evaluate(
            _listing("walmart_us", f"w{index}", brand=f"Regional Dairy {index}"),
            competitor,
            _policy(),
            decided_at=DECIDED_AT,
        )
        for index in range(1, 5)
    )
    labels = tuple(
        GoldMatchLabelV2(
            case_id=f"milk-many-to-one-{index}",
            benchmark_listing_id=f"listing-walmart_us-w{index}",
            competitor_listing_id="listing-aldi_us-a1",
            expected_comparable=True,
            allowed_tiers=("exact_specification",),
            critical=True,
        )
        for index in range(1, 5)
    )

    certification = certify_matching_v2(
        decisions,
        labels,
        gold_set_version="milk-compact-1.0.0",
    )

    assert certification.ready
    assert certification.candidate_recall == 1
    assert certification.auto_approval_precision == 1
    validate_instance(
        REPOSITORY_ROOT,
        "matching-v2-certification.schema.json",
        certification.to_contract(),
        label="matching v2 certification",
    )


def test_review_queue_is_deterministic_and_keeps_every_automatic_approval() -> None:
    evaluator = MatchingShadowEvaluatorV2(
        ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk"),
        "private_label",
        policy=_policy(),
    )
    result = evaluator.evaluate_listings(
        tuple(_listing("walmart_us", f"w{index}") for index in range(1, 5)),
        (_listing("aldi_us", "a1"),),
        benchmark_retailer_id="walmart_us",
        competitor_retailer_id="aldi_us",
        decided_at=DECIDED_AT,
    )
    arguments = {
        "queue_id": "milk-release-review",
        "queue_version": "1.0.0",
        "benchmark_source_reference": "artifact://search/milk/walmart#sha256=def",
        "source_references": {"aldi_us": "artifact://search/milk/aldi#sha256=abc"},
        "sampling": MatchingV2ReviewSampling(per_stratum_limit=1),
    }

    first = build_matching_v2_review_queue((result,), **arguments)
    second = build_matching_v2_review_queue((result,), **arguments)

    assert first == second
    assert len(first["cases"]) == 4
    assert first["sampling"]["selected_counts"] == {
        "aldi_us:overlapping_many_to_one_exact_specification_auto_approved": 4
    }
    assert all(case["critical"] for case in first["cases"])
    assert all(case["review_state"] == "pending" for case in first["cases"])
    assert all(len(case["evidence_refs"]) == 2 for case in first["cases"])
    validate_instance(
        REPOSITORY_ROOT,
        "matching-v2-review-queue.schema.json",
        first,
        label="matching v2 deterministic review queue",
    )


def test_operational_review_queue_keeps_every_governed_candidate() -> None:
    evaluator = MatchingShadowEvaluatorV2(
        ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk"),
        "private_label",
        policy=_policy(),
    )
    result = evaluator.evaluate_listings(
        tuple(_listing("walmart_us", f"w{index}") for index in range(1, 5)),
        (
            _listing("aldi_us", "a1"),
            _listing(
                "aldi_us",
                "a-unresolved",
                fat=None,
                volume=None,
                organic=None,
                form=None,
                container=None,
            ),
        ),
        benchmark_retailer_id="walmart_us",
        competitor_retailer_id="aldi_us",
        decided_at=DECIDED_AT,
    )

    queue = build_matching_v2_review_queue(
        (result,),
        queue_id="milk-operational-certification",
        queue_version="1.0.0",
        benchmark_source_reference="artifact://search/milk/walmart#sha256=def",
        source_references={"aldi_us": "artifact://search/milk/aldi#sha256=abc"},
        sampling=MatchingV2ReviewSampling(per_stratum_limit=1),
        selection_mode="operational_exhaustive",
    )

    assert queue["purpose"] == "operational_match_certification"
    assert queue["sampling"]["method"] == "exhaustive_governed_candidates"
    assert queue["sampling"]["available_counts"] == queue["sampling"]["selected_counts"]
    assert len(queue["cases"]) == sum(edge.tier is not None for edge in result.edges)
    assert queue["sampling"]["excluded_counts"] == {
        "aldi_us:hard_blocked_audit_sample": len(result.blocked_review_edges),
        "aldi_us:hard_blocked_pairs": result.blocked_pairs,
        "aldi_us:unresolved_without_governed_tier": sum(edge.tier is None for edge in result.edges),
    }
    validate_instance(
        REPOSITORY_ROOT,
        "matching-v2-review-queue.schema.json",
        queue,
        label="matching v2 exhaustive operational queue",
    )


def test_full_evidence_profiler_preserves_grain_and_reports_quality(tmp_path: Path) -> None:
    walmart = tmp_path / "walmart.csv"
    aldi = tmp_path / "aldi.csv"
    header = "Retailer,Product Name,Brand,Price,Zipcode,Retailer Store Id,Retailer Product Id\n"
    walmart.write_text(
        header
        + "Walmart,Great Value 2% Reduced Fat Milk 1 Gallon,Great Value,3.98,72712,100,wm1\n"
        + "Walmart,Great Value 2% Reduced Fat Milk 1 Gallon,Great Value,3.98,72712,100,wm1\n"
        + "Walmart,Marketplace 2% Reduced Fat Milk 1 Gallon,Unknown,8.98,72712,100,wm2\n",
        encoding="utf-8",
    )
    aldi.write_text(
        header
        + "ALDI,Friendly Farms 2% Reduced Fat Milk 1 Gallon,Friendly Farms,3.79,72712,10,al1\n",
        encoding="utf-8",
    )
    pdp_archive = tmp_path / "pdp.zip"
    manifest = {
        "snapshots": [
            {
                "retailer_id": "walmart_us",
                "retailer_product_id": "wm1",
                "http_status": 200,
                "observed_at": DECIDED_AT,
                "response_file": "responses/walmart_us/wm1/one.json",
            },
            {
                "retailer_id": "walmart_us",
                "retailer_product_id": "wm2",
                "http_status": 200,
                "observed_at": DECIDED_AT,
                "response_file": "responses/walmart_us/wm2/two.json",
            },
        ]
    }
    with zipfile.ZipFile(pdp_archive, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr(
            "responses/walmart_us/wm1/one.json",
            json.dumps(
                {
                    "name": "Great Value 2% Reduced Fat Milk, 1 Gallon",
                    "brand": "Great Value",
                    "seller": "Walmart.com",
                    "image_primary": "https://example.com/wm1.png",
                }
            ),
        )
        archive.writestr(
            "responses/walmart_us/wm2/two.json",
            json.dumps(
                {
                    "name": "Marketplace 2% Reduced Fat Milk, 1 Gallon",
                    "seller": "Food Service Direct",
                }
            ),
        )

    profile, queue = build_matching_v2_evidence_profile(
        REPOSITORY_ROOT,
        product_pack_id="fresh_fluid_milk",
        benchmark_retailer_id="walmart_us",
        inputs=(
            MatchingV2SourceInput(walmart, "walmart_us"),
            MatchingV2SourceInput(aldi, "aldi_us"),
        ),
        decided_at=DECIDED_AT,
        competitor_retailer_ids=("aldi_us",),
        per_stratum_limit=5,
        pdp_archives=(pdp_archive,),
        review_queue_version="1.1.0",
    )

    walmart_profile = next(
        row for row in profile["retailers"] if row["retailer_id"] == "walmart_us"
    )
    assert profile["totals"] == {
        "source_rows": 4,
        "normalized_unique_rows": 3,
        "normalization_failures": 0,
        "expected_retailer_mismatches": 0,
    }
    assert walmart_profile["duplicate_rows"] == 1
    assert walmart_profile["distinct_in_scope_products"] == 1
    assert walmart_profile["out_of_scope_reasons"] == {
        "known third-party marketplace seller excluded by Retailer Pack policy": 1
    }
    assert profile["release_use"]["eligible"] is False
    assert queue["authoritative"] is False
    assert queue["version"] == "1.1.0"
    assert queue["purpose"] == "operational_match_certification"
    assert queue["sampling"]["available_counts"] == queue["sampling"]["selected_counts"]
    assert queue["cases"] == []
    assert queue["sampling"]["excluded_counts"]["aldi_us:unresolved_without_governed_tier"] == 1
    validate_instance(
        REPOSITORY_ROOT,
        "matching-v2-evidence-profile.schema.json",
        profile,
        label="matching v2 evidence profile",
    )


def test_certification_fails_a_false_exact_approval() -> None:
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1"),
        _listing("aldi_us", "a1"),
        _policy(),
        decided_at=DECIDED_AT,
    )
    certification = certify_matching_v2(
        (decision,),
        (
            GoldMatchLabelV2(
                case_id="hard-negative",
                benchmark_listing_id=decision.benchmark.listing_id,
                competitor_listing_id=decision.competitor.listing_id,
                expected_comparable=False,
                allowed_tiers=(),
                critical=True,
            ),
        ),
        gold_set_version="negative-1.0.0",
    )

    assert not certification.ready
    assert certification.auto_approval_precision == 0
    assert any("auto-approval precision" in failure for failure in certification.failures)


def test_release_certification_rejects_unadjudicated_or_unsupported_labels() -> None:
    decision = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1"),
        _listing("aldi_us", "a1"),
        _policy(),
        decided_at=DECIDED_AT,
    )
    certification = certify_matching_v2(
        (decision,),
        (
            GoldMatchLabelV2(
                case_id="synthetic-only",
                benchmark_listing_id=decision.benchmark.listing_id,
                competitor_listing_id=decision.competitor.listing_id,
                expected_comparable=True,
                allowed_tiers=("exact_specification",),
                critical=True,
                stratum="regional_distribution_many_to_one",
            ),
        ),
        gold_set_version="synthetic-1.0.0",
        release_gate=True,
    )

    assert not certification.ready
    assert certification.strata["regional_distribution_many_to_one"]["candidate_recall"] == 1
    assert any("not adjudicated" in failure for failure in certification.failures)
    assert any("fewer than two reviewers" in failure for failure in certification.failures)
    assert any("no immutable evidence" in failure for failure in certification.failures)


def _offer(
    retailer: str,
    product: str,
    store: str,
    price: float | None,
    *,
    longitude: float,
) -> LocalOfferV2:
    return LocalOfferV2(
        retailer_id=retailer,
        listing_id=f"listing-{retailer}-{product}",
        product_id=product,
        location_scope_key=f"{retailer}|store|{store}",
        location_kind="store",
        comparison_value=price,
        observed_at="2026-08-15T10:00:00Z",
        store_number=store,
        zipcode="72712",
        offer_id=f"offer-{retailer}-{product}-{store}",
        latitude=36.37,
        longitude=longitude,
    )


def test_local_projection_retains_candidates_and_selects_lowest_offer() -> None:
    edge = DeterministicMatchEngineV2().evaluate(
        _listing("walmart_us", "w1"),
        _listing("aldi_us", "a1"),
        _policy(),
        decided_at=DECIDED_AT,
    )
    rows = LocalComparisonProjectorV2().project(
        analysis_id="analysis-1",
        competitor_retailer_id="aldi_us",
        policy_revision="milk:strict:2.0.0-shadow",
        benchmark=_offer("walmart_us", "w1", "w1", 4.00, longitude=-94.21),
        edges=[edge],
        competitor_offers=[
            _offer("aldi_us", "a1", "a1", 3.50, longitude=-94.205),
            _offer("aldi_us", "a1", "a2", 3.75, longitude=-94.20),
        ],
        price_basis="exact_package",
        selection_policy="lowest_eligible_local_offer",
        radius_miles=3,
        generated_at=DECIDED_AT,
    )

    assert len(rows) == 2
    assert rows[0]["selection"]["status"] == "selected"
    assert rows[0]["result"]["competitor_value"] == 3.5
    assert rows[1]["selection"]["status"] == "eligible_not_selected"
    assert all(row["selection"]["candidate_count"] == 2 for row in rows)
    for row in rows:
        validate_instance(
            REPOSITORY_ROOT,
            "local-comparison-observation-v2.schema.json",
            row,
            label="local comparison v2",
        )


def test_reconciliation_separates_product_location_losses_from_unique_stores() -> None:
    engine = DeterministicMatchEngineV2()
    competitor = _listing("aldi_us", "a1")
    rows: list[dict[str, object]] = []
    for product in ("w1", "w2"):
        edge = engine.evaluate(
            _listing("walmart_us", product),
            competitor,
            _policy(),
            decided_at=DECIDED_AT,
        )
        rows.extend(
            LocalComparisonProjectorV2().project(
                analysis_id="analysis-1",
                competitor_retailer_id="aldi_us",
                policy_revision="milk:strict:2.0.0-shadow",
                benchmark=_offer("walmart_us", product, "100", 4.00, longitude=-94.21),
                edges=[edge],
                competitor_offers=[_offer("aldi_us", "a1", "12", 3.50, longitude=-94.205)],
                price_basis="exact_package",
                selection_policy="lowest_eligible_local_offer",
                radius_miles=3,
                generated_at=DECIDED_AT,
            )
        )

    summary = reconcile_local_comparisons(rows)
    assert summary["selected_product_locations"] == 2
    assert summary["losing_product_locations"] == 2
    assert summary["unique_losing_stores"] == 1
    assert summary["unique_scored_stores"] == 1


def test_unscored_comparison_has_explicit_reason() -> None:
    rows = LocalComparisonProjectorV2().project(
        analysis_id="analysis-1",
        competitor_retailer_id="aldi_us",
        policy_revision="milk:strict:2.0.0-shadow",
        benchmark=_offer("walmart_us", "w1", "100", 4.00, longitude=-94.21),
        edges=[],
        competitor_offers=[],
        price_basis="exact_package",
        selection_policy="lowest_eligible_local_offer",
        radius_miles=3,
        generated_at=DECIDED_AT,
    )

    assert rows[0]["coverage"] == {
        "semantic": False,
        "availability": False,
        "price": False,
        "reason": "no_eligible_match",
    }
    validate_instance(
        REPOSITORY_ROOT,
        "local-comparison-observation-v2.schema.json",
        rows[0],
        label="unscored local comparison v2",
    )


@pytest.mark.parametrize(
    "pack_id",
    [
        "fresh_shell_eggs",
        "fresh_fluid_milk",
        "fresh_ground_beef",
        "fresh_strawberries",
        "fresh_bananas",
    ],
)
def test_policy_compiler_is_category_neutral(pack_id: str) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
    preferred = str(pack.reporting["decision_rules"]["preferred_scorecard_profile_id"])
    policy = compile_matching_policy_v2(pack, preferred)

    assert policy.product_pack_id == pack_id
    assert policy.attributes
    assert policy.eligible_price_bases
    assert dict(policy.price_basis_requirements).get("exact_package")
    assert policy.auto_approval_tiers == ()
    assert len({attribute.name for attribute in policy.attributes}) == len(policy.attributes)


@pytest.mark.parametrize(
    ("pack_id", "profile_id", "hard_blocker"),
    [
        ("fresh_fluid_milk", "all_brand", "volume_oz"),
        ("fresh_shell_eggs", "strict", "size"),
    ],
)
def test_spec_first_packs_do_not_fail_on_brand_alone(
    pack_id: str,
    profile_id: str,
    hard_blocker: str,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
    profile = pack.profile(profile_id)
    policy = compile_matching_policy_v2(pack, profile_id)
    benchmark_attributes = {
        rule.name: AttributeValue(
            "Walmart Regional Dairy" if rule.name == "brand" else "same-spec",
            f"pdp:walmart_us:w1:{rule.name}",
        )
        for rule in policy.attributes
    }
    competitor_attributes = {
        rule.name: AttributeValue(
            "Competitor Private Label" if rule.name == "brand" else "same-spec",
            f"pdp:aldi_us:a1:{rule.name}",
        )
        for rule in policy.attributes
    }
    benchmark = ListingEvidence(
        listing_id=f"listing-walmart-{pack_id}",
        retailer_id="walmart_us",
        retailer_product_id="w1",
        attributes=benchmark_attributes,
        brand="Walmart Regional Dairy",
        brand_type="regional",
        brand_verified=True,
    )
    competitor = ListingEvidence(
        listing_id=f"listing-aldi-{pack_id}",
        retailer_id="aldi_us",
        retailer_product_id="a1",
        attributes=competitor_attributes,
        brand="Competitor Private Label",
        brand_type="private_label",
        brand_verified=True,
    )

    decision = DeterministicMatchEngineV2().evaluate(
        benchmark,
        competitor,
        policy,
        decided_at=DECIDED_AT,
    )

    brand = next(row for row in decision.evidence if row.attribute == "brand")
    assert profile["brand_policy"] == "ignore_brand"
    assert brand.role == "descriptive"
    assert brand.outcome == "conflict"
    assert decision.tier == "exact_specification"
    assert decision.status == "candidate"

    conflicting_attributes = dict(competitor_attributes)
    conflicting_attributes[hard_blocker] = AttributeValue(
        "different-spec",
        f"pdp:aldi_us:a1:{hard_blocker}",
    )
    conflict = DeterministicMatchEngineV2().evaluate(
        benchmark,
        ListingEvidence(
            listing_id=f"listing-aldi-conflict-{pack_id}",
            retailer_id="aldi_us",
            retailer_product_id="a2",
            attributes=conflicting_attributes,
            brand="Walmart Regional Dairy",
            brand_type="regional",
            brand_verified=True,
        ),
        policy,
        decided_at=DECIDED_AT,
    )

    assert conflict.status == "not_comparable"
    assert conflict.tier is None


@pytest.mark.parametrize(
    ("benchmark_volume_oz", "competitor_volume_oz"),
    [(128, 64), (64, 32), (32, 16)],
)
def test_milk_exact_package_volume_is_a_non_overridable_hard_blocker(
    benchmark_volume_oz: int,
    competitor_volume_oz: int,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    policy = compile_matching_policy_v2(pack, "all_brand")
    base_attributes = {
        rule.name: AttributeValue(
            benchmark_volume_oz if rule.name == "volume_oz" else "same-spec",
            f"pdp:walmart_us:w1:{rule.name}",
        )
        for rule in policy.attributes
    }
    competitor_attributes = {
        rule.name: AttributeValue(
            competitor_volume_oz if rule.name == "volume_oz" else "same-spec",
            f"pdp:aldi_us:a1:{rule.name}",
        )
        for rule in policy.attributes
    }

    decision = DeterministicMatchEngineV2().evaluate(
        ListingEvidence(
            listing_id="listing-walmart-milk-volume",
            retailer_id="walmart_us",
            retailer_product_id="w1",
            attributes=base_attributes,
            brand="Same Regional Dairy",
            brand_type="regional",
            brand_verified=True,
        ),
        ListingEvidence(
            listing_id="listing-aldi-milk-volume",
            retailer_id="aldi_us",
            retailer_product_id="a1",
            attributes=competitor_attributes,
            brand="Same Regional Dairy",
            brand_type="regional",
            brand_verified=True,
        ),
        policy,
        decided_at=DECIDED_AT,
    )

    volume = next(row for row in decision.evidence if row.attribute == "volume_oz")
    assert volume.role == "hard_blocker"
    assert volume.outcome == "conflict"
    assert decision.status == "not_comparable"
    assert decision.tier is None


def test_product_pack_can_configure_v2_attribute_roles_without_core_branching() -> None:
    base = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    document = copy.deepcopy(base.document)
    document["matching_v2"] = {
        "policy_version": "2.1.0-shadow",
        "certification_state": "shadow",
        "attribute_roles": {
            "volume_oz": {"role": "required_exact", "critical": True, "weight": 2},
            "fat_type": {"role": "hard_blocker", "critical": True, "weight": 3},
        },
        "exact_item_identifier_schemes": ["gtin", "upc"],
        "eligible_price_bases": ["exact_package", "normalized_unit"],
        "price_basis_requirements": {"exact_package": ["volume_oz"]},
        "minimum_equivalent_coverage": 0.9,
        "equivalent_score_threshold": 0.95,
        "allow_comparable_substitute": True,
        "auto_approval_tiers": ["exact_item", "exact_specification"],
        "geography_policy": "physical_store_radius",
        "scope_mode": "observed_distribution",
        "fulfillment_types": ["pickup"],
    }
    pack = ProductPackLoader(REPOSITORY_ROOT).load_document(document, label="configured v2 milk")
    policy = compile_matching_policy_v2(pack, "private_label")

    roles = {attribute.name: attribute for attribute in policy.attributes}
    assert policy.version == "2.1.0-shadow"
    assert roles["fat_type"].role == "hard_blocker"
    assert roles["fat_type"].weight == 3
    assert policy.minimum_equivalent_coverage == 0.9
    assert policy.eligible_price_bases == ("exact_package", "normalized_unit")
    assert policy.price_basis_requirements == (("exact_package", ("volume_oz",)),)


def _classified_offer(
    pack_attributes: dict[str, object],
    *,
    retailer: str,
    product: str,
    store: str,
    price: str = "3.50",
) -> ClassifiedOffer:
    return ClassifiedOffer(
        offer=NormalizedOffer(
            offer_id=f"offer-{retailer}-{product}-{store}",
            retailer_id=retailer,
            retailer_product_id=product,
            title=f"Product {product}",
            brand=None,
            price=Decimal(price),
            currency="USD",
            zipcode="72712",
            store_number=store,
            latitude=36.37,
            longitude=-94.21,
            in_stock=True,
            product_url=None,
            image_url=None,
            collected_at="2026-08-15T10:00:00Z",
            raw={},
        ),
        in_scope=True,
        scope_reason="milk",
        attributes={
            **pack_attributes,
            "_attribute_provenance": {name: "search" for name in pack_attributes},
        },
        metrics={"package_price": Decimal(price)},
        review_reasons=(),
    )


def test_shadow_evaluator_collapses_placements_and_is_reproducible() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    profile_id = "private_label"
    dimensions = pack.profile(profile_id)["dimensions"]
    values = {str(name): "same" for name in dimensions}
    offers = [
        _classified_offer(values, retailer="walmart_us", product="w1", store="1"),
        _classified_offer(values, retailer="walmart_us", product="w1", store="2"),
        _classified_offer(values, retailer="aldi_us", product="a1", store="10"),
        _classified_offer(values, retailer="aldi_us", product="a1", store="11"),
    ]
    evaluator = MatchingShadowEvaluatorV2(pack, profile_id)

    first = evaluator.evaluate(
        offers,
        benchmark_retailer_id="walmart_us",
        competitor_retailer_id="aldi_us",
        decided_at=DECIDED_AT,
    )
    second = evaluator.evaluate(
        reversed(offers),
        benchmark_retailer_id="walmart_us",
        competitor_retailer_id="aldi_us",
        decided_at=DECIDED_AT,
    )

    assert first.benchmark_listings == 1
    assert first.competitor_listings == 1
    assert first.possible_pairs == first.evaluated_pairs == 1
    assert first.edges[0].tier == "exact_specification"
    assert shadow_result_checksum(first) == shadow_result_checksum(second)


def test_shadow_candidate_generation_blocks_known_hard_conflicts_without_losing_unknowns() -> None:
    evaluator = MatchingShadowEvaluatorV2(
        ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk"),
        "private_label",
        policy=_policy(),
    )
    result = evaluator.evaluate_listings(
        (_listing("walmart_us", "w1", form="fluid_milk"),),
        (
            _listing("aldi_us", "a1", form="fluid_milk"),
            _listing("aldi_us", "a2", form="oat_beverage"),
            _listing("aldi_us", "a3", form=None),
        ),
        benchmark_retailer_id="walmart_us",
        competitor_retailer_id="aldi_us",
        decided_at=DECIDED_AT,
    )

    assert result.possible_pairs == 3
    assert result.evaluated_pairs == 2
    assert result.blocked_pairs == 1
    assert {edge.competitor.retailer_product_id for edge in result.edges} == {"a1", "a3"}
    assert len(result.blocked_review_edges) == 1
    assert result.blocked_review_edges[0].competitor.retailer_product_id == "a2"
    assert result.blocked_review_edges[0].status == "not_comparable"


def test_incremental_listing_accumulator_matches_batch_collapse() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    values = {str(name): "same" for name in pack.profile("private_label")["dimensions"]}
    offers = (
        _classified_offer(values, retailer="walmart_us", product="w1", store="1"),
        _classified_offer(values, retailer="walmart_us", product="w1", store="2"),
    )
    accumulator = ListingEvidenceAccumulatorV2(pack)
    accumulator.extend(offers)

    assert accumulator.listings("walmart_us") == build_listing_evidence_v2(
        offers, pack=pack, retailer_id="walmart_us"
    )


def test_shadow_listing_conflict_fails_closed() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    values = {str(name): "same" for name in pack.profile("private_label")["dimensions"]}
    conflicting = dict(values)
    conflicting["volume_oz"] = "different"
    listings = build_listing_evidence_v2(
        [
            _classified_offer(values, retailer="walmart_us", product="w1", store="1"),
            _classified_offer(conflicting, retailer="walmart_us", product="w1", store="2"),
        ],
        pack=pack,
        retailer_id="walmart_us",
    )

    assert len(listings) == 1
    assert listings[0].attributes["volume_oz"].review_status == "conflicted"
    assert listings[0].attributes["volume_oz"].value is None
