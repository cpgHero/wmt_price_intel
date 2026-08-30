from __future__ import annotations

import json
from pathlib import Path

import pytest

from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    InMemoryCollectionRepository,
)
from rci_collections.models import LocationUnit
from rci_locations import RetailerCatalog
from rci_locations.importer import read_rows, transform_row

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _retailer_catalog() -> CollectionRetailerCatalog:
    return CollectionRetailerCatalog.from_path(REPOSITORY_ROOT / "config" / "retailer-catalog.json")


def _strawberry_config() -> dict[str, object]:
    return json.loads(
        (REPOSITORY_ROOT / "examples" / "collection-definition.strawberries.json").read_text()
    )


def _egg_config() -> dict[str, object]:
    return json.loads(
        (REPOSITORY_ROOT / "examples" / "collection-definition.eggs.json").read_text()
    )


def _relevant_location_units() -> list[LocationUnit]:
    canonical_catalog = RetailerCatalog.from_path(
        REPOSITORY_ROOT / "config" / "retailer-catalog.json"
    )
    units = []
    for row in read_rows(REPOSITORY_ROOT / "fixtures" / "location_master" / "locations.csv"):
        if row["Provider"] not in {"Walmart", "ALDI"}:
            continue
        location, _ = transform_row(row, canonical_catalog)
        units.append(
            LocationUnit(
                id=str(location.source_row_id),
                retailer_id=location.retailer_id,
                zipcode=location.zipcode,
                store_number=location.store_number,
                state=location.state,
                country=location.country,
            )
        )
    return units


async def test_strawberry_cost_estimate_matches_supplied_contract() -> None:
    repository = InMemoryCollectionRepository(_relevant_location_units())
    planner = CollectionPlanner(repository, _retailer_catalog())

    plan = await planner.plan(_strawberry_config())

    expected = json.loads(
        (REPOSITORY_ROOT / "examples" / "collection-cost-estimate.strawberries.json").read_text()
    )
    by_retailer = {item.retailer_id: item for item in plan.estimate.retailers}
    for retailer in expected["retailers"]:
        actual = by_retailer[retailer["retailer_id"]]
        assert actual.location_units == retailer["location_units"]
        assert actual.estimated_pages == retailer["estimated_pages"]
        assert actual.estimated_credits == retailer["estimated_credits"]
    assert plan.estimate.estimated_total_pages == expected["estimated_total_pages"]
    assert plan.estimate.estimated_total_credits == expected["estimated_total_credits"]
    assert len(plan.initial_tasks) == expected["estimated_total_pages"]
    preflight = [task for task in plan.initial_tasks if task.is_preflight]
    assert len(preflight) == 5
    assert {task.retailer_id for task in preflight} == {"aldi_us"}
    assert plan.availability_gate == {
        "enabled": True,
        "retailer_ids": ["aldi_us"],
        "sample_size_per_retailer": 5,
        "max_billable_404_rate": 0.5,
    }


async def test_egg_vertical_slice_is_configuration_only_and_capped() -> None:
    repository = InMemoryCollectionRepository(_relevant_location_units())
    planner = CollectionPlanner(repository, _retailer_catalog())

    config = _egg_config()
    plan = await planner.plan(config)

    assert config["product_pack"] == {"id": "fresh_shell_eggs", "version": "1.1.0"}
    assert config["query"] == {
        "keyword": "fresh eggs",
        "amazon_same_day_url_template": "https://www.amazon.com/s?k={{keyword}}&i=samedaystore",
        "notes": "One-ZIP, one-page abstraction proof using the validated egg keyword.",
    }
    assert plan.estimate.estimated_total_pages == 3
    assert plan.estimate.estimated_total_credits == 5
    assert {task.request_payload["keyword"] for task in plan.initial_tasks} == {"fresh eggs"}
    assert len([task for task in plan.initial_tasks if task.is_preflight]) == 1


