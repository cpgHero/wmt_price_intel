"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useApplicationContextActions } from "@/app/components/application-context";
import type { LocationRetailer, ProximityPair, ProximityView } from "@/lib/api";

import styles from "./proximity-workspace.module.css";

const RADIUS_OPTIONS = [1, 3, 5, 10] as const;
const DEFAULT_RADIUS_MILES = 1;
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
  | "metric-total"
  | "metric-coverage"
  | "metric-gap"
  | "metric-competitor"
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

function downloadCsv(
  rows: ProximityPair[],
  selectedRadius: number,
  filename: string,
) {
  const records = filteredRowsToRecords(rows, selectedRadius);
  const columns = records.length ? Object.keys(records[0]!) : [];
  const body = [
    columns.map(csvCell).join(","),
    ...records.map((record) =>
      columns
        .map((column) => csvCell(record[column as keyof typeof record]))
        .join(","),
    ),
  ].join("\r\n");
  download(filename, "text/csv;charset=utf-8", `\uFEFF${body}`);
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
  const latitude = (pair.benchmark.latitude * Math.PI) / 180;
  const longitude = (pair.benchmark.longitude * Math.PI) / 180;
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
        role: "selected_radius",
      },
      type: "Feature",
    },
  ]);
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
  const [onlySaved, setOnlySaved] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => initialTheme());
  const [modal, setModal] = useState<ModalKind>(null);
  const [mapReady, setMapReady] = useState(false);
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
      const selectedCompetitor =
        next.competitorRetailerId ||
        availableCompetitors(nextRetailers, nextCountry)[0]?.id ||
        "";
      const selectedRadius = next.radius ?? radius;
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
      setView(body);
      setSelectedKey(body.pairs?.[0] ? pairKey(body.pairs[0]) : null);
      setStateFilter("all");
      setRelation("all");
      setSort("nearest");
      setOnlySaved(false);
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

  const scopedPairs = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return (view?.pairs ?? [])
      .filter((pair) => {
        if (onlySaved && !savedKeys.has(pairKey(pair))) return false;
        if (stateFilter !== "all" && pair.benchmark.state !== stateFilter) {
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
  }, [onlySaved, query, savedKeys, sort, stateFilter, view?.pairs]);

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
  const competitorPoints = useMemo(
    () => uniqueByLocation(scopedPairs, (pair) => pair.competitor),
    [scopedPairs],
  );
  const visibleCompetitorSites = competitorPoints.length;
  const stateOptions = view?.state_options ?? [];
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
        filteredPairs
          .slice(0, 3000)
          .map((pair) => relationshipFeature(pair, radius)),
      ),
    [filteredPairs, radius],
  );
  const selectedRadiusFeatures = useMemo(
    () =>
      selectedRadiusFeature(showRings ? selectedCoveragePair : null, radius),
    [radius, selectedCoveragePair, showRings],
  );
  const selectedPeers = selectedPair
    ? filteredPairs
        .filter(
          (pair) =>
            pair.competitor.id === selectedPair.competitor.id &&
            pair.benchmark.id !== selectedPair.benchmark.id,
        )
        .slice(0, 4)
    : [];

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
    window.setTimeout(() => {
      map.resize();
      fitToPairs(map, filteredPairs, country);
    }, 0);
  }, [
    competitorPointFeatures,
    country,
    filteredPairs,
    mapReady,
    relationshipFeatures,
    selectedRadiusFeatures,
    showCompetitors,
    showLinks,
    showRings,
    showWalmart,
    walmartPointFeatures,
  ]);

  function resetView() {
    setQuery("");
    setStateFilter("all");
    setRelation("all");
    setSort("nearest");
    setOnlySaved(false);
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
          description={
            view
              ? `${count(view.benchmark.mappable_location_count)} mappable; ${count(view.summary.paired_locations)} paired to a nearest ${view.competitor.display_name} site`
              : "No comparison loaded"
          }
          icon="W"
          iconClass={styles.blue}
          label="Total Walmart stores"
          onInfo={() => setModal("metric-total")}
          title="Open total Walmart stores definition"
          value={count(view?.benchmark.location_count ?? scopedPairs.length)}
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
          description={
            view
              ? `${count(visibleCompetitorSites)} of ${count(view.summary.competitor_mappable_locations)} mappable ${view.competitor.display_name} sites are nearest to ≥1 Walmart`
              : "Select a competitor"
          }
          icon="C"
          iconClass={styles.red}
          label="Nearest competitor sites"
          onInfo={() => setModal("metric-competitor")}
          title="Open nearest competitor sites definition"
          value={count(visibleCompetitorSites)}
        />
      </section>

      <section className={styles.explorer}>
        <section className={styles.mapSection} aria-label="Proximity map">
          <div className={styles.mapArea}>
            <div className={styles.tileMap} ref={mapContainerRef} />
            {!mapReady ? (
              <div className={styles.mapBusy}>Loading OpenFreeMap tiles…</div>
            ) : null}
            {mapError ? (
              <div className={`${styles.mapBusy} ${styles.warning}`}>
                {mapError}
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
              </div>
              <div className={styles.mapTools}>
                <button
                  className={styles.mapToolButton}
                  onClick={() => setShowFilters(true)}
                  title="Open retailer, radius, filters, and map layers"
                  type="button"
                >
                  Controls
                </button>
                <button
                  className={styles.iconButton}
                  onClick={() => {
                    if (mapRef.current) {
                      fitToPairs(mapRef.current, filteredPairs, country);
                    }
                  }}
                  title="Fit visible network"
                  type="button"
                >
                  ⤢
                </button>
                <button
                  className={styles.iconButton}
                  onClick={() =>
                    void mapContainerRef.current?.requestFullscreen()
                  }
                  title="Fullscreen map"
                  type="button"
                >
                  ⛶
                </button>
                <button
                  className={styles.iconButton}
                  onClick={() => setShowFilters(true)}
                  title="Open controls and filters"
                  type="button"
                >
                  ⚙
                </button>
                <button
                  className={styles.iconButton}
                  onClick={() => setShowTable(true)}
                  title="Open full location table"
                  type="button"
                >
                  ⇩
                </button>
              </div>
            </div>
            <div className={styles.legend}>
              <span>
                <i className={styles.walmartDot} />
                Walmart
              </span>
              <span>
                <i className={styles.competitorDot} />
                Competitor
              </span>
              <span>
                <i className={styles.coveredLineLegend} />
                within radius
              </span>
              <span>
                <i className={styles.gapLineLegend} />
                outside radius
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
            <div
              className={styles.mapCoverageCard}
              aria-label="Walmart coverage by selected competitor radius"
            >
              <div className={styles.coverageHead}>
                <h2>Coverage by radius</h2>
                <button
                  onClick={() => setShowTable(true)}
                  title="Open the downloadable location table"
                  type="button"
                >
                  Store details
                </button>
              </div>
              <p>
                Percent of paired Walmart locations whose nearest{" "}
                {view?.competitor.display_name ?? "competitor"} is within each
                straight-line radius.
              </p>
              <div className={styles.mapCoverageRows}>
                {coverageBands.map((band) => (
                  <button
                    aria-pressed={radius === band.miles}
                    className={styles.mapCoverageRow}
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
            </div>
            {selectedPair ? (
              <button
                className={styles.selectionToast}
                onClick={() => setShowSelectedDetail(true)}
                title="Open selected Walmart-to-competitor relationship details"
                type="button"
              >
                <span>Selected relationship</span>
                <strong>{miles(selectedPair.distance_miles)}</strong>
                <small>
                  Walmart #{selectedPair.benchmark.store_number} →{" "}
                  {selectedPair.competitor.retailer_display_name} #
                  {selectedPair.competitor.store_number}
                </small>
              </button>
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
                    onClick={() => setSelectedKey(pairKey(pair))}
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
                value={stateFilter}
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
          modal={modal}
          radius={radius}
          scopeMedian={scopeMedian}
          scopedPairs={scopedPairs}
          selectedCoverage={selectedCoverage}
          setModal={setModal}
          view={view}
          visibleCompetitorSites={visibleCompetitorSites}
        />
      ) : null}
    </div>
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
  modal,
  radius,
  scopeMedian,
  scopedPairs,
  selectedCoverage,
  setModal,
  view,
  visibleCompetitorSites,
}: Readonly<{
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
  view: ProximityView | null;
  visibleCompetitorSites: number;
}>) {
  const title =
    modal === "method"
      ? "How this proximity view is calculated"
      : modal === "shortlist"
        ? "Shortlisted retailer relationships"
        : modal === "notes"
          ? "How to use this page"
          : modal === "metric-total"
            ? "Total Walmart stores"
            : modal === "metric-coverage"
              ? `Coverage within ${radius} mile${radius === 1 ? "" : "s"}`
              : modal === "metric-gap"
                ? `White-space stores beyond ${radius} mile${radius === 1 ? "" : "s"}`
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

        {modal === "metric-total" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> all Walmart locations for the selected
              country in the location master, before state, relationship,
              search, or shortlist filters.
            </p>
            <p>
              <b>Calculation:</b> `benchmark.location_count` from the Proximity
              API. The supporting line also shows how many Walmart locations
              have valid coordinates and how many were successfully paired to
              the selected competitor.
            </p>
            <p>
              Current value: {count(view?.benchmark.location_count ?? 0)} total;{" "}
              {count(view?.benchmark.mappable_location_count ?? 0)} mappable;{" "}
              {count(view?.summary.paired_locations ?? 0)} paired.
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

        {modal === "metric-competitor" ? (
          <div className={styles.modalBody}>
            <p>
              <b>What it represents:</b> selected competitor locations that are
              actually represented in nearest-neighbor pairings.
            </p>
            <p>
              <b>Why it can be lower than total competitor sites:</b> the data
              is Walmart-centered. Every paired Walmart location contributes one
              nearest competitor. Competitor locations that are not the nearest
              selected-competitor site for any Walmart remain valid mappable
              locations, but they are not represented in the nearest-site pair
              list.
            </p>
            <p>
              Current value: {count(visibleCompetitorSites)} represented of{" "}
              {count(view?.summary.competitor_mappable_locations ?? 0)} mappable{" "}
              {view?.competitor.display_name ?? "competitor"} sites.
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
