"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import type { CompetitiveProductLeadership } from "@/lib/api";
import {
  freshestObservation,
  leadershipExceptions,
  marketPerformance,
  relationshipEvidence,
  summarizeMatchGroup,
} from "@/lib/product-leadership-analytics";

import styles from "./product-leadership-workspace.module.css";

type ViewName =
  | "overview"
  | "footprint"
  | "match_group"
  | "ladders"
  | "stores"
  | "markets"
  | "exceptions"
  | "history";
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
const WORKSPACES: { id: ViewName; label: string }[] = [
  { id: "overview", label: "Leadership Overview" },
  { id: "footprint", label: "Competitive Footprint" },
  { id: "match_group", label: "Match Group Analysis" },
  { id: "ladders", label: "Price Ladders" },
  { id: "stores", label: "Store Comparisons" },
  { id: "markets", label: "Market Performance" },
  { id: "exceptions", label: "Competitive Exceptions" },
  { id: "history", label: "Competitive History" },
];
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

function displayDate(value: string | null) {
  if (!value) return "Not available";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}

function brandType(value: Outcome["benchmark"]["brand_type"]) {
  return value === "private_label"
    ? "Private label"
    : value === "regional"
      ? "Regional brand"
      : value === "national"
        ? "National brand"
        : "Brand type unclassified";
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

function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: Readonly<{
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}>) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const start = total ? page * pageSize + 1 : 0;
  const end = Math.min(total, (page + 1) * pageSize);
  return (
    <div className={styles.pagination} aria-label="Table pagination">
      <span>
        Showing {count(start)}–{count(end)} of {count(total)}
      </span>
      <button
        disabled={page === 0}
        onClick={() => onChange(Math.max(0, page - 1))}
        type="button"
      >
        Previous
      </button>
      <strong>
        Page {count(page + 1)} of {count(pages)}
      </strong>
      <button
        disabled={page >= pages - 1}
        onClick={() => onChange(Math.min(pages - 1, page + 1))}
        type="button"
      >
        Next
      </button>
    </div>
  );
}

function OverviewKpis({ summary }: Readonly<{ summary: Summary }>) {
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
  const mostExposedState = [...view.state_summaries]
    .sort((left, right) => right.losing_stores - left.losing_stores)
    .find((row) => row.losing_stores > 0);
  const leadingCompetitor = [...view.competitor_summaries]
    .sort((left, right) => right.losing_stores - left.losing_stores)
    .find((row) => row.losing_stores > 0);
  return (
    <>
      <OverviewKpis summary={view.summary} />
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
            <span>
              {view.summary.leader_rate === null
                ? "—"
                : Math.round(view.summary.leader_rate * 100)}
            </span>
          </header>
          <strong>
            {view.summary.scored_stores === 0
              ? "No benchmark store currently has comparable evidence in this view."
              : `${count(view.summary.leader_stores)} stores are clear price leaders; ${count(view.summary.losing_stores)} are currently undercut.`}
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
            {view.summary.scored_stores === 0 ? (
              <li>
                No current competitor observation is comparable at the selected
                radius and governed relationship scope.
              </li>
            ) : view.summary.losing_stores === 0 ? (
              <li>
                No scored benchmark store is currently undercut in this view.
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
  onSelect,
}: Readonly<{
  rows: CompetitiveProductLeadership["state_summaries"];
  onSelect?: (
    row: CompetitiveProductLeadership["state_summaries"][number],
  ) => void;
}>) {
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
              <th>
                {onSelect ? (
                  <button
                    className={styles.marketLink}
                    onClick={() => onSelect(row)}
                    type="button"
                  >
                    {row.label}
                  </button>
                ) : (
                  row.label
                )}
              </th>
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
  onOpenState,
}: Readonly<{
  view: CompetitiveProductLeadership;
  selected: Outcome | null;
  onSelect: (row: Outcome) => void;
  onOpenState: (state: string) => void;
}>) {
  const mapped = view.outcomes.filter(
    (row) =>
      row.benchmark.latitude !== null && row.benchmark.longitude !== null,
  ).length;
  return (
    <>
      <div className={styles.kpiStrip}>
        <KpiCard
          label="Mapped benchmark stores"
          value={count(mapped)}
          note={`${rate(mapped / Math.max(view.summary.benchmark_observed_stores, 1))} of observed stores`}
        />
        <KpiCard
          label="Comparable stores"
          value={count(view.summary.scored_stores)}
          note={`${rate(view.summary.coverage_rate)} evidence coverage`}
        />
        <KpiCard
          label="Clear leaders"
          value={count(view.summary.leader_stores)}
          note={`${rate(view.summary.leader_rate)} of scored stores`}
          tone="good"
        />
        <KpiCard
          label="Current losses"
          value={count(view.summary.losing_stores)}
          note="Competitor is lower nearby"
          tone="danger"
        />
        <KpiCard
          label="Narrow leads"
          value={count(view.summary.at_risk_stores)}
          note="Inside the at-risk threshold"
          tone="warning"
        />
        <KpiCard
          label="Unscored"
          value={count(view.summary.unscored_stores)}
          note="No geographically comparable evidence"
        />
      </div>
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
        <GeographyTable
          rows={view.state_summaries}
          onSelect={(row) => onOpenState(row.label)}
        />
      </section>
    </>
  );
}

function ProductThumb({
  imageUrl,
  name,
}: Readonly<{ imageUrl: string | null; name: string }>) {
  return (
    <span className={styles.productThumb} aria-hidden="true">
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imageUrl} alt="" />
      ) : (
        name.slice(0, 1).toUpperCase()
      )}
    </span>
  );
}

