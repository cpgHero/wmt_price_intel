from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from rci_api.locations import get_location_repository
from rci_api.main import create_app
from rci_locations import InMemoryLocationRepository, RetailerCatalog
from rci_locations.importer import transform_row
from rci_locations.models import (
    ImportSummary,
    LocationRecord,
    ProximityLocation,
    RetailerDefinition,
)
from rci_locations.repository import _build_location_grid, _nearest_competitor_location

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _row(*, country: str, store_number: str, zipcode: str) -> dict[str, str]:
    return {
        "id": f"source-{store_number}",
        "created_at": "1784315055347",
        "Store_No": store_number,
        "Name": f"Target {store_number}",
        "Latitude": "44.0",
        "Longitude": "-72.0",
        "Address": "1 Main Street",
        "Street": "1 Main Street",
        "City": "Example",
        "State": "VT",
        "Zip_Code": zipcode,
        "County": "Example",
        "Phone": "",
        "Provider": "Target",
        "Status": "active",
        "Country": country,
        "mc_location_id": f"mc-{store_number}",
    }


async def _repository() -> InMemoryLocationRepository:
    repository = InMemoryLocationRepository()
    catalog = RetailerCatalog.from_path(REPOSITORY_ROOT / "config" / "retailer-catalog.json")
    records = []
    for row in (
        _row(country="USA", store_number="001", zipcode="5804"),
        _row(country="Australia", store_number="5213", zipcode="870"),
    ):
        location, resolved = transform_row(row, catalog)
        await repository.upsert_retailers([resolved.retailer], resolved.aliases)
        records.append(location)
    import_id = await repository.begin_import("locations.csv", "a" * 64)
    await repository.upsert_locations(import_id, records)
    await repository.complete_import(
        ImportSummary(
            import_id=import_id,
            source_path="locations.csv",
            source_sha256="a" * 64,
            total_rows=2,
            imported_rows=2,
            skipped_rows=0,
            retailer_count=2,
        )
    )
    return repository


async def test_location_counts_search_and_import_status_apis() -> None:
    repository = await _repository()
    app = create_app()
    app.dependency_overrides[get_location_repository] = lambda: repository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()

        retailers = (await client.get("/api/v1/retailers", params={"country": "US"})).json()
        assert [item["id"] for item in retailers] == ["target_us"]
        assert retailers[0]["location_count"] == 1

        count = await client.get("/api/v1/retailers/target_us/locations/count")
        assert count.json() == {"retailer_id": "target_us", "location_count": 1}

        search = await client.get(
            "/api/v1/locations/search",
            params={"retailer_id": "target_us", "country": "USA", "zipcode": "5804"},
        )
        assert search.status_code == 200
        assert [item["store_number"] for item in search.json()] == ["001"]
        assert search.json()[0]["raw_zipcode"] == "5804"
        assert search.json()[0]["zipcode"] == "05804"

        imports = await client.get("/api/v1/admin/location-imports")
        assert imports.status_code == 200
        assert imports.json()[0]["status"] == "completed"
        assert imports.json()[0]["imported_rows"] == 2

        latest = await client.get("/api/v1/admin/location-imports/latest")
        assert latest.status_code == 200
        assert latest.json()["id"] == imports.json()[0]["id"]


def _location(
    retailer_id: str,
    store_number: str,
    *,
    latitude: float,
    longitude: float,
    state: str = "AR",
    eligible: bool = True,
) -> LocationRecord:
    return LocationRecord(
        retailer_id=retailer_id,
        provider=retailer_id,
        provider_location_id=f"provider-{store_number}",
        store_number=store_number,
        store_name=f"{retailer_id} {store_number}",
        raw_zipcode="72712",
        zipcode="72712",
        street="1 Main Street",
        address="1 Main Street",
        city="Bentonville",
        state=state,
        county="Benton",
        country="USA",
        latitude=latitude,
        longitude=longitude,
        status="active",
        collection_eligible=eligible,
        collection_eligibility_reason=None if eligible else "retired",
        source_created_at=None,
        source_row_id=store_number,
        raw_row={},
    )


def _proximity_location(
    retailer_id: str,
    store_number: str,
    *,
    latitude: float,
    longitude: float,
) -> ProximityLocation:
    return ProximityLocation(
        id=f"{retailer_id}-{store_number}",
        retailer_id=retailer_id,
        retailer_display_name=retailer_id,
        provider_location_id=f"provider-{store_number}",
        store_number=store_number,
        store_name=f"{retailer_id} {store_number}",
        zipcode="72712",
        city="Bentonville",
        state="AR",
        country="USA",
        latitude=latitude,
        longitude=longitude,
    )


