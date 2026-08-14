"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { PriceMonitoringMap, PriceMonitoringView } from "@/lib/api";

import styles from "./evidence-retail-map.module.css";

type MapPoint = PriceMonitoringMap["points"][number];
type MapMode = "observed" | "not_observed";
type MapDetail = "summary" | "full";
type QueryUpdate = Record<string, string | null>;

interface MapMouseEvent {
  point: { x: number; y: number };
}

interface RenderedMapFeature {
  geometry?: { coordinates?: unknown };
  properties?: Record<string, unknown>;
}

interface GeoJsonSource {
  getClusterExpansionZoom(clusterId: number): Promise<number>;
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
  on(event: string, callback: () => void): void;
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
  setLayoutProperty(layerId: string, name: string, value: unknown): void;
}

interface MapLibrary {
  Map: new (options: Record<string, unknown>) => InteractiveMap;
  NavigationControl: new (options?: Record<string, unknown>) => unknown;
  ScaleControl: new (options?: Record<string, unknown>) => unknown;
}

declare global {
  interface Window {
    maplibregl?: MapLibrary;
  }
}

const MAPLIBRE_VERSION = "5.24.0";
const MAPLIBRE_SCRIPT = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.js`;
const MAPLIBRE_STYLES = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.css`;
const OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
// Keep nationwide views legible while exposing individual stores by metro-level
// zoom. The previous zoom 11 / 42 px settings kept nearby stores clustered until
// users were effectively at neighborhood scale.
const EVIDENCE_CLUSTER_MAX_ZOOM = 8;
const EVIDENCE_CLUSTER_RADIUS = 26;
const OBSERVED_SOURCE = "price-observed-locations";
const GAP_SOURCE = "price-not-observed-locations";

let mapLibraryPromise: Promise<MapLibrary> | null = null;

function loadMapLibrary() {
  if (window.maplibregl) return Promise.resolve(window.maplibregl);
  if (mapLibraryPromise) return mapLibraryPromise;
  mapLibraryPromise = new Promise<MapLibrary>((resolve, reject) => {
    if (!document.getElementById("rci-maplibre-styles")) {
      const stylesheet = document.createElement("link");
      stylesheet.crossOrigin = "anonymous";
      stylesheet.href = MAPLIBRE_STYLES;
      stylesheet.id = "rci-maplibre-styles";
      stylesheet.rel = "stylesheet";
      document.head.append(stylesheet);
    }

    const existing = document.getElementById(
      "rci-maplibre-script",
    ) as HTMLScriptElement | null;
    const script = existing ?? document.createElement("script");
    const handleLoad = () => {
      if (window.maplibregl) resolve(window.maplibregl);
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
      document.head.append(script);
    }
  });
  return mapLibraryPromise;
}

function currency(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

function signedCurrency(value: number | null) {
  if (value === null) return "—";
  const formatted = currency(Math.abs(value));
  if (Math.abs(value) < 0.005) return formatted;
  return `${value > 0 ? "+" : "−"}${formatted}`;
}

function count(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function pointPosition(point: MapPoint) {
  if (point.status === "not_observed") return "not_observed";
  const difference = point.difference_from_reference ?? 0;
  if (difference < -0.005) return "below";
  if (difference > 0.005) return "above";
  return "at";
}

function toFeatureCollection(points: MapPoint[]) {
  return {
    type: "FeatureCollection",
    features: points.map((point) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [point.longitude, point.latitude],
      },
      properties: {
        scope_key: point.scope_key,
        status: point.status,
        position: pointPosition(point),
        price_label: point.price === null ? "" : currency(point.price),
      },
    })),
  };
}

function fitToPoints(
  map: InteractiveMap,
  points: MapPoint[],
  detail: MapDetail,
) {
  if (!points.length) return;
  const longitudes = points.map((point) => point.longitude);
  const latitudes = points.map((point) => point.latitude);
  const bounds: [[number, number], [number, number]] = [
    [Math.min(...longitudes), Math.min(...latitudes)],
    [Math.max(...longitudes), Math.max(...latitudes)],
  ];
  if (bounds[0][0] === bounds[1][0] && bounds[0][1] === bounds[1][1]) {
    map.easeTo({ center: bounds[0], zoom: 13, duration: 0 });
    return;
  }
  map.fitBounds(bounds, {
    padding: detail === "summary" ? 38 : 54,
    maxZoom: 13,
    duration: 0,
  });
}

