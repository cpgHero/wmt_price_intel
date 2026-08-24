from __future__ import annotations

from pathlib import Path

from rci_collections import (
    CollectionPlanner,
    CollectionRetailerCatalog,
    InMemoryCollectionRepository,
)
from rci_collections.geography import CollectionGeographyResolver, haversine_miles
from rci_collections.models import LocationUnit

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _catalog() -> CollectionRetailerCatalog:
    return CollectionRetailerCatalog.from_path(REPOSITORY_ROOT / "config/retailer-catalog.json")


def _unit(
    identifier: str,
    retailer_id: str,
    store_number: str,
    zipcode: str,
    state: str,
    latitude: float,
    longitude: float,
    *,
    city: str = "Example",
) -> LocationUnit:
    return LocationUnit(
        id=identifier,
        retailer_id=retailer_id,
        zipcode=zipcode,
        store_number=store_number,
        state=state,
        country="USA",
        store_name=f"Store {store_number}",
        city=city,
        latitude=latitude,
        longitude=longitude,
    )


async def test_per_state_resolution_is_deterministic_and_spread() -> None:
    units = [
        _unit(
            "00000000-0000-0000-0000-000000000001", "walmart_us", "1", "11111", "AR", 35.0, -94.0
        ),
        _unit(
            "00000000-0000-0000-0000-000000000002", "walmart_us", "2", "22222", "AR", 35.0, -93.0
        ),
        _unit(
            "00000000-0000-0000-0000-000000000003", "walmart_us", "3", "33333", "AR", 35.0, -92.0
        ),
        _unit(
            "00000000-0000-0000-0000-000000000004", "walmart_us", "4", "44444", "TX", 32.0, -100.0
        ),
        _unit(
            "00000000-0000-0000-0000-000000000005", "walmart_us", "5", "55555", "TX", 32.0, -96.0
        ),
        _unit(
            "10000000-0000-0000-0000-000000000001", "aldi_us", "A1", "11111", "AR", 35.001, -94.001
        ),
    ]
    repository = InMemoryCollectionRepository(units)
    resolver = CollectionGeographyResolver(repository, _catalog())
    request = {
        "primary_retailer_id": "walmart_us",
        "competitor_retailer_ids": ["aldi_us", "amazon_us_same_day"],
        "country": "USA",
        "primary_selection": {
            "mode": "per_state",
            "states": ["AR", "TX"],
            "locations_per_state": 2,
        },
        "competitor_correspondence": {"mode": "same_zip", "radius_miles": None},
    }

    first = await resolver.resolve(request)
    second = await resolver.resolve(request)

    assert first.checksum == second.checksum
    primary = [item for item in first.locations if item.role == "primary"]
    assert len(primary) == 4
    assert {item.state for item in primary} == {"AR", "TX"}
    amazon = [item for item in first.locations if item.retailer_id == "amazon_us_same_day"]
    assert len(amazon) == len({item.zipcode for item in primary})
    assert all(item.store_number is None for item in amazon)


async def test_radius_resolution_deduplicates_competitors_and_preserves_edges() -> None:
    primary_one = _unit(
        "00000000-0000-0000-0000-000000000011",
        "walmart_us",
        "11",
        "72712",
        "AR",
        36.3729,
        -94.2088,
    )
    primary_two = _unit(
        "00000000-0000-0000-0000-000000000012",
        "walmart_us",
        "12",
        "72758",
        "AR",
        36.35,
        -94.18,
    )
    competitor = _unit(
        "10000000-0000-0000-0000-000000000011",
        "aldi_us",
        "A11",
        "72712",
        "AR",
        36.36,
        -94.19,
    )
    assert (
        haversine_miles(
            primary_one.latitude or 0,
            primary_one.longitude or 0,
            competitor.latitude or 0,
            competitor.longitude or 0,
        )
        < 3
    )
    repository = InMemoryCollectionRepository([primary_one, primary_two, competitor])
    resolver = CollectionGeographyResolver(repository, _catalog())
    resolution = await resolver.resolve(
        {
            "primary_retailer_id": "walmart_us",
            "competitor_retailer_ids": ["aldi_us"],
            "country": "USA",
            "primary_selection": {"mode": "all_locations"},
            "competitor_correspondence": {"mode": "radius", "radius_miles": 3},
        }
    )

    competitor_locations = [item for item in resolution.locations if item.retailer_id == "aldi_us"]
    assert len(competitor_locations) == 1
    assert len(resolution.edges) == 2
    assert all(edge.distance_miles <= 3 for edge in resolution.edges)


