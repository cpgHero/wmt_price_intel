"use client";

import { useMemo, useState } from "react";

import type { LocationRetailer, ProximityPair, ProximityView } from "@/lib/api";

import styles from "./proximity-workspace.module.css";

const RADIUS_OPTIONS = [1, 3, 5, 10] as const;
type RelationFilter = "all" | "within" | "outside";
type SortMode = "nearest" | "farthest" | "state" | "store";

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

function miles(value: number | null) {
  if (value === null) return "—";
  return `${new Intl.NumberFormat("en-US", {
    maximumFractionDigits: value >= 10 ? 1 : 2,
  }).format(value)} mi`;
}

function locationLabel(location: ProximityPair["benchmark"]) {
  return [location.store_name, location.city, location.state, location.zipcode]
    .filter(Boolean)
    .join(" · ");
}

function googleMapsUrl(latitude: number, longitude: number) {
  return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
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
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
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

function projection(rows: ProximityPair[]) {
  const points = rows.flatMap((pair) => [pair.benchmark, pair.competitor]);
  if (!points.length) {
    return () => ({ x: 500, y: 300 });
  }
  const minLon = Math.min(...points.map((point) => point.longitude));
  const maxLon = Math.max(...points.map((point) => point.longitude));
  const minLat = Math.min(...points.map((point) => point.latitude));
  const maxLat = Math.max(...points.map((point) => point.latitude));
  const lonSpan = Math.max(0.25, maxLon - minLon);
  const latSpan = Math.max(0.25, maxLat - minLat);
  const scale = Math.min(900 / lonSpan, 520 / latSpan);
  const renderedWidth = lonSpan * scale;
  const renderedHeight = latSpan * scale;
  const left = (1000 - renderedWidth) / 2;
  const top = (620 - renderedHeight) / 2;
  return (longitude: number, latitude: number) => ({
    x: left + (longitude - minLon) * scale,
    y: top + (maxLat - latitude) * scale,
  });
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
    initialView?.selected_radius_miles ?? 10,
  );
  const [query, setQuery] = useState("");
  const [stateFilter, setStateFilter] = useState("all");
  const [relation, setRelation] = useState<RelationFilter>("all");
  const [sort, setSort] = useState<SortMode>("nearest");
  const [showFilters, setShowFilters] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(
    initialView?.pairs[0]?.benchmark.id ?? null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const benchmarkId = country === "CANADA" ? "walmart_ca" : "walmart_us";
  const competitorOptions = retailers.filter(
    (retailer) =>
      retailer.country === country &&
      retailer.id !== benchmarkId &&
      !retailer.id.startsWith("walmart_") &&
      retailer.location_count > 0,
  );

  async function load(next: {
    country?: string;
    competitorRetailerId?: string;
    radius?: number;
  }) {
    const nextCountry = next.country ?? country;
    const nextRetailerResponse =
      next.country && next.country !== country
        ? await fetch(
            `/api/proximity/retailers?country=${encodeURIComponent(nextCountry)}`,
          )
            .then((response) => response.json())
            .catch(() => [])
        : retailers;
    const nextRetailers: LocationRetailer[] = Array.isArray(
      nextRetailerResponse,
    )
      ? nextRetailerResponse
      : [];
    if (next.country && next.country !== country) {
      setRetailers(nextRetailers);
    }
    const nextBenchmark =
      nextCountry === "CANADA" ? "walmart_ca" : "walmart_us";
    const selectedCompetitor =
      next.competitorRetailerId ||
      nextRetailers.find(
        (retailer: LocationRetailer) =>
          retailer.country === nextCountry &&
          retailer.id !== nextBenchmark &&
          !retailer.id.startsWith("walmart_") &&
          retailer.location_count > 0,
      )?.id ||
      "";
    setCountry(nextCountry);
    setCompetitorRetailerId(selectedCompetitor);
    setRadius(next.radius ?? radius);
    setError(null);
    setLoading(true);
    try {
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
        selected_radius_miles: String(next.radius ?? radius),
      });
      const response = await fetch(`/api/proximity?${parameters.toString()}`, {
        cache: "no-store",
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error || "Proximity data could not be loaded.");
      setView(body);
      setSelectedKey(body.pairs?.[0]?.benchmark?.id ?? null);
      setStateFilter("all");
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

  const filteredPairs = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const rows = (view?.pairs ?? [])
      .filter((pair) => {
        if (stateFilter !== "all" && pair.benchmark.state !== stateFilter)
          return false;
        if (relation === "within" && pair.distance_miles > radius) return false;
        if (relation === "outside" && pair.distance_miles <= radius)
          return false;
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
    return rows;
  }, [query, radius, relation, sort, stateFilter, view?.pairs]);

  const selectedPair =
    filteredPairs.find((pair) => pair.benchmark.id === selectedKey) ??
    filteredPairs[0] ??
    null;
  const project = projection(filteredPairs);
  const competitorPoints = Array.from(
    new Map(
      filteredPairs.map((pair) => [pair.competitor.id, pair.competitor]),
    ).values(),
  );

  return (
    <div className={styles.workspace}>
      <section className={styles.toolbar} aria-label="Proximity controls">
        <label>
          <span>Walmart market</span>
          <select
            value={country}
            onChange={(event) => void load({ country: event.target.value })}
          >
            <option value="USA">Walmart US</option>
            <option value="CANADA">Walmart CA</option>
          </select>
        </label>
        <label>
          <span>Compare to one retailer</span>
          <select
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
        <label>
          <span>Radius</span>
          <div className={styles.radiusGroup}>
            {RADIUS_OPTIONS.map((option) => (
              <button
                aria-pressed={radius === option}
                key={option}
                onClick={() => void load({ radius: option })}
                type="button"
              >
                {option} mi
              </button>
            ))}
          </div>
        </label>
        <label>
          <span>Search</span>
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Store, city, state, ZIP"
            type="search"
            value={query}
          />
        </label>
        <button
          className={styles.secondaryButton}
          onClick={() => setShowFilters((value) => !value)}
          type="button"
        >
          Filters
        </button>
      </section>

      {showFilters ? (
        <section className={styles.filterDrawer} aria-label="Proximity filters">
          <label>
            <span>Walmart state/province</span>
            <select
              value={stateFilter}
              onChange={(event) => setStateFilter(event.target.value)}
            >
              <option value="all">All</option>
              {(view?.state_options ?? []).map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Relationship</span>
            <select
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
          <label>
            <span>Sort</span>
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value as SortMode)}
            >
              <option value="nearest">Nearest first</option>
              <option value="farthest">Farthest first</option>
              <option value="state">State then store</option>
              <option value="store">Store number</option>
            </select>
          </label>
          <label>
            <span>Filtered rows</span>
            <input readOnly value={count(filteredPairs.length)} />
          </label>
          <button
            className={styles.secondaryButton}
            onClick={() => {
              setQuery("");
              setStateFilter("all");
              setRelation("all");
              setSort("nearest");
            }}
            type="button"
          >
            Reset
          </button>
        </section>
      ) : null}

      {error ? (
        <div className={`${styles.notice} ${styles.warning}`}>{error}</div>
      ) : null}
      {loading ? (
        <div className={styles.notice}>Loading proximity data…</div>
      ) : null}

      <section className={styles.kpis} aria-label="Proximity summary">
        <article className={styles.kpi}>
          <span>Walmart mappable locations</span>
          <strong>
            {count(view?.summary.benchmark_mappable_locations ?? 0)}
          </strong>
          <small>
            {view
              ? `${count(view.benchmark.location_count)} eligible locations in location master`
              : "No benchmark data loaded"}
          </small>
        </article>
        <article className={styles.kpi}>
          <span>Competitor mappable locations</span>
          <strong>
            {count(view?.summary.competitor_mappable_locations ?? 0)}
          </strong>
          <small>
            {view
              ? `${view.competitor.display_name} · ${count(view.competitor.location_count)} eligible`
              : "Select one competitor retailer"}
          </small>
        </article>
        <article className={styles.kpi}>
          <span>Within selected radius</span>
          <strong>{count(view?.summary.within_selected_radius ?? 0)}</strong>
          <small>
            {view
              ? `${percent(view.summary.within_selected_radius_share)} of Walmart locations`
              : "—"}
          </small>
        </article>
        <article className={styles.kpi}>
          <span>Median nearest distance</span>
          <strong>
            {miles(view?.summary.nearest_distance_median_miles ?? null)}
          </strong>
          <small>Haversine straight-line distance, not drive time</small>
        </article>
      </section>

      <section className={styles.bodyGrid}>
        <aside className={styles.listPanel}>
          <div className={styles.panelHead}>
            <div>
              <h2>Nearest competitor relationships</h2>
              <p>
                Comprehensive list: {count(filteredPairs.length)} of{" "}
                {count(view?.pairs.length ?? 0)} Walmart locations.
              </p>
            </div>
            <button
              className={styles.secondaryButton}
              onClick={() => setShowTable((value) => !value)}
              type="button"
            >
              Table
            </button>
          </div>
          <div className={styles.pairList}>
            {filteredPairs.slice(0, 250).map((pair) => (
              <button
                aria-pressed={selectedPair?.benchmark.id === pair.benchmark.id}
                className={styles.pairButton}
                key={pair.benchmark.id}
                onClick={() => setSelectedKey(pair.benchmark.id)}
                type="button"
              >
                <strong>
                  Walmart #{pair.benchmark.store_number} ·{" "}
                  <span className={styles.distance}>
                    {miles(pair.distance_miles)}
                  </span>
                </strong>
                <small>{locationLabel(pair.benchmark)}</small>
                <small>
                  Nearest {pair.competitor.retailer_display_name} #
                  {pair.competitor.store_number} ·{" "}
                  {locationLabel(pair.competitor)}
                </small>
              </button>
            ))}
            {filteredPairs.length > 250 ? (
              <p className={styles.empty}>
                Showing first 250 in the side list for speed. Open Table for all{" "}
                {count(filteredPairs.length)} rows and downloads.
              </p>
            ) : null}
          </div>
        </aside>

        <section className={styles.mapPanel} aria-label="Proximity map">
          <div className={styles.mapHead}>
            <div>
              <h2>
                {view?.benchmark.display_name ?? "Walmart"} ×{" "}
                {view?.competitor.display_name ?? "Competitor"}
              </h2>
              <p>
                Location-master proximity map. Lines show selected Walmart
                locations to their nearest selected competitor location.
              </p>
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
                <i className={styles.lineDot} />
                nearest pair
              </span>
            </div>
          </div>
          {filteredPairs.length ? (
            <svg className={styles.mapSvg} role="img" viewBox="0 0 1000 620">
              <title>Retailer proximity map</title>
              <rect fill="transparent" height="620" width="1000" />
              {filteredPairs.slice(0, 1200).map((pair) => {
                const start = project(
                  pair.benchmark.longitude,
                  pair.benchmark.latitude,
                );
                const end = project(
                  pair.competitor.longitude,
                  pair.competitor.latitude,
                );
                const selected =
                  selectedPair?.benchmark.id === pair.benchmark.id;
                return (
                  <line
                    key={`line-${pair.benchmark.id}`}
                    stroke={selected ? "#087d72" : "rgba(8, 125, 114, 0.18)"}
                    strokeWidth={selected ? 2.5 : 0.8}
                    x1={start.x}
                    x2={end.x}
                    y1={start.y}
                    y2={end.y}
                  />
                );
              })}
              {competitorPoints.map((location) => {
                const point = project(location.longitude, location.latitude);
                return (
                  <circle
                    cx={point.x}
                    cy={point.y}
                    fill="#da4760"
                    key={location.id}
                    opacity="0.75"
                    r="3.6"
                  />
                );
              })}
              {filteredPairs.map((pair) => {
                const point = project(
                  pair.benchmark.longitude,
                  pair.benchmark.latitude,
                );
                const selected =
                  selectedPair?.benchmark.id === pair.benchmark.id;
                return (
                  <circle
                    cx={point.x}
                    cy={point.y}
                    fill={
                      pair.distance_miles <= radius ? "#1673db" : "transparent"
                    }
                    key={pair.benchmark.id}
                    onClick={() => setSelectedKey(pair.benchmark.id)}
                    opacity={selected ? 1 : 0.82}
                    r={selected ? 6.5 : 3.7}
                    stroke="#1673db"
                    strokeWidth={selected ? 2.4 : 1.2}
                  />
                );
              })}
            </svg>
          ) : (
            <div className={styles.empty}>
              No mappable retailer relationships match the current filters.
            </div>
          )}
          <div className={styles.mapFooter}>
            <span>
              {view?.distance_methodology ?? "No proximity dataset loaded."}
            </span>
            <span>
              1/3/5/10 mi: {count(view?.summary.within_1_mile ?? 0)} /{" "}
              {count(view?.summary.within_3_miles ?? 0)} /{" "}
              {count(view?.summary.within_5_miles ?? 0)} /{" "}
              {count(view?.summary.within_10_miles ?? 0)}
            </span>
          </div>
        </section>
      </section>

      {selectedPair ? (
        <section
          className={styles.detailDrawer}
          aria-label="Selected proximity relationship"
        >
          <div className={styles.panelHead}>
            <div>
              <h2>
                Selected pair ·{" "}
                <span className={styles.distance}>
                  {miles(selectedPair.distance_miles)}
                </span>
              </h2>
              <p>
                This drawer uses the same filtered location rows as the side
                list, map, and downloads.
              </p>
            </div>
            <div className={styles.downloadRow}>
              <button
                className={styles.secondaryButton}
                onClick={() =>
                  downloadCsv(filteredPairs, radius, "proximity-filtered.csv")
                }
                type="button"
              >
                CSV
              </button>
              <button
                className={styles.secondaryButton}
                onClick={() =>
                  downloadCsv(
                    filteredPairs,
                    radius,
                    "proximity-filtered-excel.csv",
                  )
                }
                type="button"
              >
                Excel CSV
              </button>
              <button
                className={styles.secondaryButton}
                onClick={() =>
                  downloadJson(filteredPairs, radius, "proximity-filtered.json")
                }
                type="button"
              >
                JSON
              </button>
            </div>
          </div>
          <div className={styles.detailGrid}>
            <article className={styles.detailCard}>
              <h3>Walmart location</h3>
              <p>
                #{selectedPair.benchmark.store_number} ·{" "}
                {locationLabel(selectedPair.benchmark)}
                <br />
                {selectedPair.benchmark.latitude.toFixed(5)},{" "}
                {selectedPair.benchmark.longitude.toFixed(5)}
                <br />
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
              </p>
            </article>
            <article className={styles.detailCard}>
              <h3>Nearest selected competitor</h3>
              <p>
                {selectedPair.competitor.retailer_display_name} #
                {selectedPair.competitor.store_number} ·{" "}
                {locationLabel(selectedPair.competitor)}
                <br />
                {selectedPair.competitor.latitude.toFixed(5)},{" "}
                {selectedPair.competitor.longitude.toFixed(5)}
                <br />
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
              </p>
            </article>
          </div>
        </section>
      ) : null}

      {showTable ? (
        <section className={styles.detailDrawer} aria-label="Location table">
          <div className={styles.panelHead}>
            <div>
              <h2>Location table</h2>
              <p>
                All filtered Walmart rows with their nearest selected
                competitor. Counts and exports reconcile to this table.
              </p>
            </div>
            <button
              className={styles.secondaryButton}
              onClick={() => setShowTable(false)}
              type="button"
            >
              Close
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
                  <th>Coordinates</th>
                </tr>
              </thead>
              <tbody>
                {filteredPairs.map((pair) => (
                  <tr key={pair.benchmark.id}>
                    <td>{pair.benchmark.store_number}</td>
                    <td>{locationLabel(pair.benchmark)}</td>
                    <td>{pair.competitor.store_number}</td>
                    <td>{locationLabel(pair.competitor)}</td>
                    <td>{miles(pair.distance_miles)}</td>
                    <td>{pair.distance_miles <= radius ? "Yes" : "No"}</td>
                    <td>
                      {pair.benchmark.latitude.toFixed(4)},{" "}
                      {pair.benchmark.longitude.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}