function addEvidenceLayers(
  map: InteractiveMap,
  sourceId: string,
  prefix: string,
  mode: MapMode,
) {
  const isObserved = mode === "observed";
  map.addLayer({
    id: `${prefix}-clusters`,
    type: "circle",
    source: sourceId,
    filter: ["has", "point_count"],
    paint: {
      "circle-color": isObserved
        ? [
            "step",
            ["get", "point_count"],
            "#0b7b92",
            100,
            "#075f73",
            750,
            "#143b47",
          ]
        : [
            "step",
            ["get", "point_count"],
            "#f4b740",
            100,
            "#d99016",
            750,
            "#9a5b0b",
          ],
      "circle-radius": ["step", ["get", "point_count"], 16, 100, 21, 750, 27],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
      "circle-opacity": 0.92,
    },
  });
  map.addLayer({
    id: `${prefix}-cluster-count`,
    type: "symbol",
    source: sourceId,
    filter: ["has", "point_count"],
    layout: {
      "text-field": ["get", "point_count_abbreviated"],
      "text-font": ["Noto Sans Bold"],
      "text-size": 12,
    },
    paint: { "text-color": "#ffffff" },
  });
  map.addLayer({
    id: `${prefix}-points`,
    type: "circle",
    source: sourceId,
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-color": isObserved
        ? [
            "match",
            ["get", "position"],
            "below",
            "#087da1",
            "above",
            "#db7512",
            "#26383f",
          ]
        : "#f5b642",
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 4, 9, 6, 14, 9],
      "circle-stroke-color": isObserved ? "#ffffff" : "#4a3a16",
      "circle-stroke-width": 1.5,
      "circle-opacity": 0.9,
    },
  });
  if (isObserved) {
    map.addLayer({
      id: `${prefix}-price-labels`,
      type: "symbol",
      source: sourceId,
      minzoom: 10,
      filter: ["!", ["has", "point_count"]],
      layout: {
        "text-field": ["get", "price_label"],
        "text-font": ["Noto Sans Bold"],
        "text-size": 11,
        "text-offset": [0, 1.35],
        "text-anchor": "top",
      },
      paint: {
        "text-color": "#14282f",
        "text-halo-color": "#ffffff",
        "text-halo-width": 2,
      },
    });
  }
}

