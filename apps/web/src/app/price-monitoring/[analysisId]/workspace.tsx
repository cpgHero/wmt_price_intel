"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { GeometryCollection, Topology } from "topojson-specification";
import { feature } from "topojson-client";
import statesTopologySource from "us-atlas/states-10m.json";

import {
  type ApplicationContextDefinition,
  useApplicationContextDefinition,
} from "@/app/components/application-context";
import type { PriceMonitoringMap, PriceMonitoringView } from "@/lib/api";
import { displayDate } from "@/lib/presentation";

import { EvidenceRetailMap as InteractiveEvidenceRetailMap } from "./evidence-retail-map";

type Product = PriceMonitoringView["products"][number];
type Location = PriceMonitoringView["locations"][number];
type MapPoint = PriceMonitoringMap["points"][number];
type MapMode = "observed" | "not_observed";
type MapDetail = "summary" | "full";
type StateFeature = {
  id?: string | number;
  geometry: { type: string; coordinates: unknown };
};
type TabId =
  "home" | "overview" | "price-architecture" | "store-review" | "history";
type ArchitectureView = "heatmap" | "map";
type StoreReviewMode = "price" | "not_observed";

const tabIds: readonly TabId[] = [
  "home",
  "overview",
  "price-architecture",
  "store-review",
  "history",
];

const legacyTabMigration: Record<string, TabId> = {
  footprint: "overview",
  "distribution-gaps": "store-review",
  "store-exceptions": "store-review",
  "market-benchmarks": "price-architecture",
};

function normalizeTab(value: string | null | undefined): TabId {
  if (value && tabIds.includes(value as TabId)) return value as TabId;
  if (value && legacyTabMigration[value]) return legacyTabMigration[value];
  return "overview";
}

const brandLabels: Record<string, string> = {
  all: "All brand types",
  private_label: "Private label",
  regional: "Regional",
  national: "National",
  unclassified: "Unclassified",
};

const stateByFips: Record<string, string> = {
  "01": "AL",
  "02": "AK",
  "04": "AZ",
  "05": "AR",
  "06": "CA",
  "08": "CO",
  "09": "CT",
  "10": "DE",
  "11": "DC",
  "12": "FL",
  "13": "GA",
  "15": "HI",
  "16": "ID",
  "17": "IL",
  "18": "IN",
  "19": "IA",
  "20": "KS",
  "21": "KY",
  "22": "LA",
  "23": "ME",
  "24": "MD",
  "25": "MA",
  "26": "MI",
  "27": "MN",
  "28": "MS",
  "29": "MO",
  "30": "MT",
  "31": "NE",
  "32": "NV",
  "33": "NH",
  "34": "NJ",
  "35": "NM",
  "36": "NY",
  "37": "NC",
  "38": "ND",
  "39": "OH",
  "40": "OK",
  "41": "OR",
  "42": "PA",
  "44": "RI",
  "45": "SC",
  "46": "SD",
  "47": "TN",
  "48": "TX",
  "49": "UT",
  "50": "VT",
  "51": "VA",
  "53": "WA",
  "54": "WV",
  "55": "WI",
  "56": "WY",
  "72": "PR",
};

const statesTopology = statesTopologySource as Topology;
const stateFeatures = (
  feature(
    statesTopology,
    statesTopology.objects.states as GeometryCollection,
  ) as unknown as {
    features: StateFeature[];
  }
).features;

function currency(value: number | null) {
  return value === null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
}

function unitCurrency(value: number | null, unit: string | null) {
  return value === null || !unit ? "—" : `${currency(value)}/${unit}`;
}

function unitCurrencyRange(
  minimum: number | null,
  maximum: number | null,
  unit: string | null,
) {
  return minimum === null || maximum === null || !unit
    ? "—"
    : `${currency(minimum)}–${currency(maximum)}/${unit}`;
}

function percent(value: number | null) {
  return value === null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(value);
}

function count(value: number) {
  return value.toLocaleString("en-US");
}

function signedCurrency(value: number) {
  if (value === 0) return "$0.00";
  return `${value > 0 ? "+" : "−"}${currency(Math.abs(value))}`;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function booleanLabel(value: unknown): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "Not supplied";
}

