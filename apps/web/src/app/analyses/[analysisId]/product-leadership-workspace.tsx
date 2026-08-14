"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { CompetitiveProductLeadership } from "@/lib/api";

import styles from "./product-leadership-workspace.module.css";

type ViewName = "overview" | "footprint" | "stores";
type Outcome = CompetitiveProductLeadership["outcomes"][number];
type Summary = CompetitiveProductLeadership["summary"];

interface MapMouseEvent {
  point: { x: number; y: number };
}

interface RenderedMapFeature {
  properties?: Record<string, unknown>;
}

interface InteractiveMap {
  addControl(control: unknown, position?: string): void;
  addLayer(layer: Record<string, unknown>): void;
  addSource(id: string, source: Record<string, unknown>): void;
  fitBounds(
    bounds: [[number, number], [number, number]],
    options?: Record<string, unknown>,
  ): void;
  getCanvas(): HTMLCanvasElement;
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
}

interface MapLibrary {
  Map: new (options: Record<string, unknown>) => InteractiveMap;
  NavigationControl: new (options?: Record<string, unknown>) => unknown;
  ScaleControl: new (options?: Record<string, unknown>) => unknown;
}

const MAPLIBRE_VERSION = "5.24.0";
const MAPLIBRE_SCRIPT = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.js`;
const MAPLIBRE_STYLES = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.css`;
const OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
const SOURCE_ID = "competitive-product-leadership-outcomes";
const POINT_LAYER = "competitive-product-leadership-points";
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
    const loaded = () => {
      if (browser.maplibregl) resolve(browser.maplibregl);
      else reject(new Error("The interactive map library did not initialize."));
    };
    script.addEventListener("load", loaded, { once: true });
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

function rate(value: number | null) {
  return value === null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(value);
}

function money(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 3,
  }).format(value);
}

function signedMoney(value: number | null) {
  if (value === null) return "—";
  if (Math.abs(value) < 0.0005) return money(0);
  return `${value > 0 ? "+" : "−"}${money(Math.abs(value))}`;
}

function statusLabel(status: Outcome["status"]) {
  return status === "at_risk"
    ? "At risk"
    : status.charAt(0).toUpperCase() + status.slice(1);
}

function outcomeFeatures(outcomes: Outcome[]) {
  return {
    type: "FeatureCollection",
    features: outcomes
      .filter(
        (row) =>
          row.benchmark.latitude !== null && row.benchmark.longitude !== null,
      )
      .map((row) => ({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [row.benchmark.longitude, row.benchmark.latitude],
        },
        properties: { id: row.id, status: row.status },
      })),
  };
}

