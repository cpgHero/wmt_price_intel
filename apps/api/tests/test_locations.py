from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from rci_api.locations import get_location_repository
from rci_api.main import create_app
from rci_locations import InMemoryLocationRepository, RetailerCatalog
from rci_locations.importer import transform_row
from rci_locations.models import ImportSummary

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
