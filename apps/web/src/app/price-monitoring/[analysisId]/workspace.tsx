"use client";

import { useEffect, useMemo, useState } from "react";
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
type TabId = "overview" | "products" | "geography" | "brands" | "quality";

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

function updateQuery(parameters: Record<string, string | null>) {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(parameters)) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  window.history.replaceState(window.history.state, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function PriceRange({ product }: Readonly<{ product: Product }>) {
  const stats = product.price_stats;
  const span = Math.max((stats.maximum ?? 0) - (stats.minimum ?? 0), 0);
  const modalPosition =
    span > 0 && stats.modal_price !== null && stats.minimum !== null
      ? ((stats.modal_price - stats.minimum) / span) * 100
      : 50;
  return (
    <div className="pm-price-range">
      <div>
        <span>{currency(stats.minimum)}</span>
        <i style={{ left: `${modalPosition}%` }} title="Most common price" />
        <span>{currency(stats.maximum)}</span>
      </div>
      <small>
        Most common {currency(stats.modal_price)} · {percent(stats.modal_share)}{" "}
        of observations
      </small>
    </div>
  );
}

function RetailMap({ view }: Readonly<{ view: PriceMonitoringView }>) {
  const stateRows = new Map(
    view.geographies
      .filter((row) => row.level === "state")
      .map((row) => [row.key, row]),
  );
  const maximumRange = Math.max(
    0.01,
    ...view.geographies.map((row) => row.price_stats.range ?? 0),
  );
  const points = view.filters.state ? view.locations : [];
  return (
    <div className="pm-map-stage">
      <svg
        className="pm-map"
        role="img"
        aria-label={`${view.retailer.name} observed price geography`}
        viewBox="0 0 960 520"
      >
        <g className="pm-state-layer">
          {stateFeatures.map((state) => {
            const fips = String(state.id ?? "").padStart(2, "0");
            const stateCode = stateByFips[fips];
            const geography = stateRows.get(stateCode);
            const intensity = geography
              ? 0.18 + 0.7 * ((geography.price_stats.range ?? 0) / maximumRange)
              : 0;
            return (
              <path
                aria-label={
                  geography
                    ? `${stateCode}: ${count(geography.locations)} locations, ${currency(geography.price_stats.observation_median)} median package price`
                    : stateCode
                }
                className={`${geography ? "has-data" : ""} ${view.filters.state === stateCode ? "selected" : ""}`}
                d={geometryPath(state.geometry)}
                key={fips}
                onClick={() => {
                  if (geography) updateQuery({ state: stateCode, city: null });
                }}
                role={geography ? "button" : undefined}
                style={geography ? { fillOpacity: intensity } : undefined}
                tabIndex={geography ? 0 : undefined}
              />
            );
          })}
        </g>
        <g className="pm-location-layer">
          {points
            .filter((row) => row.latitude !== null && row.longitude !== null)
            .map((row) => {
              const point = projectCoordinate(row.longitude!, row.latitude!);
              return (
                <circle
                  aria-label={`${row.store_name ?? row.store_number ?? row.zipcode}: median ${currency(row.median_price)}`}
                  cx={point.x}
                  cy={point.y}
                  key={row.scope_key}
                  r={view.filters.city === row.city ? 4.5 : 2.8}
                />
              );
            })}
        </g>
      </svg>
      <aside className="pm-map-legend">
        <span>Price range across observed products</span>
        <div>
          <i /> <i /> <i /> <i />
        </div>
        <small>Lower variation</small>
        <small>Higher variation</small>
        <p>
          {view.filters.state
            ? `${count(points.length)} observed locations in ${view.filters.city ?? view.filters.state}. Dots represent stores or service areas.`
            : "Select a colored state to inspect cities and individual retailer locations."}
        </p>
      </aside>
    </div>
  );
}

function ProductDrawer({
  product,
  retailer,
  onClose,
}: Readonly<{
  product: Product;
  retailer: string;
  onClose: () => void;
}>) {
  function downloadLocations() {
    const header = [
      "retailer",
      "product_id",
      "store_number",
      "store_name",
      "zipcode",
      "city",
      "state",
      "price",
      "observed_at",
    ];
    const rows = product.sample_locations.map((location) => [
      retailer,
      product.product_id,
      location.store_number,
      location.store_name,
      location.zipcode,
      location.city,
      location.state,
      location.price,
      location.observed_at,
    ]);
    const csv = [header, ...rows]
      .map((row) =>
        row
          .map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`)
          .join(","),
      )
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${retailer}-${product.product_id}-locations.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="pm-drawer-layer">
      <button
        aria-label="Close product details"
        className="pm-drawer-backdrop"
        onClick={onClose}
        type="button"
      />
      <aside
        className="pm-product-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`${product.name} price details`}
      >
        <header>
          <div className="pm-product-identity">
            {product.image_url ? (
              <img src={product.image_url} alt="" />
            ) : (
              <span aria-hidden="true">P</span>
            )}
            <div>
              <p>
                {retailer} · {brandLabels[product.brand_type]}
              </p>
              <h2>{product.name}</h2>
              <small>
                {product.brand ?? "Brand not classified"} · ID{" "}
                {product.product_id}
              </small>
            </div>
          </div>
          <button
            aria-label="Close product details"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>
        <section className="pm-drawer-metrics">
          <div>
            <span>Observed locations</span>
            <strong>{count(product.locations)}</strong>
          </div>
          <div>
            <span>Most common price</span>
            <strong>{currency(product.price_stats.modal_price)}</strong>
          </div>
          <div>
            <span>Observed range</span>
            <strong>
              {currency(product.price_stats.minimum)}–
              {currency(product.price_stats.maximum)}
            </strong>
          </div>
          <div>
            <span>Price consistency</span>
            <strong>{percent(product.consistency_rate)}</strong>
          </div>
        </section>
        <section className="pm-drawer-section">
          <header>
            <div>
              <p className="section-kicker">Store-level evidence</p>
              <h3>Where this price was observed</h3>
            </div>
            <button
              className="button secondary"
              onClick={downloadLocations}
              type="button"
            >
              Download CSV
            </button>
          </header>
          <div className="pm-location-table-wrap">
            <table className="pm-location-table">
              <thead>
                <tr>
                  <th>Location</th>
                  <th>ZIP</th>
                  <th>City</th>
                  <th>Price</th>
                  <th>Observed</th>
                </tr>
              </thead>
              <tbody>
                {product.sample_locations.map((location) => (
                  <tr key={location.scope_key}>
                    <td>
                      <strong>
                        {location.store_name ??
                          (location.store_number
                            ? `Store ${location.store_number}`
                            : "Service area")}
                      </strong>
                      <small>
                        {location.store_number
                          ? `#${location.store_number}`
                          : "ZIP-based"}
                      </small>
                    </td>
                    <td>{location.zipcode ?? "—"}</td>
                    <td>
                      {[location.city, location.state]
                        .filter(Boolean)
                        .join(", ") || "—"}
                    </td>
                    <td>
                      <strong>{currency(location.price)}</strong>
                    </td>
                    <td>
                      {location.observed_at
                        ? displayDate(location.observed_at)
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <footer>
          <p>
            Price and location come from Search. PDP contributes identity only.
          </p>
          {product.url ? (
            <a
              className="text-link"
              href={product.url}
              rel="noreferrer"
              target="_blank"
            >
              Open retailer product page ↗
            </a>
          ) : null}
        </footer>
      </aside>
    </div>
  );
}

function ProductGrid({ view }: Readonly<{ view: PriceMonitoringView }>) {
  return (
    <div className="pm-product-grid">
      {view.products.map((product) => (
        <button
          className="pm-product-card"
          key={product.product_id}
          onClick={() => updateQuery({ product_id: product.product_id })}
          type="button"
        >
          <header>
            {product.image_url ? (
              <img src={product.image_url} alt="" loading="lazy" />
            ) : (
              <span className="pm-product-fallback" aria-hidden="true">
                P
              </span>
            )}
            <div>
              <span>{brandLabels[product.brand_type]}</span>
              <strong>{product.name}</strong>
              <small>{product.brand ?? "Brand not classified"}</small>
            </div>
          </header>
          <PriceRange product={product} />
          <footer>
            <span>
              {count(product.locations)} locations · {count(product.states)}{" "}
              states
            </span>
            <strong>View locations →</strong>
          </footer>
        </button>
      ))}
    </div>
  );
}

export function PriceMonitoringWorkspace({
  initialView,
}: Readonly<{ initialView: PriceMonitoringView }>) {
  const [view, setView] = useState(initialView);
  const [tab, setTab] = useState<TabId>("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function loadView() {
      const controller = new AbortController();
      setLoading(true);
      setError(null);
      const query = new URL(window.location.href).searchParams.toString();
      fetch(
        `/api/price-monitoring/${encodeURIComponent(initialView.analysis_id)}?${query}`,
        {
          cache: "no-store",
          signal: controller.signal,
        },
      )
        .then(async (response) => {
          if (!response.ok)
            throw new Error(`Price view returned ${response.status}`);
          setView((await response.json()) as PriceMonitoringView);
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
  }, [initialView.analysis_id]);

  const contextDefinition = useMemo<ApplicationContextDefinition>(
    () => ({
      label: "Price-monitoring context",
      controls: [
        {
          id: "retailer-view",
          label: "Retailer view",
          title: "Choose the retailer to monitor",
          description:
            "Each view is retailer-specific. No cross-retailer matching is used here.",
          value: view.retailer.name,
          selectedValue: view.filters.retailer_id,
          defaultValue: "",
          queryParameter: "retailer",
          resetQueryParameters: ["state", "city", "product_id"],
          options: view.filter_options.retailers.map((row) => ({
            value: row.id,
            label: row.name,
            description:
              "View this retailer's observed products, stores, and package prices.",
          })),
        },
        {
          id: "brand-portfolio",
          label: "Brand portfolio",
          title: "Filter by governed brand type",
          description:
            "Brand classifications come from Retailer Packs, the brand foundation, and confirmed Brand Workbench decisions.",
          value: brandLabels[view.filters.brand_type],
          selectedValue: view.filters.brand_type,
          defaultValue: "all",
          queryParameter: "brand_type",
          resetQueryParameters: ["product_id"],
          options: [
            {
              value: "all",
              label: "All brand types",
              description: `${count(view.source.classified_rows)} classified Search rows in the source view.`,
            },
            ...view.filter_options.brand_types.map((row) => ({
              value: row.value,
              label: row.label,
              description: `${count(row.count)} eligible product-location observations before geography filters.`,
            })),
          ],
        },
        {
          id: "source-readiness",
          label: "Source readiness",
          title: "Price-monitoring evidence and quality",
          description:
            "Search price and location are authoritative. Quality checks remain visible rather than silently dropping evidence.",
          value: view.quality.status === "ready" ? "Ready" : "Review caveats",
          tone: view.quality.status === "ready" ? "ready" : "attention",
          facts: [
            {
              label: "Usable price rows",
              value: percent(view.summary.usable_price_rate),
            },
            {
              label: "Location coverage",
              value: percent(view.summary.coverage_rate),
            },
            {
              label: "Immutable artifacts",
              value: count(view.source.artifact_checksums.length),
            },
            { label: "Analytical grain", value: "Product × retailer location" },
          ],
          messages: [
            view.source.grain,
            "PDP identity enrichment cannot override Search price or location.",
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
  const geographyLabel = ["USA", view.filters.state, view.filters.city]
    .filter(Boolean)
    .join(" / ");
  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "products", label: "Products" },
    { id: "geography", label: "Geography" },
    { id: "brands", label: "Brand portfolio" },
    { id: "quality", label: "Quality & definitions" },
  ];

  return (
    <>
      <header className="pm-masthead">
        <div>
          <p className="eyebrow">Price monitoring · {view.retailer.name}</p>
          <h1>{view.product_pack.name}</h1>
          <p>
            Where this retailer&apos;s package prices vary—and which products
            and locations explain the range.
          </p>
        </div>
        <dl>
          <div>
            <dt>Observed</dt>
            <dd>
              {view.source.observed_end
                ? displayDate(view.source.observed_end)
                : "Current run"}
            </dd>
          </div>
          <div>
            <dt>Geography</dt>
            <dd>{geographyLabel}</dd>
          </div>
          <div>
            <dt>Product Pack</dt>
            <dd>v{view.product_pack.version}</dd>
          </div>
        </dl>
      </header>
      <nav className="pm-tabs" aria-label="Price monitoring sections">
        {tabs.map((item) => (
          <button
            aria-current={tab === item.id ? "page" : undefined}
            key={item.id}
            onClick={() => setTab(item.id)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>
      <section className="pm-filter-row" aria-label="Geography filters">
        <label>
          <span>State</span>
          <select
            value={view.filters.state ?? ""}
            onChange={(event) =>
              updateQuery({ state: event.target.value || null, city: null })
            }
          >
            <option value="">All states</option>
            {view.filter_options.states.map((row) => (
              <option value={row.value} key={row.value}>
                {row.label} · {count(row.count)}
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
              updateQuery({ city: event.target.value || null })
            }
          >
            <option value="">All cities</option>
            {view.filter_options.cities.map((row) => (
              <option value={row.value} key={row.value}>
                {row.label} · {count(row.count)}
              </option>
            ))}
          </select>
        </label>
        {view.filters.state || view.filters.city ? (
          <button
            className="text-link"
            onClick={() => updateQuery({ state: null, city: null })}
            type="button"
          >
            Reset geography
          </button>
        ) : null}
        <span className="pm-loading-status" aria-live="polite">
          {loading
            ? "Refreshing evidence…"
            : (error ??
              `${count(view.summary.eligible_observations)} eligible observations`)}
        </span>
      </section>

      {tab === "overview" ? (
        <section className="pm-tab-content">
          <div className="pm-metric-grid">
            <article>
              <span>Observed locations</span>
              <strong>{count(view.summary.observed_locations)}</strong>
              <small>
                {view.summary.expected_locations
                  ? `${percent(view.summary.coverage_rate)} of ${count(view.summary.expected_locations)} expected`
                  : "Observed Search footprint"}
              </small>
            </article>
            <article>
              <span>Observed products</span>
              <strong>{count(view.summary.observed_products)}</strong>
              <small>Product Pack-admitted assortment</small>
            </article>
            <article>
              <span>Typical package price</span>
              <strong>
                {currency(view.price_distribution.observation_median)}
              </strong>
              <small>Observation-weighted; mix-sensitive</small>
            </article>
            <article>
              <span>Price consistency</span>
              <strong>{percent(view.summary.price_consistency_rate)}</strong>
              <small>
                At each product&apos;s most common price ± Product Pack
                tolerance
              </small>
            </article>
          </div>
          <div className="pm-two-column">
            <article className="pm-panel pm-distribution-panel">
              <header>
                <div>
                  <p className="section-kicker">Portfolio distribution</p>
                  <h2>Observed package-price spread</h2>
                </div>
                <span>Mix-sensitive</span>
              </header>
              <p>
                These values describe every admitted package sold by{" "}
                {view.retailer.name}. Use a product drill-down for a
                like-product store range.
              </p>
              <div className="pm-distribution-scale">
                <i style={{ left: "0%" }} />
                <i style={{ left: "25%" }} />
                <i className="median" style={{ left: "50%" }} />
                <i style={{ left: "75%" }} />
                <i style={{ left: "100%" }} />
              </div>
              <dl className="pm-five-number">
                <div>
                  <dt>Low</dt>
                  <dd>{currency(view.price_distribution.minimum)}</dd>
                </div>
                <div>
                  <dt>Q1</dt>
                  <dd>{currency(view.price_distribution.q1)}</dd>
                </div>
                <div>
                  <dt>Median</dt>
                  <dd>
                    {currency(view.price_distribution.observation_median)}
                  </dd>
                </div>
                <div>
                  <dt>Q3</dt>
                  <dd>{currency(view.price_distribution.q3)}</dd>
                </div>
                <div>
                  <dt>High</dt>
                  <dd>{currency(view.price_distribution.maximum)}</dd>
                </div>
              </dl>
              <footer>
                <span>Equal-weighted product median</span>
                <strong>
                  {currency(
                    view.price_distribution.product_equal_weighted_median,
                  )}
                </strong>
              </footer>
            </article>
            <article className="pm-panel pm-brand-summary">
              <header>
                <div>
                  <p className="section-kicker">Portfolio composition</p>
                  <h2>Price and breadth by brand type</h2>
                </div>
                <button
                  className="text-link"
                  onClick={() => setTab("brands")}
                  type="button"
                >
                  Open portfolio →
                </button>
              </header>
              <div>
                {view.brand_portfolio.map((row) => (
                  <button
                    key={row.brand_type}
                    onClick={() => updateQuery({ brand_type: row.brand_type })}
                    type="button"
                  >
                    <span>{brandLabels[row.brand_type]}</span>
                    <strong>{count(row.products)} products</strong>
                    <small>
                      {count(row.locations)} locations · median{" "}
                      {currency(row.median_price)}
                    </small>
                  </button>
                ))}
              </div>
            </article>
          </div>
          <article className="pm-panel pm-overview-products">
            <header>
              <div>
                <p className="section-kicker">Products driving the footprint</p>
                <h2>Most broadly distributed products</h2>
              </div>
              <button
                className="text-link"
                onClick={() => setTab("products")}
                type="button"
              >
                View all products →
              </button>
            </header>
            <ProductGrid
              view={{ ...view, products: view.products.slice(0, 6) }}
            />
          </article>
        </section>
      ) : null}

      {tab === "products" ? (
        <section className="pm-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Product-level price evidence</p>
              <h2>Which products vary by location?</h2>
            </div>
            <p>
              Each range compares the same retailer product ID across observed
              locations. Select a product for its store-level evidence and CSV
              download.
            </p>
          </article>
          <ProductGrid view={view} />
        </section>
      ) : null}

      {tab === "geography" ? (
        <section className="pm-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">
                Country → state → city → location
              </p>
              <h2>Where price and assortment vary</h2>
            </div>
            <p>
              Map color reflects the package-price range across the visible
              product mix, not a same-product price index. Choose a product to
              isolate its footprint.
            </p>
          </article>
          <RetailMap view={view} />
          <div className="pm-geography-table">
            <header>
              <h2>
                {view.filters.state ? "Cities in scope" : "States in scope"}
              </h2>
              <span>{count(view.geographies.length)} geographies</span>
            </header>
            <table>
              <thead>
                <tr>
                  <th>Geography</th>
                  <th>Locations</th>
                  <th>Products</th>
                  <th>Median package price</th>
                  <th>Range</th>
                </tr>
              </thead>
              <tbody>
                {view.geographies.map((row) => (
                  <tr
                    key={row.key}
                    onClick={() =>
                      updateQuery(
                        row.level === "state"
                          ? { state: row.key, city: null }
                          : { city: row.key },
                      )
                    }
                  >
                    <td>
                      <strong>{row.label}</strong>
                    </td>
                    <td>{count(row.locations)}</td>
                    <td>{count(row.products)}</td>
                    <td>{currency(row.price_stats.observation_median)}</td>
                    <td>
                      {currency(row.price_stats.minimum)}–
                      {currency(row.price_stats.maximum)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {tab === "brands" ? (
        <section className="pm-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Governed brand roles</p>
              <h2>Private label, regional, and national portfolio</h2>
            </div>
            <p>
              Brand types use retailer-aware exact governance. Unclassified
              brands remain visible so they can be resolved in Brand Workbench.
            </p>
          </article>
          <div className="pm-brand-portfolio-grid">
            {view.brand_portfolio.map((row) => (
              <button
                className="pm-brand-portfolio-card"
                key={row.brand_type}
                onClick={() => updateQuery({ brand_type: row.brand_type })}
                type="button"
              >
                <span>{brandLabels[row.brand_type]}</span>
                <strong>{count(row.products)}</strong>
                <p>products across {count(row.locations)} locations</p>
                <dl>
                  <div>
                    <dt>Observations</dt>
                    <dd>{count(row.observations)}</dd>
                  </div>
                  <div>
                    <dt>Median package price</dt>
                    <dd>{currency(row.median_price)}</dd>
                  </div>
                </dl>
                <small>Open filtered product portfolio →</small>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {tab === "quality" ? (
        <section className="pm-tab-content">
          <article className="pm-section-intro">
            <div>
              <p className="section-kicker">Trust and interpretation</p>
              <h2>Quality checks and metric definitions</h2>
            </div>
            <p>
              Every exception is disclosed. The dashboard does not use PDP
              price, infer missing location identities, or create AI-computed
              metrics.
            </p>
          </article>
          <div className="pm-two-column">
            <article className="pm-panel pm-quality-list">
              <header>
                <div>
                  <p className="section-kicker">Data checks</p>
                  <h2>
                    {view.quality.status === "ready"
                      ? "No recorded caveats"
                      : "Review these caveats"}
                  </h2>
                </div>
                <span
                  className={`readiness-pill ${view.quality.status === "ready" ? "ready" : "caveat"}`}
                >
                  {view.quality.status}
                </span>
              </header>
              <div>
                {view.quality.checks.map((check) => (
                  <article key={check.id}>
                    <span>{check.count ? "!" : "✓"}</span>
                    <div>
                      <strong>{check.label}</strong>
                      <p>{check.definition}</p>
                    </div>
                    <b>
                      {count(check.count)} · {percent(check.rate)}
                    </b>
                  </article>
                ))}
              </div>
            </article>
            <article className="pm-panel pm-definitions">
              <p className="section-kicker">Metric contract</p>
              <h2>How to read this view</h2>
              <dl>
                <div>
                  <dt>Grain</dt>
                  <dd>{view.source.grain}</dd>
                </div>
                <div>
                  <dt>Current observation</dt>
                  <dd>
                    The latest Search row within this run for one
                    product-location pair.
                  </dd>
                </div>
                <div>
                  <dt>Location coverage</dt>
                  <dd>
                    Distinct observed retailer locations divided by the
                    run&apos;s planned location scope.
                  </dd>
                </div>
                <div>
                  <dt>Price consistency</dt>
                  <dd>
                    Share of product-location observations at that
                    product&apos;s modal price within Product Pack tolerance.
                  </dd>
                </div>
                <div>
                  <dt>Portfolio median</dt>
                  <dd>
                    Mix-sensitive median across visible product-location
                    observations; not a competitive index.
                  </dd>
                </div>
              </dl>
              <footer>
                <span>Immutable evidence</span>
                <code>
                  {view.source.artifact_checksums.length
                    ? `${view.source.artifact_checksums[0].slice(0, 16)}…`
                    : "No artifact checksum"}
                </code>
              </footer>
            </article>
          </div>
        </section>
      ) : null}

      {selectedProduct ? (
        <ProductDrawer
          product={selectedProduct}
          retailer={view.retailer.name}
          onClose={() => updateQuery({ product_id: null })}
        />
      ) : null}
    </>
  );
}