function LeadershipMap({
  outcomes,
  selected,
  onSelect,
}: Readonly<{
  outcomes: Outcome[];
  selected: Outcome | null;
  onSelect: (outcome: Outcome) => void;
}>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<InteractiveMap | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!containerRef.current) return;
    loadMapLibrary()
      .then((library) => {
        if (cancelled || !containerRef.current) return;
        const map = new library.Map({
          container: containerRef.current,
          style: OPENFREEMAP_STYLE,
          center: [-97.5, 38.4],
          zoom: 3,
          attributionControl: true,
        });
        mapRef.current = map;
        map.addControl(new library.NavigationControl(), "top-right");
        map.addControl(
          new library.ScaleControl({ unit: "imperial" }),
          "bottom-left",
        );
        map.on("load", () => {
          map.addSource(SOURCE_ID, {
            type: "geojson",
            data: outcomeFeatures(outcomes),
            cluster: true,
            clusterMaxZoom: 4,
            clusterRadius: 26,
          });
          map.addLayer({
            id: `${POINT_LAYER}-clusters`,
            type: "circle",
            source: SOURCE_ID,
            filter: ["has", "point_count"],
            paint: {
              "circle-color": "#173f4a",
              "circle-radius": [
                "step",
                ["get", "point_count"],
                16,
                100,
                21,
                500,
                27,
              ],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
              "circle-opacity": 0.9,
            },
          });
          map.addLayer({
            id: `${POINT_LAYER}-cluster-count`,
            type: "symbol",
            source: SOURCE_ID,
            filter: ["has", "point_count"],
            layout: {
              "text-field": ["get", "point_count_abbreviated"],
              "text-font": ["Noto Sans Bold"],
              "text-size": 11,
            },
            paint: { "text-color": "#ffffff" },
          });
          map.addLayer({
            id: POINT_LAYER,
            type: "circle",
            source: SOURCE_ID,
            filter: ["!", ["has", "point_count"]],
            paint: {
              "circle-color": [
                "match",
                ["get", "status"],
                "leader",
                "#16855b",
                "tied",
                "#2c76c7",
                "at_risk",
                "#d38b17",
                "losing",
                "#d14848",
                "#758394",
              ],
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["zoom"],
                3,
                4,
                9,
                6,
                14,
                9,
              ],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1.5,
              "circle-opacity": 0.92,
            },
          });
          map.on("click", POINT_LAYER, (event) => {
            const feature = map.queryRenderedFeatures(event.point, {
              layers: [POINT_LAYER],
            })[0];
            const id = String(feature?.properties?.id ?? "");
            const outcome = outcomes.find((row) => row.id === id);
            if (outcome) onSelect(outcome);
          });
          const points = outcomes.filter(
            (row) =>
              row.benchmark.latitude !== null &&
              row.benchmark.longitude !== null,
          );
          if (points.length) {
            const longitudes = points.map(
              (row) => row.benchmark.longitude as number,
            );
            const latitudes = points.map(
              (row) => row.benchmark.latitude as number,
            );
            map.fitBounds(
              [
                [Math.min(...longitudes), Math.min(...latitudes)],
                [Math.max(...longitudes), Math.max(...latitudes)],
              ],
              { padding: 48, maxZoom: 12, duration: 0 },
            );
          }
          map.getCanvas().style.cursor = "pointer";
        });
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setError(cause instanceof Error ? cause.message : "Map unavailable.");
      });
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [onSelect, outcomes]);

  return (
    <div className={styles.mapShell}>
      <div className={styles.map} ref={containerRef} />
      {error ? <p className={styles.mapError}>{error}</p> : null}
      {selected ? (
        <div className={styles.mapCallout}>
          <small>{statusLabel(selected.status)}</small>
          <strong>
            {selected.benchmark.store_name ||
              `Store ${selected.benchmark.store_number || "—"}`}
          </strong>
          <span>
            {selected.benchmark.city}, {selected.benchmark.state}{" "}
            {selected.benchmark.zipcode}
          </span>
          <b>
            {money(selected.benchmark.comparison_value)} vs.{" "}
            {money(selected.competitor?.comparison_value ?? null)}
          </b>
        </div>
      ) : null}
    </div>
  );
}

function KpiCard({
  label,
  value,
  note,
  tone = "neutral",
}: Readonly<{
  label: string;
  value: string;
  note: string;
  tone?: "neutral" | "good" | "warning" | "danger";
}>) {
  return (
    <article className={`${styles.kpi} ${styles[tone]}`}>
      <small>{label}</small>
      <strong>{value}</strong>
      <span>{note}</span>
    </article>
  );
}

function KpiStrip({ summary }: Readonly<{ summary: Summary }>) {
  return (
    <div className={styles.kpiStrip}>
      <KpiCard
        label="Clear leader rate"
        value={rate(summary.leader_rate)}
        note={`${count(summary.leader_stores)} of ${count(summary.scored_stores)} scored stores`}
        tone="good"
      />
      <KpiCard
        label="Comparable coverage"
        value={rate(summary.coverage_rate)}
        note={`${count(summary.scored_stores)} of ${count(summary.benchmark_observed_stores)} observed stores`}
      />
      <KpiCard
        label="Losing stores"
        value={count(summary.losing_stores)}
        note="A nearby matched competitor is lower"
        tone="danger"
      />
      <KpiCard
        label="Average losing gap"
        value={money(summary.average_losing_gap)}
        note={`Maximum ${money(summary.maximum_losing_gap)}`}
        tone="danger"
      />
      <KpiCard
        label="At-risk stores"
        value={count(summary.at_risk_stores)}
        note="Benchmark lead is narrow"
        tone="warning"
      />
      <KpiCard
        label="Unscored stores"
        value={count(summary.unscored_stores)}
        note="No comparable governed observation"
      />
    </div>
  );
}

