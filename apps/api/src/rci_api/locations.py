"""Location-master read and administration endpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from statistics import median
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from rci_locations.models import (
    ImportState,
    LocationSearchResult,
    ProximityResult,
    RetailerCount,
)
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


class ProximityRetailerResponse(BaseModel):
    id: str
    display_name: str
    country: str
    location_count: int
    mappable_location_count: int


class ProximityLocationResponse(BaseModel):
    id: str
    retailer_id: str
    retailer_display_name: str
    provider_location_id: str | None
    store_number: str
    store_name: str | None
    zipcode: str | None
    city: str | None
    state: str | None
    country: str
    latitude: float
    longitude: float


class ProximityPairResponse(BaseModel):
    benchmark: ProximityLocationResponse
    competitor: ProximityLocationResponse
    distance_miles: float
    within_1_mile: bool
    within_3_miles: bool
    within_5_miles: bool
    within_10_miles: bool


class ProximitySummaryResponse(BaseModel):
    benchmark_mappable_locations: int
    competitor_mappable_locations: int
    paired_locations: int
    selected_radius_miles: float
    within_selected_radius: int
    within_selected_radius_share: float | None
    within_1_mile: int
    within_3_miles: int
    within_5_miles: int
    within_10_miles: int
    nearest_distance_median_miles: float | None
    nearest_distance_average_miles: float | None


class ProximityResponse(BaseModel):
    schema_version: str
    generated_at: datetime
    source_authority: str
    distance_methodology: str
    benchmark: ProximityRetailerResponse
    competitor: ProximityRetailerResponse
    country: str
    selected_radius_miles: float
    state_options: list[str]
    summary: ProximitySummaryResponse
    pairs: list[ProximityPairResponse]


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
RadiusMiles = Annotated[float, Query(ge=0.1, le=250)]


async def _default_walmart_retailer_id(
    repository: LocationReadRepository,
    country: str,
) -> str:
    retailers = await repository.list_retailers(country)
    preferred_ids = {
        "USA": ("walmart_us",),
        "CANADA": ("walmart_ca", "walmart_canada"),
    }.get(country, (f"walmart_{country.lower()}",))
    by_id = {retailer.id: retailer for retailer in retailers}
    for retailer_id in preferred_ids:
        if retailer_id in by_id:
            return retailer_id
    for retailer in retailers:
        if retailer.display_name.casefold().startswith("walmart"):
            return retailer.id
    raise LookupError(f"Walmart retailer is unavailable for {country}")


def _rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _proximity_response(
    result: ProximityResult,
    *,
    country: str,
    selected_radius_miles: float,
) -> ProximityResponse:
    pairs = [
        ProximityPairResponse(
            benchmark=ProximityLocationResponse(**asdict(pair.benchmark)),
            competitor=ProximityLocationResponse(**asdict(pair.competitor)),
            distance_miles=round(pair.distance_miles, 4),
            within_1_mile=pair.distance_miles <= 1,
            within_3_miles=pair.distance_miles <= 3,
            within_5_miles=pair.distance_miles <= 5,
            within_10_miles=pair.distance_miles <= 10,
        )
        for pair in result.pairs
    ]
    distances = [pair.distance_miles for pair in result.pairs]
    within_selected = sum(pair.distance_miles <= selected_radius_miles for pair in result.pairs)
    states = sorted(
        {
            pair.benchmark.state
            for pair in result.pairs
            if pair.benchmark.state is not None and pair.benchmark.state != ""
        }
    )
    paired_count = len(result.pairs)
    return ProximityResponse(
        schema_version="1.0.0-retailer-proximity",
        generated_at=datetime.now(UTC),
        source_authority="retailer_location collection_eligible rows with non-null coordinates",
        distance_methodology=(
            "Nearest competitor is computed from location-master coordinates using "
            "Haversine straight-line distance. This is not drive time, inventory, "
            "product assortment, or store-level in-stock evidence."
        ),
        benchmark=ProximityRetailerResponse(**asdict(result.benchmark)),
        competitor=ProximityRetailerResponse(**asdict(result.competitor)),
        country=country,
        selected_radius_miles=selected_radius_miles,
        state_options=states,
        summary=ProximitySummaryResponse(
            benchmark_mappable_locations=result.benchmark.mappable_location_count,
            competitor_mappable_locations=result.competitor.mappable_location_count,
            paired_locations=paired_count,
            selected_radius_miles=selected_radius_miles,
            within_selected_radius=within_selected,
            within_selected_radius_share=(within_selected / paired_count if paired_count else None),
            within_1_mile=sum(pair.distance_miles <= 1 for pair in result.pairs),
            within_3_miles=sum(pair.distance_miles <= 3 for pair in result.pairs),
            within_5_miles=sum(pair.distance_miles <= 5 for pair in result.pairs),
            within_10_miles=sum(pair.distance_miles <= 10 for pair in result.pairs),
            nearest_distance_median_miles=_rounded(median(distances)) if distances else None,
            nearest_distance_average_miles=(
                _rounded(sum(distances) / len(distances)) if distances else None
            ),
        ),
        pairs=pairs,
    )


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


@router.get("/proximity", response_model=ProximityResponse, tags=["locations"])
async def retailer_proximity(
    repository: LocationRepositoryDependency,
    competitor_retailer_id: str,
    country: str = "USA",
    benchmark_retailer_id: str | None = None,
    selected_radius_miles: RadiusMiles = 1,
) -> ProximityResponse:
    canonical_country = normalize_country(country)
    try:
        benchmark = benchmark_retailer_id or await _default_walmart_retailer_id(
            repository, canonical_country
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if benchmark == competitor_retailer_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose one competitor retailer different from Walmart.",
        )
    try:
        result = await repository.nearest_retailer_proximity(
            benchmark_retailer_id=benchmark,
            competitor_retailer_id=competitor_retailer_id,
            country=canonical_country,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return _proximity_response(
        result,
        country=canonical_country,
        selected_radius_miles=selected_radius_miles,
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
