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
                        engine._comparison_metric(profile),
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


async def test_published_product_pack_version_is_immutable() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    repository = InMemoryProductPackRepository()

    assert await repository.publish(pack) == pack
    assert await repository.publish(pack) == pack
    with pytest.raises(ValueError, match="immutable"):
        await repository.publish(replace(pack, checksum="0" * 64))
