"""Deterministic geography resolution for collection definitions."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from rci_collections.catalog import CollectionRetailerCatalog
from rci_collections.models import (
    GeographyEdge,
    GeographyLocation,
    GeographyResolution,
    JsonObject,
    LocationUnit,
)
from rci_collections.planner import canonical_checksum
from rci_collections.ports import LocationUniverseRepository
from rci_locations.normalization import normalize_country, normalize_zipcode

EARTH_RADIUS_MILES = 3_958.7613


def haversine_miles(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return the great-circle distance in statute miles."""

    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(value)))


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _location_sort_key(unit: LocationUnit) -> tuple[str, str, str]:
    return unit.state or "", unit.store_number, unit.id


def _coordinates(unit: LocationUnit) -> tuple[float, float]:
    if unit.latitude is None or unit.longitude is None:
        raise ValueError(f"location {unit.id!r} has no coordinates")
    return unit.latitude, unit.longitude


def _spread_sample(rows: Sequence[LocationUnit], count: int) -> list[LocationUnit]:
    """Select a deterministic geographically dispersed sample."""

    candidates = sorted(
        (row for row in rows if row.latitude is not None and row.longitude is not None),
        key=_location_sort_key,
    )
    if len(candidates) <= count:
        return candidates
    if not candidates:
        return sorted(rows, key=_location_sort_key)[:count]
    centroid_lat = sum(_coordinates(row)[0] for row in candidates) / len(candidates)
    centroid_lon = sum(_coordinates(row)[1] for row in candidates) / len(candidates)
    first = min(
        candidates,
        key=lambda row: (
            haversine_miles(
                centroid_lat,
                centroid_lon,
                *_coordinates(row),
            ),
            _location_sort_key(row),
        ),
    )
    selected = [first]
    selected_ids = {first.id}
    while len(selected) < count:
        remaining = [row for row in candidates if row.id not in selected_ids]
        chosen = min(
            remaining,
            key=lambda row: (
                -min(
                    haversine_miles(
                        *_coordinates(row),
                        *_coordinates(existing),
                    )
                    for existing in selected
                ),
                _location_sort_key(row),
            ),
        )
        selected.append(chosen)
        selected_ids.add(chosen.id)
    return sorted(selected, key=_location_sort_key)