function evidenceCount(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function attributeRows(value: unknown): Array<[string, string]> {
  return Object.entries(objectValue(value))
    .flatMap(([key, rowValue]): Array<[string, string]> => {
      if (rowValue === null || rowValue === undefined || rowValue === "")
        return [];
      if (typeof rowValue === "object") return [];
      return [[key.replaceAll("_", " "), String(rowValue)]];
    })
    .slice(0, 16);
}

function updateQuery(parameters: Record<string, string | null>) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(parameters)) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  window.history.pushState(window.history.state, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function updateTab(tab: TabId) {
  const url = new URL(window.location.href);
  url.searchParams.set("tab", tab);
  window.history.pushState(window.history.state, "", url);
}

function projectCoordinate(longitude: number, latitude: number) {
  return {
    x: ((longitude + 125) / 59) * 900 + 30,
    y: ((50 - latitude) / 26) * 460 + 30,
  };
}

type CoordinateProjector = (
  longitude: number,
  latitude: number,
) => { x: number; y: number };

function coordinateRingPath(
  value: unknown,
  projector: CoordinateProjector = projectCoordinate,
) {
  if (!Array.isArray(value)) return "";
  const points = value.filter(
    (item): item is [number, number] =>
      Array.isArray(item) &&
      typeof item[0] === "number" &&
      typeof item[1] === "number",
  );
  if (points.length === 0) return "";
  return `${points
    .map(([longitude, latitude], index) => {
      const { x, y } = projector(longitude, latitude);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ")} Z`;
}

function geometryPath(
  geometry: { type: string; coordinates: unknown },
  projector: CoordinateProjector = projectCoordinate,
) {
  if (!Array.isArray(geometry.coordinates)) return "";
  const polygons =
    geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons
    .flatMap((polygon) => (Array.isArray(polygon) ? polygon : []))
    .map((ring) => coordinateRingPath(ring, projector))
    .filter(Boolean)
    .join(" ");
}

function coordinatePairs(value: unknown, output: Array<[number, number]>) {
  if (!Array.isArray(value)) return;
  if (
    value.length >= 2 &&
    typeof value[0] === "number" &&
    typeof value[1] === "number"
  ) {
    output.push([value[0], value[1]]);
    return;
  }
  for (const item of value) coordinatePairs(item, output);
}

function projectionForFeature(state: StateFeature | undefined) {
  if (!state) return projectCoordinate;
  const points: Array<[number, number]> = [];
  coordinatePairs(state.geometry.coordinates, points);
  if (!points.length) return projectCoordinate;
  const longitudes = points.map(([longitude]) => longitude);
  const latitudes = points.map(([, latitude]) => latitude);
  const minimumLongitude = Math.min(...longitudes);
  const maximumLongitude = Math.max(...longitudes);
  const minimumLatitude = Math.min(...latitudes);
  const maximumLatitude = Math.max(...latitudes);
  const longitudeSpan = Math.max(0.1, maximumLongitude - minimumLongitude);
  const latitudeSpan = Math.max(0.1, maximumLatitude - minimumLatitude);
  const scale = Math.min(840 / longitudeSpan, 430 / latitudeSpan);
  const renderedWidth = longitudeSpan * scale;
  const renderedHeight = latitudeSpan * scale;
  const left = (960 - renderedWidth) / 2;
  const top = (520 - renderedHeight) / 2;
  return (longitude: number, latitude: number) => ({
    x: left + (longitude - minimumLongitude) * scale,
    y: top + (maximumLatitude - latitude) * scale,
  });
}

function downloadCsv(analysisId: string, retailerId: string, product: Product) {
  const parameters = new URLSearchParams({
    retailer: retailerId,
    product_id: product.product_id,
  });
  const current = new URL(window.location.href).searchParams;
  for (const key of ["brand_type", "state", "city", "zipcode"]) {
    const value = current.get(key);
    if (value) parameters.set(key, value);
  }
  const anchor = document.createElement("a");
  anchor.href = `/api/price-monitoring/${encodeURIComponent(analysisId)}/evidence.csv?${parameters.toString()}`;
  anchor.download = `${retailerId}-${product.product_id}-price-evidence.csv`;
  anchor.click();
}

function PriceHistogram({ product }: Readonly<{ product: Product }>) {
  const maximum = Math.max(
    1,
    ...product.price_histogram.map((bin) => bin.count),
  );
  return (
    <div
      className="pi-histogram"
      aria-label="Observed store price distribution"
    >
      {product.price_histogram.map((bin) => (
        <div key={`${bin.lower}-${bin.upper}`}>
          <span>{count(bin.count)}</span>
          <i
            style={{ height: `${Math.max(8, (bin.count / maximum) * 100)}%` }}
          />
          <small>{currency(bin.lower)}</small>
        </div>
      ))}
    </div>
  );
}

function RetailMap({ view }: Readonly<{ view: PriceMonitoringView }>) {
  const stateRows = new Map(
    view.geographies
      .filter((row) => row.level === "state")
      .map((row) => [row.key, row]),
  );
  const medians = view.geographies
    .map((row) => row.price_stats.observation_median)
    .filter((value): value is number => value !== null);
  const minimum = medians.length ? Math.min(...medians) : 0;
  const maximum = medians.length ? Math.max(...medians) : minimum;
  const span = Math.max(0.01, maximum - minimum);
  const marketPoints = view.filters.state
    ? view.filters.city
      ? view.locations
          .filter((row) => row.latitude !== null && row.longitude !== null)
          .slice(0, 600)
          .map((row) => ({
            key: row.scope_key,
            label:
              row.store_name ?? row.store_number ?? row.zipcode ?? "Location",
            latitude: row.latitude!,
            longitude: row.longitude!,
            price: row.median_price,
            locations: 1,
            city: null,
          }))
      : view.geographies
          .filter(
            (row) =>
              row.level === "city" &&
              row.latitude !== null &&
              row.latitude !== undefined &&
              row.longitude !== null &&
              row.longitude !== undefined,
          )
          .map((row) => ({
            key: row.key,
            label: row.label,
            latitude: row.latitude!,
            longitude: row.longitude!,
            price: row.price_stats.observation_median,
            locations: row.locations,
            city: row.key,
          }))
    : [];
  const projectedMarketPoints = marketPoints.map((row) => ({
    ...row,
    point: projectCoordinate(row.longitude, row.latitude),
  }));
  const mapViewBox = (() => {
    if (!view.filters.state || !projectedMarketPoints.length)
      return "0 0 960 520";
    const xValues = projectedMarketPoints.map((row) => row.point.x);
    const yValues = projectedMarketPoints.map((row) => row.point.y);
    const minimumWidth = view.filters.city ? 70 : 150;
    const minimumHeight = view.filters.city ? 55 : 100;
    const rawWidth = Math.max(...xValues) - Math.min(...xValues);
    const rawHeight = Math.max(...yValues) - Math.min(...yValues);
    const width = Math.max(minimumWidth, rawWidth * 1.35);
    const height = Math.max(minimumHeight, rawHeight * 1.45);
    const centerX = (Math.min(...xValues) + Math.max(...xValues)) / 2;
    const centerY = (Math.min(...yValues) + Math.max(...yValues)) / 2;
    return `${centerX - width / 2} ${centerY - height / 2} ${width} ${height}`;
  })();
  return (
    <div className="pm-map-stage pi-map-stage">
      <svg
        className="pm-map"
        role="img"
        aria-label={`${view.retailer.name} exact-product observed price footprint`}
        viewBox={mapViewBox}
      >
        <g className="pm-state-layer">
          {stateFeatures.map((state) => {
            const fips = String(state.id ?? "").padStart(2, "0");
            const stateCode = stateByFips[fips];
            const geography = stateRows.get(stateCode);
            const selectedAggregate =
              view.filters.state === stateCode && view.products[0]
                ? {
                    locations: view.summary.observed_locations,
                    price_stats: view.products[0].price_stats,
                  }
                : undefined;
            const stateEvidence = geography ?? selectedAggregate;
            const medianPrice =
              stateEvidence?.price_stats.observation_median ?? null;
            const ratio =
              medianPrice === null ? 0 : (medianPrice - minimum) / span;
            const hasData = Boolean(stateEvidence);
            return (
              <path
                aria-label={
                  stateEvidence
                    ? `${stateCode}: ${count(stateEvidence.locations)} observed locations, ${currency(medianPrice)} median price`
                    : stateCode
                }
                className={`${hasData ? "has-data" : ""} ${view.filters.state === stateCode ? "selected" : ""}`}
                d={geometryPath(state.geometry)}
                key={fips}
                onClick={() => {
                  if (hasData) {
                    updateQuery({
                      state: stateCode,
                      city: null,
                      zipcode: null,
                    });
                  }
                }}
                onKeyDown={(event) => {
                  if (hasData && (event.key === "Enter" || event.key === " ")) {
                    updateQuery({
                      state: stateCode,
                      city: null,
                      zipcode: null,
                    });
                  }
                }}
                role={hasData ? "button" : undefined}
                style={
                  hasData
                    ? {
                        fill: `hsl(190 62% ${Math.round(88 - ratio * 34)}%)`,
                        fillOpacity: 1,
                      }
                    : undefined
                }
                tabIndex={hasData ? 0 : undefined}
              />
            );
          })}
        </g>
        <g className="pm-location-layer">
          {projectedMarketPoints.map((row) => {
            const point = row.point;
            return (
              <circle
                aria-label={`${row.label}: ${count(row.locations)} observed ${row.locations === 1 ? "location" : "locations"}, ${currency(row.price)}`}
                cx={point.x}
                cy={point.y}
                key={row.key}
                onClick={() => {
                  if (row.city) updateQuery({ city: row.city, zipcode: null });
                }}
                r={
                  row.city
                    ? Math.min(9, 3.5 + Math.sqrt(row.locations) / 2)
                    : 3.8
                }
                role={row.city ? "button" : undefined}
                tabIndex={row.city ? 0 : undefined}
              />
            );
          })}
        </g>
      </svg>
      <aside className="pm-map-legend">
        <span>
          {view.filters.city
            ? "Observed stores in the selected city"
            : view.filters.state
              ? "Select a city to drill into stores and ZIPs"
              : "Select a state to drill into cities, ZIPs, and stores"}
        </span>
        <div>
          <i />
          <i />
          <i />
          <i />
        </div>
        <small>{currency(minimum)}</small>
        <small>{currency(maximum)}</small>
        <p>
          Teal shading shows median Search price for the exact product. Location
          names and geography come from the retailer location master.
        </p>
      </aside>
    </div>
  );
}

function EvidenceRetailMap({
  view,
  detail = "full",
}: Readonly<{ view: PriceMonitoringView; detail?: MapDetail }>) {
  const [mode, setMode] = useState<MapMode>("observed");
  const [mapData, setMapData] = useState<PriceMonitoringMap | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<MapPoint | null>(null);

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
      "/api/price-monitoring/" +
        encodeURIComponent(view.analysis_id) +
        "/map?" +
        parameters.toString(),
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Map evidence returned " + response.status);
        }
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

  const stateRows = new Map(
    view.geographies
      .filter((row) => row.level === "state")
      .map((row) => [row.key, row]),
  );
  const gapStateRows = new Map(
    (view.distribution_gaps?.geographies ?? [])
      .filter((row) => row.level === "state")
      .map((row) => [row.key, row]),
  );
  const selectedFeature = view.filters.state
    ? stateFeatures.find((state) => {
        const fips = String(state.id ?? "").padStart(2, "0");
        return stateByFips[fips] === view.filters.state;
      })
    : undefined;
  const projection = projectionForFeature(selectedFeature);
  const visibleFeatures = selectedFeature ? [selectedFeature] : stateFeatures;
  const visiblePoints = (mapData?.points ?? []).filter(
    (point) => point.status === mode,
  );
  const modeTotal = mapData
    ? mode === "observed"
      ? mapData.display.observed_locations
      : mapData.display.not_observed_locations
    : 0;
  const modeSampled = mapData
    ? mode === "observed"
      ? mapData.display.observed_sampled
      : mapData.display.not_observed_sampled
    : false;

  function pointClass(point: MapPoint) {
    if (point.status === "not_observed") return "not-observed";
    const difference = point.difference_from_reference ?? 0;
    if (difference < -0.005) return "price-lower";
    if (difference > 0.005) return "price-higher";
    return "price-parity";
  }

  function pointLabel(point: MapPoint) {
    const location =
      point.store_name ??
      (point.store_number ? "Store " + point.store_number : null) ??
      point.zipcode ??
      "Location";
    if (point.status === "not_observed") {
      return location + ": not observed in the successful Search result";
    }
    return (
      location +
      ": " +
      currency(point.price) +
      ", " +
      signedCurrency(point.difference_from_reference ?? 0) +
      " versus the visible footprint median"
    );
  }

  return (
    <div className="pm-map-stage pi-map-stage pi-evidence-map-stage">
      <svg
        className="pm-map"
        role="img"
        aria-label={
          view.retailer.name +
          " exact-product " +
          (mode === "observed" ? "observed" : "not observed") +
          " location footprint"
        }
        viewBox="0 0 960 520"
      >
        <g className="pm-state-layer">
          {visibleFeatures.map((state) => {
            const fips = String(state.id ?? "").padStart(2, "0");
            const stateCode = stateByFips[fips];
            const geography = stateRows.get(stateCode);
            const gapGeography = gapStateRows.get(stateCode);
            const selectedAggregate =
              view.filters.state === stateCode && view.products[0]
                ? {
                    locations: view.summary.observed_locations,
                    price_stats: view.products[0].price_stats,
                  }
                : undefined;
            const stateEvidence = geography ?? selectedAggregate;
            const hasData = Boolean(
              stateEvidence || gapGeography?.eligible_locations,
            );
            const observedCount = stateEvidence?.locations ?? 0;
            const notObservedCount = gapGeography?.not_observed_locations ?? 0;
            const isSelectedState = view.filters.state === stateCode;
            return (
              <path
                aria-label={
                  hasData
                    ? stateCode +
                      ": " +
                      count(observedCount) +
                      " observed and " +
                      count(notObservedCount) +
                      " not observed locations"
                    : stateCode
                }
                className={
                  (hasData ? "has-data" : "") +
                  (isSelectedState ? " selected" : "")
                }
                d={geometryPath(state.geometry, projection)}
                key={fips}
                onClick={() => {
                  if (hasData && !isSelectedState) {
                    updateQuery({
                      state: stateCode,
                      city: null,
                      zipcode: null,
                    });
                  }
                }}
                onKeyDown={(event) => {
                  if (
                    hasData &&
                    !isSelectedState &&
                    (event.key === "Enter" || event.key === " ")
                  ) {
                    updateQuery({
                      state: stateCode,
                      city: null,
                      zipcode: null,
                    });
                  }
                }}
                role={hasData && !isSelectedState ? "button" : undefined}
                tabIndex={hasData && !isSelectedState ? 0 : undefined}
              />
            );
          })}
        </g>
        <g className="pm-location-layer">
          {visiblePoints.map((row) => {
            const point = projection(row.longitude, row.latitude);
            const label = pointLabel(row);
            return (
              <circle
                aria-label={label}
                className={pointClass(row)}
                cx={point.x}
                cy={point.y}
                key={row.status + ":" + row.scope_key}
                onClick={() => {
                  if (!view.filters.state && row.state) {
                    updateQuery({
                      state: row.state,
                      city: null,
                      zipcode: null,
                    });
                  } else {
                    setSelectedPoint(row);
                  }
                }}
                r={view.filters.state ? 4.2 : detail === "summary" ? 2.4 : 2.1}
                role="button"
                tabIndex={0}
              >
                <title>{label}</title>
              </circle>
            );
          })}
        </g>
        {!mapData && !mapError ? (
          <text className="pi-map-status" x="480" y="490" textAnchor="middle">
            Loading location evidence…
          </text>
        ) : null}
      </svg>
      <aside className="pm-map-legend">
        <div
          className="pi-map-mode"
          role="group"
          aria-label="Location evidence"
        >
          <button
            aria-pressed={mode === "observed"}
            className={mode === "observed" ? "active" : ""}
            onClick={() => {
              setMode("observed");
              setSelectedPoint(null);
            }}
            type="button"
          >
            Observed
          </button>
          <button
            aria-pressed={mode === "not_observed"}
            className={mode === "not_observed" ? "active" : ""}
            onClick={() => {
              setMode("not_observed");
              setSelectedPoint(null);
            }}
            type="button"
          >
            Not observed
          </button>
        </div>
        <span>
          {mapData
            ? count(visiblePoints.length) +
              " mapped of " +
              count(modeTotal) +
              (mode === "observed"
                ? " observed locations"
                : " not observed locations")
            : (mapError ?? "Loading exact-product locations…")}
        </span>
        {mode === "observed" ? (
          <div className="pi-price-legend" aria-label="Price difference legend">
            <span className="price-lower">Below median</span>
            <span className="price-parity">At median</span>
            <span className="price-higher">Above median</span>
          </div>
        ) : (
          <div className="pi-price-legend">
            <span className="not-observed">Search non-observation</span>
          </div>
        )}
        {selectedPoint ? (
          <div className="pi-map-point-detail">
            <small>
              {selectedPoint.status === "observed"
                ? "Observed store"
                : "Search non-observation"}
            </small>
            <strong>
              {selectedPoint.store_name ??
                (selectedPoint.store_number
                  ? "Store " + selectedPoint.store_number
                  : "ZIP " + selectedPoint.zipcode)}
            </strong>
            <span>
              {[selectedPoint.city, selectedPoint.state, selectedPoint.zipcode]
                .filter(Boolean)
                .join(" · ")}
            </span>
            {selectedPoint.status === "observed" ? (
              <b>
                {currency(selectedPoint.price)} ·{" "}
                {signedCurrency(selectedPoint.difference_from_reference ?? 0)}{" "}
                vs. median
              </b>
            ) : null}
          </div>
        ) : null}
        <p>
          {view.filters.state
            ? view.filters.state +
              " is fitted to the map. Select a point for store detail."
            : "Select a state or location point to open the state footprint."}{" "}
          Price colors compare each observed store with the median for the
          visible footprint. Location details come from the retailer location
          master.
          {modeSampled ? " This overview is a bounded map sample." : ""}
        </p>
      </aside>
    </div>
  );
}