export function EvidenceRetailMap({
  view,
  detail = "full",
  onScopeChange,
}: Readonly<{
  view: PriceMonitoringView;
  detail?: MapDetail;
  onScopeChange: (parameters: QueryUpdate) => void;
}>) {
  const [mode, setMode] = useState<MapMode>("observed");
  const [mapData, setMapData] = useState<PriceMonitoringMap | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState<MapPoint | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<InteractiveMap | null>(null);

  useEffect(() => {
    if (!view.filters.product_id) return;
    const controller = new AbortController();
    const parameters = new URLSearchParams({
      retailer: view.filters.retailer_id,
      brand_type: view.filters.brand_type,
      product_id: view.filters.product_id,
      detail,
    });
    if (view.filters.state) parameters.set("state", view.filters.state);
    if (view.filters.city) parameters.set("city", view.filters.city);
    if (view.filters.zipcode) parameters.set("zipcode", view.filters.zipcode);
    fetch(
      `/api/price-monitoring/${encodeURIComponent(view.analysis_id)}/map?${parameters.toString()}`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`Map evidence returned ${response.status}`);
        setMapError(null);
        setSelectedPoint(null);
        setMapData((await response.json()) as PriceMonitoringMap);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError")
          return;
        setMapData(null);
        setMapError(
          reason instanceof Error
            ? reason.message
            : "Map evidence could not be loaded.",
        );
      });
    return () => controller.abort();
  }, [detail, view]);

  const pointByScope = useMemo(
    () =>
      new Map((mapData?.points ?? []).map((point) => [point.scope_key, point])),
    [mapData],
  );

  useEffect(() => {
    if (!containerRef.current || !mapData) return;
    let cancelled = false;
    let map: InteractiveMap | null = null;
    setMapReady(false);
    loadMapLibrary()
      .then((library) => {
        if (cancelled || !containerRef.current) return;
        map = new library.Map({
          container: containerRef.current,
          style: OPENFREEMAP_STYLE,
          center: [-96.5, 38.5],
          zoom: 3.2,
          maxZoom: 18,
          minZoom: 2,
          attributionControl: true,
        });
        mapRef.current = map;
        map.addControl(
          new library.NavigationControl({ showCompass: false }),
          "top-right",
        );
        map.addControl(
          new library.ScaleControl({ unit: "imperial" }),
          "bottom-left",
        );
        map.on("load", () => {
          if (!map || cancelled) return;
          const observed = mapData.points.filter(
            (point) => point.status === "observed",
          );
          const gaps = mapData.points.filter(
            (point) => point.status === "not_observed",
          );
          map.addSource(OBSERVED_SOURCE, {
            type: "geojson",
            data: toFeatureCollection(observed),
            cluster: true,
            clusterMaxZoom: EVIDENCE_CLUSTER_MAX_ZOOM,
            clusterRadius: EVIDENCE_CLUSTER_RADIUS,
          });
          map.addSource(GAP_SOURCE, {
            type: "geojson",
            data: toFeatureCollection(gaps),
            cluster: true,
            clusterMaxZoom: EVIDENCE_CLUSTER_MAX_ZOOM,
            clusterRadius: EVIDENCE_CLUSTER_RADIUS,
          });
          addEvidenceLayers(map, OBSERVED_SOURCE, "observed", "observed");
          addEvidenceLayers(map, GAP_SOURCE, "gap", "not_observed");

          const selectPoint = (prefix: string) => (event: MapMouseEvent) => {
            if (!map) return;
            const feature = map.queryRenderedFeatures(event.point, {
              layers: [`${prefix}-points`],
            })[0];
            const scopeKey = String(feature?.properties?.scope_key ?? "");
            setSelectedPoint(pointByScope.get(scopeKey) ?? null);
          };
          const expandCluster =
            (sourceId: string, prefix: string) =>
            async (event: MapMouseEvent) => {
              if (!map) return;
              const feature = map.queryRenderedFeatures(event.point, {
                layers: [`${prefix}-clusters`],
              })[0];
              const clusterId = Number(feature?.properties?.cluster_id);
              if (!Number.isFinite(clusterId)) return;
              const zoom = await map
                .getSource(sourceId)
                ?.getClusterExpansionZoom(clusterId);
              const coordinates = feature?.geometry?.coordinates;
              if (
                zoom !== undefined &&
                Array.isArray(coordinates) &&
                coordinates.length >= 2
              ) {
                map.easeTo({
                  center: coordinates,
                  zoom,
                });
              }
            };

          map.on("click", "observed-points", selectPoint("observed"));
          map.on("click", "gap-points", selectPoint("gap"));
          map.on(
            "click",
            "observed-clusters",
            expandCluster(OBSERVED_SOURCE, "observed"),
          );
          map.on("click", "gap-clusters", expandCluster(GAP_SOURCE, "gap"));
          for (const layer of [
            "observed-points",
            "gap-points",
            "observed-clusters",
            "gap-clusters",
          ]) {
            map.on("mouseenter", layer, () => {
              if (map) map.getCanvas().style.cursor = "pointer";
            });
            map.on("mouseleave", layer, () => {
              if (map) map.getCanvas().style.cursor = "";
            });
          }
          fitToPoints(map, mapData.points, detail);
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
      mapRef.current = null;
      map?.remove();
    };
  }, [detail, mapData, pointByScope]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const observedVisibility = mode === "observed" ? "visible" : "none";
    const gapVisibility = mode === "not_observed" ? "visible" : "none";
    for (const layer of [
      "observed-clusters",
      "observed-cluster-count",
      "observed-points",
      "observed-price-labels",
    ]) {
      map.setLayoutProperty(layer, "visibility", observedVisibility);
    }
    for (const layer of ["gap-clusters", "gap-cluster-count", "gap-points"]) {
      map.setLayoutProperty(layer, "visibility", gapVisibility);
    }
    const visiblePoints =
      mapData?.points.filter((point) => point.status === mode) ?? [];
    fitToPoints(map, visiblePoints, detail);
  }, [detail, mapData, mapReady, mode]);

  const display = mapData?.display;
  const hasPricePositionCounts = Boolean(
    display &&
    Number.isFinite(display.below_reference_locations) &&
    Number.isFinite(display.at_reference_locations) &&
    Number.isFinite(display.above_reference_locations),
  );
  const modeTotal = display
    ? mode === "observed"
      ? display.observed_locations
      : display.not_observed_locations
    : 0;
  const modePoints = display
    ? mode === "observed"
      ? display.observed_points
      : display.not_observed_points
    : 0;
  const modeSampled = display
    ? mode === "observed"
      ? display.observed_sampled
      : display.not_observed_sampled
    : false;

  return (
    <div
      className={`${styles.stage} ${detail === "summary" ? styles.summary : ""}`}
    >
      <div className={styles.mapShell}>
        <div
          aria-label={`${view.retailer.name} exact-product location map`}
          className={styles.map}
          ref={containerRef}
          role="application"
        />
        {!mapReady ? (
          <div className={styles.loading} role="status">
            {mapError ?? "Loading streets, places, and store evidence…"}
          </div>
        ) : null}
        <div className={styles.mapHint}>
          Scroll to zoom · drag to explore · select a cluster to expand
        </div>
      </div>
      <aside className={styles.inspector}>
        <div
          className={styles.mode}
          role="group"
          aria-label="Location evidence"
        >
          <button
            aria-pressed={mode === "observed"}
            className={mode === "observed" ? styles.active : ""}
            onClick={() => {
              setMode("observed");
              setSelectedPoint(null);
            }}
            type="button"
          >
            Observed
            <small>{display ? count(display.observed_locations) : "—"}</small>
          </button>
          <button
            aria-pressed={mode === "not_observed"}
            className={mode === "not_observed" ? styles.active : ""}
            onClick={() => {
              setMode("not_observed");
              setSelectedPoint(null);
            }}
            type="button"
          >
            Not observed
            <small>
              {display ? count(display.not_observed_locations) : "—"}
            </small>
          </button>
        </div>

        {mode === "observed" && display && hasPricePositionCounts ? (
          <section className={styles.positionSummary}>
            <header>
              <span>Store price position</span>
              <strong>
                vs. {currency(mapData?.reference_price ?? null)} median
              </strong>
            </header>
            <dl>
              <div className={styles.below}>
                <dt>Below</dt>
                <dd>{count(display.below_reference_locations)}</dd>
              </div>
              <div className={styles.at}>
                <dt>At</dt>
                <dd>{count(display.at_reference_locations)}</dd>
              </div>
              <div className={styles.above}>
                <dt>Above</dt>
                <dd>{count(display.above_reference_locations)}</dd>
              </div>
            </dl>
          </section>
        ) : null}

        <p className={styles.coverage}>
          <strong>{count(modePoints)} mapped</strong> of {count(modeTotal)}{" "}
          locations
          {modeSampled ? " · bounded overview sample" : ""}
        </p>

        {selectedPoint ? (
          <section className={styles.pointDetail}>
            <small>
              {selectedPoint.status === "observed"
                ? "Observed store"
                : "Search non-observation"}
            </small>
            <strong>
              {selectedPoint.store_name ??
                (selectedPoint.store_number
                  ? `Store ${selectedPoint.store_number}`
                  : `ZIP ${selectedPoint.zipcode ?? "—"}`)}
            </strong>
            <span>
              {[selectedPoint.city, selectedPoint.state, selectedPoint.zipcode]
                .filter(Boolean)
                .join(" · ")}
            </span>
            {selectedPoint.status === "observed" ? (
              <b>
                {currency(selectedPoint.price)} ·{" "}
                {signedCurrency(selectedPoint.difference_from_reference)} vs.
                median
              </b>
            ) : (
              <p>
                Product did not appear in the successful Search result; this is
                not proof of non-carriage.
              </p>
            )}
            <div className={styles.drillActions}>
              {selectedPoint.state ? (
                <button
                  onClick={() =>
                    onScopeChange({
                      state: selectedPoint.state,
                      city: null,
                      zipcode: null,
                    })
                  }
                  type="button"
                >
                  State · {selectedPoint.state}
                </button>
              ) : null}
              {selectedPoint.state && selectedPoint.city ? (
                <button
                  onClick={() =>
                    onScopeChange({
                      state: selectedPoint.state,
                      city: selectedPoint.city,
                      zipcode: null,
                    })
                  }
                  type="button"
                >
                  City · {selectedPoint.city}
                </button>
              ) : null}
              {selectedPoint.state &&
              selectedPoint.city &&
              selectedPoint.zipcode ? (
                <button
                  onClick={() =>
                    onScopeChange({
                      state: selectedPoint.state,
                      city: selectedPoint.city,
                      zipcode: selectedPoint.zipcode,
                    })
                  }
                  type="button"
                >
                  ZIP · {selectedPoint.zipcode}
                </button>
              ) : null}
            </div>
          </section>
        ) : (
          <p className={styles.prompt}>
            Select a store point for exact price and location detail.
          </p>
        )}

        <footer>
          Search is authoritative for price and observation. Store names and
          geography come from the retailer location master. Map data ©
          OpenStreetMap contributors.
        </footer>
      </aside>
    </div>
  );
}