async def test_radius_resolution_can_limit_nearest_locations_per_retailer() -> None:
    primary = _unit(
        "00000000-0000-0000-0000-000000000013",
        "walmart_us",
        "13",
        "46038",
        "IN",
        39.980997,
        -86.001516,
    )
    near_aldi = _unit(
        "10000000-0000-0000-0000-000000000013",
        "aldi_us",
        "A13",
        "46038",
        "IN",
        39.981,
        -86.002,
    )
    farther_aldi = _unit(
        "10000000-0000-0000-0000-000000000014",
        "aldi_us",
        "A14",
        "46038",
        "IN",
        39.99,
        -86.01,
    )
    target = _unit(
        "20000000-0000-0000-0000-000000000013",
        "target_us",
        "T13",
        "46038",
        "IN",
        39.982,
        -86.003,
    )
    repository = InMemoryCollectionRepository([primary, farther_aldi, target, near_aldi])
    resolver = CollectionGeographyResolver(repository, _catalog())

    resolution = await resolver.resolve(
        {
            "primary_retailer_id": "walmart_us",
            "competitor_retailer_ids": ["aldi_us", "target_us"],
            "country": "USA",
            "primary_selection": {"mode": "all_locations"},
            "competitor_correspondence": {
                "mode": "radius",
                "radius_miles": 5,
                "maximum_locations_per_retailer_per_primary": 1,
            },
        }
    )

    competitors = [item for item in resolution.locations if item.role == "competitor"]
    assert {(item.retailer_id, item.store_number) for item in competitors} == {
        ("aldi_us", "A13"),
        ("target_us", "T13"),
    }
    assert len(resolution.edges) == 2


async def test_approved_resolution_plans_from_snapshot_not_live_master() -> None:
    repository = InMemoryCollectionRepository(
        [
            _unit(
                "00000000-0000-0000-0000-000000000021",
                "walmart_us",
                "21",
                "03038",
                "NH",
                42.8,
                -71.3,
            ),
            _unit(
                "10000000-0000-0000-0000-000000000021",
                "aldi_us",
                "475-107",
                "03039",
                "NH",
                42.81,
                -71.31,
            ),
        ]
    )
    catalog = _catalog()
    resolver = CollectionGeographyResolver(repository, catalog)
    resolution = await repository.save_geography_resolution(
        await resolver.resolve(
            {
                "primary_retailer_id": "walmart_us",
                "competitor_retailer_ids": ["aldi_us", "amazon_us_same_day"],
                "country": "USA",
                "primary_selection": {"mode": "custom_zips", "zipcodes": ["03038"]},
                "competitor_correspondence": {"mode": "radius", "radius_miles": 3},
            }
        )
    )
    repository._location_units.clear()
    planner = CollectionPlanner(repository, catalog)
    config = {
        "id": "snapshot-test",
        "benchmark_retailer": "walmart_us",
        "query": {"keyword": "milk"},
        "retailers": [
            {
                "retailer_id": item.retailer_id,
                "adapter_id": item.adapter_id,
                "enabled": True,
            }
            for item in catalog.enabled()
        ],
        "geography": {
            "strategy": "approved_resolution",
            "country": "USA",
            "resolution_id": resolution.id,
            "resolution_checksum": resolution.checksum,
        },
        "pagination": {"max_pages": 1, "stop_on_empty": True},
    }

    plan = await planner.plan(config)

    assert plan.estimate.estimated_total_pages == 3
    assert plan.estimate.estimated_total_credits == 5
    assert {
        task.zipcode for task in plan.initial_tasks if task.retailer_id == "amazon_us_same_day"
    } == {"03038"}
