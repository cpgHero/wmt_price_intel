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

function locationLabel(location: ProximityPair["benchmark"]) {
  return [location.store_name, location.city, location.state, location.zipcode]
    .filter(Boolean)
    .join(" · ");
}

function googleMapsUrl(latitude: number, longitude: number) {
  return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
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

function mercator(longitude: number, latitude: number) {
  const limitedLatitude = Math.max(
    -85.05112878,
    Math.min(85.05112878, latitude),
  );
  const sine = Math.sin((limitedLatitude * Math.PI) / 180);
  return {
    x: (longitude + 180) / 360,
    y: 0.5 - Math.log((1 + sine) / (1 - sine)) / (4 * Math.PI),
  };
}

function tickValues(minimum: number, maximum: number, target = 6) {
  const span = Math.max(1, maximum - minimum);
  const raw = span / target;
  const exponent = Math.floor(Math.log10(raw));
  const base = 10 ** exponent;
  const scaled = raw / base;
  const step =
    (scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10) * base;
  const first = Math.ceil(minimum / step) * step;
  const ticks: number[] = [];
  for (let value = first; value <= maximum; value += step) {
    ticks.push(Number(value.toFixed(4)));
  }
  return ticks;
}

function projection(rows: ProximityPair[]) {
  const points = rows.flatMap((pair) => [pair.benchmark, pair.competitor]);
  if (!points.length) {
    return {
      bounds: {
        maxLatitude: 50,
        maxLongitude: -66,
        minLatitude: 24,
        minLongitude: -125,
      },
      latitudeTicks: [],
      longitudeTicks: [],
      point: () => ({ x: 500, y: 320 }),
    };
  }
  const minLongitude = Math.min(...points.map((point) => point.longitude));
  const maxLongitude = Math.max(...points.map((point) => point.longitude));
  const minLatitude = Math.min(...points.map((point) => point.latitude));
  const maxLatitude = Math.max(...points.map((point) => point.latitude));
  const projected = points.map((point) =>
    mercator(point.longitude, point.latitude),
  );
  const minX = Math.min(...projected.map((point) => point.x));
  const maxX = Math.max(...projected.map((point) => point.x));
  const minY = Math.min(...projected.map((point) => point.y));
  const maxY = Math.max(...projected.map((point) => point.y));
  const xSpan = Math.max(0.003, maxX - minX);
  const ySpan = Math.max(0.003, maxY - minY);
  const scale = Math.min(870 / xSpan, 520 / ySpan);
  const renderedWidth = xSpan * scale;
  const renderedHeight = ySpan * scale;
  const left = (1000 - renderedWidth) / 2;
  const top = (640 - renderedHeight) / 2 + 14;
  return {
    bounds: { maxLatitude, maxLongitude, minLatitude, minLongitude },
    latitudeTicks: tickValues(minLatitude, maxLatitude, 7),
    longitudeTicks: tickValues(minLongitude, maxLongitude, 7),
    point: (longitude: number, latitude: number) => {
      const position = mercator(longitude, latitude);
      return {
        x: left + (position.x - minX) * scale,
        y: top + (position.y - minY) * scale,
      };
    },
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

  const competitorOptions = useMemo(
    () => availableCompetitors(retailers, country),
    [country, retailers],
  );

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
      setCountry(nextCountry);
      setCompetitorRetailerId(selectedCompetitor);
      setRadius(next.radius ?? radius);
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
      if (!response.ok) {
        throw new Error(body.error || "Proximity data could not be loaded.");
      }
      setView(body);
      setSelectedKey(body.pairs?.[0]?.benchmark?.id ?? null);
      setStateFilter("all");
      setRelation("all");
      setSort("nearest");
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
    return (view?.pairs ?? [])
      .filter((pair) => {
        if (stateFilter !== "all" && pair.benchmark.state !== stateFilter) {
          return false;
        }
        if (relation === "within" && pair.distance_miles > radius) return false;
        if (relation === "outside" && pair.distance_miles <= radius) {
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
        if (sort === "farthest") {
          return right.distance_miles - left.distance_miles;
        }
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
  }, [query, radius, relation, sort, stateFilter, view?.pairs]);

  const selectedPair =
    filteredPairs.find((pair) => pair.benchmark.id === selectedKey) ??
    filteredPairs[0] ??
    null;
  const map = useMemo(() => projection(filteredPairs), [filteredPairs]);
  const competitorPoints = useMemo(
    () =>
      Array.from(
        new Map(
          filteredPairs.map((pair) => [pair.competitor.id, pair.competitor]),
        ).values(),
      ),
    [filteredPairs],
  );
  const filteredWithin = filteredPairs.filter(
    (pair) => pair.distance_miles <= radius,
  ).length;
  const visibleMedian = median(
    filteredPairs.map((pair) => pair.distance_miles),
  );
  const visibleCompetitorSites = competitorPoints.length;
  const stateOptions = view?.state_options ?? [];
  const visibleShare = filteredPairs.length
    ? filteredWithin / filteredPairs.length
    : null;

  return (
    <div className={styles.workspace}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <div className={styles.brandMark}>↔</div>
          <div>
            <div className={styles.brandWord}>CPGHero Proximity</div>
            <div className={styles.brandCaption}>
              Walmart {country === "CANADA" ? "CA" : "US"} vs one retailer
            </div>
          </div>
        </div>
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
        </div>
        <div className={styles.actions}>
          <button
            className={styles.btn}
            onClick={() => setShowFilters(true)}
            type="button"
          >
            Filters
          </button>
          <button
            className={`${styles.btn} ${styles.primary}`}
            onClick={() => setShowTable(true)}
            type="button"
          >
            Location table
          </button>
        </div>
      </header>

      <section className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>Analytics</p>
          <h1>Retailer proximity explorer</h1>
          <p>
            Source-backed nearest-store relationships from the location master.
            Distances are Haversine straight-line miles; this is not drive time,
            inventory, assortment, or product distribution.
          </p>
        </div>
        <div className={styles.snapshot}>
          <i />
          {view ? count(view.summary.paired_locations) : "No"} Walmart locations
          paired
        </div>
      </section>

      {error ? (
        <div className={`${styles.notice} ${styles.warning}`}>{error}</div>
      ) : null}
      {loading ? (
        <div className={styles.notice}>Loading proximity data…</div>
      ) : null}

      <section className={styles.kpis} aria-label="Proximity summary">
        <article className={styles.kpi}>
          <div>
            <span>Visible Walmart locations</span>
            <strong>{count(filteredPairs.length)}</strong>
            <small>
              {view
                ? `${count(view.summary.paired_locations)} total paired in this comparison`
                : "No comparison loaded"}
            </small>
          </div>
          <b className={`${styles.kpiIcon} ${styles.blue}`}>W</b>
        </article>
        <article className={styles.kpi}>
          <div>
            <span>Within {radius} miles</span>
            <strong>{count(filteredWithin)}</strong>
            <small>{percent(visibleShare)} of visible Walmart locations</small>
          </div>
          <b className={`${styles.kpiIcon} ${styles.green}`}>≤</b>
        </article>
        <article className={styles.kpi}>
          <div>
            <span>Median nearest distance</span>
            <strong>{miles(visibleMedian)}</strong>
            <small>
              Average full-network distance:{" "}
              {miles(view?.summary.nearest_distance_average_miles ?? null)}
            </small>
          </div>
          <b className={`${styles.kpiIcon} ${styles.green}`}>mi</b>
        </article>
        <article className={styles.kpi}>
          <div>
            <span>Competitor sites represented</span>
            <strong>{count(visibleCompetitorSites)}</strong>
            <small>
              {view
                ? `${count(view.summary.competitor_mappable_locations)} mappable ${view.competitor.display_name} sites`
                : "Select a competitor"}
            </small>
          </div>
          <b className={`${styles.kpiIcon} ${styles.red}`}>C</b>
        </article>
      </section>

      <section className={styles.explorer}>
        <aside className={styles.sidebar}>
          <div className={styles.sideFilter}>
            <div className={styles.sectionLine}>
              <h2>Controls</h2>
              <button
                className={styles.textButton}
                onClick={() => {
                  setQuery("");
                  setStateFilter("all");
                  setRelation("all");
                  setSort("nearest");
                }}
                type="button"
              >
                Reset view
              </button>
            </div>
            <label className={styles.field}>
              <span>Walmart market</span>
              <select
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
              <span>Radius</span>
              <div className={styles.radiusSet}>
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
            </div>
            <label className={styles.searchbox}>
              <span>⌕</span>
              <input
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search store, city, state, ZIP"
                type="search"
                value={query}
              />
            </label>
            <div
              className={styles.relationSet}
              aria-label="Relationship filter"
            >
              <button
                className={relation === "all" ? styles.active : undefined}
                onClick={() => setRelation("all")}
                type="button"
              >
                All
              </button>
              <button
                className={relation === "within" ? styles.active : undefined}
                onClick={() => setRelation("within")}
                type="button"
              >
                Inside
              </button>
              <button
                className={relation === "outside" ? styles.active : undefined}
                onClick={() => setRelation("outside")}
                type="button"
              >
                Gaps
              </button>
            </div>
            <div className={styles.scopeChip}>
              <span>{count(filteredPairs.length)} visible pairs</span>
              <span>{count(stateOptions.length)} states/provinces</span>
            </div>
          </div>

          <div className={styles.listTop}>
            <div className={styles.listTabs}>
              <button
                className={relation === "all" ? styles.activeTab : undefined}
                onClick={() => setRelation("all")}
                type="button"
              >
                All <span>{count(view?.pairs.length ?? 0)}</span>
              </button>
              <button
                className={relation === "within" ? styles.activeTab : undefined}
                onClick={() => setRelation("within")}
                type="button"
              >
                Inside <span>{count(filteredWithin)}</span>
              </button>
              <button
                className={
                  relation === "outside" ? styles.activeTab : undefined
                }
                onClick={() => setRelation("outside")}
                type="button"
              >
                Gaps{" "}
                <span>
                  {count(Math.max(0, filteredPairs.length - filteredWithin))}
                </span>
              </button>
            </div>
            <div className={styles.sortRow}>
              <span>Nearest relationships</span>
              <select
                value={sort}
                onChange={(event) => setSort(event.target.value as SortMode)}
              >
                <option value="nearest">Nearest first</option>
                <option value="farthest">Farthest first</option>
                <option value="state">State then store</option>
                <option value="store">Store number</option>
              </select>
            </div>
          </div>

          <div className={styles.pairList}>
            {filteredPairs.slice(0, 500).map((pair) => {
              const selected = selectedPair?.benchmark.id === pair.benchmark.id;
              return (
                <button
                  aria-pressed={selected}
                  className={styles.storeCard}
                  key={pair.benchmark.id}
                  onClick={() => setSelectedKey(pair.benchmark.id)}
                  type="button"
                >
                  <span className={styles.retIcon}>W</span>
                  <span className={styles.storeText}>
                    <strong>
                      #{pair.benchmark.store_number} ·{" "}
                      {pair.benchmark.city || "Unknown city"},{" "}
                      {pair.benchmark.state || "—"}
                    </strong>
                    <small>
                      {pair.benchmark.store_name || "Walmart location"}
                    </small>
                    <small>
                      Nearest {pair.competitor.retailer_display_name} #
                      {pair.competitor.store_number}
                    </small>
                  </span>
                  <span
                    className={
                      pair.distance_miles <= radius
                        ? styles.distance
                        : `${styles.distance} ${styles.out}`
                    }
                  >
                    {miles(pair.distance_miles)}
                  </span>
                </button>
              );
            })}
            {filteredPairs.length > 500 ? (
              <p className={styles.listNote}>
                Showing first 500 in this rail for speed. Open the location
                table for all {count(filteredPairs.length)} visible rows and
                downloads.
              </p>
            ) : null}
            {!filteredPairs.length ? (
              <p className={styles.empty}>
                No mappable retailer relationships match the current filters.
              </p>
            ) : null}
          </div>

          <div className={styles.sideBottom}>
            <button onClick={() => setShowTable(true)} type="button">
              Export visible rows
            </button>
            <span>{view?.schema_version ?? "No schema"}</span>
          </div>
        </aside>

        <section className={styles.mapSection} aria-label="Proximity map">
          <div className={styles.mapArea}>
            <div className={styles.mapToolbar}>
              <div className={styles.quickViews}>
                <button
                  className={relation === "all" ? styles.active : undefined}
                  onClick={() => setRelation("all")}
                  type="button"
                >
                  Full network
                </button>
                <button
                  className={relation === "within" ? styles.active : undefined}
                  onClick={() => setRelation("within")}
                  type="button"
                >
                  Covered
                </button>
                <button
                  className={relation === "outside" ? styles.active : undefined}
                  onClick={() => setRelation("outside")}
                  type="button"
                >
                  White space
                </button>
              </div>
              <div className={styles.mapTools}>
                <button
                  className={styles.iconButton}
                  onClick={() => setShowFilters(true)}
                  title="Open filter drawer"
                  type="button"
                >
                  ⚙
                </button>
                <button
                  className={styles.iconButton}
                  onClick={() => setShowTable(true)}
                  title="Open full table"
                  type="button"
                >
                  ⇩
                </button>
              </div>
            </div>

            {filteredPairs.length ? (
              <svg className={styles.mapSvg} role="img" viewBox="0 0 1000 640">
                <title>Retailer proximity map</title>
                <rect className={styles.water} height="640" width="1000" />
                <rect
                  className={styles.landMass}
                  height="520"
                  rx="120"
                  width="850"
                  x="75"
                  y="70"
                />
                {map.longitudeTicks.map((longitude) => {
                  const top = map.point(longitude, map.bounds.maxLatitude);
                  const bottom = map.point(longitude, map.bounds.minLatitude);
                  return (
                    <g key={`lon-${longitude}`}>
                      <line
                        className={styles.gridLine}
                        x1={top.x}
                        x2={bottom.x}
                        y1={top.y}
                        y2={bottom.y}
                      />
                      <text className={styles.gridLabel} x={top.x + 4} y="622">
                        {Math.abs(Math.round(longitude))}°W
                      </text>
                    </g>
                  );
                })}
                {map.latitudeTicks.map((latitude) => {
                  const left = map.point(map.bounds.minLongitude, latitude);
                  const right = map.point(map.bounds.maxLongitude, latitude);
                  return (
                    <g key={`lat-${latitude}`}>
                      <line
                        className={styles.gridLine}
                        x1={left.x}
                        x2={right.x}
                        y1={left.y}
                        y2={right.y}
                      />
                      <text className={styles.gridLabel} x="18" y={left.y - 4}>
                        {Math.abs(Math.round(latitude))}°N
                      </text>
                    </g>
                  );
                })}
                <text className={styles.mapLabel} x="78" y="112">
                  {country === "CANADA" ? "CANADA" : "UNITED STATES"}
                </text>
                {filteredPairs.slice(0, 1800).map((pair) => {
                  const start = map.point(
                    pair.benchmark.longitude,
                    pair.benchmark.latitude,
                  );
                  const end = map.point(
                    pair.competitor.longitude,
                    pair.competitor.latitude,
                  );
                  const selected =
                    selectedPair?.benchmark.id === pair.benchmark.id;
                  return (
                    <line
                      className={
                        selected
                          ? styles.selectedLine
                          : pair.distance_miles <= radius
                            ? styles.coveredLine
                            : styles.gapLine
                      }
                      key={`line-${pair.benchmark.id}`}
                      x1={start.x}
                      x2={end.x}
                      y1={start.y}
                      y2={end.y}
                    />
                  );
                })}
                {competitorPoints.map((location) => {
                  const point = map.point(
                    location.longitude,
                    location.latitude,
                  );
                  return (
                    <rect
                      className={styles.competitorPoint}
                      height="6.5"
                      key={location.id}
                      rx="1.8"
                      width="6.5"
                      x={point.x - 3.25}
                      y={point.y - 3.25}
                    />
                  );
                })}
                {filteredPairs.map((pair) => {
                  const point = map.point(
                    pair.benchmark.longitude,
                    pair.benchmark.latitude,
                  );
                  const selected =
                    selectedPair?.benchmark.id === pair.benchmark.id;
                  return (
                    <circle
                      className={
                        selected
                          ? styles.selectedPoint
                          : pair.distance_miles <= radius
                            ? styles.walmartPoint
                            : styles.walmartPointOut
                      }
                      cx={point.x}
                      cy={point.y}
                      key={pair.benchmark.id}
                      onClick={() => setSelectedKey(pair.benchmark.id)}
                      r={selected ? 7 : 3.6}
                    />
                  );
                })}
              </svg>
            ) : (
              <div className={styles.mapEmpty}>
                No mappable retailer relationships match the current filters.
              </div>
            )}

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

            <div className={styles.zoomControl} aria-hidden="true">
              <button tabIndex={-1} type="button">
                +
              </button>
              <button tabIndex={-1} type="button">
                −
              </button>
            </div>

            {selectedPair ? (
              <aside className={styles.detailPanel} aria-label="Selected pair">
                <div className={styles.detailHeader}>
                  <span>Selected relationship</span>
                  <strong>{miles(selectedPair.distance_miles)}</strong>
                </div>
                <div className={styles.detailStack}>
                  <article>
                    <b>Walmart</b>
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
                      Open coordinate
                    </a>
                  </article>
                  <article>
                    <b>{selectedPair.competitor.retailer_display_name}</b>
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
                      Open coordinate
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
              </aside>
            ) : null}

            <div className={styles.mapFooter}>
              <span>
                <i />
                Offline-ready coordinate map · location-master source
              </span>
              <span>
                1/3/5/10 mi: {count(view?.summary.within_1_mile ?? 0)} /{" "}
                {count(view?.summary.within_3_miles ?? 0)} /{" "}
                {count(view?.summary.within_5_miles ?? 0)} /{" "}
                {count(view?.summary.within_10_miles ?? 0)}
              </span>
            </div>
          </div>
        </section>
      </section>

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
                <span>Explorer filters</span>
                <h2>Refine the visible network</h2>
              </div>
              <button onClick={() => setShowFilters(false)} type="button">
                ×
              </button>
            </div>
            <label className={styles.field}>
              <span>Walmart state/province</span>
              <select
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
                value={sort}
                onChange={(event) => setSort(event.target.value as SortMode)}
              >
                <option value="nearest">Nearest first</option>
                <option value="farthest">Farthest first</option>
                <option value="state">State then store</option>
                <option value="store">Store number</option>
              </select>
            </label>
            <div className={styles.drawerStats}>
              <span>Visible rows</span>
              <strong>{count(filteredPairs.length)}</strong>
              <small>
                Exports, list, and map all use this same filtered population.
              </small>
            </div>
            <button
              className={styles.btn}
              onClick={() => {
                setQuery("");
                setStateFilter("all");
                setRelation("all");
                setSort("nearest");
              }}
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
              <button onClick={() => setShowTable(false)} type="button">
                ×
              </button>
            </div>
            <div className={styles.downloadRow}>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadCsv(filteredPairs, radius, "proximity-filtered.csv")
                }
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
                type="button"
              >
                Excel CSV
              </button>
              <button
                className={styles.btn}
                onClick={() =>
                  downloadJson(filteredPairs, radius, "proximity-filtered.json")
                }
                type="button"
              >
                JSON
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
                    <tr key={pair.benchmark.id}>
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
    </div>
  );
}