class CollectionGeographyResolver:
    def __init__(
        self,
        universe: LocationUniverseRepository,
        retailer_catalog: CollectionRetailerCatalog,
    ) -> None:
        self._universe = universe
        self._catalog = retailer_catalog

    async def resolve(self, request: JsonObject) -> GeographyResolution:
        primary_id = str(request["primary_retailer_id"])
        competitor_ids = sorted(set(_strings(request.get("competitor_retailer_ids"))))
        if primary_id in competitor_ids:
            raise ValueError("the primary retailer cannot also be a competitor")
        primary_capability = self._catalog.get(primary_id)
        if primary_capability.status != "enabled":
            raise ValueError(f"primary retailer {primary_id!r} is not enabled")
        if primary_capability.location_dimension != "store_zip":
            raise ValueError("the primary retailer must have store-level locations")
        for retailer_id in competitor_ids:
            capability = self._catalog.get(retailer_id)
            if capability.status != "enabled":
                raise ValueError(f"competitor retailer {retailer_id!r} is not enabled")

        country = normalize_country(request.get("country", "USA"))
        store_retailer_ids = [primary_id] + [
            retailer_id
            for retailer_id in competitor_ids
            if self._catalog.get(retailer_id).location_dimension == "store_zip"
        ]
        source_rows = await self._universe.list_location_units(store_retailer_ids, country)
        by_retailer: dict[str, list[LocationUnit]] = defaultdict(list)
        for row in source_rows:
            if row.zipcode:
                by_retailer[row.retailer_id].append(row)

        selection = request.get("primary_selection")
        correspondence = request.get("competitor_correspondence")
        if not isinstance(selection, dict) or not isinstance(correspondence, dict):
            raise ValueError("primary selection and competitor correspondence are required")
        exclusions = {
            (str(item.get("retailer_id")), str(item.get("scope_key")))
            for item in request.get("exclusions", [])
            if isinstance(item, dict) and item.get("retailer_id") and item.get("scope_key")
        }
        primary_rows = self._select_primary(by_retailer[primary_id], selection, country)
        primary_rows = [
            row for row in primary_rows if (row.retailer_id, f"location:{row.id}") not in exclusions
        ]
        if not primary_rows:
            raise ValueError("the requested geography contains no primary retailer locations")

        resolution_id = str(uuid4())
        namespace = UUID(resolution_id)
        locations: list[GeographyLocation] = []
        source_to_snapshot: dict[tuple[str, str], str] = {}
        for row in primary_rows:
            location = self._snapshot_store(
                namespace,
                row,
                role="primary",
                reason=str(selection["mode"]),
            )
            locations.append(location)
            source_to_snapshot[(row.retailer_id, row.id)] = location.id

        edge_sources: list[tuple[str, str, float]] = []
        for retailer_id in competitor_ids:
            capability = self._catalog.get(retailer_id)
            if capability.location_dimension == "zipcode":
                for zipcode in sorted({row.zipcode for row in primary_rows if row.zipcode}):
                    if (retailer_id, f"zip:{zipcode}") in exclusions:
                        continue
                    locations.append(
                        self._snapshot_zip(
                            namespace,
                            retailer_id,
                            str(zipcode),
                            country,
                            reason="primary_zip_universe",
                        )
                    )
                continue
            selected, retailer_edges = self._select_competitor(
                primary_rows,
                by_retailer[retailer_id],
                correspondence,
            )
            selected = [
                row for row in selected if (row.retailer_id, f"location:{row.id}") not in exclusions
            ]
            selected_ids = {row.id for row in selected}
            retailer_edges = [
                edge for edge in retailer_edges if edge[1].split("|", 1)[1] in selected_ids
            ]
            for row in selected:
                location = self._snapshot_store(
                    namespace,
                    row,
                    role="competitor",
                    reason=str(correspondence["mode"]),
                )
                locations.append(location)
                source_to_snapshot[(row.retailer_id, row.id)] = location.id
            edge_sources.extend(retailer_edges)

        edges = tuple(
            GeographyEdge(
                primary_location_id=source_to_snapshot[(primary_id, primary_source_id)],
                competitor_location_id=source_to_snapshot[(competitor_id, competitor_source_id)],
                distance_miles=round(distance, 4),
            )
            for primary_source_id, competitor_key, distance in sorted(edge_sources)
            for competitor_id, competitor_source_id in [competitor_key.split("|", 1)]
        )
        ordered_locations = tuple(
            sorted(locations, key=lambda item: (item.role, item.retailer_id, item.scope_key))
        )
        competitors = {
            retailer_id: sum(
                1
                for item in ordered_locations
                if item.role == "competitor" and item.retailer_id == retailer_id
            )
            for retailer_id in competitor_ids
        }
        counts: JsonObject = {
            "total": len(ordered_locations),
            "primary": len(primary_rows),
            "competitors": competitors,
        }
        location_by_id = {item.id: item for item in ordered_locations}
        canonical_request = dict(request)
        canonical_request["country"] = country
        checksum_payload: JsonObject = {
            "request": canonical_request,
            "locations": [
                {
                    "role": item.role,
                    "retailer_id": item.retailer_id,
                    "retailer_location_id": item.retailer_location_id,
                    "scope_key": item.scope_key,
                    "store_number": item.store_number,
                    "zipcode": item.zipcode,
                    "city": item.city,
                    "state": item.state,
                    "country": item.country,
                    "latitude": item.latitude,
                    "longitude": item.longitude,
                    "selection_reason": item.selection_reason,
                }
                for item in ordered_locations
            ],
            "edges": [
                {
                    "primary": location_by_id[edge.primary_location_id].scope_key,
                    "competitor_retailer": location_by_id[edge.competitor_location_id].retailer_id,
                    "competitor": location_by_id[edge.competitor_location_id].scope_key,
                    "distance_miles": edge.distance_miles,
                }
                for edge in edges
            ],
        }
        return GeographyResolution(
            id=resolution_id,
            request=canonical_request,
            checksum=canonical_checksum(checksum_payload),
            status="ready",
            counts=counts,
            locations=ordered_locations,
            edges=edges,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def _select_primary(
        rows: list[LocationUnit], selection: JsonObject, country: str
    ) -> list[LocationUnit]:
        mode = str(selection["mode"])
        states = {value.upper() for value in _strings(selection.get("states"))}
        if mode == "all_locations":
            selected = rows
        elif mode == "states":
            selected = [row for row in rows if row.state and row.state.upper() in states]
        elif mode == "per_state":
            count = int(selection.get("locations_per_state") or 0)
            if count < 1:
                raise ValueError("locations_per_state is required for per_state selection")
            grouped: dict[str, list[LocationUnit]] = defaultdict(list)
            for row in rows:
                if row.state and (not states or row.state.upper() in states):
                    grouped[row.state.upper()].append(row)
            selected = [
                row for state in sorted(grouped) for row in _spread_sample(grouped[state], count)
            ]
        elif mode == "state_cities":
            city_pairs = {
                (str(item["state"]).upper(), str(item["city"]).strip().casefold())
                for item in selection.get("cities", [])
                if isinstance(item, dict) and item.get("state") and item.get("city")
            }
            selected = [
                row
                for row in rows
                if row.state
                and row.city
                and (row.state.upper(), row.city.strip().casefold()) in city_pairs
            ]
        elif mode == "custom_zips":
            zipcodes = {
                normalized
                for value in _strings(selection.get("zipcodes"))
                for normalized in [normalize_zipcode(value, country)]
                if normalized
            }
            selected = [row for row in rows if row.zipcode in zipcodes]
        elif mode == "custom_locations":
            location_ids = set(_strings(selection.get("location_ids")))
            selected = [row for row in rows if row.id in location_ids]
        else:
            raise ValueError(f"unsupported primary selection mode {mode!r}")
        return sorted(selected, key=_location_sort_key)

    @staticmethod
    def _select_competitor(
        primary_rows: list[LocationUnit],
        competitor_rows: list[LocationUnit],
        correspondence: JsonObject,
    ) -> tuple[list[LocationUnit], list[tuple[str, str, float]]]:
        mode = str(correspondence["mode"])
        if mode == "same_zip":
            zipcodes = {row.zipcode for row in primary_rows if row.zipcode}
            return (
                sorted(
                    (row for row in competitor_rows if row.zipcode in zipcodes),
                    key=_location_sort_key,
                ),
                [],
            )
        if mode == "primary_states":
            states = {row.state.upper() for row in primary_rows if row.state}
            return (
                sorted(
                    (row for row in competitor_rows if row.state and row.state.upper() in states),
                    key=_location_sort_key,
                ),
                [],
            )
        if mode != "radius":
            raise ValueError(f"unsupported competitor correspondence mode {mode!r}")
        radius = int(correspondence.get("radius_miles") or 0)
        if radius not in {1, 3, 5}:
            raise ValueError("radius_miles must be 1, 3, or 5")
        grid: dict[tuple[int, int], list[LocationUnit]] = defaultdict(list)
        for row in competitor_rows:
            if row.latitude is not None and row.longitude is not None:
                grid[(math.floor(row.latitude), math.floor(row.longitude))].append(row)
        selected: dict[str, LocationUnit] = {}
        edges: list[tuple[str, str, float]] = []
        for primary in primary_rows:
            if primary.latitude is None or primary.longitude is None:
                continue
            cell = (math.floor(primary.latitude), math.floor(primary.longitude))
            for lat_offset in (-1, 0, 1):
                for lon_offset in (-1, 0, 1):
                    for competitor in grid.get((cell[0] + lat_offset, cell[1] + lon_offset), []):
                        distance = haversine_miles(
                            *_coordinates(primary), *_coordinates(competitor)
                        )
                        if distance <= radius:
                            selected[competitor.id] = competitor
                            edges.append(
                                (
                                    primary.id,
                                    f"{competitor.retailer_id}|{competitor.id}",
                                    distance,
                                )
                            )
        return sorted(selected.values(), key=_location_sort_key), edges

    @staticmethod
    def _snapshot_store(
        namespace: UUID,
        row: LocationUnit,
        *,
        role: str,
        reason: str,
    ) -> GeographyLocation:
        scope_key = f"location:{row.id}"
        return GeographyLocation(
            id=str(uuid5(namespace, f"{role}:{row.retailer_id}:{scope_key}")),
            role=role,
            retailer_id=row.retailer_id,
            retailer_location_id=row.id,
            scope_key=scope_key,
            store_number=row.store_number,
            store_name=row.store_name,
            zipcode=str(row.zipcode),
            city=row.city,
            state=row.state,
            country=row.country,
            latitude=row.latitude,
            longitude=row.longitude,
            selection_reason=reason,
        )

    @staticmethod
    def _snapshot_zip(
        namespace: UUID,
        retailer_id: str,
        zipcode: str,
        country: str,
        *,
        reason: str,
    ) -> GeographyLocation:
        scope_key = f"zip:{zipcode}"
        return GeographyLocation(
            id=str(uuid5(namespace, f"competitor:{retailer_id}:{scope_key}")),
            role="competitor",
            retailer_id=retailer_id,
            retailer_location_id=None,
            scope_key=scope_key,
            store_number=None,
            store_name=None,
            zipcode=zipcode,
            city=None,
            state=None,
            country=country,
            latitude=None,
            longitude=None,
            selection_reason=reason,
        )
