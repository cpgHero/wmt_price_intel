"""Location-master read and administration endpoints."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import median
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from rci_locations.models import (
    ImportState,
    LocationSearchResult,
    ProximityLocation,
    ProximityPair,
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


class ProximityDistanceSummaryResponse(BaseModel):
    average_miles: float | None
    median_miles: float | None
    p75_miles: float | None
    p90_miles: float | None
    max_miles: float | None


class ProximityStateSummaryResponse(BaseModel):
    state: str
    walmart_locations: int
    covered_locations: int
    gap_locations: int
    coverage_share: float | None
    median_distance_miles: float | None


class ProximityCompetitorNetworkSummaryResponse(BaseModel):
    competitor_location_id: str
    competitor_store_number: str
    competitor_store_name: str | None
    city: str | None
    state: str | None
    latitude: float
    longitude: float
    assigned_walmart_locations: int
    covered_walmart_locations: int
    gap_walmart_locations: int
    coverage_share: float | None
    median_distance_miles: float | None
    nearest_distance_miles: float | None
    farthest_distance_miles: float | None
    representative_pair_key: str


class ProximityMapBoundsResponse(BaseModel):
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float


class ProximityMapClusterResponse(BaseModel):
    role: str
    latitude: float
    longitude: float
    location_count: int
    covered_locations: int
    gap_locations: int
    label: str
    representative_pair_key: str | None


class ProximityMapSummaryResponse(BaseModel):
    schema_version: str
    cluster_cell_degrees: float
    bounds: ProximityMapBoundsResponse | None
    walmart_clusters: list[ProximityMapClusterResponse]
    competitor_clusters: list[ProximityMapClusterResponse]


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
    distance_summary: ProximityDistanceSummaryResponse
    state_summary: list[ProximityStateSummaryResponse]
    competitor_network_summary: list[ProximityCompetitorNetworkSummaryResponse]
    map_summary: ProximityMapSummaryResponse
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


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[int(rank)]
    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]
    return lower_value + (upper_value - lower_value) * (rank - lower)


def _distance_summary(distances: list[float]) -> ProximityDistanceSummaryResponse:
    return ProximityDistanceSummaryResponse(
        average_miles=_rounded(sum(distances) / len(distances)) if distances else None,
        median_miles=_rounded(median(distances)) if distances else None,
        p75_miles=_rounded(_percentile(distances, 0.75)),
        p90_miles=_rounded(_percentile(distances, 0.9)),
        max_miles=_rounded(max(distances)) if distances else None,
    )


@dataclass(slots=True)
class _MapClusterBucket:
    representative_location: ProximityLocation
    representative_pair_key: str
    covered_locations: int = 0
    gap_locations: int = 0
    latitude_total: float = 0.0
    location_count: int = 0
    longitude_total: float = 0.0


def _pair_key(pair: ProximityPair) -> str:
    return f"{pair.benchmark.id}::{pair.competitor.id}"


def _cluster_label(location: ProximityLocation, location_count: int) -> str:
    place = ", ".join(part for part in (location.city, location.state) if part)
    if location_count == 1:
        return place or location.store_name or location.store_number
    return f"{place or location.state or location.country} · {location_count} locations"


def _map_clusters(
    pairs: list[ProximityPair],
    *,
    role: str,
    selected_radius_miles: float,
    cluster_cell_degrees: float,
) -> list[ProximityMapClusterResponse]:
    grouped: dict[tuple[int, int], _MapClusterBucket] = {}
    represented_competitors: set[str] = set()
    for pair in pairs:
        if role == "competitor":
            if pair.competitor.id in represented_competitors:
                continue
            represented_competitors.add(pair.competitor.id)
            location = pair.competitor
        else:
            location = pair.benchmark
        key = (
            math.floor(location.latitude / cluster_cell_degrees),
            math.floor(location.longitude / cluster_cell_degrees),
        )
        if key not in grouped:
            grouped[key] = _MapClusterBucket(
                representative_location=location,
                representative_pair_key=_pair_key(pair),
            )
        bucket = grouped[key]
        bucket.latitude_total += location.latitude
        bucket.longitude_total += location.longitude
        bucket.location_count += 1
        if pair.distance_miles <= selected_radius_miles:
            bucket.covered_locations += 1
        else:
            bucket.gap_locations += 1

    clusters: list[ProximityMapClusterResponse] = []
    for bucket in grouped.values():
        location_count = bucket.location_count
        clusters.append(
            ProximityMapClusterResponse(
                role=role,
                latitude=round(bucket.latitude_total / location_count, 4),
                longitude=round(bucket.longitude_total / location_count, 4),
                location_count=location_count,
                covered_locations=bucket.covered_locations,
                gap_locations=bucket.gap_locations,
                label=_cluster_label(bucket.representative_location, location_count),
                representative_pair_key=bucket.representative_pair_key,
            )
        )
    return sorted(clusters, key=lambda cluster: (-cluster.location_count, cluster.label))


def _proximity_map_summary(
    pairs: list[ProximityPair],
    *,
    selected_radius_miles: float,
) -> ProximityMapSummaryResponse:
    cluster_cell_degrees = 2.0
    points = [location for pair in pairs for location in (pair.benchmark, pair.competitor)]
    bounds = (
        ProximityMapBoundsResponse(
            min_latitude=round(min(location.latitude for location in points), 4),
            max_latitude=round(max(location.latitude for location in points), 4),
            min_longitude=round(min(location.longitude for location in points), 4),
            max_longitude=round(max(location.longitude for location in points), 4),
        )
        if points
        else None
    )
    return ProximityMapSummaryResponse(
        schema_version="1.0.0-proximity-map-summary",
        cluster_cell_degrees=cluster_cell_degrees,
        bounds=bounds,
        walmart_clusters=_map_clusters(
            pairs,
            role="walmart",
            selected_radius_miles=selected_radius_miles,
            cluster_cell_degrees=cluster_cell_degrees,
        ),
        competitor_clusters=_map_clusters(
            pairs,
            role="competitor",
            selected_radius_miles=selected_radius_miles,
            cluster_cell_degrees=cluster_cell_degrees,
        ),
    )


def _proximity_state_summary(
    pairs: list[ProximityPair],
    *,
    selected_radius_miles: float,
) -> list[ProximityStateSummaryResponse]:
    grouped: dict[str, list[ProximityPair]] = {}
    for pair in pairs:
        state = pair.benchmark.state or "Unknown"
        grouped.setdefault(state, []).append(pair)

    rows: list[ProximityStateSummaryResponse] = []
    for state, state_pairs in grouped.items():
        distances = [pair.distance_miles for pair in state_pairs]
        covered = sum(pair.distance_miles <= selected_radius_miles for pair in state_pairs)
        total = len(state_pairs)
        rows.append(
            ProximityStateSummaryResponse(
                state=state,
                walmart_locations=total,
                covered_locations=covered,
                gap_locations=max(0, total - covered),
                coverage_share=(covered / total if total else None),
                median_distance_miles=_rounded(median(distances)) if distances else None,
            )
        )
    return sorted(rows, key=lambda row: (-row.gap_locations, row.state))


def _proximity_competitor_network_summary(
    pairs: list[ProximityPair],
    *,
    selected_radius_miles: float,
) -> list[ProximityCompetitorNetworkSummaryResponse]:
    grouped: dict[str, list[ProximityPair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.competitor.id, []).append(pair)

    rows: list[ProximityCompetitorNetworkSummaryResponse] = []
    for competitor_location_id, network_pairs in grouped.items():
        competitor = network_pairs[0].competitor
        sorted_pairs = sorted(network_pairs, key=lambda pair: pair.distance_miles)
        distances = [pair.distance_miles for pair in sorted_pairs]
        covered = sum(pair.distance_miles <= selected_radius_miles for pair in sorted_pairs)
        total = len(sorted_pairs)
        rows.append(
            ProximityCompetitorNetworkSummaryResponse(
                competitor_location_id=competitor_location_id,
                competitor_store_number=competitor.store_number,
                competitor_store_name=competitor.store_name,
                city=competitor.city,
                state=competitor.state,
                latitude=competitor.latitude,
                longitude=competitor.longitude,
                assigned_walmart_locations=total,
                covered_walmart_locations=covered,
                gap_walmart_locations=max(0, total - covered),
                coverage_share=(covered / total if total else None),
                median_distance_miles=_rounded(median(distances)) if distances else None,
                nearest_distance_miles=_rounded(distances[0]) if distances else None,
                farthest_distance_miles=_rounded(distances[-1]) if distances else None,
                representative_pair_key=_pair_key(sorted_pairs[0]),
            )
        )
    return sorted(
        rows,
        key=lambda row: (
            -row.covered_walmart_locations,
            -row.assigned_walmart_locations,
            row.median_distance_miles if row.median_distance_miles is not None else math.inf,
            row.competitor_store_number,
        ),
    )


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
        distance_summary=_distance_summary(distances),
        state_summary=_proximity_state_summary(
            list(result.pairs),
            selected_radius_miles=selected_radius_miles,
        ),
        competitor_network_summary=_proximity_competitor_network_summary(
            list(result.pairs),
            selected_radius_miles=selected_radius_miles,
        ),
        map_summary=_proximity_map_summary(
            list(result.pairs),
            selected_radius_miles=selected_radius_miles,
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
