from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

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