async def test_multi_keyword_query_expands_tasks_and_cost_without_inflating_locations() -> None:
    repository = InMemoryCollectionRepository(
        [
            LocationUnit(
                id="walmart-2098",
                retailer_id="walmart_us",
                zipcode="43219",
                store_number="2098",
                state="OH",
                country="USA",
            )
        ]
    )
    planner = CollectionPlanner(repository, _retailer_catalog())
    config = _egg_config()
    config["query"] = {
        "keyword": "amino vitamins",
        "keywords": ["amino vitamins", "vitamin c"],
        "amazon_same_day_url_template": "https://www.amazon.com/s?k={{keyword}}&i=samedaystore",
        "notes": "Multi-keyword contract test.",
    }
    config["retailers"] = [
        {
            "retailer_id": "walmart_us",
            "adapter_id": "metricscart_walmart_search_zipcode_v2",
            "enabled": True,
            "max_pages_override": 1,
            "request_overrides": {},
        }
    ]
    config["geography"] = {
        "strategy": "all_retailer_locations",
        "benchmark_retailer": "walmart_us",
        "country": "USA",
    }

    plan = await planner.plan(config)

    estimate = plan.estimate.retailers[0]
    assert estimate.location_units == 1
    assert estimate.estimated_pages == 2
    assert estimate.estimated_credits == 2
    assert len(plan.initial_tasks) == 2
    assert {task.request_payload["keyword"] for task in plan.initial_tasks} == {
        "amino vitamins",
        "vitamin c",
    }
    assert len({task.request_fingerprint for task in plan.initial_tasks}) == 2


async def test_planner_rejects_definition_adapter_that_differs_from_enabled_catalog() -> None:
    repository = InMemoryCollectionRepository(
        [
            LocationUnit(
                id="walmart-2098",
                retailer_id="walmart_us",
                zipcode="43219",
                store_number="2098",
                state="OH",
                country="USA",
            )
        ]
    )
    planner = CollectionPlanner(repository, _retailer_catalog())
    config = _egg_config()
    config["retailers"] = [
        {
            "retailer_id": "walmart_us",
            "adapter_id": "metricscart_walmart_typo",
            "enabled": True,
            "max_pages_override": 1,
            "request_overrides": {},
        }
    ]
    config["geography"] = {
        "strategy": "all_retailer_locations",
        "benchmark_retailer": "walmart_us",
        "country": "USA",
    }

    with pytest.raises(ValueError, match="does not match enabled catalog adapter"):
        await planner.plan(config)


async def test_recovery_gate_excludes_only_preflight_scope_and_preserves_full_geography() -> None:
    repository = InMemoryCollectionRepository(
        [
            LocationUnit(
                id=f"walmart-{index}",
                retailer_id="walmart_us",
                zipcode=f"90{index:03d}",
                store_number=str(2400 + index),
                state="CA",
                country="USA",
            )
            for index in range(6)
        ]
    )
    planner = CollectionPlanner(repository, _retailer_catalog())
    config = _strawberry_config()
    config["retailers"] = [
        {
            "retailer_id": "walmart_us",
            "adapter_id": "metricscart_walmart_search_zipcode_v2",
            "enabled": True,
            "max_pages_override": 1,
            "request_overrides": {},
        }
    ]
    config["geography"] = {
        "strategy": "all_retailer_locations",
        "benchmark_retailer": "walmart_us",
        "country": "USA",
    }
    config["availability_gate"] = {
        "enabled": True,
        "retailer_ids": ["walmart_us"],
        "sample_size_per_retailer": 5,
        "max_billable_404_rate": 0.5,
    }
    baseline = await planner.plan(config)
    excluded_scope = next(
        task.location_scope_key for task in baseline.initial_tasks if task.is_preflight
    )

    recovery_gate = config["availability_gate"]
    assert isinstance(recovery_gate, dict)
    recovery_gate.update(
        {
            "minimum_successful_samples": 4,
            "max_transient_nonbillable_failures": 1,
            "excluded_preflight_location_scope_keys": [excluded_scope],
        }
    )
    recovery = await planner.plan(config)

    assert len(recovery.initial_tasks) == 6
    excluded_task = next(
        task for task in recovery.initial_tasks if task.location_scope_key == excluded_scope
    )
    assert excluded_task.is_preflight is False
    assert len([task for task in recovery.initial_tasks if task.is_preflight]) == 5
    assert recovery.availability_gate == {
        "enabled": True,
        "retailer_ids": ["walmart_us"],
        "sample_size_per_retailer": 5,
        "max_billable_404_rate": 0.5,
        "minimum_successful_samples": 4,
        "max_transient_nonbillable_failures": 1,
        "excluded_preflight_location_scope_keys": [excluded_scope],
    }


