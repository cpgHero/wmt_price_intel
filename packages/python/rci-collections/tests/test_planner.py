from __future__ import annotations

import json
from pathlib import Path

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
    assert len(plan.initial_tasks) == 11500


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