def test_spatial_grid_nearest_refines_to_exact_adjacent_cell_match() -> None:
    benchmark = _proximity_location(
        "walmart_us",
        "100",
        latitude=36.01,
        longitude=-94.01,
    )
    competitors = [
        _proximity_location(
            "competitor_us",
            "same-cell-seed",
            latitude=36.95,
            longitude=-94.95,
        ),
        _proximity_location(
            "competitor_us",
            "adjacent-cell-nearest",
            latitude=36.01,
            longitude=-93.99,
        ),
    ]

    nearest = _nearest_competitor_location(
        benchmark,
        competitors,
        _build_location_grid(competitors),
    )

    assert nearest is not None
    assert nearest[0].store_number == "adjacent-cell-nearest"
    assert nearest[1] < 2


async def test_retailer_proximity_pairs_walmart_to_one_selected_competitor() -> None:
    repository = InMemoryLocationRepository()
    await repository.upsert_retailers(
        [
            RetailerDefinition("walmart_us", "Walmart (US)", "USA", True, True),
            RetailerDefinition("costco_us", "Costco", "USA", True, True),
            RetailerDefinition("target_us", "Target", "USA", True, True),
        ],
        [],
    )
    import_id = await repository.begin_import("locations.csv", "b" * 64)
    await repository.upsert_locations(
        import_id,
        [
            _location("walmart_us", "100", latitude=36.3729, longitude=-94.2088),
            _location("walmart_us", "200", latitude=36.0104, longitude=-94.1599),
            _location("costco_us", "c-near", latitude=36.3716, longitude=-94.2035),
            _location("costco_us", "c-far", latitude=34.7465, longitude=-92.2896),
            _location("target_us", "t-ignored", latitude=36.11, longitude=-94.15),
            _location(
                "costco_us",
                "c-unmappable",
                latitude=34.7465,
                longitude=-92.2896,
                eligible=False,
            ),
        ],
    )
    app = create_app()
    app.dependency_overrides[get_location_repository] = lambda: repository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/proximity",
            params={
                "country": "US",
                "competitor_retailer_id": "costco_us",
                "selected_radius_miles": "5",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0.0-retailer-proximity"
    assert body["benchmark"]["id"] == "walmart_us"
    assert body["competitor"]["id"] == "costco_us"
    assert body["summary"]["paired_locations"] == 2
    assert body["summary"]["competitor_mappable_locations"] == 2
    assert body["summary"]["within_selected_radius"] == 1
    assert body["distance_summary"]["median_miles"] is not None
    assert body["distance_summary"]["p75_miles"] is not None
    assert body["distance_summary"]["p90_miles"] is not None
    assert body["state_summary"] == [
        {
            "state": "AR",
            "walmart_locations": 2,
            "covered_locations": 1,
            "gap_locations": 1,
            "coverage_share": 0.5,
            "median_distance_miles": body["distance_summary"]["median_miles"],
        }
    ]
    assert body["competitor_network_summary"] == [
        {
            "competitor_location_id": body["pairs"][0]["competitor"]["id"],
            "competitor_store_number": "c-near",
            "competitor_store_name": "costco_us c-near",
            "city": "Bentonville",
            "state": "AR",
            "latitude": 36.3716,
            "longitude": -94.2035,
            "assigned_walmart_locations": 2,
            "covered_walmart_locations": 1,
            "gap_walmart_locations": 1,
            "coverage_share": 0.5,
            "median_distance_miles": body["distance_summary"]["median_miles"],
            "nearest_distance_miles": body["pairs"][0]["distance_miles"],
            "farthest_distance_miles": body["pairs"][1]["distance_miles"],
            "representative_pair_key": (
                f"{body['pairs'][0]['benchmark']['id']}::{body['pairs'][0]['competitor']['id']}"
            ),
        }
    ]
    assert body["map_summary"]["schema_version"] == "1.0.0-proximity-map-summary"
    assert body["map_summary"]["bounds"]["min_latitude"] <= 36.0104
    assert (
        sum(cluster["location_count"] for cluster in body["map_summary"]["walmart_clusters"]) == 2
    )
    assert (
        sum(cluster["location_count"] for cluster in body["map_summary"]["competitor_clusters"])
        == 1
    )
    assert {pair["competitor"]["store_number"] for pair in body["pairs"]} == {"c-near"}
    assert "not drive time" in body["distance_methodology"]


async def test_retailer_proximity_requires_a_distinct_competitor() -> None:
    repository = InMemoryLocationRepository()
    await repository.upsert_retailers(
        [RetailerDefinition("walmart_us", "Walmart (US)", "USA", True, True)],
        [],
    )
    app = create_app()
    app.dependency_overrides[get_location_repository] = lambda: repository
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await app.state.database_probe.dispose()
        response = await client.get(
            "/api/v1/proximity",
            params={"country": "USA", "competitor_retailer_id": "walmart_us"},
        )

    assert response.status_code == 422
