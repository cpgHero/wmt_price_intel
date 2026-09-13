"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useApplicationContextActions } from "@/app/components/application-context";
import type {
  ProximityCompetitorMarketSummary,
  ProximityCompetitorPair,
  ProximityCompetitorNetworkSummary,
  ProximityCompetitorStateSummary,
  ProximityDistanceSummary,
  LocationRetailer,
  ProximityMapCluster,
  ProximityMapSummary,
  ProximityMarketSummary,
  ProximityPair,
  ProximityStateSummary,
  ProximityView,
} from "@/lib/api";
import {
  competitorFootprintStatesForView,
  type ComparisonScope,
  recommendedScopeForView,
  selectCompetitorForProximityLoad,
} from "@/lib/proximity-workspace-model";

import styles from "./proximity-workspace.module.css";

const RADIUS_OPTIONS = [1, 3, 5, 10] as const;
const DEFAULT_RADIUS_MILES = 1;
const DETAIL_ROW_RENDER_LIMIT = 100;
const MAPLIBRE_VERSION = "5.24.0";
const MAPLIBRE_SCRIPT = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.js`;
const MAPLIBRE_STYLES = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.css`;
const OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
const WALMART_SOURCE = "proximity-walmart";
const COMPETITOR_SOURCE = "proximity-competitor";
const RELATIONSHIP_SOURCE = "proximity-relationships";
const SELECTED_RADIUS_SOURCE = "proximity-selected-radius";
const MAP_CLUSTER_MAX_ZOOM = 8;
const MAP_CLUSTER_RADIUS = 38;

type RelationFilter = "all" | "within" | "outside";
type SortMode = "nearest" | "farthest" | "state" | "store";
type ThemeMode = "light" | "dark";
type ModalKind =
  | "method"
  | "shortlist"
  | "notes"
  | "metric-scope"
  | "metric-total"
  | "metric-coverage"
  | "metric-gap"
  | "metric-competitor-whitespace"
  | "metric-market"
  | "metric-pressure"
  | "metric-distance"
  | null;

interface MapMouseEvent {
  point: { x: number; y: number };
  lngLat?: { lat: number; lng: number };
}

interface RenderedMapFeature {
  geometry?: { coordinates?: unknown };
  properties?: Record<string, unknown>;
}

interface GeoJsonSource {
  getClusterExpansionZoom(clusterId: number): Promise<number>;
  setData(data: FeatureCollection): void;
}

interface InteractiveMap {
  addControl(control: unknown, position?: string): void;
  addLayer(layer: Record<string, unknown>): void;
  addSource(id: string, source: Record<string, unknown>): void;
  easeTo(options: Record<string, unknown>): void;
  fitBounds(
    bounds: [[number, number], [number, number]],
    options?: Record<string, unknown>,
  ): void;
  getCanvas(): HTMLCanvasElement;
  getSource(id: string): GeoJsonSource | undefined;
  on(event: "idle", callback: () => void): void;
  on(event: "load", callback: () => void): void;
  on(
    event: string,
    layerId: string,
    callback: (event: MapMouseEvent) => void,
  ): void;
  queryRenderedFeatures(
    point: { x: number; y: number },
    options: { layers: string[] },
  ): RenderedMapFeature[];
  remove(): void;
  resize(): void;
  setLayoutProperty(layerId: string, name: string, value: unknown): void;
}

interface MapBounds {
  max_latitude: number;
  max_longitude: number;
  min_latitude: number;
  min_longitude: number;
}

interface MapPopup {
  addTo(map: InteractiveMap): MapPopup;
  remove(): void;
  setHTML(html: string): MapPopup;
  setLngLat(lngLat: [number, number] | { lat: number; lng: number }): MapPopup;
}

interface MapLibrary {
  Map: new (options: Record<string, unknown>) => InteractiveMap;
  NavigationControl: new (options?: Record<string, unknown>) => unknown;
  Popup: new (options?: Record<string, unknown>) => MapPopup;
  ScaleControl: new (options?: Record<string, unknown>) => unknown;
}

type Feature = {
  geometry:
    | { coordinates: [number, number]; type: "Point" }
    | { coordinates: [number, number][]; type: "LineString" }
    | { coordinates: [number, number][][]; type: "Polygon" };
  properties: Record<string, string | number | boolean | null>;
  type: "Feature";
};

type FeatureCollection = {
  features: Feature[];
  type: "FeatureCollection";
};

let mapLibraryPromise: Promise<MapLibrary> | null = null;

function loadMapLibrary() {
  const browser = window as unknown as { maplibregl?: MapLibrary };
  if (browser.maplibregl) return Promise.resolve(browser.maplibregl);
  if (mapLibraryPromise) return mapLibraryPromise;
  mapLibraryPromise = new Promise<MapLibrary>((resolve, reject) => {
    if (!document.getElementById("rci-maplibre-styles")) {
      const stylesheet = document.createElement("link");
      stylesheet.crossOrigin = "anonymous";
      stylesheet.href = MAPLIBRE_STYLES;
      stylesheet.id = "rci-maplibre-styles";
      stylesheet.rel = "stylesheet";
      document.head.appendChild(stylesheet);
    }

    const existing = document.getElementById(
      "rci-maplibre-script",
    ) as HTMLScriptElement | null;
    const script = existing ?? document.createElement("script");
    const handleLoad = () => {
      const loadedBrowser = window as unknown as { maplibregl?: MapLibrary };
      if (loadedBrowser.maplibregl) resolve(loadedBrowser.maplibregl);
      else reject(new Error("The interactive map library did not initialize."));
    };
    script.addEventListener("load", handleLoad, { once: true });
    script.addEventListener(
      "error",
      () =>
        reject(new Error("The interactive map library could not be loaded.")),
      { once: true },
    );
    if (!existing) {
      script.async = true;
      script.crossOrigin = "anonymous";
      script.id = "rci-maplibre-script";
      script.src = MAPLIBRE_SCRIPT;
      document.head.appendChild(script);
    }
  });
  return mapLibraryPromise;
}

function count(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function percent(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
    style: "percent",
  }).format(value);
}

function miles(value: number | null, digits?: number) {
  if (value === null) return "—";
  const maximumFractionDigits =
    digits ?? (value >= 100 ? 0 : value >= 10 ? 1 : 2);
  return `${new Intl.NumberFormat("en-US", {
    maximumFractionDigits,
  }).format(value)} mi`;
}

function median(values: number[]) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[mid]!
    : (sorted[mid - 1]! + sorted[mid]!) / 2;
}

function percentileValue(values: number[], percentile: number) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  if (sorted.length === 1) return sorted[0]!;
  const rank = (sorted.length - 1) * percentile;
  const lower = Math.floor(rank);
  const upper = Math.ceil(rank);
  if (lower === upper) return sorted[lower]!;
  return sorted[lower]! + (sorted[upper]! - sorted[lower]!) * (rank - lower);
}

function distanceSummaryForRows(
  rows: ProximityPair[],
): ProximityDistanceSummary {
  const distances = rows.map((pair) => pair.distance_miles);
  return {
    average_miles: distances.length
      ? distances.reduce((total, value) => total + value, 0) / distances.length
      : null,
    max_miles: distances.length ? Math.max(...distances) : null,
    median_miles: median(distances),
    p75_miles: percentileValue(distances, 0.75),
    p90_miles: percentileValue(distances, 0.9),
  };
}

function haversineMiles(
  leftLatitude: number,
  leftLongitude: number,
  rightLatitude: number,
  rightLongitude: number,
) {
  const earthRadiusMiles = 3958.7613;
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const latitudeDelta = toRadians(rightLatitude - leftLatitude);
  const longitudeDelta = toRadians(rightLongitude - leftLongitude);
  const left = toRadians(leftLatitude);
  const right = toRadians(rightLatitude);
  const a =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(left) * Math.cos(right) * Math.sin(longitudeDelta / 2) ** 2;
  return 2 * earthRadiusMiles * Math.asin(Math.sqrt(a));
}

function competitorPairsForRows(
  rows: ProximityPair[],
): ProximityCompetitorPair[] {
  const walmartLocations = new Map(
    rows.map((pair) => [pair.benchmark.id, pair.benchmark]),
  );
  const competitorLocations = new Map(
    rows.map((pair) => [pair.competitor.id, pair.competitor]),
  );
  return [...competitorLocations.values()]
    .flatMap((competitor) => {
      let nearestWalmart: ProximityPair["benchmark"] | null = null;
      let nearestDistance = Number.POSITIVE_INFINITY;
      for (const walmart of walmartLocations.values()) {
        const distance = haversineMiles(
          competitor.latitude,
          competitor.longitude,
          walmart.latitude,
          walmart.longitude,
        );
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearestWalmart = walmart;
        }
      }
      if (!nearestWalmart) return [];
      return [
        {
          competitor,
          distance_miles: nearestDistance,
          nearest_walmart: nearestWalmart,
          within_1_mile: nearestDistance <= 1,
          within_3_miles: nearestDistance <= 3,
          within_5_miles: nearestDistance <= 5,
          within_10_miles: nearestDistance <= 10,
        },
      ];
    })
    .sort((left, right) => right.distance_miles - left.distance_miles);
}

function competitorStateSummaryForRows(
  rows: ProximityCompetitorPair[],
  selectedRadius: number,
): ProximityCompetitorStateSummary[] {
  const grouped = new Map<string, ProximityCompetitorPair[]>();
  for (const pair of rows) {
    const state = pair.competitor.state || "Unknown";
    grouped.set(state, [...(grouped.get(state) ?? []), pair]);
  }
  return [...grouped.entries()]
    .map(([state, statePairs]) => {
      const within = statePairs.filter(
        (pair) => pair.distance_miles <= selectedRadius,
      ).length;
      return {
        competitor_locations: statePairs.length,
        coverage_share: statePairs.length ? within / statePairs.length : null,
        gap_locations: Math.max(0, statePairs.length - within),
        median_distance_to_walmart_miles: median(
          statePairs.map((pair) => pair.distance_miles),
        ),
        state,
        within_radius_locations: within,
      };
    })
    .sort(
      (left, right) =>
        right.gap_locations - left.gap_locations ||
        right.competitor_locations - left.competitor_locations ||
        left.state.localeCompare(right.state),
    );
}

function walmartStateSummaryForRows(
  rows: ProximityPair[],
  selectedRadius: number,
): ProximityStateSummary[] {
  const grouped = new Map<string, ProximityPair[]>();
  for (const pair of rows) {
    const state = pair.benchmark.state || "Unknown";
    grouped.set(state, [...(grouped.get(state) ?? []), pair]);
  }
  return [...grouped.entries()]
    .map(([state, statePairs]) => {
      const covered = statePairs.filter(
        (pair) => pair.distance_miles <= selectedRadius,
      ).length;
      return {
        coverage_share: statePairs.length ? covered / statePairs.length : null,
        covered_locations: covered,
        gap_locations: Math.max(0, statePairs.length - covered),
        median_distance_miles: median(
          statePairs.map((pair) => pair.distance_miles),
        ),
        state,
        walmart_locations: statePairs.length,
      };
    })
    .sort(
      (left, right) =>
        right.gap_locations - left.gap_locations ||
        right.walmart_locations - left.walmart_locations ||
        left.state.localeCompare(right.state),
    );
}

function marketKey(
  location: Pick<ProximityPair["benchmark"], "city" | "state">,
) {
  return `${location.state || "Unknown"}::${location.city || "Unknown city"}`;
}

function walmartMarketSummaryForRows(
  rows: ProximityPair[],
  selectedRadius: number,
): ProximityMarketSummary[] {
  const grouped = new Map<string, ProximityPair[]>();
  for (const pair of rows) {
    const key = marketKey(pair.benchmark);
    grouped.set(key, [...(grouped.get(key) ?? []), pair]);
  }
  return [...grouped.entries()]
    .map(([key, marketPairs]) => {
      const location = marketPairs[0]!.benchmark;
      const covered = marketPairs.filter(
        (pair) => pair.distance_miles <= selectedRadius,
      ).length;
      return {
        city: location.city || "Unknown city",
        coverage_share: marketPairs.length
          ? covered / marketPairs.length
          : null,
        covered_locations: covered,
        gap_locations: Math.max(0, marketPairs.length - covered),
        market_key: key,
        median_distance_miles: median(
          marketPairs.map((pair) => pair.distance_miles),
        ),
        state: location.state || "Unknown",
        walmart_locations: marketPairs.length,
      };
    })
    .sort(
      (left, right) =>
        right.gap_locations - left.gap_locations ||
        right.walmart_locations - left.walmart_locations ||
        left.state.localeCompare(right.state) ||
        left.city.localeCompare(right.city),
    );
}

function competitorMarketSummaryForRows(
  rows: ProximityCompetitorPair[],
  selectedRadius: number,
): ProximityCompetitorMarketSummary[] {
  const grouped = new Map<string, ProximityCompetitorPair[]>();
  for (const pair of rows) {
    const key = marketKey(pair.competitor);
    grouped.set(key, [...(grouped.get(key) ?? []), pair]);
  }
  return [...grouped.entries()]
    .map(([key, marketPairs]) => {
      const location = marketPairs[0]!.competitor;
      const within = marketPairs.filter(
        (pair) => pair.distance_miles <= selectedRadius,
      ).length;
      return {
        city: location.city || "Unknown city",
        competitor_locations: marketPairs.length,
        coverage_share: marketPairs.length ? within / marketPairs.length : null,
        gap_locations: Math.max(0, marketPairs.length - within),
        market_key: key,
        median_distance_to_walmart_miles: median(
          marketPairs.map((pair) => pair.distance_miles),
        ),
        state: location.state || "Unknown",
        within_radius_locations: within,
      };
    })
    .sort(
      (left, right) =>
        right.gap_locations - left.gap_locations ||
        right.competitor_locations - left.competitor_locations ||
        left.state.localeCompare(right.state) ||
        left.city.localeCompare(right.city),
    );
}

function competitorNetworkSummaryForRows(
  rows: ProximityPair[],
  selectedRadius: number,
): ProximityCompetitorNetworkSummary[] {
  const grouped = new Map<string, ProximityPair[]>();
  for (const pair of rows) {
    grouped.set(pair.competitor.id, [
      ...(grouped.get(pair.competitor.id) ?? []),
      pair,
    ]);
  }
  return [...grouped.entries()]
    .map(([competitorLocationId, networkPairs]) => {
      const sortedPairs = [...networkPairs].sort(
        (left, right) => left.distance_miles - right.distance_miles,
      );
      const competitor = sortedPairs[0]!.competitor;
      const covered = sortedPairs.filter(
        (pair) => pair.distance_miles <= selectedRadius,
      ).length;
      const distances = sortedPairs.map((pair) => pair.distance_miles);
      return {
        assigned_walmart_locations: sortedPairs.length,
        city: competitor.city,
        competitor_location_id: competitorLocationId,
        competitor_store_name: competitor.store_name,
        competitor_store_number: competitor.store_number,
        coverage_share: sortedPairs.length
          ? covered / sortedPairs.length
          : null,
        covered_walmart_locations: covered,
        farthest_distance_miles: distances.at(-1) ?? null,
        gap_walmart_locations: Math.max(0, sortedPairs.length - covered),
        latitude: competitor.latitude,
        longitude: competitor.longitude,
        median_distance_miles: median(distances),
        nearest_distance_miles: distances[0] ?? null,
        representative_pair_key: pairKey(sortedPairs[0]!),
        state: competitor.state,
      };
    })
    .sort(
      (left, right) =>
        right.covered_walmart_locations - left.covered_walmart_locations ||
        right.assigned_walmart_locations - left.assigned_walmart_locations ||
        (left.median_distance_miles ?? Number.POSITIVE_INFINITY) -
          (right.median_distance_miles ?? Number.POSITIVE_INFINITY) ||
        left.competitor_store_number.localeCompare(
          right.competitor_store_number,
        ),
    );
}

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function locationLabel(location: ProximityPair["benchmark"]) {
  return [location.store_name, location.city, location.state, location.zipcode]
    .filter(Boolean)
    .join(" · ");
}