function StoreDrawer({
  location,
  product,
  onClose,
}: Readonly<{
  location: Location;
  product: Product;
  onClose: () => void;
}>) {
  return (
    <div className="pm-drawer-layer">
      <button
        aria-label="Close store details"
        className="pm-drawer-backdrop"
        onClick={onClose}
        type="button"
      />
      <aside
        className="pm-product-drawer pi-store-drawer"
        role="dialog"
        aria-modal="true"
      >
        <header>
          <div>
            <p className="section-kicker">Store-level Search evidence</p>
            <h2>
              {location.store_name ??
                (location.store_number
                  ? `Store ${location.store_number}`
                  : `ZIP ${location.zipcode}`)}
            </h2>
            <small>
              {[location.city, location.state, location.zipcode]
                .filter(Boolean)
                .join(" · ")}
            </small>
          </div>
          <button
            aria-label="Close store details"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>
        <section className="pm-drawer-metrics">
          <div>
            <span>Observed price</span>
            <strong>{currency(location.median_price)}</strong>
          </div>
          <div>
            <span>Selected product</span>
            <strong>{product.name}</strong>
          </div>
          <div>
            <span>Store ID</span>
            <strong>{location.store_number ?? "Service area"}</strong>
          </div>
          <div>
            <span>Evidence</span>
            <strong>
              Search ·{" "}
              {location.sponsorship_status === "sponsored"
                ? "Sponsored"
                : location.sponsorship_status === "organic"
                  ? "Organic"
                  : "Sponsorship unknown"}
            </strong>
          </div>
        </section>
        <section className="pm-drawer-section">
          <h3>What this record means</h3>
          <p>
            The selected retailer product was observed at this location in the
            current collection. Price and location come from Search; PDP data
            contributes only product identity and imagery.
          </p>
        </section>
      </aside>
    </div>
  );
}

function PdpReferencePanel({ product }: Readonly<{ product: Product }>) {
  const pdp = objectValue(product.pdp);
  const enriched = pdp.enriched === true;
  const fulfillment = objectValue(pdp.fulfillment);
  const reviews = objectValue(pdp.reviews);
  const demand = objectValue(pdp.demand);
  const content = objectValue(pdp.content);
  const relationshipCounts = objectValue(pdp.relationship_counts);
  const media = objectValue(pdp.media);
  const identifiers = attributeRows(pdp.identifiers);
  const specifications = attributeRows(pdp.specification);
  const physicalProperties = attributeRows(pdp.physical_properties);
  const rating = numberValue(reviews.rating);
  const reviewCount = numberValue(
    reviews.reviews_count ?? reviews.rating_count,
  );
  const monthlySales = numberValue(demand.monthly_sales_volume);
  const weeklySales = numberValue(demand.weekly_sales_volume);
  const imageCount =
    numberValue(media.image_count) ?? evidenceCount(media.images);
  const mediaImages = Array.from(
    new Set(
      [
        product.image_url,
        ...(Array.isArray(media.images) ? media.images : []),
      ].filter(
        (value): value is string =>
          typeof value === "string" && value.trim().length > 0,
      ),
    ),
  ).slice(0, 12);
  const videoCount =
    numberValue(content.video_count) ??
    numberValue(media.video_count) ??
    evidenceCount(media.videos);
  const relationshipCount = Object.values(relationshipCounts).reduce<number>(
    (total, value) => total + (numberValue(value) ?? 0),
    0,
  );
  const description =
    textValue(pdp.description_short) ?? textValue(pdp.description_full);
  const category = textValue(pdp.category_path);
  const unmappedFields = Array.isArray(pdp.unmapped_source_fields)
    ? pdp.unmapped_source_fields.filter(
        (value): value is string => typeof value === "string",
      )
    : [];

  return (
    <article className="pm-panel pi-pdp-reference">
      <header>
        <div>
          <p className="section-kicker">Product Details reference</p>
          <h2>Identity, attributes, and commerce context</h2>
        </div>
        <span className={`pi-evidence-pill ${enriched ? "" : "organic"}`}>
          {enriched ? "PDP enriched" : "PDP not available"}
        </span>
      </header>
      {enriched ? (
        <>
          <div className="pi-pdp-summary-grid">
            <div>
              <span>Seller</span>
              <strong>
                {product.seller ?? "Not supplied by retailer PDP"}
              </strong>
              <small>PDP seller; not inferred from the retailer name</small>
            </div>
            <div>
              <span>Category</span>
              <strong>{category ?? "Not supplied"}</strong>
              <small>
                {textValue(pdp.item_condition) ?? "Condition not supplied"}
              </small>
            </div>
            <div>
              <span>Ratings & reviews</span>
              <strong>
                {rating === null
                  ? "Not supplied"
                  : `${rating.toFixed(1)} rating`}
              </strong>
              <small>
                {reviewCount === null
                  ? "Review count not supplied"
                  : `${count(reviewCount)} reviews/ratings`}
              </small>
            </div>
            <div>
              <span>Demand context</span>
              <strong>
                {monthlySales !== null
                  ? `${count(monthlySales)} monthly sales`
                  : weeklySales !== null
                    ? `${count(weeklySales)} weekly sales`
                    : "Not supplied"}
              </strong>
              <small>
                PDP reference only; never substituted for Search demand
              </small>
            </div>
            <div>
              <span>Fulfillment context</span>
              <strong>
                Pickup {booleanLabel(fulfillment.pickup_available)} · Shipping{" "}
                {textValue(fulfillment.shipping_type) ?? "not supplied"}
              </strong>
              <small>
                Retailer fulfilled{" "}
                {booleanLabel(fulfillment.fulfilled_by_retailer)}
              </small>
            </div>
            <div>
              <span>Content depth</span>
              <strong>
                {count(imageCount)} images · {count(videoCount)} videos
              </strong>
              <small>
                {count(relationshipCount)} related or variant product references
              </small>
            </div>
          </div>
          {description ? (
            <p className="pi-pdp-description">{description}</p>
          ) : null}
          <details className="pi-pdp-details">
            <summary>View identifiers and product attributes</summary>
            <div>
              {mediaImages.length ? (
                <section className="pi-pdp-media">
                  <h3>Product images</h3>
                  <div>
                    {mediaImages.map((imageUrl, index) => (
                      <a
                        href={imageUrl}
                        key={imageUrl}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          alt={`${product.name} product image ${index + 1}`}
                          loading="lazy"
                          src={imageUrl}
                        />
                      </a>
                    ))}
                  </div>
                </section>
              ) : null}
              <section>
                <h3>Identifiers</h3>
                <dl>
                  {identifiers.length ? (
                    identifiers.map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))
                  ) : (
                    <div>
                      <dt>Retailer ID</dt>
                      <dd>{product.product_id}</dd>
                    </div>
                  )}
                </dl>
              </section>
              <section>
                <h3>Specifications</h3>
                <dl>
                  {[...specifications, ...physicalProperties].length ? (
                    [...specifications, ...physicalProperties].map(
                      ([label, value], index) => (
                        <div key={`${label}:${index}`}>
                          <dt>{label}</dt>
                          <dd>{value}</dd>
                        </div>
                      ),
                    )
                  ) : (
                    <div>
                      <dt>Attributes</dt>
                      <dd>Not supplied in this PDP</dd>
                    </div>
                  )}
                </dl>
              </section>
            </div>
          </details>
          {unmappedFields.length ? (
            <p className="pi-pdp-governance-note">
              {count(unmappedFields.length)} newly observed provider fields are
              retained in the immutable raw payload and queued for schema
              review.
            </p>
          ) : null}
        </>
      ) : (
        <p className="pi-pdp-description">
          No successful Product Details payload is linked to this exact retailer
          product. Search still provides its governed name, price, and location
          evidence.
        </p>
      )}
      <footer>
        <span>
          PDP owns descriptive identity. Search remains authoritative for store
          price, observed availability, sponsorship, and collection time.
        </span>
        {product.url ? (
          <a href={product.url} rel="noreferrer" target="_blank">
            Open retailer product page ↗
          </a>
        ) : null}
      </footer>
    </article>
  );
}