@pytest.mark.parametrize(
    ("gate_override", "expected_minimum", "expected_maximum"),
    [
        ({"minimum_successful_samples": 4}, 4, 1),
        ({"max_transient_nonbillable_failures": 1}, 4, 1),
    ],
)
async def test_recovery_gate_derives_missing_quorum_companion(
    gate_override: dict[str, int],
    expected_minimum: int,
    expected_maximum: int,
) -> None:
    repository = InMemoryCollectionRepository(
        [
            LocationUnit(
                id=f"walmart-{index}",
                retailer_id="walmart_us",
                zipcode=f"90{index:03d}",
                store_number=str(2400 + index),
                state="CA",
                country="USA",
            )
            for index in range(6)
        ]
    )
    planner = CollectionPlanner(repository, _retailer_catalog())
    config = _strawberry_config()
    config["retailers"] = [
        {
            "retailer_id": "walmart_us",
            "adapter_id": "metricscart_walmart_search_zipcode_v2",
            "enabled": True,
            "max_pages_override": 1,
            "request_overrides": {},
        }
    ]
    config["geography"] = {
        "strategy": "all_retailer_locations",
        "benchmark_retailer": "walmart_us",
        "country": "USA",
    }
    config["availability_gate"] = {
        "enabled": True,
        "retailer_ids": ["walmart_us"],
        "sample_size_per_retailer": 5,
        "max_billable_404_rate": 0.5,
        **gate_override,
    }

    plan = await planner.plan(config)

    assert plan.availability_gate["minimum_successful_samples"] == expected_minimum
    assert plan.availability_gate["max_transient_nonbillable_failures"] == expected_maximum


@pytest.mark.parametrize(
    "gate_policy",
    [
        {"minimum_successful_samples": 4, "max_transient_nonbillable_failures": 1},
        {"minimum_successful_samples": 1, "max_transient_nonbillable_failures": 4},
    ],
)
async def test_resilient_gate_rejects_policy_larger_than_actual_retailer_sample(
    gate_policy: dict[str, int],
) -> None:
    repository = InMemoryCollectionRepository(
        [
            LocationUnit(
                id=f"walmart-{index}",
                retailer_id="walmart_us",
                zipcode=f"90{index:03d}",
                store_number=str(2400 + index),
                state="CA",
                country="USA",
            )
            for index in range(3)
        ]
    )
    planner = CollectionPlanner(repository, _retailer_catalog())
    config = _strawberry_config()
    config["retailers"] = [
        {
            "retailer_id": "walmart_us",
            "adapter_id": "metricscart_walmart_search_zipcode_v2",
            "enabled": True,
            "max_pages_override": 1,
            "request_overrides": {},
        }
    ]
    config["geography"] = {
        "strategy": "all_retailer_locations",
        "benchmark_retailer": "walmart_us",
        "country": "USA",
    }
    config["availability_gate"] = {
        "enabled": True,
        "retailer_ids": ["walmart_us"],
        "sample_size_per_retailer": 5,
        "max_billable_404_rate": 0.5,
        **gate_policy,
    }

    with pytest.raises(ValueError, match="exceeds the 3 available preflight samples"):
        await planner.plan(config)


async def test_non_paginated_retailer_rejects_multiple_pages_before_launch() -> None:
    repository = InMemoryCollectionRepository(
        [
            LocationUnit(
                id="giant-eagle-230",
                retailer_id="giant_eagle_us",
                zipcode="44111",
                store_number="230",
                state="OH",
                country="USA",
            )
        ]
    )
    planner = CollectionPlanner(repository, _retailer_catalog())
    config = _egg_config()
    config["benchmark_retailer"] = "giant_eagle_us"
    config["retailers"] = [
        {
            "retailer_id": "giant_eagle_us",
            "adapter_id": "metricscart_giant_eagle_serp_zipcode",
            "enabled": True,
            "max_pages_override": 2,
            "request_overrides": {},
        }
    ]
    config["geography"] = {
        "strategy": "all_retailer_locations",
        "benchmark_retailer": "giant_eagle_us",
        "country": "USA",
    }

    with pytest.raises(ValueError, match="does not support Search pagination"):
        await planner.plan(config)


async def test_definition_publication_is_checksum_idempotent_and_versioned() -> None:
    repository = InMemoryCollectionRepository()
    config = _strawberry_config()
    from rci_collections.planner import canonical_checksum

    first = await repository.publish_definition(config, canonical_checksum(config))
    repeated = await repository.publish_definition(config, canonical_checksum(config))
    revised_config = dict(config)
    revised_config["name"] = "Revised Strawberry Collection"
    revised = await repository.publish_definition(
        revised_config, canonical_checksum(revised_config)
    )

    assert repeated.version_id == first.version_id
    assert revised.id == first.id
    assert revised.version == 2