function pairKey(pair: ProximityPair) {
  return `${pair.benchmark.id}::${pair.competitor.id}`;
}

function competitorPairKey(pair: ProximityCompetitorPair) {
  return `${pair.nearest_walmart.id}::${pair.competitor.id}`;
}

function googleMapsUrl(latitude: number, longitude: number) {
  return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
}

function initialTheme(): ThemeMode {
  if (typeof window === "undefined") return "light";
  if (document.documentElement.dataset.theme === "dark") return "dark";
  const appTheme = window.localStorage.getItem("rci-theme");
  if (appTheme === "dark" || appTheme === "light") return appTheme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function walmartRetailerId(country: string) {
  return country === "CANADA" ? "walmart_ca" : "walmart_us";
}

function availableCompetitors(retailers: LocationRetailer[], country: string) {
  const benchmark = walmartRetailerId(country);
  return retailers
    .filter(
      (retailer) =>
        retailer.country === country &&
        retailer.id !== benchmark &&
        !retailer.id.startsWith("walmart_") &&
        retailer.location_count > 0,
    )
    .sort(
      (left, right) =>
        Number(right.active) - Number(left.active) ||
        Number(right.catalogued) - Number(left.catalogued) ||
        right.location_count - left.location_count ||
        left.display_name.localeCompare(right.display_name),
    );
}

function filteredRowsToRecords(rows: ProximityPair[], selectedRadius: number) {
  return rows.map((pair) => ({
    walmart_retailer_id: pair.benchmark.retailer_id,
    walmart_location_id: pair.benchmark.id,
    walmart_store_number: pair.benchmark.store_number,
    walmart_store_name: pair.benchmark.store_name,
    walmart_city: pair.benchmark.city,
    walmart_state: pair.benchmark.state,
    walmart_zipcode: pair.benchmark.zipcode,
    walmart_country: pair.benchmark.country,
    walmart_latitude: pair.benchmark.latitude,
    walmart_longitude: pair.benchmark.longitude,
    competitor_retailer_id: pair.competitor.retailer_id,
    competitor_location_id: pair.competitor.id,
    competitor_store_number: pair.competitor.store_number,
    competitor_store_name: pair.competitor.store_name,
    competitor_city: pair.competitor.city,
    competitor_state: pair.competitor.state,
    competitor_zipcode: pair.competitor.zipcode,
    competitor_country: pair.competitor.country,
    competitor_latitude: pair.competitor.latitude,
    competitor_longitude: pair.competitor.longitude,
    nearest_distance_miles: pair.distance_miles,
    within_1_mile: pair.within_1_mile,
    within_3_miles: pair.within_3_miles,
    within_5_miles: pair.within_5_miles,
    within_10_miles: pair.within_10_miles,
    selected_radius_miles: selectedRadius,
    within_selected_radius: pair.distance_miles <= selectedRadius,
  }));
}

function competitorRowsToRecords(
  rows: ProximityCompetitorPair[],
  selectedRadius: number,
) {
  return rows.map((pair) => ({
    competitor_retailer_id: pair.competitor.retailer_id,
    competitor_location_id: pair.competitor.id,
    competitor_store_number: pair.competitor.store_number,
    competitor_store_name: pair.competitor.store_name,
    competitor_city: pair.competitor.city,
    competitor_state: pair.competitor.state,
    competitor_zipcode: pair.competitor.zipcode,
    competitor_country: pair.competitor.country,
    competitor_latitude: pair.competitor.latitude,
    competitor_longitude: pair.competitor.longitude,
    nearest_walmart_retailer_id: pair.nearest_walmart.retailer_id,
    nearest_walmart_location_id: pair.nearest_walmart.id,
    nearest_walmart_store_number: pair.nearest_walmart.store_number,
    nearest_walmart_store_name: pair.nearest_walmart.store_name,
    nearest_walmart_city: pair.nearest_walmart.city,
    nearest_walmart_state: pair.nearest_walmart.state,
    nearest_walmart_zipcode: pair.nearest_walmart.zipcode,
    nearest_walmart_country: pair.nearest_walmart.country,
    nearest_walmart_latitude: pair.nearest_walmart.latitude,
    nearest_walmart_longitude: pair.nearest_walmart.longitude,
    nearest_walmart_distance_miles: pair.distance_miles,
    within_1_mile: pair.within_1_mile,
    within_3_miles: pair.within_3_miles,
    within_5_miles: pair.within_5_miles,
    within_10_miles: pair.within_10_miles,
    selected_radius_miles: selectedRadius,
    walmart_within_selected_radius: pair.distance_miles <= selectedRadius,
  }));
}

function csvCell(value: unknown) {
  const text =
    typeof value === "boolean"
      ? value
        ? "True"
        : "False"
      : String(value ?? "");
  const safe = /^[=+@-]/.test(text) ? `'${text}` : text;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

function download(filename: string, type: string, body: string) {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function downloadRecordsCsv(
  records: Array<Record<string, unknown>>,
  filename: string,
) {
  const columns = records.length ? Object.keys(records[0]!) : [];
  const body = [
    columns.map(csvCell).join(","),
    ...records.map((record) =>
      columns.map((column) => csvCell(record[column])).join(","),
    ),
  ].join("\r\n");
  download(filename, "text/csv;charset=utf-8", `\uFEFF${body}`);
}

function downloadCsv(
  rows: ProximityPair[],
  selectedRadius: number,
  filename: string,
) {
  downloadRecordsCsv(filteredRowsToRecords(rows, selectedRadius), filename);
}

function downloadJson(
  rows: ProximityPair[],
  selectedRadius: number,
  filename: string,
) {
  download(
    filename,
    "application/json;charset=utf-8",
    JSON.stringify(filteredRowsToRecords(rows, selectedRadius), null, 2),
  );
}

function downloadCompetitorCsv(
  rows: ProximityCompetitorPair[],
  selectedRadius: number,
  filename: string,
) {
  downloadRecordsCsv(competitorRowsToRecords(rows, selectedRadius), filename);
}

function downloadCompetitorJson(
  rows: ProximityCompetitorPair[],
  selectedRadius: number,
  filename: string,
) {
  download(
    filename,
    "application/json;charset=utf-8",
    JSON.stringify(competitorRowsToRecords(rows, selectedRadius), null, 2),
  );
}

function downloadGeoJson(
  rows: ProximityPair[],
  selectedRadius: number,
  filename: string,
) {
  const features = rows.flatMap((pair) => [
    walmartFeature(pair, selectedRadius),
    competitorFeature(pair, selectedRadius),
    relationshipFeature(pair, selectedRadius),
  ]);
  download(
    filename,
    "application/geo+json;charset=utf-8",
    JSON.stringify({ features, type: "FeatureCollection" }, null, 2),
  );
}

function walmartFeature(pair: ProximityPair, selectedRadius: number): Feature {
  return {
    geometry: {
      coordinates: [pair.benchmark.longitude, pair.benchmark.latitude],
      type: "Point",
    },
    properties: {
      city: pair.benchmark.city,
      distance_miles: pair.distance_miles,
      key: pairKey(pair),
      location_id: pair.benchmark.id,
      role: "walmart",
      selected_radius_miles: selectedRadius,
      state: pair.benchmark.state,
      store_name: pair.benchmark.store_name,
      store_number: pair.benchmark.store_number,
      within_selected_radius: pair.distance_miles <= selectedRadius,
    },
    type: "Feature",
  };
}

function competitorFeature(
  pair: ProximityPair,
  selectedRadius: number,
): Feature {
  return {
    geometry: {
      coordinates: [pair.competitor.longitude, pair.competitor.latitude],
      type: "Point",
    },
    properties: {
      city: pair.competitor.city,
      distance_miles: pair.distance_miles,
      key: pairKey(pair),
      location_id: pair.competitor.id,
      retailer: pair.competitor.retailer_display_name,
      role: "competitor",
      selected_radius_miles: selectedRadius,
      state: pair.competitor.state,
      store_name: pair.competitor.store_name,
      store_number: pair.competitor.store_number,
      within_selected_radius: pair.distance_miles <= selectedRadius,
    },
    type: "Feature",
  };
}

function relationshipFeature(
  pair: ProximityPair,
  selectedRadius: number,
): Feature {
  return {
    geometry: {
      coordinates: [
        [pair.benchmark.longitude, pair.benchmark.latitude],
        [pair.competitor.longitude, pair.competitor.latitude],
      ],
      type: "LineString",
    },
    properties: {
      distance_miles: pair.distance_miles,
      key: pairKey(pair),
      role: "relationship",
      selected_radius_miles: selectedRadius,
      within_selected_radius: pair.distance_miles <= selectedRadius,
    },
    type: "Feature",
  };
}

function featureCollection(features: Feature[]): FeatureCollection {
  return { features, type: "FeatureCollection" };
}

function uniqueByLocation(
  rows: ProximityPair[],
  select: (pair: ProximityPair) => ProximityPair["benchmark"],
) {
  const seen = new Set<string>();
  const unique: ProximityPair[] = [];
  for (const pair of rows) {
    const location = select(pair);
    if (seen.has(location.id)) continue;
    seen.add(location.id);
    unique.push(pair);
  }
  return unique;
}

function selectedRadiusFeature(
  pair: ProximityPair | null,
  radiusMiles: number,
): FeatureCollection {
  if (!pair) return featureCollection([]);
  const earthRadiusMiles = 3958.8;
  const latitude = (pair.competitor.latitude * Math.PI) / 180;
  const longitude = (pair.competitor.longitude * Math.PI) / 180;
  const angular = radiusMiles / earthRadiusMiles;
  const coordinates: [number, number][] = [];
  for (let step = 0; step <= 96; step += 1) {
    const bearing = (step / 96) * Math.PI * 2;
    const latitude2 = Math.asin(
      Math.sin(latitude) * Math.cos(angular) +
        Math.cos(latitude) * Math.sin(angular) * Math.cos(bearing),
    );
    const longitude2 =
      longitude +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angular) * Math.cos(latitude),
        Math.cos(angular) - Math.sin(latitude) * Math.sin(latitude2),
      );
    coordinates.push([
      (longitude2 * 180) / Math.PI,
      (latitude2 * 180) / Math.PI,
    ]);
  }
  return featureCollection([
    {
      geometry: { coordinates: [coordinates], type: "Polygon" },
      properties: {
        key: pairKey(pair),
        radius_miles: radiusMiles,
        role: "selected_competitor_radius",
      },
      type: "Feature",
    },
  ]);
}

function radiusEllipse(
  pair: ProximityPair | null,
  radiusMiles: number,
  bounds: MapBounds,
) {
  if (!pair) return null;
  const center = projectToMap(
    pair.competitor.latitude,
    pair.competitor.longitude,
    bounds,
  );
  const latitudeMiles = 69.172;
  const longitudeMiles =
    latitudeMiles *
    Math.max(0.14, Math.cos((pair.competitor.latitude * Math.PI) / 180));
  const north = projectToMap(
    pair.competitor.latitude + radiusMiles / latitudeMiles,
    pair.competitor.longitude,
    bounds,
  );
  const east = projectToMap(
    pair.competitor.latitude,
    pair.competitor.longitude + radiusMiles / longitudeMiles,
    bounds,
  );
  return {
    cx: center.x,
    cy: center.y,
    rx: Math.max(9, Math.abs(east.x - center.x)),
    ry: Math.max(9, Math.abs(north.y - center.y)),
  };
}

function fitToPairs(
  map: InteractiveMap,
  rows: ProximityPair[],
  country: string,
) {
  if (!rows.length) {
    map.easeTo({
      center: country === "CANADA" ? [-96, 56] : [-97, 38.5],
      duration: 0,
      zoom: country === "CANADA" ? 2.8 : 3.1,
    });
    return;
  }
  const points = rows.flatMap((pair) => [pair.benchmark, pair.competitor]);
  const longitudes = points.map((point) => point.longitude);
  const latitudes = points.map((point) => point.latitude);
  const bounds: [[number, number], [number, number]] = [
    [Math.min(...longitudes), Math.min(...latitudes)],
    [Math.max(...longitudes), Math.max(...latitudes)],
  ];
  map.fitBounds(bounds, { duration: 0, maxZoom: 12, padding: 72 });
}

function popupHtml(feature: RenderedMapFeature | undefined) {
  const properties = feature?.properties ?? {};
  if (properties.point_count) {
    return `<strong>${escapeHtml(properties.point_count)} locations</strong><span>Click to zoom into this cluster.</span>`;
  }
  const role = String(properties.role ?? "");
  const label =
    role === "competitor"
      ? String(properties.retailer ?? "Competitor")
      : role === "walmart"
        ? "Walmart"
        : "Relationship";
  return `<strong>${escapeHtml(label)} ${escapeHtml(properties.store_number ?? "")}</strong><span>${escapeHtml(properties.store_name ?? "")}</span><span>${escapeHtml(properties.city ?? "")}${properties.state ? `, ${escapeHtml(properties.state)}` : ""}</span><span>${escapeHtml(miles(Number(properties.distance_miles ?? 0)))} to nearest paired location</span>`;
}

function setLayerVisibility(
  map: InteractiveMap,
  layerIds: string[],
  visible: boolean,
) {
  for (const layerId of layerIds) {
    map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
  }
}

function mapBoundsForPairs(rows: ProximityPair[], country: string): MapBounds {
  if (!rows.length) {
    return country === "CANADA"
      ? {
          max_latitude: 72,
          max_longitude: -52,
          min_latitude: 41,
          min_longitude: -142,
        }
      : {
          max_latitude: 50,
          max_longitude: -66,
          min_latitude: 24,
          min_longitude: -125,
        };
  }
  const points = rows.flatMap((pair) => [pair.benchmark, pair.competitor]);
  const latitudes = points.map((point) => point.latitude);
  const longitudes = points.map((point) => point.longitude);
  const minLatitude = Math.min(...latitudes);
  const maxLatitude = Math.max(...latitudes);
  const minLongitude = Math.min(...longitudes);
  const maxLongitude = Math.max(...longitudes);
  const latitudePadding = Math.max(1.5, (maxLatitude - minLatitude) * 0.08);
  const longitudePadding = Math.max(2.5, (maxLongitude - minLongitude) * 0.08);
  return {
    max_latitude: maxLatitude + latitudePadding,
    max_longitude: maxLongitude + longitudePadding,
    min_latitude: minLatitude - latitudePadding,
    min_longitude: minLongitude - longitudePadding,
  };
}

function projectToMap(latitude: number, longitude: number, bounds: MapBounds) {
  const longitudeRange = Math.max(
    0.0001,
    bounds.max_longitude - bounds.min_longitude,
  );
  const latitudeRange = Math.max(
    0.0001,
    bounds.max_latitude - bounds.min_latitude,
  );
  const x = ((longitude - bounds.min_longitude) / longitudeRange) * 1000;
  const y = ((bounds.max_latitude - latitude) / latitudeRange) * 610;
  return {
    x: Math.min(982, Math.max(18, x)),
    y: Math.min(592, Math.max(18, y)),
  };
}

function clientClusterRows(
  rows: ProximityPair[],
  role: "competitor" | "walmart",
  selectedRadius: number,
) {
  const cellSize = 2;
  const representedCompetitors = new Set<string>();
  const buckets = new Map<
    string,
    {
      covered_locations: number;
      gap_locations: number;
      latitude_total: number;
      location_count: number;
      longitude_total: number;
      representative_label: string;
      representative_pair_key: string;
      role: string;
    }
  >();
  for (const pair of rows) {
    const location = role === "walmart" ? pair.benchmark : pair.competitor;
    if (role === "competitor") {
      if (representedCompetitors.has(location.id)) continue;
      representedCompetitors.add(location.id);
    }
    const key = `${Math.floor(location.latitude / cellSize)}:${Math.floor(
      location.longitude / cellSize,
    )}`;
    const bucket = buckets.get(key) ?? {
      covered_locations: 0,
      gap_locations: 0,
      latitude_total: 0,
      location_count: 0,
      longitude_total: 0,
      representative_label:
        [location.city, location.state].filter(Boolean).join(", ") ||
        location.store_name ||
        location.store_number,
      representative_pair_key: pairKey(pair),
      role,
    };
    bucket.latitude_total += location.latitude;
    bucket.longitude_total += location.longitude;
    bucket.location_count += 1;
    if (pair.distance_miles <= selectedRadius) bucket.covered_locations += 1;
    else bucket.gap_locations += 1;
    buckets.set(key, bucket);
  }
  return [...buckets.values()]
    .map((bucket) => ({
      covered_locations: bucket.covered_locations,
      gap_locations: bucket.gap_locations,
      label:
        bucket.location_count === 1
          ? bucket.representative_label
          : `${bucket.representative_label} · ${bucket.location_count} locations`,
      latitude: bucket.latitude_total / bucket.location_count,
      location_count: bucket.location_count,
      longitude: bucket.longitude_total / bucket.location_count,
      representative_pair_key: bucket.representative_pair_key,
      role: bucket.role,
    }))
    .sort((left, right) => right.location_count - left.location_count);
}

function mapSummaryForRows(
  rows: ProximityPair[],
  view: ProximityView | null,
  radius: number,
  country: string,
): ProximityMapSummary {
  if (view?.map_summary && rows.length === view.pairs.length) {
    return view.map_summary;
  }
  return {
    bounds: mapBoundsForPairs(rows, country),
    cluster_cell_degrees: 2,
    competitor_clusters: clientClusterRows(rows, "competitor", radius),
    schema_version: "1.0.0-proximity-map-summary-client-filtered",
    walmart_clusters: clientClusterRows(rows, "walmart", radius),
  };
}

export function ProximityWorkspace({
  initialView,
  initialRetailers,
  initialCountry,
  initialCompetitorRetailerId,
}: Readonly<{
  initialView: ProximityView | null;
  initialRetailers: LocationRetailer[];
  initialCountry: string;
  initialCompetitorRetailerId: string | null;
}>) {
  const [country, setCountry] = useState(initialCountry);
  const [retailers, setRetailers] = useState(initialRetailers);
  const [competitorRetailerId, setCompetitorRetailerId] = useState(
    initialCompetitorRetailerId ?? "",
  );
  const [view, setView] = useState(initialView);
  const [radius, setRadius] = useState(
    initialView?.selected_radius_miles ?? DEFAULT_RADIUS_MILES,
  );
  const [comparisonScope, setComparisonScope] = useState<ComparisonScope>(() =>
    recommendedScopeForView(initialView),
  );
  const [query, setQuery] = useState("");
  const [stateFilter, setStateFilter] = useState("all");
  const [relation, setRelation] = useState<RelationFilter>("all");
  const [sort, setSort] = useState<SortMode>("nearest");
  const [showFilters, setShowFilters] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [showLinks, setShowLinks] = useState(true);
  const [showRings, setShowRings] = useState(true);
  const [showWalmart, setShowWalmart] = useState(true);
  const [showCompetitors, setShowCompetitors] = useState(true);
  const [showSelectedDetail, setShowSelectedDetail] = useState(false);
  const [competitorStateDetail, setCompetitorStateDetail] = useState<
    string | null
  >(null);
  const [competitorMarketDetail, setCompetitorMarketDetail] = useState<
    string | null
  >(null);
  const [onlySaved, setOnlySaved] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => initialTheme());
  const [modal, setModal] = useState<ModalKind>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapEnhanced, setMapEnhanced] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [savedByComparison, setSavedByComparison] = useState<
    Record<string, string[]>
  >(() => {
    if (typeof window === "undefined") return {};
    try {
      const stored = window.localStorage.getItem("proximity-shortlists");
      return stored ? (JSON.parse(stored) as Record<string, string[]>) : {};
    } catch {
      return {};
    }
  });
  const [selectedKey, setSelectedKey] = useState<string | null>(
    initialView?.pairs[0] ? pairKey(initialView.pairs[0]) : null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<InteractiveMap | null>(null);
  const popupRef = useRef<MapPopup | null>(null);
  const pairByKeyRef = useRef<Map<string, ProximityPair>>(new Map());
  const shortlistStorageKey = `proximity-shortlist:${country}:${competitorRetailerId}`;
  const savedKeys = useMemo(
    () => new Set(savedByComparison[shortlistStorageKey] ?? []),
    [savedByComparison, shortlistStorageKey],
  );

  const competitorOptions = useMemo(
    () => availableCompetitors(retailers, country),
    [country, retailers],
  );

  useEffect(() => {
    const syncFromDocument = () =>
      setTheme(
        document.documentElement.dataset.theme === "dark" ? "dark" : "light",
      );
    syncFromDocument();
    const observer = new MutationObserver(syncFromDocument);
    observer.observe(document.documentElement, {
      attributeFilter: ["data-theme"],
      attributes: true,
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    window.localStorage.setItem(
      "proximity-shortlists",
      JSON.stringify(savedByComparison),
    );
  }, [savedByComparison]);

  async function load(next: {
    country?: string;
    competitorRetailerId?: string;
    radius?: number;
  }) {
    const nextCountry = next.country ?? country;
    setLoading(true);
    setError(null);
    try {
      let nextRetailers = retailers;
      if (next.country && next.country !== country) {
        const retailerResponse = await fetch(
          `/api/proximity/retailers?country=${encodeURIComponent(nextCountry)}`,
          { cache: "no-store" },
        );
        const retailerBody: unknown = await retailerResponse.json();
        if (!retailerResponse.ok || !Array.isArray(retailerBody)) {
          throw new Error("Retailer locations could not be loaded.");
        }
        nextRetailers = retailerBody as LocationRetailer[];
        setRetailers(nextRetailers);
      }
      const competitorOptionsForCountry = availableCompetitors(
        nextRetailers,
        nextCountry,
      );
      const selectedCompetitor = selectCompetitorForProximityLoad({
        competitorOptions: competitorOptionsForCountry,
        countryChanged: Boolean(next.country && next.country !== country),
        currentCompetitorRetailerId: competitorRetailerId,
        requestedCompetitorRetailerId: next.competitorRetailerId,
      });
      const selectedRadius = next.radius ?? radius;
      const comparisonChanged =
        Boolean(next.competitorRetailerId) ||
        Boolean(next.country && next.country !== country);
      setCountry(nextCountry);
      setCompetitorRetailerId(selectedCompetitor);
      setRadius(selectedRadius);
      if (!selectedCompetitor) {
        setView(null);
        setError(
          "No competitor retailer with location-master rows is available for this country.",
        );
        return;
      }
      const parameters = new URLSearchParams({
        country: nextCountry,
        competitor_retailer_id: selectedCompetitor,
        selected_radius_miles: String(selectedRadius),
      });
      const response = await fetch(`/api/proximity?${parameters.toString()}`, {
        cache: "no-store",
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.error || "Proximity data could not be loaded.");
      }
      const nextView = body as ProximityView;
      setView(nextView);
      if (comparisonChanged) {
        setComparisonScope(recommendedScopeForView(nextView));
      }
      setSelectedKey(body.pairs?.[0] ? pairKey(body.pairs[0]) : null);
      setStateFilter("all");
      setRelation("all");
      setSort("nearest");
      setOnlySaved(false);
      setCompetitorStateDetail(null);
      setCompetitorMarketDetail(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Proximity data could not be loaded.",
      );
      setView(null);
    } finally {
      setLoading(false);
    }
  }

  const competitorFootprintStates = useMemo(
    () => competitorFootprintStatesForView(view),
    [view],
  );
  const competitorFootprintStateSet = useMemo(
    () => new Set(competitorFootprintStates),
    [competitorFootprintStates],
  );
  const isCompetitorFootprintScope =
    comparisonScope === "competitor-footprint" &&
    competitorFootprintStates.length > 0;
  const competitorFootprintLabel =
    competitorFootprintStates.length === 0
      ? "no competitor states"
      : competitorFootprintStates.length <= 6
        ? competitorFootprintStates.join(", ")
        : `${competitorFootprintStates.length} states/provinces`;
  const effectiveStateFilter =
    stateFilter !== "all" &&
    (!isCompetitorFootprintScope ||
      competitorFootprintStateSet.has(stateFilter))
      ? stateFilter
      : "all";

  const scopedPairs = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return (view?.pairs ?? [])
      .filter((pair) => {
        if (
          isCompetitorFootprintScope &&
          !competitorFootprintStateSet.has(pair.benchmark.state || "")
        ) {
          return false;
        }
        if (onlySaved && !savedKeys.has(pairKey(pair))) return false;
        if (
          effectiveStateFilter !== "all" &&
          pair.benchmark.state !== effectiveStateFilter
        ) {
          return false;
        }
        if (!normalizedQuery) return true;
        return [
          pair.benchmark.store_number,
          pair.benchmark.store_name,
          pair.benchmark.city,
          pair.benchmark.state,
          pair.benchmark.zipcode,
          pair.competitor.store_number,
          pair.competitor.store_name,
          pair.competitor.city,
          pair.competitor.state,
          pair.competitor.zipcode,
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      })
      .sort((left, right) => {
        if (sort === "farthest")
          return right.distance_miles - left.distance_miles;
        if (sort === "state") {
          return (
            (left.benchmark.state || "").localeCompare(
              right.benchmark.state || "",
            ) ||
            left.benchmark.store_number.localeCompare(
              right.benchmark.store_number,
            )
          );
        }
        if (sort === "store") {
          return left.benchmark.store_number.localeCompare(
            right.benchmark.store_number,
          );
        }
        return left.distance_miles - right.distance_miles;
      });
  }, [
    competitorFootprintStateSet,
    isCompetitorFootprintScope,
    effectiveStateFilter,
    onlySaved,
    query,
    savedKeys,
    sort,
    view?.pairs,
  ]);

  const filteredPairs = useMemo(
    () =>
      scopedPairs.filter((pair) => {
        if (relation === "within" && pair.distance_miles > radius) return false;
        if (relation === "outside" && pair.distance_miles <= radius) {
          return false;
        }
        return true;
      }),
    [radius, relation, scopedPairs],
  );

  const selectedPair =
    filteredPairs.find((pair) => pairKey(pair) === selectedKey) ??
    filteredPairs[0] ??
    null;
  const scopedPairByKey = useMemo(
    () => new Map(scopedPairs.map((pair) => [pairKey(pair), pair])),
    [scopedPairs],
  );
  const selectedCoveragePair =
    selectedPair ??
    (selectedKey ? scopedPairByKey.get(selectedKey) : null) ??
    null;
  const selectedCompetitorLocationId =
    selectedCoveragePair?.competitor.id ?? null;
  const selectedNetworkPairs = useMemo(
    () =>
      selectedCompetitorLocationId
        ? scopedPairs
            .filter(
              (pair) => pair.competitor.id === selectedCompetitorLocationId,
            )
            .sort((left, right) => left.distance_miles - right.distance_miles)
        : [],
    [scopedPairs, selectedCompetitorLocationId],
  );
  const selectedNetworkWithin = selectedNetworkPairs.filter(
    (pair) => pair.distance_miles <= radius,
  ).length;
  const selectedNetworkDistances = selectedNetworkPairs.map(
    (pair) => pair.distance_miles,
  );
  const selectedNetworkMedian = median(selectedNetworkDistances);
  const selectedNetworkFarthest = selectedNetworkDistances.length
    ? Math.max(...selectedNetworkDistances)
    : null;
  const selectedNetworkCoverageShare = selectedNetworkPairs.length
    ? selectedNetworkWithin / selectedNetworkPairs.length
    : null;
  const filteredWithin = filteredPairs.filter(
    (pair) => pair.distance_miles <= radius,
  ).length;
  const filteredOutside = Math.max(0, filteredPairs.length - filteredWithin);
  const scopeMedian = median(scopedPairs.map((pair) => pair.distance_miles));
  const coverageBands = RADIUS_OPTIONS.map((option) => {
    const within = scopedPairs.filter(
      (pair) => pair.distance_miles <= option,
    ).length;
    const outside = Math.max(0, scopedPairs.length - within);
    return {
      label: `≤${option} mi`,
      miles: option,
      outside,
      share: scopedPairs.length ? within / scopedPairs.length : null,
      within,
    };
  });
  const selectedCoverage =
    coverageBands.find((band) => band.miles === radius) ?? coverageBands[0];
  const totalWalmartLocations =
    view?.benchmark.location_count ?? scopedPairs.length;
  const walmartScopeLabel = isCompetitorFootprintScope
    ? "Walmart stores in competitor footprint"
    : "Total Walmart stores";
  const walmartScopeDescription =
    view && isCompetitorFootprintScope
      ? `${count(scopedPairs.length)} Walmart locations in ${competitorFootprintLabel}; ${count(totalWalmartLocations)} total ${view.benchmark.display_name} locations`
      : view
        ? `${count(view.benchmark.mappable_location_count)} mappable; ${count(view.summary.paired_locations)} paired to a nearest ${view.competitor.display_name} site`
        : "No comparison loaded";
  const comparisonScopeLabel = isCompetitorFootprintScope
    ? `Competitor footprint (${competitorFootprintLabel})`
    : `All ${view?.benchmark.display_name ?? "Walmart"} locations`;
  const distanceSummary = useMemo(() => {
    if (
      view?.distance_summary &&
      scopedPairs.length === view.pairs.length &&
      effectiveStateFilter === "all" &&
      !query.trim() &&
      !onlySaved
    ) {
      return view.distance_summary;
    }
    return distanceSummaryForRows(scopedPairs);
  }, [effectiveStateFilter, onlySaved, query, scopedPairs, view]);
  const competitorNetworkSummaries = useMemo(() => {
    if (
      view?.competitor_network_summary &&
      scopedPairs.length === view.pairs.length &&
      effectiveStateFilter === "all" &&
      !query.trim() &&
      !onlySaved
    ) {
      return view.competitor_network_summary;
    }
    return competitorNetworkSummaryForRows(scopedPairs, radius);
  }, [effectiveStateFilter, onlySaved, query, radius, scopedPairs, view]);
  const hasScopedDimensionFilters =
    isCompetitorFootprintScope ||
    effectiveStateFilter !== "all" ||
    Boolean(query.trim()) ||
    onlySaved;
  const competitorPerspectivePairs = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const sourceRows =
      view?.competitor_pairs ?? competitorPairsForRows(scopedPairs);
    return sourceRows
      .filter((pair) => {
        if (onlySaved && !savedKeys.has(competitorPairKey(pair))) return false;
        if (
          effectiveStateFilter !== "all" &&
          pair.competitor.state !== effectiveStateFilter
        ) {
          return false;
        }
        if (!normalizedQuery) return true;
        return [
          pair.competitor.store_number,
          pair.competitor.store_name,
          pair.competitor.city,
          pair.competitor.state,
          pair.competitor.zipcode,
          pair.nearest_walmart.store_number,
          pair.nearest_walmart.store_name,
          pair.nearest_walmart.city,
          pair.nearest_walmart.state,
          pair.nearest_walmart.zipcode,
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      })
      .sort(
        (left, right) =>
          right.distance_miles - left.distance_miles ||
          (left.competitor.state || "").localeCompare(
            right.competitor.state || "",
          ) ||
          left.competitor.store_number.localeCompare(
            right.competitor.store_number,
          ),
      );
  }, [effectiveStateFilter, onlySaved, query, savedKeys, scopedPairs, view]);
  const competitorStateSummaries = useMemo(() => {
    if (!hasScopedDimensionFilters && view?.competitor_state_summary) {
      return view.competitor_state_summary;
    }
    return competitorStateSummaryForRows(competitorPerspectivePairs, radius);
  }, [competitorPerspectivePairs, hasScopedDimensionFilters, radius, view]);
  const walmartMarketSummaries = useMemo(() => {
    if (!hasScopedDimensionFilters && view?.market_summary) {
      return view.market_summary;
    }
    return walmartMarketSummaryForRows(scopedPairs, radius);
  }, [hasScopedDimensionFilters, radius, scopedPairs, view]);
  const walmartStateSummaries = useMemo(() => {
    if (!hasScopedDimensionFilters && view?.state_summary) {
      return view.state_summary;
    }
    return walmartStateSummaryForRows(scopedPairs, radius);
  }, [hasScopedDimensionFilters, radius, scopedPairs, view]);
  const competitorMarketSummaries = useMemo(() => {
    if (!hasScopedDimensionFilters && view?.competitor_market_summary) {
      return view.competitor_market_summary;
    }
    return competitorMarketSummaryForRows(competitorPerspectivePairs, radius);
  }, [competitorPerspectivePairs, hasScopedDimensionFilters, radius, view]);
  const competitorGapLocations = competitorPerspectivePairs.filter(
    (pair) => pair.distance_miles > radius,
  ).length;
  const competitorWithinLocations = Math.max(
    0,
    competitorPerspectivePairs.length - competitorGapLocations,
  );
  const competitorGapShare = competitorPerspectivePairs.length
    ? competitorGapLocations / competitorPerspectivePairs.length
    : null;
  const competitorWhiteSpaceStates = competitorStateSummaries.slice(0, 5);
  const competitorWhiteSpaceMarkets = competitorMarketSummaries
    .filter((market) => market.gap_locations > 0)
    .slice(0, 5);
  const walmartPressureStates = walmartStateSummaries
    .filter((state) => state.covered_locations > 0)
    .sort(
      (left, right) =>
        (right.coverage_share ?? -1) - (left.coverage_share ?? -1) ||
        right.covered_locations - left.covered_locations ||
        right.walmart_locations - left.walmart_locations ||
        left.state.localeCompare(right.state),
    )
    .slice(0, 5);
  const walmartWhiteSpaceMarkets = walmartMarketSummaries
    .filter((market) => market.gap_locations > 0)
    .slice(0, 5);
  const competitorStateDetailRows = competitorPerspectivePairs
    .filter(
      (pair) =>
        competitorStateDetail === "all" ||
        (pair.competitor.state || "Unknown") === competitorStateDetail,
    )
    .sort(
      (left, right) =>
        Number(right.distance_miles > radius) -
          Number(left.distance_miles > radius) ||
        right.distance_miles - left.distance_miles ||
        (left.competitor.state || "").localeCompare(
          right.competitor.state || "",
        ) ||
        left.competitor.store_number.localeCompare(
          right.competitor.store_number,
        ),
    );
  const competitorStateDetailSummary =
    competitorStateDetail === "all"
      ? null
      : competitorStateSummaries.find(
          (state) => state.state === competitorStateDetail,
        );
  const competitorMarketDetailRows = competitorMarketSummaries.filter(
    (market) =>
      competitorMarketDetail === "all" ||
      market.market_key === competitorMarketDetail,
  );
  const competitorMarketDetailPairRows = competitorPerspectivePairs
    .filter(
      (pair) =>
        competitorMarketDetail === "all" ||
        marketKey(pair.competitor) === competitorMarketDetail,
    )
    .sort(
      (left, right) =>
        Number(right.distance_miles > radius) -
          Number(left.distance_miles > radius) ||
        right.distance_miles - left.distance_miles ||
        (left.competitor.state || "").localeCompare(
          right.competitor.state || "",
        ) ||
        (left.competitor.city || "").localeCompare(
          right.competitor.city || "",
        ) ||
        left.competitor.store_number.localeCompare(
          right.competitor.store_number,
        ),
    );
  const competitorMarketDetailSummary =
    competitorMarketDetail === "all" || !competitorMarketDetail
      ? null
      : competitorMarketSummaries.find(
          (market) => market.market_key === competitorMarketDetail,
        );
  const competitorMarketDetailGapLocations =
    competitorMarketDetailPairRows.filter(
      (pair) => pair.distance_miles > radius,
    ).length;
  const competitorMarketDetailWithinLocations = Math.max(
    0,
    competitorMarketDetailPairRows.length - competitorMarketDetailGapLocations,
  );
  const visibleCompetitorMarketDetailPairRows =
    competitorMarketDetailPairRows.slice(0, DETAIL_ROW_RENDER_LIMIT);
  const visibleCompetitorStateDetailRows = competitorStateDetailRows.slice(
    0,
    DETAIL_ROW_RENDER_LIMIT,
  );
  const strongestCompetitorNetworks = [
    ...competitorNetworkSummaries.filter(
      (network) => network.covered_walmart_locations > 0,
    ),
    ...competitorNetworkSummaries.filter(
      (network) => network.covered_walmart_locations === 0,
    ),
  ].slice(0, 5);
  const stateOptions = useMemo(() => {
    const options = view?.state_options ?? [];
    if (!isCompetitorFootprintScope) return options;
    return options.filter((option) => competitorFootprintStateSet.has(option));
  }, [competitorFootprintStateSet, isCompetitorFootprintScope, view]);
  const visibleShare = filteredPairs.length
    ? filteredWithin / filteredPairs.length
    : null;
  const walmartPointFeatures = useMemo(
    () =>
      featureCollection(
        filteredPairs.map((pair) => walmartFeature(pair, radius)),
      ),
    [filteredPairs, radius],
  );
  const competitorPointFeatures = useMemo(
    () =>
      featureCollection(
        uniqueByLocation(filteredPairs, (pair) => pair.competitor).map((pair) =>
          competitorFeature(pair, radius),
        ),
      ),
    [filteredPairs, radius],
  );
  const relationshipFeatures = useMemo(
    () =>
      featureCollection(
        selectedNetworkPairs.map((pair) => relationshipFeature(pair, radius)),
      ),
    [radius, selectedNetworkPairs],
  );
  const selectedRadiusFeatures = useMemo(
    () =>
      selectedRadiusFeature(showRings ? selectedCoveragePair : null, radius),
    [radius, selectedCoveragePair, showRings],
  );
  const selectedPeers = selectedPair
    ? selectedNetworkPairs
        .filter(
          (pair) =>
            pair.competitor.id === selectedPair.competitor.id &&
            pair.benchmark.id !== selectedPair.benchmark.id,
        )
        .slice(0, 4)
    : [];
  const compactMapSummary = useMemo(
    () => mapSummaryForRows(filteredPairs, view, radius, country),
    [country, filteredPairs, radius, view],
  );

  useEffect(() => {
    pairByKeyRef.current = new Map(
      [...scopedPairs, ...filteredPairs].map((pair) => [pairKey(pair), pair]),
    );
  }, [filteredPairs, scopedPairs]);

  useEffect(() => {
    if (!mapContainerRef.current) return;
    let cancelled = false;
    let map: InteractiveMap | null = null;
    setMapReady(false);
    setMapEnhanced(false);
    setMapError(null);
    loadMapLibrary()
      .then((library) => {
        if (cancelled || !mapContainerRef.current) return;
        map = new library.Map({
          attributionControl: true,
          center: country === "CANADA" ? [-96, 56] : [-97, 38.5],
          container: mapContainerRef.current,
          maxZoom: 18,
          minZoom: country === "CANADA" ? 2 : 2.5,
          style: OPENFREEMAP_STYLE,
          zoom: country === "CANADA" ? 2.8 : 3.1,
        });
        mapRef.current = map;
        popupRef.current = new library.Popup({
          closeButton: false,
          closeOnClick: false,
          maxWidth: "280px",
        });
        map.addControl(
          new library.NavigationControl({ showCompass: true }),
          "top-right",
        );
        map.addControl(
          new library.ScaleControl({ unit: "imperial" }),
          "bottom-left",
        );
        map.on("load", () => {
          if (!map || cancelled) return;
          map.addSource(RELATIONSHIP_SOURCE, {
            data: featureCollection([]),
            type: "geojson",
          });
          map.addSource(SELECTED_RADIUS_SOURCE, {
            data: featureCollection([]),
            type: "geojson",
          });
          map.addSource(WALMART_SOURCE, {
            cluster: true,
            clusterMaxZoom: MAP_CLUSTER_MAX_ZOOM,
            clusterRadius: MAP_CLUSTER_RADIUS,
            data: featureCollection([]),
            type: "geojson",
          });
          map.addSource(COMPETITOR_SOURCE, {
            cluster: true,
            clusterMaxZoom: MAP_CLUSTER_MAX_ZOOM,
            clusterRadius: MAP_CLUSTER_RADIUS,
            data: featureCollection([]),
            type: "geojson",
          });
          map.addLayer({
            id: "selected-radius-fill",
            paint: {
              "fill-color": "#65dfbf",
              "fill-opacity": 0.14,
            },
            source: SELECTED_RADIUS_SOURCE,
            type: "fill",
          });
          map.addLayer({
            id: "selected-radius-line",
            paint: {
              "line-color": "#65dfbf",
              "line-dasharray": [2, 2],
              "line-opacity": 0.72,
              "line-width": 2,
            },
            source: SELECTED_RADIUS_SOURCE,
            type: "line",
          });
          map.addLayer({
            id: "relationship-lines",
            paint: {
              "line-color": [
                "case",
                ["==", ["get", "within_selected_radius"], true],
                "#65dfbf",
                "#ff7285",
              ],
              "line-opacity": [
                "case",
                ["==", ["get", "within_selected_radius"], true],
                0.35,
                0.48,
              ],
              "line-width": [
                "case",
                ["==", ["get", "within_selected_radius"], true],
                1,
                1.25,
              ],
            },
            source: RELATIONSHIP_SOURCE,
            type: "line",
          });
          for (const [sourceId, prefix, color] of [
            [WALMART_SOURCE, "walmart", "#1673db"],
            [COMPETITOR_SOURCE, "competitor", "#ff5f7a"],
          ] as const) {
            map.addLayer({
              filter: ["has", "point_count"],
              id: `${prefix}-clusters`,
              paint: {
                "circle-color": color,
                "circle-opacity": 0.9,
                "circle-radius": [
                  "step",
                  ["get", "point_count"],
                  17,
                  25,
                  22,
                  100,
                  28,
                  500,
                  34,
                ],
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2,
              },
              source: sourceId,
              type: "circle",
            });
            map.addLayer({
              filter: ["has", "point_count"],
              id: `${prefix}-cluster-count`,
              layout: {
                "text-field": ["get", "point_count_abbreviated"],
                "text-font": ["Noto Sans Bold"],
                "text-size": 12,
              },
              paint: { "text-color": "#ffffff" },
              source: sourceId,
              type: "symbol",
            });
          }
          map.addLayer({
            filter: ["!", ["has", "point_count"]],
            id: "competitor-points",
            paint: {
              "circle-color": "#ff5f7a",
              "circle-opacity": 0.92,
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["zoom"],
                3,
                4,
                9,
                7,
                14,
                10,
              ],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1.75,
            },
            source: COMPETITOR_SOURCE,
            type: "circle",
          });
          map.addLayer({
            filter: ["!", ["has", "point_count"]],
            id: "walmart-points",
            paint: {
              "circle-color": [
                "case",
                ["==", ["get", "within_selected_radius"], true],
                "#1673db",
                "#edf7ff",
              ],
              "circle-opacity": 0.96,
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["zoom"],
                3,
                4,
                9,
                7,
                14,
                10,
              ],
              "circle-stroke-color": [
                "case",
                ["==", ["get", "within_selected_radius"], true],
                "#ffffff",
                "#ff7285",
              ],
              "circle-stroke-width": 2,
            },
            source: WALMART_SOURCE,
            type: "circle",
          });

          const selectFeature = (layerId: string) => (event: MapMouseEvent) => {
            if (!map) return;
            const feature = map.queryRenderedFeatures(event.point, {
              layers: [layerId],
            })[0];
            const key = String(feature?.properties?.key ?? "");
            const pair = pairByKeyRef.current.get(key);
            if (!pair) return;
            setSelectedKey(pairKey(pair));
            setShowSelectedDetail(true);
            map.easeTo({
              center: [pair.competitor.longitude, pair.competitor.latitude],
              duration: 420,
              zoom: 10.8,
            });
          };
          const expandCluster =
            (sourceId: string, layerId: string) =>
            async (event: MapMouseEvent) => {
              if (!map) return;
              const feature = map.queryRenderedFeatures(event.point, {
                layers: [layerId],
              })[0];
              const clusterId = Number(feature?.properties?.cluster_id);
              const coordinates = feature?.geometry?.coordinates;
              const zoom = Number.isFinite(clusterId)
                ? await map
                    .getSource(sourceId)
                    ?.getClusterExpansionZoom(clusterId)
                : undefined;
              if (
                zoom !== undefined &&
                Array.isArray(coordinates) &&
                coordinates.length >= 2
              ) {
                map.easeTo({ center: coordinates, zoom });
              }
            };
          const hoverFeature = (layerId: string) => (event: MapMouseEvent) => {
            if (!map || !popupRef.current) return;
            const feature = map.queryRenderedFeatures(event.point, {
              layers: [layerId],
            })[0];
            const coordinates = feature?.geometry?.coordinates;
            popupRef.current
              .setLngLat(
                Array.isArray(coordinates) && coordinates.length >= 2
                  ? ([Number(coordinates[0]), Number(coordinates[1])] as [
                      number,
                      number,
                    ])
                  : (event.lngLat ?? [-97, 38.5]),
              )
              .setHTML(popupHtml(feature))
              .addTo(map);
          };
          const clearHover = () => {
            if (map) map.getCanvas().style.cursor = "";
            popupRef.current?.remove();
          };

          for (const layerId of ["walmart-points", "competitor-points"]) {
            map.on("click", layerId, selectFeature(layerId));
            map.on("mouseenter", layerId, () => {
              if (map) map.getCanvas().style.cursor = "pointer";
            });
            map.on("mousemove", layerId, hoverFeature(layerId));
            map.on("mouseleave", layerId, clearHover);
          }
          for (const [sourceId, layerId] of [
            [WALMART_SOURCE, "walmart-clusters"],
            [COMPETITOR_SOURCE, "competitor-clusters"],
          ] as const) {
            map.on("click", layerId, expandCluster(sourceId, layerId));
            map.on("mouseenter", layerId, () => {
              if (map) map.getCanvas().style.cursor = "pointer";
            });
            map.on("mousemove", layerId, hoverFeature(layerId));
            map.on("mouseleave", layerId, clearHover);
          }
          setMapReady(true);
          map.on("idle", () => {
            if (!cancelled) setMapEnhanced(true);
          });
        });
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setMapError(
          reason instanceof Error
            ? reason.message
            : "The interactive map could not start.",
        );
      });
    return () => {
      cancelled = true;
      setMapReady(false);
      setMapEnhanced(false);
      popupRef.current?.remove();
      popupRef.current = null;
      mapRef.current = null;
      map?.remove();
    };
  }, [country]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    map.getSource(WALMART_SOURCE)?.setData(walmartPointFeatures);
    map.getSource(COMPETITOR_SOURCE)?.setData(competitorPointFeatures);
    map.getSource(RELATIONSHIP_SOURCE)?.setData(relationshipFeatures);
    map.getSource(SELECTED_RADIUS_SOURCE)?.setData(selectedRadiusFeatures);
    setLayerVisibility(
      map,
      ["walmart-clusters", "walmart-cluster-count", "walmart-points"],
      showWalmart,
    );
    setLayerVisibility(
      map,
      ["competitor-clusters", "competitor-cluster-count", "competitor-points"],
      showCompetitors,
    );
    setLayerVisibility(map, ["relationship-lines"], showLinks);
    setLayerVisibility(
      map,
      ["selected-radius-fill", "selected-radius-line"],
      showRings,
    );
  }, [
    competitorPointFeatures,
    mapReady,
    relationshipFeatures,
    selectedRadiusFeatures,
    showCompetitors,
    showLinks,
    showRings,
    showWalmart,
    walmartPointFeatures,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    window.setTimeout(() => {
      map.resize();
      fitToPairs(map, filteredPairs, country);
    }, 0);
  }, [country, filteredPairs, mapReady]);

  function resetView() {
    setQuery("");
    setStateFilter("all");
    setRelation("all");
    setSort("nearest");
    setOnlySaved(false);
    setComparisonScope(recommendedScopeForView(view));
    setCompetitorStateDetail(null);
    setCompetitorMarketDetail(null);
  }

  function toggleSaved(pair: ProximityPair) {
    const key = pairKey(pair);
    setSavedByComparison((current) => {
      const currentKeys = new Set(current[shortlistStorageKey] ?? []);
      if (currentKeys.has(key)) currentKeys.delete(key);
      else currentKeys.add(key);
      return {
        ...current,
        [shortlistStorageKey]: Array.from(currentKeys),
      };
    });
  }

  function focusMapOnPair(pair: ProximityPair) {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    map.easeTo({
      center: [pair.competitor.longitude, pair.competitor.latitude],
      duration: 420,
      zoom: Math.max(radius <= 1 ? 11.4 : radius <= 3 ? 10.2 : 9.1, 8.5),
    });
  }

  function selectRelationship(key: string) {
    const pair = pairByKeyRef.current.get(key) ?? scopedPairByKey.get(key);
    setSelectedKey(key);
    setShowSelectedDetail(true);
    if (pair) focusMapOnPair(pair);
  }

  const shellActions = useMemo(
    () => (
      <div className={styles.shellActions} aria-label="Proximity page actions">
        <button
          className={styles.btn}
          onClick={() => setModal("shortlist")}
          title="Open saved Walmart-to-competitor relationships"
          type="button"
        >
          Shortlist <span className={styles.pill}>{savedKeys.size}</span>
        </button>
        <button
          className={styles.btn}
          onClick={() => setModal("notes")}
          title="Open guidance for using the Proximity page"
          type="button"
        >
          Notes
        </button>
        <div className={styles.menuWrap}>
          <button
            className={styles.btn}
            onClick={() => setShowExportMenu((current) => !current)}
            title="Export the currently filtered proximity evidence"
            type="button"
          >
            Export ▾
          </button>
          {showExportMenu ? (
            <div className={styles.exportMenu}>
              <button
                onClick={() => {
                  downloadCsv(filteredPairs, radius, "proximity-filtered.csv");
                  setShowExportMenu(false);
                }}
                title="Download visible rows as CSV"
                type="button"
              >
                Visible rows · CSV
              </button>
              <button
                onClick={() => {
                  downloadCsv(
                    filteredPairs,
                    radius,
                    "proximity-filtered-excel.csv",
                  );
                  setShowExportMenu(false);
                }}
                title="Download visible rows as an Excel-compatible CSV"
                type="button"
              >
                Visible rows · Excel CSV
              </button>
              <button
                onClick={() => {
                  downloadJson(
                    filteredPairs,
                    radius,
                    "proximity-filtered.json",
                  );
                  setShowExportMenu(false);
                }}
                title="Download visible rows as JSON"
                type="button"
              >
                Visible rows · JSON
              </button>
              <button
                onClick={() => {
                  downloadGeoJson(
                    filteredPairs,
                    radius,
                    "proximity-filtered.geojson",
                  );
                  setShowExportMenu(false);
                }}
                title="Download visible rows as GeoJSON for mapping workflows"
                type="button"
              >
                Map layer · GeoJSON
              </button>
            </div>
          ) : null}
        </div>
        <button
          className={styles.btn}
          onClick={() => setShowFilters(true)}
          title="Open retailer, radius, filter, and map-layer controls"
          type="button"
        >
          Controls
        </button>
        <button
          className={`${styles.btn} ${styles.primary}`}
          onClick={() => setShowTable(true)}
          title="Open the full downloadable Walmart and competitor location table"
          type="button"
        >
          Location table
        </button>
      </div>
    ),
    [filteredPairs, radius, savedKeys.size, showExportMenu],
  );
  useApplicationContextActions(shellActions);

  return (
    <div
      className={`${styles.workspace} ${theme === "dark" ? styles.dark : ""}`}
    >
      <header className={styles.topbar}>
        <div className={styles.commandIntro}>
          <h1>Retailer proximity explorer</h1>
          <div className={styles.topCenter} aria-label="Retailer comparison">
            <span className={styles.retailerChip}>
              <i className={styles.walmartDot} />
              {view?.benchmark.display_name ?? "Walmart"}
            </span>
            <span className={styles.connector}>nearest to</span>
            <span className={styles.retailerChip}>
              <i className={styles.competitorDot} />
              {view?.competitor.display_name ?? "Selected retailer"}
            </span>
            <span className={styles.snapshot}>
              <i />
              {view ? count(view.summary.paired_locations) : "No"} Walmart
              locations paired
            </span>
            <button
              className={styles.scopeChip}
              onClick={() => setModal("metric-scope")}
              title="Open comparison-scope definition"
              type="button"
            >
              Scope: {comparisonScopeLabel}
            </button>
          </div>
          <p>
            OpenFreeMap / OpenMapTiles / OpenStreetMap base map with
            source-backed nearest-store relationships from the location master.
            Distances are straight-line Haversine miles; not drive time,
            inventory, assortment, or product distribution.
          </p>
        </div>
      </header>

      {error ? (
        <div className={`${styles.notice} ${styles.warning}`}>{error}</div>
      ) : null}
      {loading ? (
        <div className={styles.notice}>Loading proximity data…</div>
      ) : null}

      <section className={styles.kpis} aria-label="Proximity summary">
        <MetricCard
          description={walmartScopeDescription}
          icon="W"
          iconClass={styles.blue}
          label={walmartScopeLabel}
          onInfo={() => setModal("metric-total")}
          title="Open Walmart store denominator definition"
          value={count(
            isCompetitorFootprintScope
              ? scopedPairs.length
              : totalWalmartLocations,
          )}
        />
        <MetricCard
          description={`${count(selectedCoverage?.within ?? filteredWithin)} of ${count(scopedPairs.length)} paired Walmart locations`}
          icon="≤"
          iconClass={styles.green}
          label={`Coverage within ${radius} mile${radius === 1 ? "" : "s"}`}
          onInfo={() => setModal("metric-coverage")}
          title="Open radius coverage definition"
          value={percent(selectedCoverage?.share ?? visibleShare)}
        />
        <MetricCard
          description={`${percent(scopedPairs.length ? (selectedCoverage?.outside ?? filteredOutside) / scopedPairs.length : null)} of paired Walmart locations`}
          icon="gap"
          iconClass={styles.red}
          label={`White-space stores > ${radius} mile${radius === 1 ? "" : "s"}`}
          onInfo={() => setModal("metric-gap")}
          title="Open white-space stores definition"
          value={count(selectedCoverage?.outside ?? filteredOutside)}
        />
        <MetricCard
          description={`${percent(competitorGapShare)} of ${count(competitorPerspectivePairs.length)} mappable ${view?.competitor.display_name ?? "competitor"} sites`}
          icon="C"
          iconClass={styles.red}
          label={`Competitor sites > ${radius} mi`}
          onInfo={() => setModal("metric-competitor-whitespace")}
          title="Open competitor white-space definition"
          value={count(competitorGapLocations)}
        />
      </section>

      <section className={styles.insightDeck} aria-label="Proximity insights">
        <article
          className={`${styles.coverageCard} ${styles.insightPanelWide}`}
          aria-label="Walmart coverage by selected competitor radius"
        >
          <div className={styles.coverageHead}>
            <div>
              <h2>Coverage by radius</h2>
              <p>
                Percent of paired Walmart locations whose nearest{" "}
                {view?.competitor.display_name ?? "competitor"} is within each
                straight-line radius.
              </p>
            </div>
            <div className={styles.cardActions}>
              <button
                className={styles.cardInfoButton}
                onClick={() => setModal("metric-coverage")}
                title="Open radius coverage definition"
                type="button"
              >
                i
              </button>
              <button
                onClick={() => setShowTable(true)}
                title="Open the downloadable location table"
                type="button"
              >
                Store details
              </button>
            </div>
          </div>
          <div className={styles.coverageRows}>
            {coverageBands.map((band) => (
              <button
                aria-pressed={radius === band.miles}
                className={styles.coverageRow}
                key={band.miles}
                onClick={() => void load({ radius: band.miles })}
                title={`Switch selected radius to ${band.miles} mile${band.miles === 1 ? "" : "s"}`}
                type="button"
              >
                <span>{band.label}</span>
                <i>
                  <b style={{ width: percent(band.share) }} />
                </i>
                <strong>{count(band.within)}</strong>
                <small>{count(band.outside)} gaps</small>
                <small>{percent(band.share)}</small>
              </button>
            ))}
          </div>
        </article>

        <article className={styles.insightPanel}>
          <div className={styles.coverageHead}>
            <div>
              <h2>Competitor white-space by state</h2>
              <p>
                Where {view?.competitor.display_name ?? "the competitor"} has
                locations without Walmart within {radius} mi.
              </p>
            </div>
            <div className={styles.cardActions}>
              <button
                className={styles.cardInfoButton}
                onClick={() => setModal("metric-competitor-whitespace")}
                title="Open competitor white-space definition"
                type="button"
              >
                i
              </button>
              <button
                onClick={() => setCompetitorStateDetail("all")}
                title="Open the full competitor white-space state list"
                type="button"
              >
                All states
              </button>
            </div>
          </div>
          <div className={styles.rankedList}>
            {competitorWhiteSpaceStates.map((state) => (
              <button
                key={state.state}
                onClick={() => setCompetitorStateDetail(state.state)}
                title={`Open ${state.state} ${view?.competitor.display_name ?? "competitor"} locations whose nearest Walmart is beyond ${radius} mile${radius === 1 ? "" : "s"}`}
                type="button"
              >
                <span>{state.state}</span>
                <b>{count(state.gap_locations)} gaps</b>
                <small>
                  {count(state.competitor_locations)} competitor sites ·{" "}
                  {percent(state.coverage_share)} near Walmart · median{" "}
                  {miles(state.median_distance_to_walmart_miles)}
                </small>
              </button>
            ))}
          </div>
        </article>

        <article className={styles.insightPanel}>
          <div className={styles.coverageHead}>
            <div>
              <h2>Competitor white-space markets</h2>
              <p>
                City/state markets where{" "}
                {view?.competitor.display_name ?? "the competitor"} has
                locations without Walmart inside {radius} mi.
              </p>
            </div>
            <div className={styles.cardActions}>
              <button
                className={styles.cardInfoButton}
                onClick={() => setModal("metric-market")}
                title="Open market white-space definition"
                type="button"
              >
                i
              </button>
              <button
                onClick={() => setCompetitorMarketDetail("all")}
                title="Open the full competitor white-space market list"
                type="button"
              >
                All markets
              </button>
            </div>
          </div>
          <div className={styles.rankedList}>
            {competitorWhiteSpaceMarkets.map((market) => (
              <button
                key={market.market_key}
                onClick={() => setCompetitorMarketDetail(market.market_key)}
                title={`Open ${market.city}, ${market.state} competitor white-space details`}
                type="button"
              >
                <span>
                  {market.city}, {market.state}
                </span>
                <b>{count(market.gap_locations)} gaps</b>
                <small>
                  {count(market.competitor_locations)} competitor sites ·{" "}
                  {percent(market.coverage_share)} near Walmart · median{" "}
                  {miles(market.median_distance_to_walmart_miles)}
                </small>
              </button>
            ))}
          </div>
        </article>

        <article className={styles.insightPanel}>
          <div className={styles.coverageHead}>
            <div>
              <h2>Highest-overlap competitor sites</h2>
              <p>
                Competitor locations with the most Walmart stores inside{" "}
                {radius} mi.
              </p>
            </div>
          </div>
          <div className={styles.rankedList}>
            {strongestCompetitorNetworks.map((network) => (
              <button
                key={network.competitor_location_id}
                onClick={() =>
                  selectRelationship(network.representative_pair_key)
                }
                title={`Inspect ${view?.competitor.display_name ?? "competitor"} #${network.competitor_store_number} and its nearby Walmart network`}
                type="button"
              >
                <span>
                  #{network.competitor_store_number} ·{" "}
                  {network.city || "Unknown city"}
                  {network.state ? `, ${network.state}` : ""}
                </span>
                <b>{count(network.covered_walmart_locations)} nearby</b>
                <small>
                  {count(network.assigned_walmart_locations)} total assigned ·
                  median {miles(network.median_distance_miles)}
                </small>
              </button>
            ))}
          </div>
        </article>

        <article className={styles.insightPanel}>
          <div className={styles.coverageHead}>
            <div>
              <h2>Walmart competitive pressure states</h2>
              <p>
                States where the largest share of Walmart stores has this
                competitor inside {radius} mi.
              </p>
            </div>
            <button
              className={styles.cardInfoButton}
              onClick={() => setModal("metric-pressure")}
              title="Open competitive pressure definition"
              type="button"
            >
              i
            </button>
          </div>
          <div className={styles.rankedList}>
            {walmartPressureStates.map((state) => (
              <button
                key={state.state}
                onClick={() => {
                  setStateFilter(state.state);
                  setRelation("within");
                }}
                title={`Filter to ${state.state} Walmart stores with ${view?.competitor.display_name ?? "the competitor"} inside ${radius} mile${radius === 1 ? "" : "s"}`}
                type="button"
              >
                <span>{state.state}</span>
                <b>{percent(state.coverage_share)}</b>
                <small>
                  {count(state.covered_locations)} of{" "}
                  {count(state.walmart_locations)} Walmart stores covered ·
                  median {miles(state.median_distance_miles)}
                </small>
              </button>
            ))}
          </div>
        </article>

        <article className={styles.insightPanel}>
          <div className={styles.coverageHead}>
            <div>
              <h2>Walmart white-space markets</h2>
              <p>
                City/state Walmart markets whose nearest{" "}
                {view?.competitor.display_name ?? "competitor"} is farther than{" "}
                {radius} mi.
              </p>
            </div>
            <button
              className={styles.cardInfoButton}
              onClick={() => setModal("metric-gap")}
              title="Open Walmart white-space definition"
              type="button"
            >
              i
            </button>
          </div>
          <div className={styles.rankedList}>
            {walmartWhiteSpaceMarkets.map((market) => (
              <button
                key={market.market_key}
                onClick={() => {
                  setStateFilter(market.state);
                  setQuery(market.city);
                  setRelation("outside");
                }}
                title={`Filter to ${market.city}, ${market.state} Walmart white-space stores`}
                type="button"
              >
                <span>
                  {market.city}, {market.state}
                </span>
                <b>{count(market.gap_locations)} gaps</b>
                <small>
                  {count(market.walmart_locations)} Walmart stores ·{" "}
                  {percent(market.coverage_share)} covered · median{" "}
                  {miles(market.median_distance_miles)}
                </small>
              </button>
            ))}
          </div>
        </article>

        <article className={styles.insightPanel}>
          <div className={styles.coverageHead}>
            <div>
              <h2>Distance profile</h2>
              <p>Nearest-competitor distance across active Walmart scope.</p>
            </div>
            <button
              className={styles.cardInfoButton}
              onClick={() => setModal("metric-distance")}
              title="Open distance profile definition"
              type="button"
            >
              i
            </button>
          </div>
          <div className={styles.distanceGrid}>
            <span>
              Median <b>{miles(distanceSummary.median_miles)}</b>
            </span>
            <span>
              P75 <b>{miles(distanceSummary.p75_miles)}</b>
            </span>
            <span>
              P90 <b>{miles(distanceSummary.p90_miles)}</b>
            </span>
            <span>
              Max <b>{miles(distanceSummary.max_miles)}</b>
            </span>
          </div>
        </article>
      </section>

      <section className={styles.explorer}>
        <section className={styles.mapSection} aria-label="Proximity map">
          <div className={styles.mapArea}>
            <StaticProximityMap
              country={country}
              onSelect={selectRelationship}
              selectedPair={selectedPair}
              showCompetitors={showCompetitors}
              showLinks={showLinks}
              showRings={showRings}
              showWalmart={showWalmart}
              radius={radius}
              summary={compactMapSummary}
              selectedNetworkPairs={selectedNetworkPairs}
            />
            <div
              aria-hidden={!mapEnhanced}
              className={`${styles.tileMap} ${mapEnhanced ? styles.tileMapEnhanced : ""}`}
              ref={mapContainerRef}
            />
            {!mapEnhanced ? (
              <div className={styles.mapStatusPill}>
                Fast source-backed cluster map shown · OpenFreeMap tiles loading
                in the background
              </div>
            ) : null}
            {mapError ? (
              <div className={`${styles.mapBusy} ${styles.warning}`}>
                Tile map unavailable; showing the fast source-backed cluster
                map. {mapError}
              </div>
            ) : null}
            <div className={styles.mapToolbar}>
              <div className={styles.quickViews}>
                <button
                  className={relation === "all" ? styles.active : undefined}
                  onClick={() => setRelation("all")}
                  title="Show all paired Walmart locations, including covered and white-space stores"
                  type="button"
                >
                  <strong>All Walmart stores</strong>
                  <small>Covered and white-space</small>
                </button>
                <button
                  className={relation === "within" ? styles.active : undefined}
                  onClick={() => setRelation("within")}
                  title={`Show Walmart locations with the selected competitor within ${radius} mile${radius === 1 ? "" : "s"}`}
                  type="button"
                >
                  <strong>Covered within radius</strong>
                  <small>Nearest competitor is close</small>
                </button>
                <button
                  className={relation === "outside" ? styles.active : undefined}
                  onClick={() => setRelation("outside")}
                  title={`Show Walmart locations without the selected competitor within ${radius} mile${radius === 1 ? "" : "s"}`}
                  type="button"
                >
                  <strong>White-space stores</strong>
                  <small>Nearest competitor is farther away</small>
                </button>
                {query ||
                effectiveStateFilter !== "all" ||
                relation !== "all" ||
                sort !== "nearest" ||
                onlySaved ||
                comparisonScope !== recommendedScopeForView(view) ? (
                  <button
                    className={styles.resetQuickView}
                    onClick={resetView}
                    title="Reset search, state, relationship, sort, and shortlist filters"
                    type="button"
                  >
                    <strong>Reset view</strong>
                    <small>Return to all locations</small>
                  </button>
                ) : null}
              </div>
            </div>
            <div className={styles.legend}>
              <span title="Blue circles are grouped Walmart locations from the active filtered set.">
                <i className={styles.walmartDot} />
                Walmart clusters
              </span>
              <span title="Red squares/circles are competitor sites represented as nearest neighbors to at least one Walmart.">
                <i className={styles.competitorDot} />
                Represented competitor clusters
              </span>
              <span title="Lines show Walmart stores assigned to the selected competitor site. Solid lines are inside the selected radius; dashed lines are outside.">
                <i className={styles.coveredLineLegend} />
                selected network links
              </span>
              <span title="The dashed ring is the selected radius around the selected competitor site.">
                <i className={styles.radiusRingLegend} />
                selected radius
              </span>
            </div>
            <div className={styles.mapInsightPanel}>
              <span>Current view</span>
              <strong>{count(filteredPairs.length)} Walmart pairs shown</strong>
              <small>
                {relation === "within"
                  ? `${count(filteredWithin)} locations have the selected competitor within ${radius} mile${radius === 1 ? "" : "s"}.`
                  : relation === "outside"
                    ? `${count(filteredOutside)} locations are white-space at the selected radius.`
                    : `${count(filteredWithin)} covered / ${count(filteredOutside)} white-space at ${radius} mile${radius === 1 ? "" : "s"}.`}
              </small>
            </div>
            {selectedPair ? (
              <aside
                aria-label="Selected competitor network"
                className={styles.selectedNetworkPanel}
              >
                <div className={styles.selectedNetworkHead}>
                  <div>
                    <span>Selected network</span>
                    <h2>
                      {selectedPair.competitor.retailer_display_name} #
                      {selectedPair.competitor.store_number}
                    </h2>
                    <p>
                      {selectedPair.competitor.city || "Unknown city"}
                      {selectedPair.competitor.state
                        ? `, ${selectedPair.competitor.state}`
                        : ""}{" "}
                      · nearest to {count(selectedNetworkPairs.length)} Walmart
                      locations.
                    </p>
                  </div>
                  <button
                    onClick={() => toggleSaved(selectedPair)}
                    title="Save or remove this selected competitor network from the shortlist"
                    type="button"
                  >
                    {savedKeys.has(pairKey(selectedPair)) ? "★" : "☆"}
                  </button>
                </div>
                <div className={styles.networkMetrics}>
                  <span>
                    Selected pair <b>{miles(selectedPair.distance_miles)}</b>
                  </span>
                  <span>
                    Within {radius} mi{" "}
                    <b>
                      {count(selectedNetworkWithin)} /{" "}
                      {count(selectedNetworkPairs.length)}
                    </b>
                  </span>
                  <span>
                    Coverage <b>{percent(selectedNetworkCoverageShare)}</b>
                  </span>
                  <span>
                    Median <b>{miles(selectedNetworkMedian)}</b>
                  </span>
                  <span>
                    Farthest <b>{miles(selectedNetworkFarthest)}</b>
                  </span>
                </div>
                <div className={styles.networkActions}>
                  <button
                    onClick={() => {
                      setRelation("all");
                      focusMapOnPair(selectedPair);
                    }}
                    title="Recenter the map on this selected competitor network"
                    type="button"
                  >
                    Recenter
                  </button>
                  <button
                    onClick={() => setShowSelectedDetail(true)}
                    title="Open the full selected relationship drawer"
                    type="button"
                  >
                    Details
                  </button>
                  <button
                    onClick={() => setShowTable(true)}
                    title="Open the downloadable location table"
                    type="button"
                  >
                    Table
                  </button>
                </div>
                <div className={styles.networkRows}>
                  {selectedNetworkPairs.slice(0, 6).map((pair) => (
                    <button
                      key={pairKey(pair)}
                      onClick={() => selectRelationship(pairKey(pair))}
                      title={`Select Walmart #${pair.benchmark.store_number} in this competitor network`}
                      type="button"
                    >
                      <span>
                        Walmart #{pair.benchmark.store_number}
                        <small>
                          {pair.benchmark.city || "Unknown city"}
                          {pair.benchmark.state
                            ? `, ${pair.benchmark.state}`
                            : ""}
                        </small>
                      </span>
                      <b>{miles(pair.distance_miles)}</b>
                    </button>
                  ))}
                </div>
              </aside>
            ) : null}
          </div>
          <div className={styles.mapFooter}>
            <span>
              <i />
              OpenFreeMap tiles · OpenMapTiles · © OpenStreetMap contributors
            </span>
            <span>
              Radius coverage 1/3/5/10 mi:{" "}
              {coverageBands.map((band) => count(band.within)).join(" / ")}
            </span>
          </div>
        </section>
      </section>

      {showSelectedDetail && selectedPair ? (
        <div
          className={styles.drawerBackdrop}
          onClick={() => setShowSelectedDetail(false)}
          role="presentation"
        >
          <aside
            aria-label="Selected proximity relationship"
            className={`${styles.drawer} ${styles.detailDrawer}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.drawerHead}>
              <div>
                <span>Selected relationship</span>
                <h2>{miles(selectedPair.distance_miles)} apart</h2>
                <p>
                  Walmart #{selectedPair.benchmark.store_number} paired to the
                  nearest {selectedPair.competitor.retailer_display_name} store
                  from the location master.
                </p>
              </div>
              <button
                onClick={() => setShowSelectedDetail(false)}
                title="Close selected relationship details"
                type="button"
              >
                ×
              </button>
            </div>
            <button
              className={styles.saveButton}
              onClick={() => toggleSaved(selectedPair)}
              title="Save or remove this relationship from the shortlist"
              type="button"
            >
              {savedKeys.has(pairKey(selectedPair)) ? "Saved ★" : "Save ☆"}
            </button>
            <div className={styles.drawerStats}>
              <span>Selected competitor network</span>
              <strong>{count(selectedNetworkPairs.length)}</strong>
              <small>
                Visible Walmart locations whose nearest{" "}
                {selectedPair.competitor.retailer_display_name} site is #
                {selectedPair.competitor.store_number};{" "}
                {count(selectedNetworkWithin)} are within {radius} mile
                {radius === 1 ? "" : "s"}.
              </small>
            </div>
            <div className={styles.detailStack}>
              <article>
                <b>
                  <i className={styles.walmartDot} />
                  Walmart
                </b>
                <p>
                  #{selectedPair.benchmark.store_number} ·{" "}
                  {locationLabel(selectedPair.benchmark)}
                </p>
                <a
                  href={googleMapsUrl(
                    selectedPair.benchmark.latitude,
                    selectedPair.benchmark.longitude,
                  )}
                  rel="noreferrer"
                  target="_blank"
                >
                  Open Walmart coordinate
                </a>
              </article>
              <article>
                <b>
                  <i className={styles.competitorDot} />
                  {selectedPair.competitor.retailer_display_name}
                </b>
                <p>
                  #{selectedPair.competitor.store_number} ·{" "}
                  {locationLabel(selectedPair.competitor)}
                </p>
                <a
                  href={googleMapsUrl(
                    selectedPair.competitor.latitude,
                    selectedPair.competitor.longitude,
                  )}
                  rel="noreferrer"
                  target="_blank"
                >
                  Open competitor coordinate
                </a>
              </article>
            </div>
            <div className={styles.radiusFacts}>
              {RADIUS_OPTIONS.map((option) => (
                <span
                  className={
                    selectedPair.distance_miles <= option
                      ? styles.inside
                      : styles.outside
                  }
                  key={option}
                >
                  ≤ {option} mi
                </span>
              ))}
            </div>
            {selectedPeers.length ? (
              <div className={styles.peerList}>
                <span>Other visible Walmart locations nearest this site</span>
                {selectedPeers.map((pair) => (
                  <button
                    key={pair.benchmark.id}
                    onClick={() => {
                      setSelectedKey(pairKey(pair));
                      focusMapOnPair(pair);
                    }}
                    title="Select this Walmart relationship"
                    type="button"
                  >
                    #{pair.benchmark.store_number} ·{" "}
                    {pair.benchmark.city || "Unknown city"},{" "}
                    {pair.benchmark.state || "—"}
                    <b>{miles(pair.distance_miles)}</b>
                  </button>
                ))}
              </div>
            ) : null}
          </aside>
        </div>
      ) : null}

      {showFilters ? (
        <div
          className={styles.drawerBackdrop}
          onClick={() => setShowFilters(false)}
          role="presentation"
        >
          <aside
            aria-label="Proximity filters"
            className={styles.drawer}
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.drawerHead}>
              <div>
                <span>Map controls</span>
                <h2>Choose the retailer, radius, filters, and layers</h2>
              </div>
              <button
                onClick={() => setShowFilters(false)}
                title="Close map controls"
                type="button"
              >
                ×
              </button>
            </div>
            <label className={styles.field}>
              <span>Walmart market</span>
              <select
                title="Choose Walmart US or Walmart Canada"
                value={country}
                onChange={(event) => void load({ country: event.target.value })}
              >
                <option value="USA">Walmart US</option>
                <option value="CANADA">Walmart CA</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>Compare to one retailer</span>
              <select
                title="Choose the competitor retailer for nearest-store pairing"
                value={competitorRetailerId}
                onChange={(event) =>
                  void load({ competitorRetailerId: event.target.value })
                }
              >
                {competitorOptions.length === 0 ? (
                  <option value="">No competitor locations</option>
                ) : null}
                {competitorOptions.map((retailer) => (
                  <option key={retailer.id} value={retailer.id}>
                    {retailer.display_name} · {count(retailer.location_count)}
                  </option>
                ))}
              </select>
            </label>
            <div className={styles.field}>
              <span>Comparison scope</span>
              <div className={styles.scopeSet}>
                <button
                  aria-pressed={comparisonScope === "all-walmart"}
                  onClick={() => setComparisonScope("all-walmart")}
                  title="Use all paired Walmart locations in the selected country as the denominator"
                  type="button"
                >
                  All Walmart
                </button>
                <button
                  aria-pressed={comparisonScope === "competitor-footprint"}
                  disabled={competitorFootprintStates.length === 0}
                  onClick={() => setComparisonScope("competitor-footprint")}
                  title={`Use only Walmart locations in states/provinces where ${view?.competitor.display_name ?? "the competitor"} has mappable locations`}
                  type="button"
                >
                  Competitor footprint
                </button>
              </div>
              <small className={styles.fieldHint}>
                {isCompetitorFootprintScope
                  ? `Using Walmart locations in ${competitorFootprintLabel}.`
                  : `Using all ${view?.benchmark.display_name ?? "Walmart"} locations in ${country}.`}
              </small>
            </div>
            <div className={styles.field}>
              <span>Competition radius</span>
              <div className={styles.radiusSet}>
                {RADIUS_OPTIONS.map((option) => (
                  <button
                    aria-pressed={radius === option}
                    key={option}
                    onClick={() => void load({ radius: option })}
                    title={`Use ${option} mile${option === 1 ? "" : "s"} as the selected coverage radius`}
                    type="button"
                  >
                    {option} mi
                  </button>
                ))}
              </div>
            </div>
            <label className={styles.searchbox}>
              <span>⌕</span>
              <input
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search store, city, state, ZIP"
                title="Search Walmart and competitor store details"
                type="search"
                value={query}
              />
            </label>
            <label className={styles.field}>
              <span>Walmart state/province</span>
              <select
                title="Filter Walmart locations by state or province"
                value={effectiveStateFilter}
                onChange={(event) => setStateFilter(event.target.value)}
              >
                <option value="all">All</option>
                {stateOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>Relationship</span>
              <select
                title="Filter by whether the nearest competitor is inside or outside the selected radius"
                value={relation}
                onChange={(event) =>
                  setRelation(event.target.value as RelationFilter)
                }
              >
                <option value="all">All Walmart locations</option>
                <option value="within">Within selected radius</option>
                <option value="outside">Outside selected radius</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>Sort</span>
              <select
                title="Sort the table and selected relationship sequence"
                value={sort}
                onChange={(event) => setSort(event.target.value as SortMode)}
              >
                <option value="nearest">Nearest first</option>
                <option value="farthest">Farthest first</option>
                <option value="state">State then store</option>
                <option value="store">Store number</option>
              </select>
            </label>
            <label className={styles.checkRow}>
              <input
                checked={onlySaved}
                onChange={(event) => setOnlySaved(event.target.checked)}
                title="Show only shortlisted relationships"
                type="checkbox"
              />
              <span>Only show shortlisted relationships</span>
            </label>
            <div className={styles.layerBox}>
              <div className={styles.sectionLine}>
                <h2>Map layers</h2>
                <button
                  className={styles.textButton}
                  onClick={() => setModal("method")}
                  title="Open map and metric methodology"
                  type="button"
                >
                  Method
                </button>
              </div>
              <div className={styles.layerGrid}>
                {[
                  ["Walmart", showWalmart, setShowWalmart],
                  ["Competitor", showCompetitors, setShowCompetitors],
                  ["Links", showLinks, setShowLinks],
                  ["Selected radius", showRings, setShowRings],
                  ["Saved only", onlySaved, setOnlySaved],
                ].map(([label, value, setter]) => (
                  <button
                    aria-pressed={Boolean(value)}
                    key={String(label)}
                    onClick={() =>
                      (setter as (next: boolean) => void)(!Boolean(value))
                    }
                    title={`Toggle ${String(label).toLowerCase()} layer`}
                    type="button"
                  >
                    <span>{String(label)}</span>
                    <i />
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.drawerStats}>
              <span>Visible rows</span>
              <strong>{count(filteredPairs.length)}</strong>
              <small>
                Exports, table, KPIs, and map all use this same filtered
                population.
              </small>
            </div>
            <button
              className={styles.btn}
              onClick={resetView}
              title="Reset state, search, relationship, sort, and shortlist filters"
              type="button"
            >
              Reset filters
            </button>
          </aside>
        </div>
      ) : null}

      {competitorStateDetail ? (
        <div
          className={styles.drawerBackdrop}
          onClick={() => setCompetitorStateDetail(null)}
          role="presentation"
        >
          <section
            aria-label="Competitor white-space detail"
            className={`${styles.drawer} ${styles.tableDrawer}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.drawerHead}>
              <div>
                <span>Competitor-location evidence</span>
                <h2>
                  {competitorStateDetail === "all"
                    ? "All competitor white-space states"
                    : `${competitorStateDetail} competitor white-space`}
                </h2>
                <p>
                  Showing{" "}
                  {count(
                    Math.min(
                      competitorStateDetailRows.length,
                      DETAIL_ROW_RENDER_LIMIT,
                    ),
                  )}{" "}
                  of {count(competitorStateDetailRows.length)}{" "}
                  {view?.competitor.display_name ?? "competitor"} locations
                  paired to their nearest Walmart. Downloads include the full
                  list; rows outside {radius} mi are the selected competitor’s
                  white-space locations.
                </p>
              </div>
              <button
                onClick={() => setCompetitorStateDetail(null)}
                title="Close competitor white-space detail"
                type="button"
              >
                ×
              </button>
            </div>
            <div className={styles.tableSummary}>
              <article>
                <span>Competitor locations</span>
                <strong>
                  {count(
                    competitorStateDetailSummary?.competitor_locations ??
                      competitorPerspectivePairs.length,
                  )}
                </strong>
              </article>
              <article>
                <span>Without Walmart ≤ {radius} mi</span>
                <strong>
                  {count(
                    competitorStateDetailSummary?.gap_locations ??
                      competitorGapLocations,
                  )}
                </strong>
              </article>
              <article>
                <span>Near Walmart</span>
                <strong>
                  {count(
                    competitorStateDetailSummary?.within_radius_locations ??
                      competitorWithinLocations,
                  )}
                </strong>
              </article>
              <article>
                <span>Median to Walmart</span>
                <strong>
                  {miles(
                    competitorStateDetailSummary?.median_distance_to_walmart_miles ??
                      median(
                        competitorStateDetailRows.map(
                          (pair) => pair.distance_miles,
                        ),
                      ),
                  )}
                </strong>
              </article>
            </div>
            <div className={styles.downloadRow}>
              <button
                className={styles.btn}
                onClick={() => setCompetitorStateDetail("all")}
                title="Reset the drawer to all competitor states"
                type="button"
              >
                All states
              </button>
              <button
                className={styles.btn}
                onClick={() => setCompetitorStateDetail(null)}
                title="Close this drill-down drawer"
                type="button"
              >
                Reset view
              </button>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadCompetitorCsv(
                    competitorStateDetailRows,
                    radius,
                    "proximity-competitor-white-space.csv",
                  )
                }
                title="Download competitor white-space rows as CSV"
                type="button"
              >
                CSV
              </button>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadCompetitorJson(
                    competitorStateDetailRows,
                    radius,
                    "proximity-competitor-white-space.json",
                  )
                }
                title="Download competitor white-space rows as JSON"
                type="button"
              >
                JSON
              </button>
            </div>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Competitor #</th>
                    <th>Competitor location</th>
                    <th>Nearest Walmart #</th>
                    <th>Nearest Walmart location</th>
                    <th>Distance to Walmart</th>
                    <th>Walmart ≤ {radius} mi</th>
                    <th>Competitor coordinate</th>
                    <th>Walmart coordinate</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleCompetitorStateDetailRows.map((pair) => (
                    <tr key={pair.competitor.id}>
                      <td>{pair.competitor.store_number}</td>
                      <td>{locationLabel(pair.competitor)}</td>
                      <td>{pair.nearest_walmart.store_number}</td>
                      <td>{locationLabel(pair.nearest_walmart)}</td>
                      <td>{miles(pair.distance_miles)}</td>
                      <td>{pair.distance_miles <= radius ? "Yes" : "No"}</td>
                      <td>
                        {pair.competitor.latitude.toFixed(5)},{" "}
                        {pair.competitor.longitude.toFixed(5)}
                      </td>
                      <td>
                        {pair.nearest_walmart.latitude.toFixed(5)},{" "}
                        {pair.nearest_walmart.longitude.toFixed(5)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : null}

      {competitorMarketDetail ? (
        <div
          className={styles.drawerBackdrop}
          onClick={() => setCompetitorMarketDetail(null)}
          role="presentation"
        >
          <section
            aria-label="Competitor white-space market detail"
            className={`${styles.drawer} ${styles.tableDrawer}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.drawerHead}>
              <div>
                <span>Market-level competitor evidence</span>
                <h2>
                  {competitorMarketDetail === "all"
                    ? "All competitor white-space markets"
                    : `${competitorMarketDetailSummary?.city ?? "Market"}, ${competitorMarketDetailSummary?.state ?? ""}`}
                </h2>
                <p>
                  Showing{" "}
                  {count(
                    Math.min(
                      competitorMarketDetailPairRows.length,
                      DETAIL_ROW_RENDER_LIMIT,
                    ),
                  )}{" "}
                  of {count(competitorMarketDetailPairRows.length)}{" "}
                  {view?.competitor.display_name ?? "competitor"} locations
                  across {count(competitorMarketDetailRows.length)} market
                  {competitorMarketDetailRows.length === 1 ? "" : "s"}.
                  Downloads include the full list.
                </p>
              </div>
              <button
                onClick={() => setCompetitorMarketDetail(null)}
                title="Close competitor market detail"
                type="button"
              >
                ×
              </button>
            </div>
            <div className={styles.tableSummary}>
              <article>
                <span>Markets</span>
                <strong>{count(competitorMarketDetailRows.length)}</strong>
              </article>
              <article>
                <span>Competitor locations</span>
                <strong>{count(competitorMarketDetailPairRows.length)}</strong>
              </article>
              <article>
                <span>Without Walmart ≤ {radius} mi</span>
                <strong>{count(competitorMarketDetailGapLocations)}</strong>
              </article>
              <article>
                <span>Near Walmart</span>
                <strong>{count(competitorMarketDetailWithinLocations)}</strong>
              </article>
            </div>
            <div className={styles.downloadRow}>
              <button
                className={styles.btn}
                onClick={() => setCompetitorMarketDetail("all")}
                title="Reset the drawer to all competitor markets"
                type="button"
              >
                All markets
              </button>
              <button
                className={styles.btn}
                onClick={() => setCompetitorMarketDetail(null)}
                title="Close this market drill-down drawer"
                type="button"
              >
                Reset view
              </button>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadCompetitorCsv(
                    competitorMarketDetailPairRows,
                    radius,
                    "proximity-competitor-white-space-markets.csv",
                  )
                }
                title="Download competitor market rows as CSV"
                type="button"
              >
                CSV
              </button>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadCompetitorJson(
                    competitorMarketDetailPairRows,
                    radius,
                    "proximity-competitor-white-space-markets.json",
                  )
                }
                title="Download competitor market rows as JSON"
                type="button"
              >
                JSON
              </button>
            </div>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Market</th>
                    <th>Competitor #</th>
                    <th>Competitor location</th>
                    <th>Nearest Walmart #</th>
                    <th>Nearest Walmart location</th>
                    <th>Distance to Walmart</th>
                    <th>Walmart ≤ {radius} mi</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleCompetitorMarketDetailPairRows.map((pair) => (
                    <tr key={pair.competitor.id}>
                      <td>
                        {pair.competitor.city || "Unknown city"},{" "}
                        {pair.competitor.state || "Unknown"}
                      </td>
                      <td>{pair.competitor.store_number}</td>
                      <td>{locationLabel(pair.competitor)}</td>
                      <td>{pair.nearest_walmart.store_number}</td>
                      <td>{locationLabel(pair.nearest_walmart)}</td>
                      <td>{miles(pair.distance_miles)}</td>
                      <td>{pair.distance_miles <= radius ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : null}

      {showTable ? (
        <div
          className={styles.drawerBackdrop}
          onClick={() => setShowTable(false)}
          role="presentation"
        >
          <section
            aria-label="Location table"
            className={`${styles.drawer} ${styles.tableDrawer}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.drawerHead}>
              <div>
                <span>Downloadable evidence</span>
                <h2>All visible Walmart-to-competitor pairs</h2>
                <p>
                  {count(filteredPairs.length)} rows; the table, map, KPIs, and
                  exports reconcile to the same filtered set.
                </p>
              </div>
              <button
                onClick={() => setShowTable(false)}
                title="Close location table"
                type="button"
              >
                ×
              </button>
            </div>
            <div className={styles.tableSummary}>
              <article>
                <span>Total Walmart stores</span>
                <strong>{count(view?.benchmark.location_count ?? 0)}</strong>
              </article>
              <article>
                <span>Covered ≤ {radius} mi</span>
                <strong>
                  {count(selectedCoverage?.within ?? filteredWithin)}
                </strong>
              </article>
              <article>
                <span>White-space &gt; {radius} mi</span>
                <strong>
                  {count(selectedCoverage?.outside ?? filteredOutside)}
                </strong>
              </article>
              <article>
                <span>Coverage rate</span>
                <strong>
                  {percent(selectedCoverage?.share ?? visibleShare)}
                </strong>
              </article>
            </div>
            <div className={styles.downloadRow}>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadCsv(filteredPairs, radius, "proximity-filtered.csv")
                }
                title="Download visible rows as CSV"
                type="button"
              >
                CSV
              </button>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadCsv(
                    filteredPairs,
                    radius,
                    "proximity-filtered-excel.csv",
                  )
                }
                title="Download visible rows as an Excel-compatible CSV"
                type="button"
              >
                Excel CSV
              </button>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadJson(filteredPairs, radius, "proximity-filtered.json")
                }
                title="Download visible rows as JSON"
                type="button"
              >
                JSON
              </button>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadGeoJson(
                    filteredPairs,
                    radius,
                    "proximity-filtered.geojson",
                  )
                }
                title="Download visible rows as GeoJSON"
                type="button"
              >
                GeoJSON
              </button>
            </div>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Walmart #</th>
                    <th>Walmart location</th>
                    <th>Competitor #</th>
                    <th>Competitor location</th>
                    <th>Distance</th>
                    <th>≤ {radius} mi</th>
                    <th>Walmart coordinate</th>
                    <th>Competitor coordinate</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPairs.map((pair) => (
                    <tr key={pairKey(pair)}>
                      <td>{pair.benchmark.store_number}</td>
                      <td>{locationLabel(pair.benchmark)}</td>
                      <td>{pair.competitor.store_number}</td>
                      <td>{locationLabel(pair.competitor)}</td>
                      <td>{miles(pair.distance_miles)}</td>
                      <td>{pair.distance_miles <= radius ? "Yes" : "No"}</td>
                      <td>
                        {pair.benchmark.latitude.toFixed(5)},{" "}
                        {pair.benchmark.longitude.toFixed(5)}
                      </td>
                      <td>
                        {pair.competitor.latitude.toFixed(5)},{" "}
                        {pair.competitor.longitude.toFixed(5)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : null}

      {modal ? (
        <InfoModal
          competitorGapLocations={competitorGapLocations}
          competitorGapShare={competitorGapShare}
          comparisonScopeLabel={comparisonScopeLabel}
          competitorFootprintLabel={competitorFootprintLabel}
          competitorPairCount={competitorPerspectivePairs.length}
          competitorWithinLocations={competitorWithinLocations}
          distanceSummary={distanceSummary}
          isCompetitorFootprintScope={isCompetitorFootprintScope}
          modal={modal}
          radius={radius}
          scopeMedian={scopeMedian}
          scopedPairs={scopedPairs}
          selectedCoverage={selectedCoverage}
          setModal={setModal}
          totalWalmartLocations={totalWalmartLocations}
          view={view}
        />
      ) : null}
    </div>
  );
}

function StaticProximityMap({
  onSelect,
  radius,
  selectedPair,
  selectedNetworkPairs,
  showCompetitors,
  showLinks,
  showRings,
  showWalmart,
  summary,
}: Readonly<{
  country: string;
  onSelect: (key: string) => void;
  radius: number;
  selectedPair: ProximityPair | null;
  selectedNetworkPairs: ProximityPair[];
  showCompetitors: boolean;
  showLinks: boolean;
  showRings: boolean;
  showWalmart: boolean;
  summary: ProximityMapSummary;
}>) {
  const bounds =
    summary.bounds ??
    ({
      max_latitude: 50,
      max_longitude: -66,
      min_latitude: 24,
      min_longitude: -125,
    } satisfies MapBounds);
  const selectedStart = selectedPair
    ? projectToMap(
        selectedPair.benchmark.latitude,
        selectedPair.benchmark.longitude,
        bounds,
      )
    : null;
  const selectedEnd = selectedPair
    ? projectToMap(
        selectedPair.competitor.latitude,
        selectedPair.competitor.longitude,
        bounds,
      )
    : null;
  const selectedRing = radiusEllipse(selectedPair, radius, bounds);
  const selectedNetwork = selectedNetworkPairs.slice(0, 220).map((pair) => ({
    end: projectToMap(
      pair.competitor.latitude,
      pair.competitor.longitude,
      bounds,
    ),
    key: pairKey(pair),
    pair,
    start: projectToMap(
      pair.benchmark.latitude,
      pair.benchmark.longitude,
      bounds,
    ),
  }));
  const renderCluster = (
    cluster: ProximityMapCluster,
    className: string,
    index: number,
  ) => {
    const point = projectToMap(cluster.latitude, cluster.longitude, bounds);
    const radius = Math.min(
      34,
      Math.max(6, 5 + Math.sqrt(cluster.location_count) * 2.2),
    );
    const title = `${cluster.label}: ${count(cluster.location_count)} ${cluster.role} location${cluster.location_count === 1 ? "" : "s"}; ${count(cluster.covered_locations)} covered and ${count(cluster.gap_locations)} gaps at the selected radius.`;
    const key = cluster.representative_pair_key;
    return (
      <g
        aria-label={title}
        className={`${styles.staticCluster} ${className}`}
        key={`${cluster.role}-${index}-${cluster.latitude}-${cluster.longitude}`}
        onClick={() => {
          if (key) onSelect(key);
        }}
        onKeyDown={(event) => {
          if (key && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            onSelect(key);
          }
        }}
        role={key ? "button" : "img"}
        tabIndex={key ? 0 : -1}
      >
        <title>{title}</title>
        <circle cx={point.x} cy={point.y} r={radius} />
        {cluster.location_count >= 3 ? (
          <text x={point.x} y={point.y + 3}>
            {cluster.location_count > 999
              ? `${Math.round(cluster.location_count / 100) / 10}k`
              : cluster.location_count}
          </text>
        ) : null}
      </g>
    );
  };
  return (
    <svg
      aria-label="Fast source-backed proximity cluster map"
      className={styles.staticMap}
      role="img"
      viewBox="0 0 1000 610"
    >
      <defs>
        <radialGradient id="proximity-static-glow" cx="50%" cy="50%" r="65%">
          <stop offset="0%" stopColor="rgba(58, 140, 172, 0.34)" />
          <stop offset="62%" stopColor="rgba(30, 72, 92, 0.24)" />
          <stop offset="100%" stopColor="rgba(12, 26, 36, 0.06)" />
        </radialGradient>
      </defs>
      <rect className={styles.staticWater} height="610" width="1000" />
      <rect fill="url(#proximity-static-glow)" height="610" width="1000" />
      <g className={styles.staticGrid}>
        {Array.from({ length: 12 }).map((_, index) => (
          <line
            key={`v-${index}`}
            x1={80 + index * 74}
            x2={80 + index * 74}
            y1="40"
            y2="570"
          />
        ))}
        {Array.from({ length: 7 }).map((_, index) => (
          <line
            key={`h-${index}`}
            x1="40"
            x2="960"
            y1={70 + index * 78}
            y2={70 + index * 78}
          />
        ))}
      </g>
      <text className={styles.staticLandLabel} x="500" y="315">
        LOCATION MASTER NETWORK
      </text>
      {showRings && selectedRing ? (
        <ellipse
          className={styles.staticRadiusRing}
          cx={selectedRing.cx}
          cy={selectedRing.cy}
          rx={selectedRing.rx}
          ry={selectedRing.ry}
        >
          <title>
            Selected {radius} mile radius around{" "}
            {selectedPair?.competitor.retailer_display_name ?? "competitor"} #
            {selectedPair?.competitor.store_number ?? ""}
          </title>
        </ellipse>
      ) : null}
      {showLinks && selectedNetwork.length ? (
        <g className={styles.staticNetworkLayer}>
          <title>
            {count(selectedNetwork.length)} Walmart assignment
            {selectedNetwork.length === 1 ? "" : "s"} to the selected competitor
            site.
          </title>
          {selectedNetwork.map(({ end, key, pair, start }) => (
            <line
              className={
                pair.distance_miles <= radius
                  ? styles.staticNetworkLine
                  : styles.staticNetworkLineOut
              }
              key={key}
              x1={start.x}
              x2={end.x}
              y1={start.y}
              y2={end.y}
            />
          ))}
        </g>
      ) : null}
      {showCompetitors
        ? summary.competitor_clusters
            .slice(0, 160)
            .map((cluster, index) =>
              renderCluster(cluster, styles.staticCompetitor, index),
            )
        : null}
      {showWalmart
        ? summary.walmart_clusters
            .slice(0, 180)
            .map((cluster, index) =>
              renderCluster(cluster, styles.staticWalmart, index),
            )
        : null}
      {showLinks && selectedNetwork.length ? (
        <g className={styles.staticNetworkPoints}>
          {selectedNetwork.map(({ key, pair, start }) => (
            <circle
              className={
                pair.distance_miles <= radius
                  ? styles.staticNetworkPoint
                  : styles.staticNetworkPointOut
              }
              key={`${key}-walmart`}
              cx={start.x}
              cy={start.y}
              r={
                selectedPair && pairKey(pair) === pairKey(selectedPair)
                  ? 4.6
                  : 3.4
              }
            >
              <title>
                Walmart #{pair.benchmark.store_number} is{" "}
                {miles(pair.distance_miles)} from{" "}
                {pair.competitor.retailer_display_name} #
                {pair.competitor.store_number}.
              </title>
            </circle>
          ))}
          {selectedEnd ? (
            <rect
              className={styles.staticSelectedCompetitor}
              height="13"
              rx="3"
              width="13"
              x={selectedEnd.x - 6.5}
              y={selectedEnd.y - 6.5}
            >
              <title>
                Selected {selectedPair?.competitor.retailer_display_name} #
                {selectedPair?.competitor.store_number}
              </title>
            </rect>
          ) : null}
          {selectedStart && selectedEnd ? (
            <line
              className={styles.staticSelectedLine}
              x1={selectedStart.x}
              x2={selectedEnd.x}
              y1={selectedStart.y}
              y2={selectedEnd.y}
            />
          ) : null}
        </g>
      ) : null}
    </svg>
  );
}

function MetricCard({
  description,
  icon,
  iconClass,
  label,
  onInfo,
  title,
  value,
}: Readonly<{
  description: string;
  icon: string;
  iconClass: string;
  label: string;
  onInfo: () => void;
  title: string;
  value: string;
}>) {
  return (
    <article className={styles.kpi}>
      <div>
        <span className={styles.metricTitle}>
          {label}
          <button onClick={onInfo} title={title} type="button">
            i
          </button>
        </span>
        <strong>{value}</strong>
        <small>{description}</small>
      </div>
      <b className={`${styles.kpiIcon} ${iconClass}`}>{icon}</b>
    </article>
  );
}

function InfoModal({
  competitorGapLocations,
  competitorGapShare,
  comparisonScopeLabel,
  competitorFootprintLabel,
  competitorPairCount,
  competitorWithinLocations,
  distanceSummary,
  isCompetitorFootprintScope,
  modal,
  radius,
  scopeMedian,
  scopedPairs,
  selectedCoverage,
  setModal,
  totalWalmartLocations,
  view,
}: Readonly<{
  competitorGapLocations: number;
  competitorGapShare: number | null;
  comparisonScopeLabel: string;
  competitorFootprintLabel: string;
  competitorPairCount: number;
  competitorWithinLocations: number;
  distanceSummary: ProximityDistanceSummary;
  isCompetitorFootprintScope: boolean;
  modal: Exclude<ModalKind, null>;
  radius: number;
  scopeMedian: number | null;
  scopedPairs: ProximityPair[];
  selectedCoverage:
    | {
        label: string;
        miles: number;
        outside: number;
        share: number | null;
        within: number;
      }
    | undefined;
  setModal: (modal: ModalKind) => void;
  totalWalmartLocations: number;
  view: ProximityView | null;
}>) {
  const title =
    modal === "method"
      ? "How this proximity view is calculated"
      : modal === "shortlist"
        ? "Shortlisted retailer relationships"
        : modal === "notes"
          ? "How to use this page"
          : modal === "metric-scope"
            ? "Comparison scope"
            : modal === "metric-total"
              ? isCompetitorFootprintScope
                ? "Walmart stores in competitor footprint"
                : "Total Walmart stores"
              : modal === "metric-coverage"
                ? `Coverage within ${radius} mile${radius === 1 ? "" : "s"}`
                : modal === "metric-gap"
                  ? `White-space stores beyond ${radius} mile${radius === 1 ? "" : "s"}`
                  : modal === "metric-competitor-whitespace"
                    ? `Competitor sites beyond ${radius} mile${radius === 1 ? "" : "s"}`
                    : modal === "metric-market"
                      ? "Competitor white-space markets"
                      : modal === "metric-pressure"
                        ? "Walmart competitive pressure states"
                        : modal === "metric-distance"
                          ? "Distance profile"
                          : "Nearest competitor sites represented";
  const eyebrow = modal.startsWith("metric-")
    ? "Metric definition"
    : modal === "method"
      ? "Data method"
      : modal === "shortlist"
        ? "Saved relationships"
        : "Workspace notes";

  return (
    <div
      className={styles.drawerBackdrop}
      onClick={() => setModal(null)}
      role="presentation"
    >
      <section
        aria-modal="true"
        className={styles.modal}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className={styles.drawerHead}>
          <div>
            <span>{eyebrow}</span>
            <h2>{title}</h2>
          </div>
          <button
            onClick={() => setModal(null)}
            title="Close explanation"
            type="button"
          >
            ×
          </button>
        </div>

        {modal === "method" ? (
          <div className={styles.modalBody}>
            <p>
              Each row starts with a Walmart US or CA location from the location
              master and pairs it to the nearest selected competitor location
              with valid latitude and longitude.
            </p>
            <p>
              The map base is OpenFreeMap using OpenMapTiles and OpenStreetMap
              contributors. Distances are Haversine straight-line miles, useful
              for footprint and white-space analysis, but not drive time,
              traffic-aware distance, inventory, item distribution, or store
              operating status.
            </p>
            <p>
              Filters apply to the same row set used by metric cards, map
              layers, table rows, and downloads. Current median nearest distance
              is {miles(scopeMedian)} across {count(scopedPairs.length)} paired
              Walmart locations.
            </p>
          </div>
        ) : null}

        {modal === "metric-scope" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> the denominator used for Walmart-side
              coverage and white-space metrics on this page.
            </p>
            <p>
              <b>All Walmart</b> uses every paired Walmart location in the
              selected country. <b>Competitor footprint</b> uses only Walmart
              locations in states/provinces where the selected competitor has
              mappable locations in the location master.
            </p>
            <p>
              Current scope: {comparisonScopeLabel}. This keeps regional
              retailers like H-E-B from being evaluated against Walmart stores
              in states where that competitor has no sourced location footprint.
            </p>
          </div>
        ) : null}

        {modal === "metric-total" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b>{" "}
              {isCompetitorFootprintScope
                ? `Walmart locations in ${competitorFootprintLabel}, because the selected competitor is being evaluated in its sourced footprint.`
                : "all Walmart locations for the selected country in the location master, before state, relationship, search, or shortlist filters."}
            </p>
            <p>
              <b>Calculation:</b>{" "}
              {isCompetitorFootprintScope
                ? "paired Walmart rows where Walmart state/province is also present in the selected competitor’s mappable location states/provinces."
                : "`benchmark.location_count` from the Proximity API. The supporting line also shows how many Walmart locations have valid coordinates and how many were successfully paired to the selected competitor."}
            </p>
            <p>
              Current value: {count(scopedPairs.length)} in the active scope;{" "}
              {count(totalWalmartLocations)} total{" "}
              {view?.benchmark.display_name ?? "Walmart"} locations in the
              selected country.
            </p>
          </div>
        ) : null}

        {modal === "metric-coverage" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> the share of paired Walmart locations
              whose nearest selected competitor location is within the selected
              radius.
            </p>
            <p>
              <b>Calculation:</b> Walmart paired locations with
              `nearest_distance_miles ≤ selected_radius_miles` divided by all
              paired Walmart locations in the active state/search/shortlist
              scope. The covered/gap view toggle does not change this
              denominator.
            </p>
            <p>
              Current value: {count(selectedCoverage?.within ?? 0)} of{" "}
              {count(scopedPairs.length)} ={" "}
              {percent(selectedCoverage?.share ?? null)}.
            </p>
          </div>
        ) : null}

        {modal === "metric-gap" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> paired Walmart locations whose nearest
              selected competitor is farther away than the selected radius.
            </p>
            <p>
              <b>Calculation:</b> paired Walmart locations minus covered Walmart
              locations for the selected radius and active filters.
            </p>
            <p>
              Current value: {count(selectedCoverage?.outside ?? 0)} locations,
              or{" "}
              {percent(
                scopedPairs.length
                  ? (selectedCoverage?.outside ?? 0) / scopedPairs.length
                  : null,
              )}{" "}
              of paired Walmart locations.
            </p>
          </div>
        ) : null}

        {modal === "metric-competitor-whitespace" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> selected competitor locations whose
              nearest Walmart is farther away than the selected radius.
            </p>
            <p>
              <b>Why this matters:</b> it flips the perspective from
              Walmart-centered coverage to competitor-centered white space,
              highlighting markets where the competitor has a physical footprint
              but no Walmart location inside the selected proximity radius.
            </p>
            <p>
              <b>Calculation:</b> every mappable{" "}
              {view?.competitor.display_name ?? "competitor"} location is paired
              to its nearest mappable Walmart location. Locations with
              `nearest_walmart_distance_miles &gt; selected_radius_miles` are
              counted as competitor white-space sites.
            </p>
            <p>
              Current value: {count(competitorGapLocations)} white-space sites;{" "}
              {count(competitorWithinLocations)} near Walmart;{" "}
              {count(competitorPairCount)} competitor sites total;{" "}
              {percent(competitorGapShare)} white-space.
            </p>
          </div>
        ) : null}

        {modal === "metric-market" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> city/state markets where the selected
              competitor has mappable locations whose nearest Walmart is farther
              away than the selected radius.
            </p>
            <p>
              <b>Calculation:</b> group competitor-to-nearest-Walmart rows by
              competitor city and state, then count competitor locations with
              `nearest_walmart_distance_miles &gt; selected_radius_miles`.
            </p>
            <p>
              <b>How to use it:</b> this is the best current location-master
              view for competitor footprint where Walmart has weaker immediate
              physical adjacency. It is still straight-line proximity, not drive
              time, assortment, demand, or sales.
            </p>
          </div>
        ) : null}

        {modal === "metric-pressure" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> states where Walmart stores are most
              likely to have the selected competitor nearby at the active
              radius.
            </p>
            <p>
              <b>Calculation:</b> Walmart stores whose nearest selected
              competitor is within the selected radius divided by all paired
              Walmart stores in that state and active filter scope.
            </p>
            <p>
              <b>How to use it:</b> high-pressure states are useful for
              merchant, broker, and supplier teams evaluating where pricing,
              merchandising, distribution, and local competitive readouts may
              deserve extra attention.
            </p>
          </div>
        ) : null}

        {modal === "metric-distance" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> the distribution of nearest selected
              competitor distances for the active Walmart scope.
            </p>
            <p>
              <b>Calculation:</b> sort active Walmart-to-nearest-competitor pair
              rows by `nearest_distance_miles`, then report the median, 75th
              percentile, 90th percentile, and maximum straight-line Haversine
              distance.
            </p>
            <p>
              Current values: median {miles(distanceSummary.median_miles)}, P75{" "}
              {miles(distanceSummary.p75_miles)}, P90{" "}
              {miles(distanceSummary.p90_miles)}, max{" "}
              {miles(distanceSummary.max_miles)}.
            </p>
          </div>
        ) : null}

        {modal === "notes" ? (
          <div className={styles.modalBody}>
            <p>
              Start with the 1-mile default to understand immediate competitive
              adjacency, then use 3, 5, and 10 miles to distinguish
              neighborhood, trade-area, and broader market proximity.
            </p>
            <p>
              Suggested workflow: choose one competitor, review coverage by
              radius, toggle between covered and white-space stores, inspect a
              selected relationship, and export CSV/JSON/GeoJSON for downstream
              analysis.
            </p>
          </div>
        ) : null}

        {modal === "shortlist" ? (
          <div className={styles.modalBody}>
            <p>
              Shortlisted relationships are stored in this browser for the
              selected Walmart market and competitor.
            </p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
