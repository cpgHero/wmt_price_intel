"""Location-master read and administration endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from rci_locations.models import ImportState, LocationSearchResult, RetailerCount
from rci_locations.normalization import normalize_country, normalize_zipcode
from rci_locations.ports import LocationReadRepository
from rci_locations.repository import PostgresLocationRepository

router = APIRouter(prefix="/api/v1")


class RetailerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    country: str
    active: bool
    catalogued: bool
    location_count: int


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    retailer_id: str
    provider: str
    provider_location_id: str | None
    store_number: str
    store_name: str | None
    raw_zipcode: str | None
    zipcode: str | None
    city: str | None
    state: str | None
    country: str
    latitude: float | None
    longitude: float | None


class LocationCountResponse(BaseModel):
    retailer_id: str
    location_count: int


class ImportStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_path: str
    source_sha256: str
    status: str
    total_rows: int
    imported_rows: int
    skipped_rows: int
    retailer_count: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


def get_location_repository(request: Request) -> LocationReadRepository:
    return PostgresLocationRepository(request.app.state.database_probe.engine)


LocationRepositoryDependency = Annotated[LocationReadRepository, Depends(get_location_repository)]
PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0)]


@router.get("/retailers", response_model=list[RetailerResponse], tags=["locations"])
async def list_retailers(
    repository: LocationRepositoryDependency,
    country: str | None = None,
) -> list[RetailerCount]:
    canonical_country = normalize_country(country) if country is not None else None
    return await repository.list_retailers(canonical_country)


@router.get(
    "/retailers/{retailer_id}/locations/count",
    response_model=LocationCountResponse,
    tags=["locations"],
)
async def count_locations(
    retailer_id: str,
    repository: LocationRepositoryDependency,
) -> LocationCountResponse:
    return LocationCountResponse(
        retailer_id=retailer_id,
        location_count=await repository.count_locations(retailer_id),
    )


@router.get("/locations/search", response_model=list[LocationResponse], tags=["locations"])
async def search_locations(
    repository: LocationRepositoryDependency,
    retailer_id: str | None = None,
    country: str | None = None,
    query: str | None = Query(default=None, max_length=200),
    zipcode: str | None = Query(default=None, max_length=20),
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> list[LocationSearchResult]:
    canonical_country = normalize_country(country) if country is not None else None
    canonical_zipcode = (
        normalize_zipcode(zipcode, canonical_country) if zipcode is not None else None
    )
    return await repository.search_locations(
        retailer_id=retailer_id,
        country=canonical_country,
        query=query.strip() if query else None,
        zipcode=canonical_zipcode,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/location-imports/latest",
    response_model=ImportStatusResponse,
    tags=["admin"],
)
async def latest_location_import(
    repository: LocationRepositoryDependency,
) -> ImportState:
    imports = await repository.list_imports(1)
    if not imports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No location imports have run.",
        )
    return imports[0]


@router.get(
    "/admin/location-imports",
    response_model=list[ImportStatusResponse],
    tags=["admin"],
)
async def list_location_imports(
    repository: LocationRepositoryDependency,
    limit: PageLimit = 20,
) -> list[ImportState]:
    return await repository.list_imports(limit)