function StatusDistribution({ summary }: Readonly<{ summary: Summary }>) {
  const total = Math.max(1, summary.benchmark_observed_stores);
  const rows = [
    ["Leader", summary.leader_stores, "leader"],
    ["Tied", summary.tied_stores, "tied"],
    ["At risk", summary.at_risk_stores, "at_risk"],
    ["Losing", summary.losing_stores, "losing"],
    ["Unscored", summary.unscored_stores, "unscored"],
  ] as const;
  return (
    <section className={styles.card}>
      <header>
        <div>
          <h3>Store leadership status</h3>
          <p>
            Every observed benchmark store appears in one mutually exclusive
            status.
          </p>
        </div>
      </header>
      <div className={styles.statusStack}>
        {rows.map(([label, value, status]) => (
          <div key={status}>
            <span>{label}</span>
            <i>
              <b
                className={styles[status]}
                style={{
                  width: `${Math.max(value ? 1.5 : 0, (value / total) * 100)}%`,
                }}
              />
            </i>
            <strong>{count(value)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function Overview({
  view,
  selected,
  onSelect,
  onOpenFootprint,
}: Readonly<{
  view: CompetitiveProductLeadership;
  selected: Outcome | null;
  onSelect: (row: Outcome) => void;
  onOpenFootprint: () => void;
}>) {
  const mostExposedState = [...view.state_summaries].sort(
    (left, right) => right.losing_stores - left.losing_stores,
  )[0];
  const leadingCompetitor = [...view.competitor_summaries].sort(
    (left, right) => right.losing_stores - left.losing_stores,
  )[0];
  return (
    <>
      <KpiStrip summary={view.summary} />
      <div className={styles.overviewGrid}>
        <section className={`${styles.card} ${styles.brief}`}>
          <header>
            <div>
              <h3>Analyst brief</h3>
              <p>
                Current store-level price position under the governed
                comparison.
              </p>
            </div>
            <span>{Math.round((view.summary.leader_rate ?? 0) * 100)}</span>
          </header>
          <strong>
            {count(view.summary.leader_stores)} stores are clear price leaders;{" "}
            {count(view.summary.losing_stores)} are currently undercut.
          </strong>
          <ul>
            <li>
              {count(view.summary.scored_stores)} of{" "}
              {count(view.summary.benchmark_observed_stores)} observed stores
              have comparable nearby evidence.
            </li>
            {leadingCompetitor ? (
              <li>
                {leadingCompetitor.competitor} is the lowest-price competitor at{" "}
                {count(leadingCompetitor.losing_stores)} benchmark stores.
              </li>
            ) : null}
            {mostExposedState ? (
              <li>
                {mostExposedState.label} has the largest current loss count at{" "}
                {count(mostExposedState.losing_stores)} stores.
              </li>
            ) : null}
          </ul>
        </section>
        <StatusDistribution summary={view.summary} />
      </div>
      <section className={styles.card}>
        <header>
          <div>
            <h3>National competitive footprint</h3>
            <p>
              Benchmark stores colored by current product price-leadership
              status.
            </p>
          </div>
          <button type="button" onClick={onOpenFootprint}>
            Open footprint workspace
          </button>
        </header>
        <LeadershipMap
          outcomes={view.outcomes}
          selected={selected}
          onSelect={onSelect}
        />
      </section>
      <section className={styles.card}>
        <header>
          <div>
            <h3>State watchlist</h3>
            <p>
              Prioritized by current losing-store count, with coverage shown
              alongside.
            </p>
          </div>
        </header>
        <GeographyTable
          rows={view.state_summaries
            .slice()
            .sort((a, b) => b.losing_stores - a.losing_stores)}
        />
      </section>
    </>
  );
}

function GeographyTable({
  rows,
}: Readonly<{ rows: CompetitiveProductLeadership["state_summaries"] }>) {
  return (
    <div className={styles.tableWrap}>
      <table>
        <thead>
          <tr>
            <th>Market</th>
            <th>Scored / observed</th>
            <th>Coverage</th>
            <th>Leader</th>
            <th>At risk</th>
            <th>Losing</th>
            <th>Average gap</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <th>{row.label}</th>
              <td>
                {count(row.scored_stores)} /{" "}
                {count(row.benchmark_observed_stores)}
              </td>
              <td>{rate(row.coverage_rate)}</td>
              <td>{count(row.leader_stores)}</td>
              <td>{count(row.at_risk_stores)}</td>
              <td>
                <b className={styles.lossText}>{count(row.losing_stores)}</b>
              </td>
              <td>{signedMoney(row.average_gap)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Footprint({
  view,
  selected,
  onSelect,
}: Readonly<{
  view: CompetitiveProductLeadership;
  selected: Outcome | null;
  onSelect: (row: Outcome) => void;
}>) {
  return (
    <>
      <KpiStrip summary={view.summary} />
      <section className={`${styles.card} ${styles.footprintCard}`}>
        <header>
          <div>
            <h3>Store-level competitive map</h3>
            <p>
              Zoom to local streets, select a store, or review its exact
              competitor below.
            </p>
          </div>
          <div className={styles.legend}>
            {(["leader", "tied", "at_risk", "losing", "unscored"] as const).map(
              (status) => (
                <span key={status}>
                  <i className={styles[status]} />
                  {statusLabel(status)}
                </span>
              ),
            )}
          </div>
        </header>
        <LeadershipMap
          outcomes={view.outcomes}
          selected={selected}
          onSelect={onSelect}
        />
      </section>
      <section className={styles.card}>
        <header>
          <div>
            <h3>Geographic scorecard</h3>
            <p>State-level outcomes reconcile to the national summary.</p>
          </div>
        </header>
        <GeographyTable rows={view.state_summaries} />
      </section>
    </>
  );
}

function StoreComparisons({
  view,
}: Readonly<{ view: CompetitiveProductLeadership }>) {
  const [status, setStatus] = useState<"all" | Outcome["status"]>("all");
  const rows = view.outcomes.filter(
    (row) => status === "all" || row.status === status,
  );
  return (
    <>
      <KpiStrip summary={view.summary} />
      <section className={styles.card}>
        <header>
          <div>
            <h3>Detailed store comparisons</h3>
            <p>
              One row per observed benchmark store; prices and locations come
              from Search evidence.
            </p>
          </div>
          <div className={styles.statusFilter}>
            {(
              [
                "all",
                "losing",
                "at_risk",
                "tied",
                "leader",
                "unscored",
              ] as const
            ).map((value) => (
              <button
                className={status === value ? styles.active : ""}
                key={value}
                onClick={() => setStatus(value)}
                type="button"
              >
                {value === "all" ? "All stores" : statusLabel(value)}
              </button>
            ))}
          </div>
        </header>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Benchmark store</th>
                <th>Benchmark price</th>
                <th>Lowest competitor</th>
                <th>Competitor price</th>
                <th>Distance</th>
                <th>Gap</th>
                <th>Reduction to lead</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <span
                      className={`${styles.statusPill} ${styles[row.status]}`}
                    >
                      {statusLabel(row.status)}
                    </span>
                  </td>
                  <th>
                    {row.benchmark.store_name ||
                      `Store ${row.benchmark.store_number || "—"}`}
                    <small>
                      {row.benchmark.city}, {row.benchmark.state}{" "}
                      {row.benchmark.zipcode}
                    </small>
                  </th>
                  <td>{money(row.benchmark.comparison_value)}</td>
                  <td>
                    {row.competitor ? (
                      <>
                        {row.competitor.retailer_name}
                        <small>
                          {row.competitor.product_name} · store{" "}
                          {row.competitor.store_number ||
                            row.competitor.zipcode}
                        </small>
                      </>
                    ) : (
                      "No comparable observation"
                    )}
                  </td>
                  <td>{money(row.competitor?.comparison_value ?? null)}</td>
                  <td>
                    {row.distance_miles === null
                      ? row.competitor?.location_kind === "service_area"
                        ? "Same ZIP"
                        : "—"
                      : `${row.distance_miles.toFixed(2)} mi`}
                  </td>
                  <td>{signedMoney(row.competitor_minus_benchmark)}</td>
                  <td>{money(row.comparison_value_reduction_to_lead)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export function ProductLeadershipWorkspace({
  analysisId,
  competitorId,
  profileId,
  productId,
  radiusMiles,
}: Readonly<{
  analysisId: string;
  competitorId: string;
  profileId: string;
  productId: string | null;
  radiusMiles: 1 | 3 | 5;
}>) {
  const [view, setView] = useState<CompetitiveProductLeadership | null>(null);
  const [viewName, setViewName] = useState<ViewName>("overview");
  const [selected, setSelected] = useState<Outcome | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const query = useMemo(() => {
    const parameters = new URLSearchParams({
      competitor: competitorId,
      profile: profileId,
      radius_miles: String(radiusMiles),
    });
    if (productId) parameters.set("product", productId);
    return parameters.toString();
  }, [competitorId, productId, profileId, radiusMiles]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/competitive-product-leadership?${query}`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        const body = (await response.json()) as CompetitiveProductLeadership & {
          error?: string;
        };
        if (!response.ok)
          throw new Error(
            body.error || `Leadership evidence returned ${response.status}`,
          );
        setError("");
        setView(body);
        setSelected(
          body.outcomes.find((row) => row.status === "losing") ??
            body.outcomes[0] ??
            null,
        );
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error
              ? cause.message
              : "Leadership evidence is unavailable.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [analysisId, query]);

  if (loading && !view)
    return (
      <div className={styles.state}>
        <strong>Building the store-level price-leadership view…</strong>
        <span>
          Reconciling current Search prices, governed matches, and retailer
          locations.
        </span>
      </div>
    );
  if (error && !view)
    return (
      <div className={`${styles.state} ${styles.error}`}>
        <strong>Product leadership is unavailable</strong>
        <span>{error}</span>
      </div>
    );
  if (!view) return null;
  return (
    <div className={styles.workspace}>
      <header className={styles.workspaceHeader}>
        <div className={styles.productIdentity}>
          <span>
            {view.benchmark_product.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={view.benchmark_product.image_url} alt="" />
            ) : (
              view.benchmark_product.name.slice(0, 1)
            )}
          </span>
          <div>
            <small>Benchmark product</small>
            <h2>{view.benchmark_product.name}</h2>
            <p>
              {view.benchmark_retailer.name} · {view.policy.comparison_unit} ·{" "}
              {view.filters.radius_miles}-mile competitor radius
            </p>
          </div>
        </div>
        <div className={styles.governance}>
          <b>Governed comparison</b>
          <span>
            {view.relationships.length} approved or decision-ready match
            {view.relationships.length === 1 ? "" : "es"}
          </span>
          <small>Search price · PDP identity · location-master geography</small>
        </div>
      </header>
      <nav
        className={styles.viewNav}
        aria-label="Product leadership workspaces"
      >
        {(["overview", "footprint", "stores"] as const).map((name) => (
          <button
            className={viewName === name ? styles.active : ""}
            key={name}
            onClick={() => setViewName(name)}
            type="button"
          >
            {name === "overview"
              ? "Leadership Overview"
              : name === "footprint"
                ? "Competitive Footprint"
                : "Store Comparisons"}
          </button>
        ))}
      </nav>
      <div className={styles.definitionStrip}>
        <span>
          <b>Scored denominator</b>
          {count(view.summary.scored_stores)} stores with nearby comparable
          evidence
        </span>
        <span>
          <b>Parity</b>±{money(view.policy.parity_tolerance)}
        </span>
        <span>
          <b>At-risk lead</b>≤ {money(view.policy.at_risk_threshold)}
        </span>
        <span title={view.policy.comparison_definition}>
          <b>Method</b>Lowest governed competitor value in radius
        </span>
      </div>
      {error ? (
        <p className={styles.staleWarning}>
          {error} Showing the last loaded view.
        </p>
      ) : null}
      {viewName === "overview" ? (
        <Overview
          view={view}
          selected={selected}
          onSelect={setSelected}
          onOpenFootprint={() => setViewName("footprint")}
        />
      ) : null}
      {viewName === "footprint" ? (
        <Footprint view={view} selected={selected} onSelect={setSelected} />
      ) : null}
      {viewName === "stores" ? <StoreComparisons view={view} /> : null}
    </div>
  );
}
