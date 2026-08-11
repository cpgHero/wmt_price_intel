from __future__ import annotations

import copy
import json
from dataclasses import replace
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

from rci_analytics.matching import ComparisonEngine
from rci_analytics.product_pack import (
    InMemoryProductPackRepository,
    ProductPackLoader,
    primary_exact_profile,
)
from rci_contracts import ContractError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_product_pack_loads_with_schema_and_semantic_validation() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")

    assert pack.id == "fresh_strawberries"
    assert pack.version == "1.0.0"
    assert len(pack.checksum) == 64
    assert pack.profile("strict")["dimensions"] == [
        "weight_oz",
        "organic",
        "form",
        "specialty_claim",
    ]
    assert pack.report_blueprint == {
        "id": "fresh_strawberries_leadership",
        "version": "1.0.0",
    }


@pytest.mark.parametrize(
    ("pack_id", "expected_profile"),
    [
        ("fresh_strawberries", "strict"),
        ("fresh_ground_beef", "strict"),
        ("fresh_shell_eggs", "strict"),
        ("fresh_fluid_milk", "same_brand_exact"),
        ("fresh_bananas", "strict_each"),
    ],
)
def test_primary_exact_profile_is_product_pack_driven(
    pack_id: str,
    expected_profile: str,
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)

    profile = primary_exact_profile(pack)

    assert profile["id"] == expected_profile


def test_primary_exact_profile_honors_active_modes_without_requiring_package_price() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_shell_eggs")

    profile = primary_exact_profile(pack, configured_profile_ids={"compatible"})

    assert profile["id"] == "compatible"
    assert ComparisonEngine(pack).comparison_metric(str(profile["id"])) == "price_per_dozen"


def test_narrative_golden_topics_match_each_product_pack_playbook() -> None:
    narrative_benchmarks = json.loads(
        (REPOSITORY_ROOT / "fixtures/golden/narrative-benchmarks.json").read_text()
    )

    for pack_id, benchmark in narrative_benchmarks["categories"].items():
        pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
        assert benchmark["product_pack_id"] == pack.id
        assert (
            benchmark["required_topics"] == pack.reporting["narrative_playbook"]["required_topics"]
        )


def test_milk_uses_generic_distribution_scope_and_brand_portfolios() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")

    assert pack.version == "1.2.0"
    assert all(
        profile["relationship_scope_policy"]
        == {
            "default_scope_mode": "observed_benchmark_product_footprint",
            "allow_scoped_reuse": True,
            "relationship_role": "primary",
            "conflict_behavior": "exclude_from_price_comparison",
            "comparison_context_grain": "benchmark_location",
            "minimum_locations": 1,
            "future_location_policy": "require_review",
        }
        for profile in pack.matching_profiles
    )
    portfolios = {value["id"]: value for value in pack.document["brand_rules"]["portfolios"]}
    assert portfolios["walmart_private_label"]["role"] == "private_label"
    assert portfolios["regional_milk_brands"]["role"] == "regional"
    assert portfolios["national_milk_brands"]["role"] == "national"
    assert pack.reporting["brand_portfolio_panels"]


def test_every_product_pack_defines_generic_decision_reporting_rules() -> None:
    for pack_id in (
        "fresh_strawberries",
        "fresh_ground_beef",
        "fresh_shell_eggs",
        "fresh_fluid_milk",
        "fresh_bananas",
    ):
        pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
        rules = pack.reporting["decision_rules"]

        assert rules["preferred_scorecard_profile_id"] in rules["profile_priority"]
        assert set(rules["profile_priority"]) == {
            str(profile["id"]) for profile in pack.matching_profiles
        }
        assert rules["executive_relationship_states"] == ["suggested", "confirmed"]
        assert rules["parity_display"] == "include"


