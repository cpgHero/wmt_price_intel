"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { GeometryCollection, Topology } from "topojson-specification";
import { feature } from "topojson-client";
import statesTopologySource from "us-atlas/states-10m.json";

import {
  type ApplicationContextDefinition,
  useApplicationContextDefinition,
} from "@/app/components/application-context";
import type { PriceMonitoringView } from "@/lib/api";
import { displayDate } from "@/lib/presentation";

type Product = PriceMonitoringView["products"][number];
type Location = PriceMonitoringView["locations"][number];
type TabId =
  | "home"
  | "overview"
  | "footprint"
  | "price-architecture"
  | "distribution-gaps"
  | "store-exceptions"
  | "market-benchmarks"
  | "history";

const tabIds: readonly TabId[] = [
  "home",
  "overview",
  "footprint",
  "price-architecture",
  "distribution-gaps",
  "store-exceptions",
  "market-benchmarks",
  "history",
];

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
    features: Array<{
      id?: string | number;
      geometry: { type: string; coordinates: unknown };
    }>;
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

function coordinateRingPath(value: unknown) {
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
      const { x, y } = projectCoordinate(longitude, latitude);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ")} Z`;
}

function geometryPath(geometry: { type: string; coordinates: unknown }) {
  if (!Array.isArray(geometry.coordinates)) return "";
  const polygons =
    geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons
    .flatMap((polygon) => (Array.isArray(polygon) ? polygon : []))
    .map(coordinateRingPath)
    .filter(Boolean)
    .join(" ");
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
  return (
    <div className="pm-map-stage pi-map-stage">
      <svg
        className="pm-map"
        role="img"
        aria-label={`${view.retailer.name} exact-product observed price footprint`}
        viewBox="0 0 960 520"
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
          {marketPoints.map((row) => {
            const point = projectCoordinate(row.longitude, row.latitude);
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

function GapMarketTable({ view }: Readonly<{ view: PriceMonitoringView }>) {
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
          {view.distribution_gaps.geographies.slice(0, 100).map((row) => (
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

function GapLocationTable({ view }: Readonly<{ view: PriceMonitoringView }>) {
  const locations = view.distribution_gaps.locations.slice(0, 200);
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
      {view.distribution_gaps.location_display.total > locations.length ? (
        <p className="pi-table-summary">
          Showing {count(locations.length)} of{" "}
          {count(view.distribution_gaps.location_display.total)}
          {view.distribution_gaps.location_display.missing_location_details
            ? ` non-observations; ${count(view.distribution_gaps.location_display.missing_location_details)} planned locations lack complete location-master detail.`
            : " non-observations."}
        </p>
      ) : null}
    </div>
  );
}

function ProductCatalog({ view }: Readonly<{ view: PriceMonitoringView }>) {
  return (
    <section className="pi-product-catalog">
      <header>
        <div>
          <p className="section-kicker">Single-retailer product intelligence</p>
          <h2>Select a product to open its workspace</h2>
        </div>
        <p>
          Products are ranked by the number of locations where they appeared in
          governed Search evidence.
        </p>
      </header>
      <div>
        {view.filter_options.products.map((product) => (
          <button
            key={product.value}
            onClick={() =>
              updateQuery({ product_id: product.value, tab: "overview" })
            }
            type="button"
          >
            {product.image_url ? (
              <img src={product.image_url} alt="" />
            ) : (
              <span aria-hidden="true">P</span>
            )}
            <div>
              <small>{brandLabels[product.brand_type]}</small>
              <strong>{product.label}</strong>
              <p>{product.brand ?? "Brand unresolved"}</p>
            </div>
            <b>{count(product.count)} locations →</b>
          </button>
        ))}
      </div>
    </section>
  );
}

export function PriceMonitoringWorkspace({
  initialView,
  initialTab,
}: Readonly<{ initialView: PriceMonitoringView; initialTab?: string }>) {
  const [view, setView] = useState(initialView);
  const [tab, setTab] = useState<TabId>(
    tabIds.includes(initialTab as TabId) ? (initialTab as TabId) : "overview",
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openLocation, setOpenLocation] = useState<Location | null>(null);
  const viewCache = useRef(new Map<string, PriceMonitoringView>());

  useEffect(() => {
    function loadView() {
      const url = new URL(window.location.href);
      const nextTab = url.searchParams.get("tab") as TabId | null;
      if (nextTab) setTab(nextTab);
      const requestParameters = new URLSearchParams(url.searchParams);
      requestParameters.delete("tab");
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
    const initialParameters = new URL(window.location.href).searchParams;
    initialParameters.delete("tab");
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
          options: view.filter_options.states.map((row) => ({
            value: row.value,
            label: row.label,
            description: `${count(row.count)} eligible product-location observations`,
          })),
        },
        {
          id: "source-readiness",
          label: "Source readiness",
          title: "Evidence, quality, and metric eligibility",
          description:
            "Unsupported measures remain unavailable rather than being inferred.",
          value: view.quality.status === "ready" ? "Ready" : "Review caveats",
          tone: view.quality.status === "ready" ? "ready" : "attention",
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
    { id: "footprint", label: "Product Footprint" },
    { id: "price-architecture", label: "Price Architecture" },
    { id: "distribution-gaps", label: "Distribution Gaps" },
    { id: "store-exceptions", label: "Store Exceptions" },
    { id: "market-benchmarks", label: "Market Benchmarks" },
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
        <section className="pm-filter-row">
          <label>
            <span>Product</span>
            <select
              value=""
              onChange={(event) =>
                updateQuery({ product_id: event.target.value || null })
              }
            >
              <option value="">Select a product</option>
              {view.filter_options.products.map((row) => (
                <option value={row.value} key={row.value}>
                  {row.label} · {count(row.count)} locations
                </option>
              ))}
            </select>
          </label>
          <span className="pm-loading-status">
            {loading ? "Refreshing evidence…" : error}
          </span>
        </section>
        <ProductCatalog view={view} />
      </>
    );
  }

  const stats = selectedProduct.price_stats;
  const availability = selectedProduct.availability;
  const promotion = selectedProduct.promotion;
  const sponsorship = selectedProduct.sponsorship;
  const topGapMarket = view.distribution_gaps.geographies[0] ?? null;
  const assessment = view.exceptions.length
    ? `${count(view.exceptions.length)} store prices fall outside the exact product's 1.5×IQR range and merit review.`
    : stats.range === 0
      ? "The selected product was observed at one consistent price across the visible store footprint."
      : `The selected product spans ${currency(stats.minimum)} to ${currency(stats.maximum)} across ${count(selectedProduct.locations)} observed locations.`;

  return (
    <>
      <header className="pm-masthead pi-masthead">
        <div className="pi-product-title">
          {selectedProduct.image_url ? (
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
              updateTab(item.id);
              setTab(item.id);
            }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>
      <section
        className="pm-filter-row"
        aria-label="Product and geography filters"
      >
        <label>
          <span>Product</span>
          <select
            value={view.filters.product_id ?? ""}
            onChange={(event) =>
              updateQuery({ product_id: event.target.value || null })
            }
          >
            {view.filter_options.products.map((row) => (
              <option value={row.value} key={row.value}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>State</span>
          <select
            value={view.filters.state ?? ""}
            onChange={(event) =>
              updateQuery({
                state: event.target.value || null,
                city: null,
                zipcode: null,
              })
            }
          >
            <option value="">All states</option>
            {view.filter_options.states.map((row) => (
              <option value={row.value} key={row.value}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>City</span>
          <select
            disabled={!view.filters.state}
            value={view.filters.city ?? ""}
            onChange={(event) =>
              updateQuery({
                city: event.target.value || null,
                zipcode: null,
              })
            }
          >
            <option value="">All cities</option>
            {view.filter_options.cities.map((row) => (
              <option value={row.value} key={row.value}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>ZIP code</span>
          <select
            disabled={!view.filters.city}
            value={view.filters.zipcode ?? ""}
            onChange={(event) =>
              updateQuery({ zipcode: event.target.value || null })
            }
          >
            <option value="">All ZIP codes</option>
            {view.filter_options.zipcodes.map((row) => (
              <option value={row.value} key={row.value}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        {view.filters.state || view.filters.city || view.filters.zipcode ? (
          <button
            className="text-link"
            onClick={() =>
              updateQuery({ state: null, city: null, zipcode: null })
            }
            type="button"
          >
            Reset geography
          </button>
        ) : null}
        <span className="pm-loading-status" aria-live="polite">
          {loading
            ? "Refreshing evidence…"
            : (error ??
              `${count(view.summary.eligible_observations)} exact-product observations`)}
        </span>
      </section>

      {tab === "home" ? <ProductCatalog view={view} /> : null}

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
                {count(stats.observation_count)} exact-product observations
              </small>
            </article>
            <article>
              <span>Price consistency</span>
              <strong>{percent(selectedProduct.consistency_rate)}</strong>
              <small>At modal price ± Product Pack tolerance</small>
            </article>
            <article>
              <span>Store exceptions</span>
              <strong>{count(view.exceptions.length)}</strong>
              <small>Governed IQR/modal rule</small>
            </article>
          </div>
          <article className="pi-assessment">
            <div>
              <p className="section-kicker">Current assessment</p>
              <h2>
                {view.exceptions.length
                  ? "Price exceptions are concentrated in a limited store set"
                  : "The current exact-product footprint is ready to explore"}
              </h2>
            </div>
            <p>{assessment}</p>
          </article>
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
          <div className="pm-two-column pi-overview-grid">
            <article className="pm-panel">
              <header>
                <div>
                  <p className="section-kicker">Exact-product footprint</p>
                  <h2>Where the product was observed</h2>
                </div>
                <button
                  className="text-link"
                  onClick={() => {
                    updateTab("footprint");
                    setTab("footprint");
                  }}
                  type="button"
                >
                  Open footprint →
                </button>
              </header>
              <RetailMap view={view} />
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

      {tab === "footprint" ? (
        <section className="pm-tab-content pi-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Country → state → city → store</p>
              <h2>Exact-product observed footprint</h2>
            </div>
            <p>
              Map color represents this product&apos;s median observed price. It
              does not mix products or imply that an uncolored location does not
              carry the item.
            </p>
          </article>
          <RetailMap view={view} />
          <article className="pm-panel">
            <header>
              <div>
                <p className="section-kicker">Store evidence</p>
                <h2>{count(view.location_display.total)} observed locations</h2>
              </div>
              <button
                className="button secondary"
                onClick={() =>
                  downloadCsv(
                    view.analysis_id,
                    view.retailer.id,
                    selectedProduct,
                  )
                }
                type="button"
              >
                Download evidence
              </button>
            </header>
            <LocationTable view={view} onOpen={setOpenLocation} />
          </article>
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
          <div className="pi-five-stat">
            <article>
              <span>Minimum</span>
              <strong>{currency(stats.minimum)}</strong>
            </article>
            <article>
              <span>Q1</span>
              <strong>{currency(stats.q1)}</strong>
            </article>
            <article>
              <span>Median</span>
              <strong>{currency(stats.observation_median)}</strong>
            </article>
            <article>
              <span>Q3</span>
              <strong>{currency(stats.q3)}</strong>
            </article>
            <article>
              <span>Maximum</span>
              <strong>{currency(stats.maximum)}</strong>
            </article>
          </div>
          <article className="pm-panel pi-architecture-panel">
            <header>
              <div>
                <p className="section-kicker">Store price distribution</p>
                <h2>{count(stats.observation_count)} observed prices</h2>
              </div>
              <span className="pi-evidence-pill">Search authoritative</span>
            </header>
            <PriceHistogram product={selectedProduct} />
            <div className="pi-signal-grid">
              <div>
                <span>Modal price</span>
                <strong>{currency(stats.modal_price)}</strong>
                <small>{percent(stats.modal_share)} of observations</small>
              </div>
              <div>
                <span>Availability</span>
                <strong>
                  {availability.status === "observed"
                    ? percent(availability.rate)
                    : "Unavailable"}
                </strong>
                <small>{availability.definition}</small>
              </div>
              <div>
                <span>Promotion</span>
                <strong>
                  {promotion.status === "observed"
                    ? percent(promotion.rate)
                    : "Unavailable"}
                </strong>
                <small>{promotion.definition}</small>
              </div>
              <div>
                <span>Sponsorship</span>
                <strong>
                  {sponsorship.status === "observed"
                    ? percent(sponsorship.rate)
                    : "Unavailable"}
                </strong>
                <small>{sponsorship.definition}</small>
              </div>
            </div>
          </article>
          <article className="pm-panel">
            <header>
              <div>
                <p className="section-kicker">Geographic structure</p>
                <h2>Price ranges by visible market</h2>
              </div>
            </header>
            <MarketTable view={view} />
          </article>
        </section>
      ) : null}

      {tab === "distribution-gaps" ? (
        <section className="pm-tab-content pi-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Evidence-aware presence</p>
              <h2>Presence and distribution gaps</h2>
            </div>
            <p>{view.presence.definition}</p>
          </article>
          <div className="pm-metric-grid pi-metric-grid">
            <article>
              <span>Observed locations</span>
              <strong>{count(view.presence.observed_locations)}</strong>
              <small>Product appeared in Search</small>
            </article>
            <article>
              <span>Planned locations</span>
              <strong>{count(view.presence.eligible_locations)}</strong>
              <small>Collection scope denominator</small>
            </article>
            <article>
              <span>Not observed</span>
              <strong>{count(view.presence.not_observed_locations)}</strong>
              <small>Inconclusive—not called a gap</small>
            </article>
            <article>
              <span>Confirmed gaps</span>
              <strong>{count(view.presence.confirmed_gap_locations)}</strong>
              <small>Requires explicit product-specific evidence</small>
            </article>
          </div>
          <article className="pi-governance-callout">
            <strong>Why “not observed” is different from “not carried”</strong>
            <p>
              A keyword Search call returns a bounded result set. A product can
              be carried but omitted from that result, so this view will not
              convert absence into a confirmed distribution gap.
            </p>
          </article>
          <article className="pm-panel">
            <header>
              <div>
                <p className="section-kicker">Market concentration</p>
                <h2>Where product non-observations are concentrated</h2>
              </div>
            </header>
            <GapMarketTable view={view} />
          </article>
          <article className="pm-panel">
            <header>
              <div>
                <p className="section-kicker">Location review list</p>
                <h2>
                  {count(view.distribution_gaps.location_display.total)} planned
                  locations where the product was not observed
                </h2>
              </div>
            </header>
            <GapLocationTable view={view} />
          </article>
        </section>
      ) : null}

      {tab === "store-exceptions" ? (
        <section className="pm-tab-content pi-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Deterministic review queue</p>
              <h2>Store price exceptions</h2>
            </div>
            <p>
              Exceptions use the exact-product 1.5×IQR range, with the Product
              Pack modal-price tolerance when IQR is zero. They identify
              evidence to review, not prescribed actions.
            </p>
          </article>
          {view.exceptions.length ? (
            <article className="pm-panel">
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
                            {[row.city, row.state].filter(Boolean).join(", ")}
                          </small>
                        </td>
                        <td>
                          <strong>{currency(row.price)}</strong>
                        </td>
                        <td>{currency(row.reference_price)}</td>
                        <td
                          className={row.difference > 0 ? "pi-up" : "pi-down"}
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
                <h2>No IQR price exceptions in the visible footprint</h2>
                <p>
                  This does not assert that every price is correct; it means
                  none meets the current deterministic outlier rule.
                </p>
              </div>
            </article>
          )}
        </section>
      ) : null}

      {tab === "market-benchmarks" ? (
        <section className="pm-tab-content pi-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Internal retailer benchmarks</p>
              <h2>How the same product varies by market</h2>
            </div>
            <p>
              Price is presented neutrally. A lower internal shelf price is not
              automatically labeled better or worse.
            </p>
          </article>
          <article className="pm-panel">
            <MarketTable view={view} />
          </article>
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