function MatchGroupAnalysis({
  view,
}: Readonly<{ view: CompetitiveProductLeadership }>) {
  const summary = summarizeMatchGroup(view.relationships, view.outcomes);
  const rows = relationshipEvidence(view.relationships, view.outcomes);
  return (
    <>
      <div className={styles.kpiStrip}>
        <KpiCard
          label="Governed relationships"
          value={count(summary.relationships)}
          note="Approved or decision-ready for this basis"
        />
        <KpiCard
          label="Competitor products"
          value={count(summary.competitorProducts)}
          note="Distinct retailer-product identities"
        />
        <KpiCard
          label="Competitor retailers"
          value={count(summary.competitorRetailers)}
          note="Participating in this product group"
        />
        <KpiCard
          label="Relationships observed"
          value={count(summary.relationshipsWithEvidence)}
          note={`${count(summary.relationships - summary.relationshipsWithEvidence)} configured relationships had no winning nearby observation`}
          tone={
            summary.relationshipsWithEvidence === summary.relationships
              ? "good"
              : "warning"
          }
        />
        <KpiCard
          label="Location-scoped matches"
          value={count(summary.locationScopedRelationships)}
          note="Admitted only in governed benchmark footprints"
        />
        <KpiCard
          label="Global matches"
          value={count(summary.globalRelationships)}
          note="Eligible across the benchmark footprint"
        />
      </div>
      <div className={styles.overviewGrid}>
        <section className={`${styles.card} ${styles.identityCard}`}>
          <header>
            <div>
              <h3>Benchmark anchor product</h3>
              <p>The product whose store-level price leadership is measured.</p>
            </div>
          </header>
          <div className={styles.anchorProduct}>
            <ProductThumb
              imageUrl={view.benchmark_product.image_url}
              name={view.benchmark_product.name}
            />
            <div>
              <strong>{view.benchmark_product.name}</strong>
              <span>{view.benchmark_retailer.name}</span>
              <small>Retailer product ID {view.benchmark_product.id}</small>
            </div>
          </div>
        </section>
        <section className={styles.card}>
          <header>
            <div>
              <h3>Match-group governance</h3>
              <p>
                Rules that protect comparability and store-footprint integrity.
              </p>
            </div>
          </header>
          <ul className={styles.keyPoints}>
            <li>Every result uses one comparison metric and unit.</li>
            <li>
              A location-scoped relationship is admitted only at its approved
              benchmark stores.
            </li>
            <li>
              Search supplies price and availability; PDP and retailer packs
              supply governed identity and brand context.
            </li>
          </ul>
        </section>
      </div>
      <section className={styles.card}>
        <header>
          <div>
            <h3>Approved equivalent products</h3>
            <p>
              Relationship-level evidence used to select the lowest nearby
              governed competitor at each benchmark store.
            </p>
          </div>
        </header>
        <div className={styles.relationshipGrid}>
          {rows.map((row) => (
            <article key={row.relationship_id}>
              <ProductThumb
                imageUrl={row.competitorImageUrl}
                name={row.competitorProductName}
              />
              <div>
                <small>{row.competitor_name}</small>
                <strong>{row.competitorProductName}</strong>
                <span>
                  {row.competitorBrand || "Brand unresolved"} ·{" "}
                  {brandType(row.competitorBrandType)}
                </span>
                <span>
                  {row.profile_label} · {row.comparison_unit}
                </span>
              </div>
              <dl>
                <div>
                  <dt>Scope</dt>
                  <dd>
                    {row.scope_mode === "global"
                      ? "All benchmark locations"
                      : `${count(row.scoped_benchmark_locations)} approved locations`}
                  </dd>
                </div>
                <div>
                  <dt>Selected nearby</dt>
                  <dd>{count(row.benchmarkLocations)} stores</dd>
                </div>
              </dl>
              <Link
                className={styles.reviewLink}
                href={`/workspace/matches/${encodeURIComponent(view.analysis_id)}?competitor=${encodeURIComponent(row.competitor_id)}&lens=${encodeURIComponent(row.profile_id)}&pair=${encodeURIComponent(row.relationship_id)}`}
              >
                Inspect PDP & match evidence
              </Link>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function MarketPerformanceWorkspace({
  view,
  focusedMarket,
  onFocus,
}: Readonly<{
  view: CompetitiveProductLeadership;
  focusedMarket: string | null;
  onFocus: (market: string | null) => void;
}>) {
  const markets = marketPerformance(view.state_summaries);
  const scoredMarkets = markets.filter((row) => row.scored_stores >= 3);
  const best = [...scoredMarkets].sort(
    (left, right) => (right.leader_rate ?? -1) - (left.leader_rate ?? -1),
  )[0];
  const mostExposed = markets[0];
  const widestGap = [...markets].sort(
    (left, right) => right.unscored_stores - left.unscored_stores,
  )[0];
  const focused = markets.find((row) => row.label === focusedMarket) ?? null;
  return (
    <>
      <div className={styles.kpiStrip}>
        <KpiCard
          label="States analyzed"
          value={count(markets.length)}
          note="Current benchmark product footprint"
        />
        <KpiCard
          label="Strongest leadership state"
          value={best?.label ?? "—"}
          note={
            best
              ? `${rate(best.leader_rate)} leader rate`
              : "No state has 3 scored stores"
          }
          tone="good"
        />
        <KpiCard
          label="Most exposed state"
          value={mostExposed?.label ?? "—"}
          note={
            mostExposed
              ? `${count(mostExposed.losing_stores)} current losses`
              : "No scored markets"
          }
          tone="danger"
        />
        <KpiCard
          label="Largest evidence gap"
          value={widestGap?.label ?? "—"}
          note={
            widestGap
              ? `${count(widestGap.unscored_stores)} unscored stores`
              : "No evidence gaps"
          }
          tone="warning"
        />
        <KpiCard
          label="National average gap"
          value={signedMoney(view.summary.average_gap)}
          note="Competitor minus benchmark; positive favors benchmark"
        />
        <KpiCard
          label="Markets with losses"
          value={count(markets.filter((row) => row.losing_stores > 0).length)}
          note="States with at least one current undercut"
          tone="danger"
        />
      </div>
      {focused ? (
        <section className={`${styles.card} ${styles.marketSpotlight}`}>
          <header>
            <div>
              <h3>{focused.label} market spotlight</h3>
              <p>
                Current state scorecard; select another state in the table
                below.
              </p>
            </div>
            <button onClick={() => onFocus(null)} type="button">
              Clear spotlight
            </button>
          </header>
          <div>
            <strong>{rate(focused.leader_rate)}</strong>
            <span>leader rate</span>
            <strong>{rate(focused.coverage_rate)}</strong>
            <span>comparable coverage</span>
            <strong>{count(focused.losing_stores)}</strong>
            <span>current losses</span>
            <strong>{signedMoney(focused.average_gap)}</strong>
            <span>average price gap</span>
          </div>
        </section>
      ) : null}
      <section className={styles.card}>
        <header>
          <div>
            <h3>State performance scorecard</h3>
            <p>
              Loss rates use scored stores; coverage uses all observed benchmark
              stores. Select a state for a focused readout.
            </p>
          </div>
        </header>
        <GeographyTable rows={markets} onSelect={(row) => onFocus(row.label)} />
      </section>
    </>
  );
}

function CompetitiveExceptions({
  view,
}: Readonly<{ view: CompetitiveProductLeadership }>) {
  const [type, setType] = useState<"all" | "high" | "medium" | "review">("all");
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const exceptions = leadershipExceptions(view.outcomes);
  const rows = exceptions.filter(
    (row) => type === "all" || row.priority === type,
  );
  const visibleRows = rows.slice(page * pageSize, (page + 1) * pageSize);
  const high = exceptions.filter((row) => row.priority === "high").length;
  const medium = exceptions.filter((row) => row.priority === "medium").length;
  const review = exceptions.filter((row) => row.priority === "review").length;
  const largest = exceptions.find(
    (row) => row.type === "competitor_undercut",
  )?.outcome;
  return (
    <>
      <div className={styles.kpiStrip}>
        <KpiCard
          label="Current undercuts"
          value={count(high)}
          note="Highest-priority store exceptions"
          tone="danger"
        />
        <KpiCard
          label="Narrow benchmark leads"
          value={count(medium)}
          note="Inside the governed risk threshold"
          tone="warning"
        />
        <KpiCard
          label="Evidence reviews"
          value={count(review)}
          note="No comparable current competitor observation"
        />
        <KpiCard
          label="Largest undercut"
          value={money(largest?.comparison_value_reduction_to_lead ?? null)}
          note="Reduction needed to regain a clear lead"
          tone="danger"
        />
        <KpiCard
          label="Exception share"
          value={rate(
            exceptions.length /
              Math.max(view.summary.benchmark_observed_stores, 1),
          )}
          note="Current exceptions among observed stores"
        />
        <KpiCard
          label="Snapshot freshness"
          value={
            freshestObservation(view.outcomes) ? "Current snapshot" : "Unknown"
          }
          note={displayDate(freshestObservation(view.outcomes))}
        />
      </div>
      <section className={styles.card}>
        <header>
          <div>
            <h3>Prioritized competitive exception queue</h3>
            <p>
              Current-snapshot facts only. Persistence and new-versus-existing
              status require certified history.
            </p>
          </div>
          <div className={styles.statusFilter}>
            {(["all", "high", "medium", "review"] as const).map((value) => (
              <button
                className={type === value ? styles.active : ""}
                key={value}
                onClick={() => {
                  setType(value);
                  setPage(0);
                }}
                type="button"
              >
                {value === "all" ? "All exceptions" : value}
              </button>
            ))}
          </div>
        </header>
        <div className={styles.exceptionList}>
          {visibleRows.map((row) => (
            <article key={row.id}>
              <span className={`${styles.priority} ${styles[row.priority]}`}>
                {row.priority}
              </span>
              <div>
                <strong>{row.label}</strong>
                <span>{row.reason}</span>
                <small>
                  {row.outcome.benchmark.store_name ||
                    `Store ${row.outcome.benchmark.store_number || "—"}`}{" "}
                  · {row.outcome.benchmark.city}, {row.outcome.benchmark.state}{" "}
                  {row.outcome.benchmark.zipcode}
                </small>
              </div>
              <div>
                <b>{money(row.outcome.benchmark.comparison_value)}</b>
                <span>benchmark</span>
              </div>
              <div>
                <b>{money(row.outcome.competitor?.comparison_value ?? null)}</b>
                <span>
                  {row.outcome.competitor?.retailer_name ??
                    "No comparable offer"}
                </span>
              </div>
              <div>
                <b>{money(row.outcome.comparison_value_reduction_to_lead)}</b>
                <span>reduction to lead</span>
              </div>
            </article>
          ))}
        </div>
        <Pagination
          page={page}
          pageSize={pageSize}
          total={rows.length}
          onChange={setPage}
        />
      </section>
    </>
  );
}

function CompetitiveHistory({
  view,
}: Readonly<{ view: CompetitiveProductLeadership }>) {
  return (
    <section className={`${styles.card} ${styles.historyState}`}>
      <div className={styles.historyIcon} aria-hidden="true">
        ↻
      </div>
      <div>
        <small>History readiness</small>
        <h3>
          Trend reporting begins with the next certified comparable snapshot
        </h3>
        <p>
          This analysis contains one immutable collection snapshot. Showing a
          trend, persistent loss, or new exception now would invent evidence.
          The current snapshot is preserved as the baseline for the same
          product, retailer set, comparison basis, radius, and geography.
        </p>
        <dl>
          <div>
            <dt>Baseline snapshot</dt>
            <dd>{displayDate(view.generated_at)}</dd>
          </div>
          <div>
            <dt>Baseline stores</dt>
            <dd>{count(view.summary.benchmark_observed_stores)}</dd>
          </div>
          <div>
            <dt>Required for first trend</dt>
            <dd>1 additional certified comparable snapshot</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function StoreComparisons({
  view,
}: Readonly<{ view: CompetitiveProductLeadership }>) {
  const [status, setStatus] = useState<"all" | Outcome["status"]>("all");
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const rows = view.outcomes.filter(
    (row) => status === "all" || row.status === status,
  );
  const visibleRows = rows.slice(page * pageSize, (page + 1) * pageSize);
  const losingRows = view.outcomes.filter((row) => row.status === "losing");
  const averageReduction = losingRows.length
    ? losingRows.reduce(
        (sum, row) => sum + (row.comparison_value_reduction_to_lead ?? 0),
        0,
      ) / losingRows.length
    : null;
  const sponsoredLowest = view.outcomes.filter(
    (row) => row.competitor?.is_sponsored === true,
  ).length;
  const discountedLowest = view.outcomes.filter(
    (row) =>
      row.competitor?.discounted_price !== null &&
      row.competitor?.discounted_price !== undefined &&
      row.competitor.discounted_price > 0 &&
      row.competitor.regular_price !== null &&
      row.competitor.discounted_price < row.competitor.regular_price,
  ).length;
  return (
    <>
      <div className={styles.kpiStrip}>
        <KpiCard
          label="Scored benchmark stores"
          value={count(view.summary.scored_stores)}
          note="One outcome per observed benchmark store"
        />
        <KpiCard
          label="Stores to inspect"
          value={count(
            view.summary.losing_stores + view.summary.at_risk_stores,
          )}
          note="Current losses plus narrow leads"
          tone="warning"
        />
        <KpiCard
          label="Average reduction to lead"
          value={money(averageReduction)}
          note="Among currently undercut stores"
          tone="danger"
        />
        <KpiCard
          label="Maximum losing gap"
          value={money(view.summary.maximum_losing_gap)}
          note="Largest current competitor advantage"
          tone="danger"
        />
        <KpiCard
          label="Discounted lowest offers"
          value={count(discountedLowest)}
          note="Search evidence shows a lower promo price"
        />
        <KpiCard
          label="Sponsored lowest offers"
          value={count(sponsoredLowest)}
          note="Search result marked sponsored"
        />
      </div>
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
                onClick={() => {
                  setStatus(value);
                  setPage(0);
                }}
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
                <th>Benchmark product & store</th>
                <th>Benchmark price</th>
                <th>Lowest competitor</th>
                <th>Competitor price</th>
                <th>Distance</th>
                <th>Gap</th>
                <th>Reduction to lead</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <span
                      className={`${styles.statusPill} ${styles[row.status]}`}
                    >
                      {statusLabel(row.status)}
                    </span>
                  </td>
                  <th>
                    <span className={styles.productCell}>
                      <ProductThumb
                        imageUrl={row.benchmark.image_url}
                        name={row.benchmark.product_name}
                      />
                      <span>
                        {row.benchmark.store_name ||
                          `Store ${row.benchmark.store_number || "—"}`}
                        <small>
                          {row.benchmark.product_name} · {row.benchmark.city},{" "}
                          {row.benchmark.state} {row.benchmark.zipcode}
                        </small>
                      </span>
                    </span>
                  </th>
                  <td>{money(row.benchmark.comparison_value)}</td>
                  <td>
                    {row.competitor ? (
                      <span className={styles.productCell}>
                        <ProductThumb
                          imageUrl={row.competitor.image_url}
                          name={row.competitor.product_name}
                        />
                        <span>
                          {row.competitor.retailer_name}
                          <small>
                            {row.competitor.product_name} ·{" "}
                            {brandType(row.competitor.brand_type)} · store{" "}
                            {row.competitor.store_number ||
                              row.competitor.zipcode}
                          </small>
                        </span>
                      </span>
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
        <Pagination
          page={page}
          pageSize={pageSize}
          total={rows.length}
          onChange={setPage}
        />
      </section>
    </>
  );
}

function PriceLadders({
  view,
  selected,
  onSelect,
}: Readonly<{
  view: CompetitiveProductLeadership;
  selected: Outcome | null;
  onSelect: (row: Outcome) => void;
}>) {
  const current = selected ?? view.outcomes[0] ?? null;
  const ladder = current?.price_ladder;
  if (!current || !ladder) {
    return (
      <section className={styles.card}>
        <header>
          <div>
            <h3>Price ladders unavailable</h3>
            <p>
              This publication predates the location-level price-ladder
              contract.
            </p>
          </div>
        </header>
      </section>
    );
  }
  return (
    <>
      <div className={styles.kpiStrip}>
        <KpiCard
          label="Walmart ladder rank"
          value={`${count(ladder.benchmark_rank)} of ${count(ladder.rung_count)}`}
          note="Dense price rank; equal prices share a rank"
          tone={ladder.benchmark_rank === 1 ? "good" : "danger"}
        />
        <KpiCard
          label="Gap to opening price"
          value={money(ladder.gap_to_leader)}
          note="Walmart price minus the lowest valid local rung"
          tone={ladder.gap_to_leader > 0 ? "danger" : "good"}
        />
        <KpiCard
          label="Lower-priced alternatives"
          value={count(ladder.lower_priced_alternatives)}
          note="Governed matched products below Walmart"
          tone={ladder.lower_priced_alternatives ? "warning" : "good"}
        />
        <KpiCard
          label="Next lower rung"
          value={money(ladder.gap_to_next_lower)}
          note="Distance from Walmart to the nearest lower price"
        />
        <KpiCard
          label="Next higher rung"
          value={money(ladder.gap_to_next_higher)}
          note="Price cushion to the nearest higher product"
        />
      </div>
      <section className={styles.card}>
        <header>
          <div>
            <h3>Local governed price ladder</h3>
            <p>{ladder.definition}</p>
          </div>
          <label className={styles.ladderSelect}>
            <span>Walmart store</span>
            <select
              value={current.id}
              onChange={(event) => {
                const outcome = view.outcomes.find(
                  (row) => row.id === event.target.value,
                );
                if (outcome) onSelect(outcome);
              }}
            >
              {view.outcomes.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.benchmark.city ||
                    row.benchmark.zipcode ||
                    "Unknown market"}
                  {row.benchmark.state ? `, ${row.benchmark.state}` : ""} ·
                  store {row.benchmark.store_number || "service area"} ·{" "}
                  {row.status}
                </option>
              ))}
            </select>
          </label>
        </header>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Product and local offer</th>
                <th>Price</th>
                <th>Gap to prior rung</th>
                <th>Versus Walmart</th>
                <th>Premium vs. opening</th>
                <th>Distance</th>
              </tr>
            </thead>
            <tbody>
              {ladder.rungs.map((rung) => (
                <tr
                  key={`${rung.position}:${rung.location.scope_key}:${rung.location.product_id}`}
                >
                  <td>
                    <strong>#{count(rung.price_rank)}</strong>
                  </td>
                  <th>
                    <span className={styles.productCell}>
                      <span className={styles.productThumb}>
                        {rung.location.image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={rung.location.image_url} alt="" />
                        ) : (
                          rung.location.product_name.slice(0, 1)
                        )}
                      </span>
                      <span>
                        <b>
                          {rung.is_benchmark
                            ? `${rung.location.retailer_name} · benchmark`
                            : rung.location.retailer_name}
                        </b>
                        <small>
                          {rung.location.product_name} ·{" "}
                          {brandType(rung.location.brand_type)} · store{" "}
                          {rung.location.store_number || rung.location.zipcode}
                        </small>
                      </span>
                    </span>
                  </th>
                  <td>{money(rung.location.comparison_value)}</td>
                  <td>{money(rung.gap_to_previous)}</td>
                  <td>{signedMoney(rung.gap_to_benchmark)}</td>
                  <td>{rate(rung.premium_vs_opening_rate)}</td>
                  <td>
                    {rung.is_benchmark
                      ? "Anchor"
                      : rung.distance_miles === null
                        ? "Same ZIP"
                        : `${rung.distance_miles.toFixed(2)} mi`}
                  </td>
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
  stateFilter,
  cityFilter,
  onGeographyOptions,
}: Readonly<{
  analysisId: string;
  competitorId: string;
  profileId: string;
  productId: string | null;
  radiusMiles: 1 | 3 | 5;
  stateFilter: string | null;
  cityFilter: string | null;
  onGeographyOptions: (
    states: CompetitiveProductLeadership["filter_options"]["states"],
    cities: CompetitiveProductLeadership["filter_options"]["cities"],
  ) => void;
}>) {
  const [loadedView, setLoadedView] = useState<{
    query: string;
    data: CompetitiveProductLeadership;
  } | null>(null);
  const [failedView, setFailedView] = useState<{
    query: string;
    message: string;
  } | null>(null);
  const [viewName, setViewName] = useState<ViewName>("overview");
  const [selected, setSelected] = useState<Outcome | null>(null);
  const [focusedMarket, setFocusedMarket] = useState<string | null>(null);
  const query = useMemo(() => {
    const parameters = new URLSearchParams({
      competitor: competitorId,
      profile: profileId,
      radius_miles: String(radiusMiles),
    });
    if (productId) parameters.set("product", productId);
    if (stateFilter) parameters.set("state", stateFilter);
    if (stateFilter && cityFilter) parameters.set("city", cityFilter);
    return parameters.toString();
  }, [
    cityFilter,
    competitorId,
    productId,
    profileId,
    radiusMiles,
    stateFilter,
  ]);
  const view = loadedView?.query === query ? loadedView.data : null;
  const error = failedView?.query === query ? failedView.message : "";
  const loading = Boolean(productId && !view && !error);

  useEffect(() => {
    if (!productId) return;
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
        setFailedView(null);
        setLoadedView({ query, data: body });
        setSelected(
          body.outcomes.find((row) => row.status === "losing") ??
            body.outcomes[0] ??
            null,
        );
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setFailedView({
            query,
            message:
              cause instanceof Error
                ? cause.message
                : "Leadership evidence is unavailable.",
          });
      });
    return () => controller.abort();
  }, [analysisId, productId, query]);

  useEffect(() => {
    const applyLocation = () => {
      const requested = new URL(window.location.href).searchParams.get(
        "leadership",
      );
      setViewName(
        WORKSPACES.some((workspace) => workspace.id === requested)
          ? (requested as ViewName)
          : "overview",
      );
    };
    applyLocation();
    window.addEventListener("popstate", applyLocation);
    return () => window.removeEventListener("popstate", applyLocation);
  }, []);

  useEffect(() => {
    if (!view) return;
    onGeographyOptions(
      stateFilter ? [] : view.filter_options.states,
      view.filter_options.cities,
    );
  }, [onGeographyOptions, stateFilter, view]);

  if (!productId)
    return (
      <div className={styles.state}>
        <strong>No benchmark product is available for this context</strong>
        <span>
          Choose a retailer and comparison basis with at least one governed
          product relationship.
        </span>
      </div>
    );
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
  const selectWorkspace = (workspace: ViewName) => {
    setViewName(workspace);
    const url = new URL(window.location.href);
    if (workspace === "overview") url.searchParams.delete("leadership");
    else url.searchParams.set("leadership", workspace);
    window.history.replaceState(window.history.state, "", url);
  };
  const drillState = (state: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set("state", state);
    url.searchParams.delete("city");
    window.history.replaceState(window.history.state, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };
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
        {WORKSPACES.map((workspace) => (
          <button
            className={viewName === workspace.id ? styles.active : ""}
            key={workspace.id}
            onClick={() => selectWorkspace(workspace.id)}
            type="button"
          >
            {workspace.label}
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
          onOpenFootprint={() => selectWorkspace("footprint")}
        />
      ) : null}
      {viewName === "footprint" ? (
        <Footprint
          view={view}
          selected={selected}
          onSelect={setSelected}
          onOpenState={drillState}
        />
      ) : null}
      {viewName === "match_group" ? <MatchGroupAnalysis view={view} /> : null}
      {viewName === "ladders" ? (
        <PriceLadders view={view} selected={selected} onSelect={setSelected} />
      ) : null}
      {viewName === "stores" ? <StoreComparisons view={view} /> : null}
      {viewName === "markets" ? (
        <MarketPerformanceWorkspace
          view={view}
          focusedMarket={focusedMarket}
          onFocus={setFocusedMarket}
        />
      ) : null}
      {viewName === "exceptions" ? <CompetitiveExceptions view={view} /> : null}
      {viewName === "history" ? <CompetitiveHistory view={view} /> : null}
    </div>
  );
}