def test_narrative_decision_lenses_resolve_runtime_metric_names() -> None:
    benchmark_categories = json.loads(
        (REPOSITORY_ROOT / "fixtures/golden/narrative-benchmarks.json").read_text()
    )["categories"]

    for pack_id in benchmark_categories:
        pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
        engine = ComparisonEngine(pack)
        possible_metric_ids = {"coverage.retailer.qualifying_zips", "quality.review_offers"}
        for profile in pack.matching_profiles:
            possible_metric_ids.add(
                ".".join(
                    (
                        "comparison",
                        "competitor",
                        str(profile["geography"]),
                        engine.comparison_metric(str(profile["id"])),
                        str(profile["id"]),
                        "segment",
                        "matches",
                    )
                )
            )
        for lens in pack.reporting["narrative_playbook"]["decision_lenses"]:
            assert any(
                fnmatchcase(metric_id, str(selector))
                for selector in lens["metric_selectors"]
                for metric_id in possible_metric_ids
            ), f"{pack_id}/{lens['id']} has no resolvable runtime metric selector"


def test_semantic_validation_rejects_unknown_dimensions() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    pack = loader.load("fresh_strawberries")
    invalid = copy.deepcopy(pack.document)
    invalid["matching_profiles"][0]["dimensions"].append("not_an_attribute")

    with pytest.raises(ContractError, match="unknown dimensions"):
        loader._validate_semantics(invalid)


def test_semantic_validation_rejects_invalid_wildcard_dimensions() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    pack = loader.load("fresh_shell_eggs")
    invalid = copy.deepcopy(pack.document)
    invalid["matching_profiles"][1]["wildcard_dimensions"].append("not_a_dimension")

    with pytest.raises(ContractError, match="wildcards non-matching dimensions"):
        loader._validate_semantics(invalid)


def test_semantic_validation_rejects_unsafe_conversion_formulas() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    pack = loader.load("fresh_strawberries")
    invalid = copy.deepcopy(pack.document)
    invalid["normalization"]["conversion_rules"][0]["formula"] = "__import__('os').getcwd()"

    with pytest.raises(ContractError, match="unsafe syntax"):
        loader._validate_semantics(invalid)


def test_semantic_validation_rejects_unknown_override_attributes() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    pack = loader.load("fresh_strawberries")
    invalid = copy.deepcopy(pack.document)
    invalid["retailer_overrides"]["walmart_us"]["products"]["44391605"]["attributes"][
        "not_an_attribute"
    ] = "bad"

    with pytest.raises(ContractError, match="unknown attributes"):
        loader._validate_semantics(invalid)


def test_semantic_validation_rejects_unknown_insight_template_fields() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    pack = loader.load("fresh_strawberries")
    invalid = copy.deepcopy(pack.document)
    invalid["reporting"]["insight_rules"][0]["title_template"] = "{category} pressure"

    with pytest.raises(ContractError, match="unknown template fields"):
        loader._validate_semantics(invalid)


def test_semantic_validation_rejects_unknown_decision_profile() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    pack = loader.load("fresh_strawberries")
    invalid = copy.deepcopy(pack.document)
    invalid["reporting"]["decision_rules"]["profile_priority"].append("not_a_profile")

    with pytest.raises(ContractError, match="unknown profiles"):
        loader._validate_semantics(invalid)


def test_semantic_validation_rejects_duplicate_retailer_brand_portfolios() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    pack = loader.load("fresh_fluid_milk")
    invalid = copy.deepcopy(pack.document)
    invalid["brand_rules"]["portfolios"][1]["retailer_ids"] = ["walmart_us"]
    invalid["brand_rules"]["portfolios"][1]["brands"] = ["Great Value"]

    with pytest.raises(ContractError, match="assign a retailer brand more than once"):
        loader._validate_semantics(invalid)


def test_semantic_validation_rejects_unknown_brand_panel_portfolio() -> None:
    loader = ProductPackLoader(REPOSITORY_ROOT)
    pack = loader.load("fresh_fluid_milk")
    invalid = copy.deepcopy(pack.document)
    invalid["reporting"]["brand_portfolio_panels"][0]["competitor_portfolio_ids"] = [
        "missing_portfolio"
    ]

    with pytest.raises(ContractError, match="references unknown portfolios"):
        loader._validate_semantics(invalid)


async def test_published_product_pack_version_is_immutable() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    repository = InMemoryProductPackRepository()

    assert await repository.publish(pack) == pack
    assert await repository.publish(pack) == pack
    with pytest.raises(ValueError, match="immutable"):
        await repository.publish(replace(pack, checksum="0" * 64))