function LocationTable({
  view,
  onOpen,
}: Readonly<{ view: PriceMonitoringView; onOpen: (row: Location) => void }>) {
  const visibleLocations = view.locations.slice(0, 200);
  return (
    <div className="pi-location-evidence-table">
      <div className="pm-location-table-wrap">
        <table className="pm-location-table pi-location-table">
          <thead>
            <tr>
              <th>Location</th>
              <th>Market</th>
              <th>Observed price</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {visibleLocations.map((row) => (
              <tr key={row.scope_key}>
                <td>
                  <button
                    className="pi-table-link"
                    onClick={() => onOpen(row)}
                    type="button"
                  >
                    <strong>
                      {row.store_name ??
                        (row.store_number
                          ? `Store ${row.store_number}`
                          : `ZIP ${row.zipcode}`)}
                    </strong>
                    <small>
                      {row.store_number
                        ? `#${row.store_number}`
                        : "Service area"}
                    </small>
                  </button>
                </td>
                <td>
                  {[row.city, row.state, row.zipcode]
                    .filter(Boolean)
                    .join(", ") || "—"}
                </td>
                <td>
                  <strong>{currency(row.median_price)}</strong>
                </td>
                <td>
                  <span
                    className={`pi-evidence-pill ${row.sponsorship_status}`}
                  >
                    {row.sponsorship_status === "sponsored"
                      ? "Sponsored"
                      : row.sponsorship_status === "organic"
                        ? "Organic"
                        : "Observed"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {view.location_display.total > visibleLocations.length ? (
        <p className="pi-table-summary">
          Showing the first {count(visibleLocations.length)} of{" "}
          {count(view.location_display.total)} locations. Download the governed
          evidence for the complete store-level file.
        </p>
      ) : null}
    </div>
  );
}

function MarketTable({ view }: Readonly<{ view: PriceMonitoringView }>) {
  const geographyLabel = view.filters.city
    ? "ZIP code"
    : view.filters.state
      ? "City"
      : "State";
  return (
    <div className="pm-location-table-wrap">
      <table className="pm-location-table pi-market-table">
        <thead>
          <tr>
            <th>{geographyLabel}</th>
            <th>Observed locations</th>
            <th>Median</th>
            <th>Range</th>
            <th>Consistency</th>
          </tr>
        </thead>
        <tbody>
          {view.geographies.map((row) => (
            <tr key={`${row.level}-${row.key}`}>
              <td>
                <button
                  className="pi-table-link"
                  onClick={() =>
                    updateQuery(
                      row.level === "state"
                        ? { state: row.key, city: null, zipcode: null }
                        : row.level === "city"
                          ? { city: row.key, zipcode: null }
                          : { zipcode: row.key },
                    )
                  }
                  type="button"
                >
                  <strong>{row.label}</strong>
                  <small>Open market</small>
                </button>
              </td>
              <td>{count(row.locations)}</td>
              <td>
                <strong>{currency(row.price_stats.observation_median)}</strong>
              </td>
              <td>
                {currency(row.price_stats.minimum)}–
                {currency(row.price_stats.maximum)}
              </td>
              <td>{percent(row.price_stats.modal_share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GapMarketTable({
  gaps,
}: Readonly<{
  gaps: PriceMonitoringView["distribution_gaps"];
}>) {
  return (
    <div className="pm-location-table-wrap">
      <table className="pm-location-table pi-gap-market-table">
        <thead>
          <tr>
            <th>Market</th>
            <th>Planned locations</th>
            <th>Observed</th>
            <th>Not observed</th>
            <th>Observed rate</th>
          </tr>
        </thead>
        <tbody>
          {gaps.geographies.slice(0, 100).map((row) => (
            <tr key={`${row.level}-${row.key}`}>
              <td>
                <button
                  className="pi-table-link"
                  onClick={() =>
                    updateQuery(
                      row.level === "state"
                        ? { state: row.key, city: null, zipcode: null }
                        : row.level === "city"
                          ? { city: row.key, zipcode: null }
                          : { zipcode: row.key },
                    )
                  }
                  type="button"
                >
                  <strong>{row.label}</strong>
                  <small>Review locations</small>
                </button>
              </td>
              <td>{count(row.eligible_locations)}</td>
              <td>{count(row.observed_locations)}</td>
              <td>
                <strong className="pi-gap-count">
                  {count(row.not_observed_locations)}
                </strong>
              </td>
              <td>{percent(row.observed_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GapLocationTable({
  gaps,
}: Readonly<{ gaps: PriceMonitoringView["distribution_gaps"] }>) {
  const locations = gaps.locations.slice(0, 200);
  return (
    <div className="pi-location-evidence-table">
      <div className="pm-location-table-wrap">
        <table className="pm-location-table pi-location-table">
          <thead>
            <tr>
              <th>Planned location</th>
              <th>City</th>
              <th>State</th>
              <th>ZIP code</th>
              <th>Search result</th>
            </tr>
          </thead>
          <tbody>
            {locations.map((row) => (
              <tr key={row.scope_key}>
                <td>
                  <strong>
                    {row.store_name ??
                      (row.store_number
                        ? `Store ${row.store_number}`
                        : `Service area ${row.zipcode ?? ""}`)}
                  </strong>
                  <small>
                    {row.store_number ? `#${row.store_number}` : row.kind}
                  </small>
                </td>
                <td>{row.city ?? "—"}</td>
                <td>{row.state ?? "—"}</td>
                <td>{row.zipcode ?? "—"}</td>
                <td>
                  <span className="pi-gap-pill">Product not observed</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {gaps.location_display.total > locations.length ? (
        <p className="pi-table-summary">
          Showing {count(locations.length)} of{" "}
          {count(gaps.location_display.total)}
          {gaps.location_display.missing_location_details
            ? ` non-observations; ${count(gaps.location_display.missing_location_details)} planned locations lack complete location-master detail.`
            : " non-observations."}
        </p>
      ) : null}
    </div>
  );
}

function GeographicHeatmap({ view }: Readonly<{ view: PriceMonitoringView }>) {
  const rows = view.geographies.slice(0, 24);
  const medians = rows
    .map((row) => row.price_stats.observation_median)
    .filter((value): value is number => value !== null);
  const minimum = medians.length ? Math.min(...medians) : 0;
  const maximum = medians.length ? Math.max(...medians) : minimum;
  const span = Math.max(0.01, maximum - minimum);

  return (
    <div className="pi-geography-heatmap" role="table">
      <div className="pi-heatmap-header" role="row">
        <span role="columnheader">Market</span>
        <span role="columnheader">Observed</span>
        <span role="columnheader">Median shelf price</span>
        <span role="columnheader">Price range</span>
        <span role="columnheader">At modal price</span>
      </div>
      {rows.map((row) => {
        const medianPrice = row.price_stats.observation_median;
        const intensity =
          medianPrice === null ? 0 : (medianPrice - minimum) / span;
        return (
          <button
            className="pi-heatmap-row"
            key={`${row.level}-${row.key}`}
            onClick={() =>
              updateQuery(
                row.level === "state"
                  ? { state: row.key, city: null, zipcode: null }
                  : row.level === "city"
                    ? { city: row.key, zipcode: null }
                    : { zipcode: row.key },
              )
            }
            role="row"
            type="button"
          >
            <span role="cell">
              <strong>{row.label}</strong>
              <small>Open {row.level}</small>
            </span>
            <span role="cell">{count(row.locations)}</span>
            <span
              className="pi-heat-cell"
              role="cell"
              style={{
                backgroundColor: `hsl(190 62% ${Math.round(94 - intensity * 38)}%)`,
                color: intensity > 0.58 ? "#ffffff" : "#12333d",
              }}
            >
              {currency(medianPrice)}
            </span>
            <span role="cell">
              {currency(row.price_stats.minimum)}–
              {currency(row.price_stats.maximum)}
            </span>
            <span role="cell">{percent(row.price_stats.modal_share)}</span>
          </button>
        );
      })}
      {view.geographies.length > rows.length ? (
        <p>
          Showing the first {count(rows.length)} of{" "}
          {count(view.geographies.length)} visible markets. Open the detail
          drawer for the complete table.
        </p>
      ) : null}
    </div>
  );
}

function LocationEvidenceDrawer({
  mode,
  view,
  product,
  onClose,
  onOpenLocation,
}: Readonly<{
  mode: MapMode;
  view: PriceMonitoringView;
  product: Product;
  onClose: () => void;
  onOpenLocation: (location: Location) => void;
}>) {
  const observed = mode === "observed";
  return (
    <div className="pm-drawer-layer">
      <button
        aria-label="Close location evidence"
        className="pm-drawer-backdrop"
        onClick={onClose}
        type="button"
      />
      <aside
        className="pm-product-drawer pi-evidence-drawer"
        role="dialog"
        aria-modal="true"
      >
        <header>
          <div>
            <p className="section-kicker">Exact-product location evidence</p>
            <h2>
              {observed ? "Observed locations" : "Search non-observations"}
            </h2>
            <small>
              {observed
                ? `${count(view.location_display.total)} locations with a positive Search price`
                : `${count(view.distribution_gaps.location_display.total)} planned locations where the product did not appear`}
            </small>
          </div>
          <button
            aria-label="Close location evidence"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>
        <section className="pm-drawer-section">
          {observed ? (
            <LocationTable view={view} onOpen={onOpenLocation} />
          ) : (
            <>
              <div className="pi-drawer-note">
                A Search non-observation is a review signal, not proof that the
                retailer does not carry the item.
              </div>
              <GapLocationTable gaps={view.distribution_gaps} />
            </>
          )}
        </section>
        <footer>
          <p>
            Search price and product-location evidence remain authoritative.
          </p>
          {observed ? (
            <button
              className="button secondary"
              onClick={() =>
                downloadCsv(view.analysis_id, view.retailer.id, product)
              }
              type="button"
            >
              Download evidence
            </button>
          ) : null}
        </footer>
      </aside>
    </div>
  );
}

function GeographyDrawer({
  view,
  onClose,
}: Readonly<{ view: PriceMonitoringView; onClose: () => void }>) {
  return (
    <div className="pm-drawer-layer">
      <button
        aria-label="Close geographic price detail"
        className="pm-drawer-backdrop"
        onClick={onClose}
        type="button"
      />
      <aside
        className="pm-product-drawer pi-evidence-drawer"
        role="dialog"
        aria-modal="true"
      >
        <header>
          <div>
            <p className="section-kicker">Geographic price structure</p>
            <h2>All visible markets</h2>
            <small>
              Exact-product Search prices; select a market to drill down.
            </small>
          </div>
          <button
            aria-label="Close geographic price detail"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>
        <section className="pm-drawer-section">
          <MarketTable view={view} />
        </section>
      </aside>
    </div>
  );
}

function FootprintModal({
  mode,
  view,
  onClose,
  onModeChange,
}: Readonly<{
  mode: MapMode;
  view: PriceMonitoringView;
  onClose: () => void;
  onModeChange: (mode: MapMode) => void;
}>) {
  return (
    <div className="pm-drawer-layer pi-map-modal-layer">
      <button
        aria-label="Close full-screen footprint"
        className="pm-drawer-backdrop"
        onClick={onClose}
        type="button"
      />
      <section
        aria-label="Full-screen exact-product footprint"
        aria-modal="true"
        className="pi-map-modal"
        role="dialog"
      >
        <header>
          <div>
            <p className="section-kicker">Exact-product footprint</p>
            <h2>
              {mode === "observed"
                ? "Observed store locations"
                : "Planned locations not observed in Search"}
            </h2>
          </div>
          <button aria-label="Close full-screen footprint" onClick={onClose}>
            ×
          </button>
        </header>
        <InteractiveEvidenceRetailMap
          clusterPoints={false}
          detail="full"
          key={`modal:${JSON.stringify(view.filters)}`}
          mode={mode}
          onModeChange={onModeChange}
          onScopeChange={updateQuery}
          view={view}
        />
      </section>
    </div>
  );
}

function ProductCatalog({
  view,
  onOpenProduct,
  loading,
}: Readonly<{
  view: PriceMonitoringView;
  loading: boolean;
  onOpenProduct: (
    productId: string,
    tab: TabId,
    evidenceMode?: MapMode,
  ) => void;
}>) {
  const [search, setSearch] = useState("");
  const [brandName, setBrandName] = useState("all");
  const [brandType, setBrandType] = useState("all");
  const [seller, setSeller] = useState("all");
  const brandNames = useMemo(
    () =>
      Array.from(
        new Set(
          view.products
            .map((product) => product.brand?.trim())
            .filter((value): value is string => Boolean(value)),
        ),
      ).sort((left, right) => left.localeCompare(right)),
    [view.products],
  );
  const brandTypes = useMemo(
    () =>
      Array.from(
        new Set(view.products.map((product) => product.brand_type)),
      ).sort((left, right) =>
        brandLabels[left].localeCompare(brandLabels[right]),
      ),
    [view.products],
  );
  const sellers = useMemo(
    () =>
      Array.from(
        new Set(
          view.products
            .map((product) => product.seller?.trim())
            .filter((value): value is string => Boolean(value)),
        ),
      ).sort((left, right) => left.localeCompare(right)),
    [view.products],
  );
  const enrichedProducts = useMemo(
    () => view.products.filter((product) => product.pdp.enriched).length,
    [view.products],
  );
  const selectedSeller =
    seller === "all" || sellers.includes(seller) ? seller : "all";
  const filteredProducts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return view.products.filter((product) => {
      const searchable = [
        product.name,
        product.product_id,
        product.brand,
        product.seller,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase();
      return (
        (!query || searchable.includes(query)) &&
        (brandName === "all" || product.brand === brandName) &&
        (brandType === "all" || product.brand_type === brandType) &&
        (selectedSeller === "all" || product.seller === selectedSeller)
      );
    });
  }, [brandName, brandType, search, selectedSeller, view.products]);
  const filtersActive =
    Boolean(search.trim()) ||
    brandName !== "all" ||
    brandType !== "all" ||
    selectedSeller !== "all";

  function clearFilters() {
    setSearch("");
    setBrandName("all");
    setBrandType("all");
    setSeller("all");
  }

  return (
    <section className="pi-product-catalog">
      <header>
        <div>
          <p className="section-kicker">Single-retailer product intelligence</p>
          <h2>Product price and distribution index</h2>
        </div>
        <p>
          One row per exact retailer product, ranked by observed locations.
          Price and location metrics come from governed Search evidence.
        </p>
      </header>
      <div className="pi-catalog-filters" aria-label="Filter retailer products">
        <label className="pi-catalog-search">
          <span>Search products</span>
          <input
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search name, product ID, brand, or seller"
            type="search"
            value={search}
          />
        </label>
        <label>
          <span>Brand name</span>
          <select
            aria-label="Filter by brand name"
            onChange={(event) => setBrandName(event.target.value)}
            value={brandName}
          >
            <option value="all">All brands</option>
            {brandNames.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Brand type</span>
          <select
            aria-label="Filter by brand type"
            onChange={(event) => setBrandType(event.target.value)}
            value={brandType}
          >
            <option value="all">All brand types</option>
            {brandTypes.map((value) => (
              <option key={value} value={value}>
                {brandLabels[value]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>PDP seller</span>
          <select
            aria-label="Filter by PDP seller"
            disabled={!sellers.length}
            onChange={(event) => setSeller(event.target.value)}
            value={selectedSeller}
          >
            <option value="all">
              {sellers.length
                ? "All PDP sellers"
                : enrichedProducts
                  ? "Seller not supplied by PDP"
                  : "PDP enrichment unavailable"}
            </option>
            {sellers.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <div className="pi-catalog-filter-status" aria-live="polite">
          <strong>
            {count(filteredProducts.length)} of {count(view.products.length)}
          </strong>
          <span>products</span>
          <button
            disabled={!filtersActive}
            onClick={clearFilters}
            type="button"
          >
            Clear
          </button>
        </div>
      </div>
      <div
        className="pi-product-table"
        role="table"
        aria-label="Retailer products"
      >
        <div className="pi-product-table-head" role="row">
          <span role="columnheader">Product</span>
          <span role="columnheader">Price</span>
          <span role="columnheader">Price range</span>
          <span role="columnheader">Location footprint</span>
          <span role="columnheader">Sponsored</span>
          <span role="columnheader">Workspace</span>
        </div>
        <div className="pi-product-table-body" role="rowgroup">
          {filteredProducts.map((product) => {
            const stats = product.price_stats;
            const typicalPrice = stats.modal_price ?? stats.observation_median;
            const unitPrice = product.unit_price;
            const typicalUnitPrice =
              unitPrice.price_stats.modal_price ??
              unitPrice.price_stats.observation_median;
            const observedRate = product.presence.observed_rate;
            const notObservedRate = product.presence.not_observed_rate;
            return (
              <article
                className="pi-product-row"
                key={product.product_id}
                role="row"
              >
                <div className="pi-product-identity" role="cell">
                  {product.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img loading="lazy" src={product.image_url} alt="" />
                  ) : (
                    <span aria-hidden="true">P</span>
                  )}
                  <div>
                    <small>{brandLabels[product.brand_type]}</small>
                    <button
                      onClick={() =>
                        onOpenProduct(product.product_id, "overview")
                      }
                      type="button"
                    >
                      {product.name}
                    </button>
                    <p>
                      {product.brand ?? "Brand unresolved"} · ID{" "}
                      {product.product_id}
                      {product.seller ? ` · Seller ${product.seller}` : ""}
                    </p>
                  </div>
                </div>
                <button
                  aria-label={`Open price architecture for ${product.name}`}
                  className="pi-product-metric pi-product-metric-link"
                  onClick={() =>
                    onOpenProduct(product.product_id, "price-architecture")
                  }
                  role="cell"
                  type="button"
                >
                  <small>Typical price</small>
                  <strong>{currency(typicalPrice)}</strong>
                  <span>Median {currency(stats.observation_median)}</span>
                  <span>
                    {unitPrice.status === "observed"
                      ? `${unitPrice.label}: ${unitCurrency(typicalUnitPrice, unitPrice.unit)}`
                      : "Unit price unavailable"}
                  </span>
                </button>
                <button
                  aria-label={`Open price range for ${product.name}`}
                  className="pi-product-metric pi-product-metric-link"
                  onClick={() =>
                    onOpenProduct(product.product_id, "price-architecture")
                  }
                  role="cell"
                  type="button"
                >
                  <small>Observed range</small>
                  <strong>
                    {currency(stats.minimum)}–{currency(stats.maximum)}
                  </strong>
                  <span>
                    {unitPrice.status === "observed"
                      ? `Unit range ${unitCurrencyRange(unitPrice.price_stats.minimum, unitPrice.price_stats.maximum, unitPrice.unit)}`
                      : "Unit range unavailable"}
                  </span>
                  <span>
                    {percent(product.consistency_rate)} shelf-price consistency
                  </span>
                </button>
                <div className="pi-product-footprint" role="cell">
                  <small>Eligible location footprint</small>
                  <div>
                    <button
                      onClick={() =>
                        onOpenProduct(
                          product.product_id,
                          "overview",
                          "observed",
                        )
                      }
                      type="button"
                    >
                      <strong>
                        {count(product.presence.observed_locations)}
                      </strong>{" "}
                      observed
                    </button>
                    <span>{percent(observedRate)}</span>
                  </div>
                  <div>
                    <button
                      onClick={() =>
                        onOpenProduct(
                          product.product_id,
                          "overview",
                          "not_observed",
                        )
                      }
                      type="button"
                    >
                      <strong>
                        {count(product.presence.not_observed_locations)}
                      </strong>{" "}
                      not observed
                    </button>
                    <span>{percent(notObservedRate)}</span>
                  </div>
                  <i aria-hidden="true">
                    <span style={{ width: `${(observedRate ?? 0) * 100}%` }} />
                  </i>
                </div>
                <button
                  aria-label={`Open sponsorship evidence for ${product.name}`}
                  className="pi-product-metric pi-product-metric-link"
                  onClick={() =>
                    onOpenProduct(product.product_id, "price-architecture")
                  }
                  role="cell"
                  type="button"
                >
                  <small>Search is_sponsored</small>
                  <strong>{percent(product.sponsorship.rate)}</strong>
                  <span>
                    {count(product.sponsorship.known_observations)} classified
                  </span>
                </button>
                <div className="pi-product-actions" role="cell">
                  <button
                    aria-busy={loading}
                    disabled={loading}
                    onClick={() =>
                      onOpenProduct(product.product_id, "overview")
                    }
                    type="button"
                  >
                    Open report
                  </button>
                  <button
                    aria-busy={loading}
                    disabled={loading}
                    onClick={() =>
                      onOpenProduct(product.product_id, "store-review")
                    }
                    type="button"
                  >
                    Store review
                  </button>
                </div>
              </article>
            );
          })}
          {!filteredProducts.length ? (
            <div className="pi-catalog-empty" role="row">
              <strong>No products match these filters.</strong>
              <span>
                Change a filter or clear all filters to restore the index.
              </span>
              <button onClick={clearFilters} type="button">
                Clear filters
              </button>
            </div>
          ) : null}
        </div>
      </div>
      <p className="pi-catalog-grain-note">
        Observed and not-observed counts use distinct retailer store IDs from
        the location master. ZIP codes are address context, not the counting
        grain; service-area retailers are identified separately.
      </p>
    </section>
  );
}

export function PriceMonitoringWorkspace({
  initialView,
  initialTab,
}: Readonly<{ initialView: PriceMonitoringView; initialTab?: string }>) {
  const [view, setView] = useState(initialView);
  const [tab, setTab] = useState<TabId>(normalizeTab(initialTab));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openLocation, setOpenLocation] = useState<Location | null>(null);
  const [locationEvidenceMode, setLocationEvidenceMode] =
    useState<MapMode | null>(null);
  const [overviewMapMode, setOverviewMapMode] = useState<MapMode>("observed");
  const [mapExpanded, setMapExpanded] = useState(false);
  const [architectureView, setArchitectureView] =
    useState<ArchitectureView>("heatmap");
  const [geographyDrawerOpen, setGeographyDrawerOpen] = useState(false);
  const [storeReviewMode, setStoreReviewMode] =
    useState<StoreReviewMode>("price");
  const viewCache = useRef(new Map<string, PriceMonitoringView>());
  const pendingEvidence = useRef<{
    productId: string;
    mode: MapMode;
  } | null>(null);

  useEffect(() => {
    function loadView() {
      const url = new URL(window.location.href);
      const requestedTab = url.searchParams.get("tab");
      if (requestedTab) {
        const nextTab = normalizeTab(requestedTab);
        setTab(nextTab);
        if (requestedTab !== nextTab) {
          url.searchParams.set("tab", nextTab);
          window.history.replaceState(window.history.state, "", url);
        }
      }
      const requestParameters = new URLSearchParams(url.searchParams);
      requestParameters.delete("tab");
      if (!requestParameters.has("retailer")) {
        requestParameters.set("retailer", initialView.retailer.id);
      }
      const cacheKey = requestParameters.toString();
      const cachedView = viewCache.current.get(cacheKey);
      if (cachedView) {
        setView(cachedView);
        setLoading(false);
        setError(null);
        return () => {};
      }
      const controller = new AbortController();
      setLoading(true);
      setError(null);
      fetch(
        `/api/price-monitoring/${encodeURIComponent(initialView.analysis_id)}?${requestParameters.toString()}`,
        { signal: controller.signal },
      )
        .then(async (response) => {
          if (!response.ok)
            throw new Error(`Price view returned ${response.status}`);
          const nextView = (await response.json()) as PriceMonitoringView;
          viewCache.current.set(cacheKey, nextView);
          setView(nextView);
        })
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError")
            return;
          setError(
            reason instanceof Error
              ? reason.message
              : "The price view could not be refreshed.",
          );
        })
        .finally(() => setLoading(false));
      return () => controller.abort();
    }
    const initialUrl = new URL(window.location.href);
    const initialRequestedTab = initialUrl.searchParams.get("tab");
    if (initialRequestedTab) {
      const migratedTab = normalizeTab(initialRequestedTab);
      if (migratedTab !== initialRequestedTab) {
        initialUrl.searchParams.set("tab", migratedTab);
        window.history.replaceState(window.history.state, "", initialUrl);
      }
    }
    const initialParameters = initialUrl.searchParams;
    initialParameters.delete("tab");
    if (!initialParameters.has("retailer")) {
      initialParameters.set("retailer", initialView.retailer.id);
    }
    viewCache.current.set(initialParameters.toString(), initialView);
    let cancel = () => {};
    const listener = () => {
      cancel();
      cancel = loadView();
    };
    window.addEventListener("popstate", listener);
    return () => {
      cancel();
      window.removeEventListener("popstate", listener);
    };
  }, [initialView]);

  useEffect(() => {
    const pending = pendingEvidence.current;
    if (
      pending === null ||
      loading ||
      error !== null ||
      view.filters.product_id !== pending.productId
    ) {
      return;
    }
    setOverviewMapMode(pending.mode);
    setLocationEvidenceMode(pending.mode);
    pendingEvidence.current = null;
  }, [error, loading, view.filters.product_id]);

  function openCatalogProduct(
    productId: string,
    nextTab: TabId,
    evidenceMode?: MapMode,
  ) {
    pendingEvidence.current = evidenceMode
      ? { productId, mode: evidenceMode }
      : null;
    setLocationEvidenceMode(null);
    updateQuery({ product_id: productId, tab: nextTab });
  }

  const contextDefinition = useMemo<ApplicationContextDefinition>(
    () => ({
      label: "Price intelligence context",
      controls: [
        {
          id: "retailer-view",
          label: "Retailer",
          title: "Choose the retailer to monitor",
          description:
            "This module examines one retailer product across its observed location footprint.",
          value: view.retailer.name,
          selectedValue: view.filters.retailer_id,
          defaultValue: "",
          queryParameter: "retailer",
          resetQueryParameters: ["state", "city", "zipcode", "product_id"],
          options: view.filter_options.retailers.map((row) => ({
            value: row.id,
            label: row.name,
            description: "Open this retailer's governed Search evidence.",
          })),
        },
        {
          id: "product-view",
          label: "Product",
          title: "Choose one retailer product",
          description:
            "Prices are compared only across locations carrying this exact retailer product ID.",
          value:
            view.filter_options.products.find(
              (row) => row.value === view.filters.product_id,
            )?.label ?? "Select a product",
          selectedValue: view.filters.product_id ?? "",
          defaultValue: "",
          queryParameter: "product_id",
          options: view.filter_options.products.map((row) => ({
            value: row.value,
            label: row.label,
            description: `${row.brand ?? "Brand unresolved"} · ${count(row.count)} observed locations`,
          })),
        },
        {
          id: "geography-view",
          label: "Geography",
          title: "Scope the visible location footprint",
          description:
            "Geography filters apply consistently to every workspace tab and export.",
          value:
            [view.filters.zipcode, view.filters.city, view.filters.state]
              .filter(Boolean)
              .join(", ") || "United States",
          selectedValue: view.filters.state ?? "",
          defaultValue: "",
          queryParameter: "state",
          resetQueryParameters: ["city", "zipcode"],
          options: [
            {
              value: "",
              label: "All states",
              description:
                "Select the complete United States location footprint.",
            },
            ...view.filter_options.states.map((row) => ({
              value: row.value,
              label: row.label,
              description: `${count(row.count)} eligible product-location observations`,
            })),
          ],
        },
        {
          id: "status-notifications",
          label: "Status & notifications",
          title: "Current assessment and evidence readiness",
          description:
            "Unsupported measures remain unavailable rather than being inferred.",
          value: view.exceptions.length
            ? `${count(view.exceptions.length)} price reviews`
            : view.quality.status === "ready"
              ? "Ready"
              : "Review caveats",
          tone:
            view.quality.status === "ready" && !view.exceptions.length
              ? "ready"
              : "attention",
          facts: [
            {
              label: "Usable price rows",
              value: percent(view.summary.usable_price_rate),
            },
            {
              label: "Observed presence",
              value: percent(view.presence.observed_presence_rate),
            },
            {
              label: "Immutable artifacts",
              value: count(view.source.artifact_checksums.length),
            },
            {
              label: "Observed through",
              value: view.source.observed_end
                ? displayDate(view.source.observed_end)
                : "—",
            },
          ],
          messages: [
            view.exceptions.length
              ? `${count(view.exceptions.length)} store prices meet the deterministic review rule. Open Store Review for exact evidence.`
              : "No store prices meet the current deterministic exception rule.",
            view.presence.definition,
            "PDP identity enrichment never overrides Search price or location.",
          ],
        },
      ],
    }),
    [view],
  );
  useApplicationContextDefinition(contextDefinition);

  const selectedProduct = view.filters.product_id
    ? (view.products[0] ?? null)
    : null;
  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "home", label: "Home" },
    { id: "overview", label: "Product Overview" },
    { id: "price-architecture", label: "Price Architecture" },
    { id: "store-review", label: "Store Review" },
    { id: "history", label: "Product History" },
  ];

  if (!selectedProduct) {
    return (
      <>
        <header className="pm-masthead pi-masthead">
          <div>
            <p className="eyebrow">Price Intelligence · {view.retailer.name}</p>
            <h1>{view.product_pack.name}</h1>
            <p>
              Select one retailer product to examine its store-level price
              footprint.
            </p>
          </div>
        </header>
        <nav
          className="pm-tabs pi-tabs"
          aria-label="Price intelligence workspaces"
        >
          <button aria-current="page" type="button">
            Home
          </button>
        </nav>
        {loading || error ? (
          <p className="pi-context-status" aria-live="polite">
            {loading ? "Refreshing evidence…" : error}
          </p>
        ) : null}
        <ProductCatalog
          loading={loading}
          onOpenProduct={openCatalogProduct}
          view={view}
        />
        {loading ? (
          <div className="pi-route-loading" role="status" aria-live="polite">
            <span aria-hidden="true" />
            <strong>Loading governed product evidence…</strong>
          </div>
        ) : null}
      </>
    );
  }

  const stats = selectedProduct.price_stats;
  const unitPrice = selectedProduct.unit_price;
  const typicalUnitPrice =
    unitPrice.price_stats.modal_price ??
    unitPrice.price_stats.observation_median;
  const availability = selectedProduct.availability;
  const sponsorship = selectedProduct.sponsorship ?? {
    status: "unavailable" as const,
    known_observations: 0,
    sponsorship_observations: 0,
    rate: null,
    definition:
      "Sponsorship was not retained in this analysis snapshot. Future collections use the Search is_sponsored boolean.",
  };
  const distributionGaps = view.distribution_gaps ?? {
    status: "search_non_observation" as const,
    definition:
      "This analysis predates location-level Search non-observation evidence.",
    location_display: {
      returned: 0,
      total: view.presence.not_observed_locations,
      sampled: false,
      missing_location_details: view.presence.not_observed_locations,
    },
    geographies: [],
    locations: [],
  };
  const topGapMarket = distributionGaps.geographies[0] ?? null;

  return (
    <>
      <header className="pm-masthead pi-masthead">
        <div className="pi-product-title">
          {selectedProduct.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={selectedProduct.image_url} alt="" />
          ) : (
            <span aria-hidden="true">P</span>
          )}
          <div>
            <p className="eyebrow">Price Intelligence · {view.retailer.name}</p>
            <h1>{selectedProduct.name}</h1>
            <p>
              {selectedProduct.brand ?? "Brand unresolved"} ·{" "}
              {brandLabels[selectedProduct.brand_type]} · Retailer ID{" "}
              {selectedProduct.product_id}
            </p>
          </div>
        </div>
        <dl>
          <div>
            <dt>Observed through</dt>
            <dd>
              {view.source.observed_end
                ? displayDate(view.source.observed_end)
                : "Current run"}
            </dd>
          </div>
          <div>
            <dt>Locations</dt>
            <dd>{count(selectedProduct.locations)}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>Search price</dd>
          </div>
        </dl>
      </header>
      <nav
        className="pm-tabs pi-tabs"
        aria-label="Price intelligence workspaces"
      >
        {tabs.map((item) => (
          <button
            aria-current={tab === item.id ? "page" : undefined}
            key={item.id}
            onClick={() => {
              if (item.id === "home") {
                updateQuery({ product_id: null, tab: "home" });
              } else {
                updateTab(item.id);
              }
              setTab(item.id);
            }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>
      {loading || error ? (
        <p className="pi-context-status" aria-live="polite">
          {loading ? "Refreshing evidence…" : error}
        </p>
      ) : null}

      {tab === "home" ? (
        <ProductCatalog
          loading={loading}
          onOpenProduct={openCatalogProduct}
          view={view}
        />
      ) : null}

      {tab === "overview" ? (
        <section className="pm-tab-content pi-tab-content">
          <div className="pm-metric-grid pi-metric-grid">
            <article>
              <span>Observed presence</span>
              <strong>{percent(view.presence.observed_presence_rate)}</strong>
              <small>
                {count(view.presence.observed_locations)} of{" "}
                {count(view.presence.eligible_locations)} planned locations
              </small>
            </article>
            <article>
              <span>Median shelf price</span>
              <strong>{currency(stats.observation_median)}</strong>
              <small>
                {unitPrice.status === "observed"
                  ? `${unitPrice.label}: ${unitCurrency(typicalUnitPrice, unitPrice.unit)}`
                  : "Unit price unavailable"}
              </small>
              <small>
                Observed range {currency(stats.minimum)}–
                {currency(stats.maximum)}
              </small>
              <small>
                {count(stats.observation_count)} exact-product observations
              </small>
            </article>
            <article>
              <span>Price consistency</span>
              <strong>{percent(selectedProduct.consistency_rate)}</strong>
              <small>At modal price ± Product Pack tolerance</small>
            </article>
            <article>
              <span>Stores to review</span>
              <strong>{count(view.exceptions.length)}</strong>
              <small>Unusual exact-product prices</small>
            </article>
          </div>
          <article className="pm-panel pi-retail-signals">
            <header>
              <div>
                <p className="section-kicker">Retail signals</p>
                <h2>What else this Search snapshot reveals</h2>
              </div>
            </header>
            <div className="pi-signal-grid">
              <div>
                <span>Geographic breadth</span>
                <strong>
                  {count(selectedProduct.states)} states ·{" "}
                  {count(selectedProduct.cities)} cities
                </strong>
                <small>
                  Location hierarchy is sourced from the retailer location
                  master.
                </small>
              </div>
              <div>
                <span>Sponsored visibility</span>
                <strong>
                  {sponsorship.status === "observed"
                    ? percent(sponsorship.rate)
                    : "Not captured in this snapshot"}
                </strong>
                <small>{sponsorship.definition}</small>
              </div>
              <div>
                <span>Largest non-observation market</span>
                <strong>
                  {topGapMarket
                    ? `${topGapMarket.label} · ${count(topGapMarket.not_observed_locations)}`
                    : "No known non-observations"}
                </strong>
                <small>
                  Review signal only; a Search omission is not proof of
                  non-carriage.
                </small>
              </div>
            </div>
          </article>
          <PdpReferencePanel product={selectedProduct} />
          <div className="pm-two-column pi-overview-grid">
            <article className="pm-panel">
              <header>
                <div>
                  <p className="section-kicker">Exact-product footprint</p>
                  <h2>
                    {overviewMapMode === "observed"
                      ? "Where the product was observed"
                      : "Where it did not appear in Search"}
                  </h2>
                </div>
                <div className="pi-panel-actions">
                  <button
                    className="button secondary"
                    onClick={() => setLocationEvidenceMode(overviewMapMode)}
                    type="button"
                  >
                    View locations
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => setMapExpanded(true)}
                    type="button"
                  >
                    Expand map
                  </button>
                </div>
              </header>
              <InteractiveEvidenceRetailMap
                clusterPoints={false}
                detail="summary"
                key={"summary:" + JSON.stringify(view.filters)}
                mode={overviewMapMode}
                onModeChange={setOverviewMapMode}
                onScopeChange={updateQuery}
                view={view}
              />
            </article>
            <article className="pm-panel">
              <header>
                <div>
                  <p className="section-kicker">Price distribution</p>
                  <h2>How store prices are structured</h2>
                </div>
                <button
                  className="text-link"
                  onClick={() => {
                    updateTab("price-architecture");
                    setTab("price-architecture");
                  }}
                  type="button"
                >
                  Open architecture →
                </button>
              </header>
              <PriceHistogram product={selectedProduct} />
              <dl className="pi-summary-list">
                <div>
                  <dt>Most common price</dt>
                  <dd>{currency(stats.modal_price)}</dd>
                </div>
                <div>
                  <dt>Observed range</dt>
                  <dd>
                    {currency(stats.minimum)}–{currency(stats.maximum)}
                  </dd>
                </div>
                <div>
                  <dt>{unitPrice.label ?? "Unit price"}</dt>
                  <dd>
                    {unitPrice.status === "observed"
                      ? unitCurrency(typicalUnitPrice, unitPrice.unit)
                      : "Unavailable"}
                  </dd>
                </div>
                <div>
                  <dt>Availability signal</dt>
                  <dd>
                    {availability.status === "observed"
                      ? percent(availability.rate)
                      : "Not supported"}
                  </dd>
                </div>
              </dl>
            </article>
          </div>
        </section>
      ) : null}

      {tab === "price-architecture" ? (
        <section className="pm-tab-content pi-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">One product · many stores</p>
              <h2>Price architecture</h2>
            </div>
            <p>
              All statistics compare the same retailer product ID. Package mix
              and competitor matching are excluded.
            </p>
          </article>
          <article className="pm-panel pi-architecture-panel pi-architecture-compact">
            <header>
              <div>
                <p className="section-kicker">Store price distribution</p>
                <h2>{count(stats.observation_count)} observed prices</h2>
              </div>
              <span className="pi-evidence-pill">Search authoritative</span>
            </header>
            <div className="pi-architecture-layout">
              <PriceHistogram product={selectedProduct} />
              <div className="pi-architecture-metrics">
                <div>
                  <span>Observed range</span>
                  <strong>
                    {currency(stats.minimum)}–{currency(stats.maximum)}
                  </strong>
                  <small>
                    Q1 {currency(stats.q1)} · Q3 {currency(stats.q3)}
                  </small>
                </div>
                <div>
                  <span>Median shelf price</span>
                  <strong>{currency(stats.observation_median)}</strong>
                  <small>Exact-product, location-weighted</small>
                </div>
                <div>
                  <span>Most common price</span>
                  <strong>{currency(stats.modal_price)}</strong>
                  <small>{percent(stats.modal_share)} of observations</small>
                </div>
                <div>
                  <span>In stock</span>
                  <strong>
                    {availability.status === "observed"
                      ? percent(availability.rate)
                      : "Unavailable"}
                  </strong>
                  <small>Positive Search price</small>
                </div>
                <div>
                  <span>Sponsored</span>
                  <strong>
                    {sponsorship.status === "observed"
                      ? percent(sponsorship.rate)
                      : "Unavailable"}
                  </strong>
                  <small>Search is_sponsored only</small>
                </div>
                <div>
                  <span>Price consistency</span>
                  <strong>{percent(selectedProduct.consistency_rate)}</strong>
                  <small>Within Product Pack modal tolerance</small>
                </div>
              </div>
            </div>
            <div className="pi-signal-definitions">
              <div>
                <strong>In-stock rule</strong>
                <span>{availability.definition}</span>
              </div>
              <div>
                <strong>Sponsorship rule</strong>
                <span>{sponsorship.definition}</span>
              </div>
            </div>
          </article>
          <article className="pm-panel">
            <header>
              <div>
                <p className="section-kicker">Geographic structure</p>
                <h2>Price ranges by visible market</h2>
              </div>
              <div className="pi-panel-actions">
                <div
                  aria-label="Geographic price visualization"
                  className="pi-view-toggle"
                  role="group"
                >
                  <button
                    aria-pressed={architectureView === "heatmap"}
                    onClick={() => setArchitectureView("heatmap")}
                    type="button"
                  >
                    Heatmap table
                  </button>
                  <button
                    aria-pressed={architectureView === "map"}
                    onClick={() => setArchitectureView("map")}
                    type="button"
                  >
                    {view.filters.city
                      ? "City map"
                      : view.filters.state
                        ? "State map"
                        : "US map"}
                  </button>
                </div>
                {view.filters.state ||
                view.filters.city ||
                view.filters.zipcode ? (
                  <button
                    className="button secondary"
                    onClick={() =>
                      updateQuery({ state: null, city: null, zipcode: null })
                    }
                    type="button"
                  >
                    Clear geography
                  </button>
                ) : null}
                <button
                  className="button secondary"
                  onClick={() => setGeographyDrawerOpen(true)}
                  type="button"
                >
                  View details
                </button>
              </div>
            </header>
            {architectureView === "heatmap" ? (
              <GeographicHeatmap view={view} />
            ) : (
              <RetailMap view={view} />
            )}
          </article>
        </section>
      ) : null}

      {tab === "store-review" ? (
        <section className="pm-tab-content pi-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Deterministic evidence review</p>
              <h2>Store review</h2>
            </div>
            <p>
              Review unusual exact-product prices or planned locations where the
              product did not appear in Search. Neither signal prescribes an
              action by itself.
            </p>
          </article>
          <div
            aria-label="Store review queue"
            className="pi-review-switch"
            role="group"
          >
            <button
              aria-pressed={storeReviewMode === "price"}
              onClick={() => setStoreReviewMode("price")}
              type="button"
            >
              <span>Unusual prices</span>
              <strong>{count(view.exceptions.length)}</strong>
              <small>Deterministic exact-product price review</small>
            </button>
            <button
              aria-pressed={storeReviewMode === "not_observed"}
              onClick={() => setStoreReviewMode("not_observed")}
              type="button"
            >
              <span>Not observed in Search</span>
              <strong>{count(view.presence.not_observed_locations)}</strong>
              <small>Inconclusive presence review</small>
            </button>
          </div>
          {storeReviewMode === "price" ? (
            <>
              <article className="pi-governance-callout pi-iqr-explainer">
                <strong>What “IQR price review” means</strong>
                <p>
                  IQR is the middle 50% of observed prices: Q3 minus Q1. A store
                  is flagged when its price is below Q1 − 1.5×IQR or above Q3 +
                  1.5×IQR. If every middle price is identical, the Product Pack
                  tolerance around the most common price is used instead. A flag
                  means “verify this evidence,” not “the price is wrong.”
                </p>
              </article>
              {view.exceptions.length ? (
                <article className="pm-panel">
                  <header>
                    <div>
                      <p className="section-kicker">Unusual price evidence</p>
                      <h2>{count(view.exceptions.length)} stores to review</h2>
                    </div>
                  </header>
                  <div className="pm-location-table-wrap">
                    <table className="pm-location-table">
                      <thead>
                        <tr>
                          <th>Store</th>
                          <th>Observed price</th>
                          <th>Median reference</th>
                          <th>Difference</th>
                          <th>Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {view.exceptions.map((row) => (
                          <tr key={row.id}>
                            <td>
                              <strong>
                                {row.store_name ??
                                  (row.store_number
                                    ? `Store ${row.store_number}`
                                    : row.zipcode)}
                              </strong>
                              <small>
                                {[row.city, row.state]
                                  .filter(Boolean)
                                  .join(", ")}
                              </small>
                            </td>
                            <td>
                              <strong>{currency(row.price)}</strong>
                            </td>
                            <td>{currency(row.reference_price)}</td>
                            <td
                              className={
                                row.difference > 0 ? "pi-up" : "pi-down"
                              }
                            >
                              {signedCurrency(row.difference)}
                            </td>
                            <td>
                              <span className={`pi-severity ${row.severity}`}>
                                {row.severity}
                              </span>
                              <small>{row.reason}</small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </article>
              ) : (
                <article className="pi-empty-workspace">
                  <span>✓</span>
                  <div>
                    <h2>No unusual prices under the current review rule</h2>
                    <p>
                      This does not assert that every price is correct; it means
                      none meets the deterministic outlier rule.
                    </p>
                  </div>
                </article>
              )}
            </>
          ) : (
            <>
              <div className="pm-metric-grid pi-metric-grid">
                <article>
                  <span>Planned locations</span>
                  <strong>{count(view.presence.eligible_locations)}</strong>
                  <small>Collection scope denominator</small>
                </article>
                <article>
                  <span>Observed</span>
                  <strong>{count(view.presence.observed_locations)}</strong>
                  <small>Product appeared with a positive Search price</small>
                </article>
                <article>
                  <span>Not observed</span>
                  <strong>{count(view.presence.not_observed_locations)}</strong>
                  <small>Review signal, not confirmed non-carriage</small>
                </article>
              </div>
              <article className="pi-governance-callout">
                <strong>
                  Why “not observed” is different from “not carried”
                </strong>
                <p>
                  Keyword Search returns a bounded result set. A carried product
                  can be omitted from those results, so the app does not convert
                  an omission into a confirmed distribution gap.
                </p>
              </article>
              <article className="pm-panel">
                <header>
                  <div>
                    <p className="section-kicker">Market concentration</p>
                    <h2>Where non-observations are concentrated</h2>
                  </div>
                  <button
                    className="button secondary"
                    onClick={() => setLocationEvidenceMode("not_observed")}
                    type="button"
                  >
                    View all locations
                  </button>
                </header>
                <GapMarketTable gaps={distributionGaps} />
              </article>
            </>
          )}
        </section>
      ) : null}

      {tab === "history" ? (
        <section className="pm-tab-content pi-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Comparable snapshots only</p>
              <h2>Product history</h2>
            </div>
            <p>
              History will compare the same retailer, product, Product Pack,
              location scope, and collection method.
            </p>
          </article>
          <article className="pi-empty-workspace">
            <span>↗</span>
            <div>
              <h2>More comparable snapshots are required</h2>
              <p>
                {view.movement.reason} No synthetic prior periods or inferred
                events are shown.
              </p>
              <dl>
                <div>
                  <dt>Current observation</dt>
                  <dd>
                    {view.source.observed_end
                      ? displayDate(view.source.observed_end)
                      : "Available"}
                  </dd>
                </div>
                <div>
                  <dt>Comparability</dt>
                  <dd>Current snapshot only</dd>
                </div>
                <div>
                  <dt>Future windows</dt>
                  <dd>Prior · 4 · 13 · 26 periods</dd>
                </div>
              </dl>
            </div>
          </article>
        </section>
      ) : null}

      {locationEvidenceMode ? (
        <LocationEvidenceDrawer
          mode={locationEvidenceMode}
          onClose={() => setLocationEvidenceMode(null)}
          onOpenLocation={(location) => {
            setLocationEvidenceMode(null);
            setOpenLocation(location);
          }}
          product={selectedProduct}
          view={view}
        />
      ) : null}

      {geographyDrawerOpen ? (
        <GeographyDrawer
          onClose={() => setGeographyDrawerOpen(false)}
          view={view}
        />
      ) : null}

      {mapExpanded ? (
        <FootprintModal
          mode={overviewMapMode}
          onClose={() => setMapExpanded(false)}
          onModeChange={setOverviewMapMode}
          view={view}
        />
      ) : null}
      {loading ? (
        <div className="pi-route-loading" role="status" aria-live="polite">
          <span aria-hidden="true" />
          <strong>Loading governed product evidence…</strong>
        </div>
      ) : null}

      {openLocation ? (
        <StoreDrawer
          location={openLocation}
          product={selectedProduct}
          onClose={() => setOpenLocation(null)}
        />
      ) : null}
    </>
  );
}
