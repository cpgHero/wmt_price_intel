"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import type { CompetitiveProductLeadership } from "@/lib/api";
import { loadCompetitiveProductLeadership } from "@/lib/competitive-product-leadership-client";
import type { ProductLeadershipViewName } from "@/lib/competitive-report-tabs";
import {
  relationshipEvidence,
  summarizeMatchGroup,
} from "@/lib/product-leadership-analytics";

import styles from "./product-leadership-workspace.module.css";

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
const BENCHMARK_MAP_COLOR = "#111827";
const COMPETITOR_MAP_COLORS = [
  "#0284c7",
  "#dc2626",
  "#7c3aed",
  "#059669",
  "#ea580c",
  "#db2777",
  "#4f46e5",
  "#65a30d",
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

type ExportCell = string | number | null;
type ExportRow = Record<string, ExportCell>;

function csvCell(value: ExportCell) {
  const text = value === null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function xmlCell(value: ExportCell) {
  return (value === null ? "" : String(value))
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function downloadExport(
  rows: ExportRow[],
  filename: string,
  format: "csv" | "excel",
) {
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  const content =
    format === "csv"
      ? [
          columns.map(csvCell).join(","),
          ...rows.map((row) =>
            columns.map((key) => csvCell(row[key])).join(","),
          ),
        ].join("\n")
      : `<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Report"><Table>${[
          columns,
          ...rows.map((row) => columns.map((key) => row[key])),
        ]
          .map(
            (row) =>
              `<Row>${row
                .map(
                  (value) =>
                    `<Cell><Data ss:Type="${typeof value === "number" ? "Number" : "String"}">${xmlCell(value)}</Data></Cell>`,
                )
                .join("")}</Row>`,
          )
          .join("")}</Table></Worksheet></Workbook>`;
  const blob = new Blob([content], {
    type:
      format === "csv"
        ? "text/csv;charset=utf-8"
        : "application/vnd.ms-excel;charset=utf-8",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${filename}.${format === "csv" ? "csv" : "xls"}`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function ExportButtons({
  rows,
  filename,
}: Readonly<{ rows: ExportRow[]; filename: string }>) {
  return (
    <div className={styles.exportButtons}>
      <button
        type="button"
        onClick={() => downloadExport(rows, filename, "csv")}
      >
        Download CSV
      </button>
      <button
        type="button"
        onClick={() => downloadExport(rows, filename, "excel")}
      >
        Download Excel
      </button>
    </div>
  );
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

function retailerMapColor(retailerId: string) {
  let hash = 0;
  for (const character of retailerId) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return COMPETITOR_MAP_COLORS[hash % COMPETITOR_MAP_COLORS.length];
}

function outcomeFeatures(outcomes: Outcome[]) {
  return {
    type: "FeatureCollection",
    features: outcomes
      .filter(
        (row) =>
          row.competitor !== null &&
          row.benchmark.latitude !== null &&
          row.benchmark.longitude !== null,
      )
      .flatMap((row) => {
        const competitor = row.competitor;
        const features = [
          {
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [row.benchmark.longitude, row.benchmark.latitude],
            },
            properties: {
              id: row.id,
              retailer: row.benchmark.retailer_name,
              color: BENCHMARK_MAP_COLOR,
              location_kind: "benchmark",
            },
          },
        ];
        if (
          competitor &&
          competitor.latitude !== null &&
          competitor.longitude !== null
        ) {
          features.push({
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [competitor.longitude, competitor.latitude],
            },
            properties: {
              id: row.id,
              retailer: competitor.retailer_name,
              color: retailerMapColor(competitor.retailer_id),
              location_kind: "competitor",
            },
          });
        }
        return features;
      }),
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
  const mappedRetailers = useMemo(() => {
    const retailers = new Map<string, string>();
    for (const row of outcomes) {
      if (row.competitor) {
        retailers.set(row.competitor.retailer_id, row.competitor.retailer_name);
      }
    }
    return [...retailers.entries()];
  }, [outcomes]);

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
          });
          map.addLayer({
            id: POINT_LAYER,
            type: "circle",
            source: SOURCE_ID,
            paint: {
              "circle-color": ["get", "color"],
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["zoom"],
                3,
                3,
                9,
                5,
                14,
                8,
              ],
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1.25,
              "circle-opacity": 0.9,
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
          const points = outcomes.flatMap((row) => {
            if (!row.competitor) return [];
            const locations = [row.benchmark, row.competitor];
            return locations.filter(
              (location) =>
                location.latitude !== null && location.longitude !== null,
            );
          });
          if (points.length) {
            const longitudes = points.map((row) => row.longitude as number);
            const latitudes = points.map((row) => row.latitude as number);
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
      <div className={styles.retailerLegend} aria-label="Map retailer legend">
        <span>
          <i style={{ background: BENCHMARK_MAP_COLOR }} />
          Walmart
        </span>
        {mappedRetailers.map(([id, name]) => (
          <span key={id}>
            <i style={{ background: retailerMapColor(id) }} />
            {name}
          </span>
        ))}
      </div>
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
          {selected.competitor ? (
            <span>
              {selected.competitor.retailer_name} ·{" "}
              {selected.competitor.store_name ||
                selected.competitor.store_number ||
                "service area"}
              {selected.distance_miles === null
                ? " · same delivery ZIP"
                : ` · ${selected.distance_miles.toFixed(2)} mi`}
            </span>
          ) : null}
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
  onOpenState,
}: Readonly<{
  view: CompetitiveProductLeadership;
  selected: Outcome | null;
  onSelect: (row: Outcome) => void;
  onOpenState: (state: string) => void;
}>) {
  const mapped = view.outcomes.filter(
    (row) =>
      row.competitor !== null &&
      row.benchmark.latitude !== null &&
      row.benchmark.longitude !== null,
  ).length;
  const mostExposedState = [...view.state_summaries]
    .sort((left, right) => right.losing_stores - left.losing_stores)
    .find((row) => row.losing_stores > 0);
  const leadingCompetitor = [...view.competitor_summaries]
    .sort((left, right) => right.losing_stores - left.losing_stores)
    .find((row) => row.losing_stores > 0);
  return (
    <>
      <div className={styles.kpiStrip}>
        <KpiCard
          label="Mapped Walmart stores"
          value={count(mapped)}
          note={`${rate(mapped / Math.max(view.summary.benchmark_observed_stores, 1))} of observed stores have mapped comparison evidence`}
        />
        <KpiCard
          label="Comparable stores"
          value={count(view.summary.scored_stores)}
          note={`${rate(view.summary.coverage_rate)} evidence coverage`}
        />
        <KpiCard
          label="Clear price leaders"
          value={count(view.summary.leader_stores)}
          note={`${rate(view.summary.leader_rate)} of scored stores`}
          tone="good"
        />
        <KpiCard
          label="Currently undercut"
          value={count(view.summary.losing_stores)}
          note="A governed nearby competitor is lower"
          tone="danger"
        />
        <KpiCard
          label="Narrow leads"
          value={count(view.summary.at_risk_stores)}
          note="Walmart leads inside the at-risk threshold"
          tone="warning"
        />
        <KpiCard
          label="Not scored"
          value={count(view.summary.unscored_stores)}
          note="No geographically comparable evidence"
        />
      </div>
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
              Individual Walmart and competitor locations; only Walmart stores
              with a comparable competitor inside the selected radius appear.
            </p>
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
            <p>
              State-level outcomes reconcile to the national scorecard and use
              the current radius and comparison basis.
            </p>
          </div>
        </header>
        <GeographyTable
          rows={view.state_summaries
            .slice()
            .sort((a, b) => b.losing_stores - a.losing_stores)}
          onSelect={(row) => onOpenState(row.label)}
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
  const exportRows = rows.map((row) => ({
    Geography: row.label,
    "Observed Walmart stores": row.benchmark_observed_stores,
    "Scored Walmart stores": row.scored_stores,
    "Coverage rate": row.coverage_rate,
    "Leader stores": row.leader_stores,
    "Tied stores": row.tied_stores,
    "At-risk stores": row.at_risk_stores,
    "Undercut stores": row.losing_stores,
    "Not scored": row.unscored_stores,
    "Average competitor minus Walmart": row.average_gap,
  }));
  return (
    <>
      <ExportButtons
        rows={exportRows}
        filename="competitive-geographic-scorecard"
      />
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
  productPackId,
}: Readonly<{
  view: CompetitiveProductLeadership;
  productPackId: string;
}>) {
  const summary = summarizeMatchGroup(view.relationships, view.outcomes);
  const rows = relationshipEvidence(view.relationships, view.outcomes).sort(
    (left, right) => right.benchmarkLocations - left.benchmarkLocations,
  );
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
                      : `${count(row.scoped_benchmark_locations)} governed benchmark stores`}
                  </dd>
                </div>
                <div>
                  <dt>Used as lowest eligible offer</dt>
                  <dd>{count(row.benchmarkLocations)} benchmark stores</dd>
                </div>
              </dl>
              <Link
                className={styles.reviewLink}
                href={`/admin/matching-v2?pack=${encodeURIComponent(productPackId)}&competitor=${encodeURIComponent(row.competitor_id)}&benchmark_product=${encodeURIComponent(row.benchmark_product_id)}&competitor_product=${encodeURIComponent(row.competitor_product_id)}`}
              >
                Open Match Certification evidence
              </Link>
            </article>
          ))}
        </div>
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
  const [scope, setScope] = useState<"all" | "exceptions">("all");
  const [status, setStatus] = useState<"all" | Outcome["status"]>("all");
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const rows = view.outcomes.filter((row) => {
    const inScope =
      scope === "all" || row.status === "losing" || row.status === "at_risk";
    return inScope && (status === "all" || row.status === status);
  });
  const visibleRows = rows.slice(page * pageSize, (page + 1) * pageSize);
  const exportRows = rows.map((row) => ({
    Status: statusLabel(row.status),
    "Walmart product": row.benchmark.product_name,
    "Walmart product ID": row.benchmark.product_id,
    "Walmart store": row.benchmark.store_number,
    City: row.benchmark.city,
    State: row.benchmark.state,
    ZIP: row.benchmark.zipcode,
    "Walmart price": row.benchmark.comparison_value,
    Competitor: row.competitor?.retailer_name ?? null,
    "Competitor product": row.competitor?.product_name ?? null,
    "Competitor product ID": row.competitor?.product_id ?? null,
    "Competitor store": row.competitor?.store_number ?? null,
    "Competitor price": row.competitor?.comparison_value ?? null,
    "Distance miles": row.distance_miles,
    "Competitor minus Walmart": row.competitor_minus_benchmark,
    "Walmart reduction to lead": row.comparison_value_reduction_to_lead,
  }));
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
              from Search evidence. Physical stores use the selected radius;
              service areas use the governed same-ZIP rule.
            </p>
          </div>
          <ExportButtons
            rows={exportRows}
            filename={
              scope === "exceptions"
                ? "competitive-store-exceptions"
                : "competitive-store-comparisons"
            }
          />
        </header>
        <div className={styles.filterToolbar}>
          <div className={styles.statusFilter}>
            {(["all", "exceptions"] as const).map((value) => (
              <button
                className={scope === value ? styles.active : ""}
                key={value}
                onClick={() => {
                  setScope(value);
                  setStatus("all");
                  setPage(0);
                }}
                type="button"
              >
                {value === "all" ? "All stores" : "Exceptions only"}
              </button>
            ))}
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
                {value === "all" ? "All statuses" : statusLabel(value)}
              </button>
            ))}
          </div>
        </div>
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

function MatchedPriceMatrix({
  view,
}: Readonly<{ view: CompetitiveProductLeadership }>) {
  const rows = view.price_ladder_summary.rows;
  const exportRows = rows.map((row) => ({
    Retailer: row.retailer_name,
    Product: row.product_name,
    "Product ID": row.product_id,
    "Brand type": brandType(row.brand_type),
    "Walmart anchor": row.is_benchmark ? "Yes" : "No",
    "Comparable Walmart stores": row.comparison_locations,
    "Footprint rate": row.footprint_rate,
    "Median price": row.price_median,
    "Minimum price": row.price_minimum,
    "Maximum price": row.price_maximum,
    "Median gap to Walmart": row.median_gap_to_benchmark,
    "Below Walmart stores": row.below_benchmark_locations,
    "Tied with Walmart stores": row.tied_benchmark_locations,
    "Above Walmart stores": row.above_benchmark_locations,
  }));
  if (!rows.length) {
    return (
      <section className={styles.card}>
        <header>
          <div>
            <h3>Matched price matrix unavailable</h3>
            <p>
              No certified matched product has comparable store-level evidence
              for the selected Walmart product, retailer, radius, and basis.
            </p>
          </div>
        </header>
      </section>
    );
  }
  return (
    <section className={styles.card}>
      <header>
        <div>
          <h3>Matched-product price matrix</h3>
          <p>
            Certified matched items positioned across the Walmart product&apos;s
            observed footprint. This is a product-match view—not the unmatched
            category price-band matrix in Price Intelligence.
          </p>
        </div>
        <ExportButtons rows={exportRows} filename="matched-price-matrix" />
      </header>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Retailer & product</th>
              <th>Comparable Walmart stores</th>
              <th>Footprint coverage</th>
              <th>Median price</th>
              <th>Observed range</th>
              <th>Median vs. Walmart</th>
              <th>Store-level position</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                className={row.is_benchmark ? styles.benchmarkRow : undefined}
                key={`${row.retailer_id}:${row.product_id}`}
              >
                <th>
                  <span className={styles.productCell}>
                    <ProductThumb
                      imageUrl={row.image_url}
                      name={row.product_name}
                    />
                    <span>
                      <b>
                        {row.retailer_name}
                        {row.is_benchmark ? " · Walmart anchor" : ""}
                      </b>
                      <small>
                        {row.product_name} · ID {row.product_id} ·{" "}
                        {brandType(row.brand_type)}
                      </small>
                    </span>
                  </span>
                </th>
                <td>{count(row.comparison_locations)}</td>
                <td>{rate(row.footprint_rate)}</td>
                <td>{money(row.price_median)}</td>
                <td>
                  {money(row.price_minimum)}–{money(row.price_maximum)}
                </td>
                <td>
                  {row.is_benchmark
                    ? "Anchor"
                    : signedMoney(row.median_gap_to_benchmark)}
                </td>
                <td>
                  {row.is_benchmark
                    ? "Walmart observed footprint"
                    : `${count(row.below_benchmark_locations)} below · ${count(row.tied_benchmark_locations)} tied · ${count(row.above_benchmark_locations)} above`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PriceLadders({
  view,
}: Readonly<{
  view: CompetitiveProductLeadership;
}>) {
  const ladder = view.price_ladder_summary;
  if (!ladder.rows.length) {
    return (
      <section className={styles.card}>
        <header>
          <div>
            <h3>Footprint price ladder unavailable</h3>
            <p>
              No governed competitor product is geographically comparable to
              this Walmart product under the current filters.
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
          label="Comparable Walmart stores"
          value={count(ladder.comparable_benchmark_locations)}
          note={`${count(ladder.benchmark_observed_locations)} Walmart stores observed`}
        />
        <KpiCard
          label="Median Walmart rank"
          value={
            ladder.median_benchmark_rank === null
              ? "—"
              : `#${ladder.median_benchmark_rank.toFixed(1)}`
          }
          note="Median local rank wherever a governed competitor is comparable"
        />
        <KpiCard
          label="Walmart rank-one share"
          value={rate(ladder.benchmark_rank_one_rate)}
          note={`${count(ladder.benchmark_rank_one_locations)} comparable stores at rank one`}
          tone={
            (ladder.benchmark_rank_one_rate ?? 0) >= 0.8 ? "good" : "warning"
          }
        />
        <KpiCard
          label="Products positioned"
          value={count(ladder.rows.length)}
          note="One footprint row per governed retailer product"
        />
        <KpiCard
          label="Geographic rule"
          value={`${count(view.filters.radius_miles)} mi`}
          note="Physical stores use radius; service areas use same ZIP"
        />
      </div>
      <section className={styles.card}>
        <header>
          <div>
            <h3>Footprint-level governed price ladder</h3>
            <p>{ladder.definition}</p>
          </div>
        </header>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Position</th>
                <th>Product</th>
                <th>Comparable footprint</th>
                <th>Median price</th>
                <th>Observed range</th>
                <th>Median vs. Walmart</th>
                <th>Store positions</th>
              </tr>
            </thead>
            <tbody>
              {ladder.rows.map((row) => (
                <tr
                  className={row.is_benchmark ? styles.benchmarkRow : undefined}
                  key={`${row.retailer_id}:${row.product_id}`}
                >
                  <td>
                    <strong>#{count(row.position)}</strong>
                  </td>
                  <th>
                    <span className={styles.productCell}>
                      <span className={styles.productThumb}>
                        {row.image_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={row.image_url} alt="" />
                        ) : (
                          row.product_name.slice(0, 1)
                        )}
                      </span>
                      <span>
                        <b>
                          {row.is_benchmark
                            ? `${row.retailer_name} · benchmark`
                            : row.retailer_name}
                        </b>
                        <small>
                          {row.product_name} · {brandType(row.brand_type)}
                        </small>
                      </span>
                    </span>
                  </th>
                  <td>
                    {count(row.comparison_locations)} stores ·{" "}
                    {rate(row.footprint_rate)}
                  </td>
                  <td>{money(row.price_median)}</td>
                  <td>
                    {money(row.price_minimum)}–{money(row.price_maximum)}
                  </td>
                  <td>
                    {row.is_benchmark
                      ? "Anchor"
                      : signedMoney(row.median_gap_to_benchmark)}
                  </td>
                  <td>
                    {row.is_benchmark
                      ? "Benchmark footprint"
                      : `${count(row.below_benchmark_locations)} below · ${count(row.tied_benchmark_locations)} tied · ${count(row.above_benchmark_locations)} above`}
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
  productPackId,
  competitorId,
  profileId,
  productId,
  radiusMiles,
  stateFilter,
  cityFilter,
  viewName,
  onGeographyOptions,
}: Readonly<{
  analysisId: string;
  productPackId: string;
  competitorId: string;
  profileId: string;
  productId: string | null;
  radiusMiles: 1 | 3 | 5;
  stateFilter: string | null;
  cityFilter: string | null;
  viewName: ProductLeadershipViewName;
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
  const [selected, setSelected] = useState<Outcome | null>(null);
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
    let active = true;
    loadCompetitiveProductLeadership({
      analysisId,
      competitorId,
      profileId,
      productId,
      radiusMiles,
      stateFilter,
      cityFilter,
    })
      .then((body) => {
        if (!active) return;
        setFailedView(null);
        setLoadedView({ query, data: body });
        setSelected(
          body.outcomes.find((row) => row.status === "losing") ??
            body.outcomes[0] ??
            null,
        );
      })
      .catch((cause: unknown) => {
        if (active)
          setFailedView({
            query,
            message:
              cause instanceof Error
                ? cause.message
                : "Leadership evidence is unavailable.",
          });
      });
    return () => {
      active = false;
    };
  }, [
    analysisId,
    cityFilter,
    competitorId,
    productId,
    profileId,
    query,
    radiusMiles,
    stateFilter,
  ]);

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
          onOpenState={drillState}
        />
      ) : null}
      {viewName === "matrix" ? <MatchedPriceMatrix view={view} /> : null}
      {viewName === "match_group" ? (
        <MatchGroupAnalysis view={view} productPackId={productPackId} />
      ) : null}
      {viewName === "ladders" ? <PriceLadders view={view} /> : null}
      {viewName === "stores" ? <StoreComparisons view={view} /> : null}
      {viewName === "history" ? <CompetitiveHistory view={view} /> : null}
    </div>
  );
}
