"use client";

import {
  type KeyboardEvent,
  type PointerEvent,
  type WheelEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useApplicationContextActions } from "@/app/components/application-context";
import type { LocationRetailer, ProximityPair, ProximityView } from "@/lib/api";
import usStatesTopology from "../../../../../config/us-states-10m.json";

import styles from "./proximity-workspace.module.css";

const RADIUS_OPTIONS = [1, 3, 5, 10] as const;
const NON_CONTIGUOUS_US_STATES = new Set(["AK", "HI", "PR"]);
const NON_CONTIGUOUS_US_STATE_IDS = new Set(["02", "15", "72"]);
type RelationFilter = "all" | "within" | "outside";
type SortMode = "nearest" | "farthest" | "state" | "store";
type ThemeMode = "light" | "dark";
type MapStyle = "insight" | "outline";
type ModalKind = "method" | "shortlist" | "notes" | null;
const SVG_EXPORT_STYLE_PROPERTIES = [
  "background-color",
  "color",
  "display",
  "fill",
  "fill-opacity",
  "font-family",
  "font-size",
  "font-weight",
  "letter-spacing",
  "line-height",
  "opacity",
  "stroke",
  "stroke-dasharray",
  "stroke-linecap",
  "stroke-linejoin",
  "stroke-opacity",
  "stroke-width",
  "text-anchor",
  "visibility",
] as const;

type Topology = {
  arcs: number[][][];
  objects: {
    states: {
      geometries: Array<{
        arcs: number[][] | number[][][];
        id?: string;
        properties?: { name?: string };
        type: "Polygon" | "MultiPolygon";
      }>;
    };
  };
  transform: {
    scale: [number, number];
    translate: [number, number];
  };
};

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
  downloadBlob(filename, new Blob([body], { type }));
}

function downloadBlob(filename: string, blob: Blob) {
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

function downloadGeoJson(
  rows: ProximityPair[],
  selectedRadius: number,
  filename: string,
) {
  const features = rows.flatMap((pair) => [
    {
      geometry: {
        coordinates: [pair.benchmark.longitude, pair.benchmark.latitude],
        type: "Point",
      },
      properties: {
        competitor_location_id: pair.competitor.id,
        competitor_retailer_id: pair.competitor.retailer_id,
        nearest_distance_miles: pair.distance_miles,
        retailer_id: pair.benchmark.retailer_id,
        role: "walmart",
        selected_radius_miles: selectedRadius,
        store_number: pair.benchmark.store_number,
        within_selected_radius: pair.distance_miles <= selectedRadius,
      },
      type: "Feature",
    },
    {
      geometry: {
        coordinates: [pair.competitor.longitude, pair.competitor.latitude],
        type: "Point",
      },
      properties: {
        nearest_walmart_location_id: pair.benchmark.id,
        nearest_walmart_store_number: pair.benchmark.store_number,
        retailer_id: pair.competitor.retailer_id,
        role: "competitor",
        selected_radius_miles: selectedRadius,
        store_number: pair.competitor.store_number,
      },
      type: "Feature",
    },
    {
      geometry: {
        coordinates: [
          [pair.benchmark.longitude, pair.benchmark.latitude],
          [pair.competitor.longitude, pair.competitor.latitude],
        ],
        type: "LineString",
      },
      properties: {
        nearest_distance_miles: pair.distance_miles,
        role: "relationship",
        selected_radius_miles: selectedRadius,
        walmart_location_id: pair.benchmark.id,
        within_selected_radius: pair.distance_miles <= selectedRadius,
      },
      type: "Feature",
    },
  ]);
  download(
    filename,
    "application/geo+json;charset=utf-8",
    JSON.stringify(
      {
        features,
        type: "FeatureCollection",
      },
      null,
      2,
    ),
  );
}

function serializeSvgForExport(svg: SVGSVGElement) {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const sourceElements = [svg, ...Array.from(svg.querySelectorAll("*"))];
  const clonedElements = [clone, ...Array.from(clone.querySelectorAll("*"))];

  sourceElements.forEach((sourceElement, index) => {
    const clonedElement = clonedElements[index];
    if (!(clonedElement instanceof SVGElement)) return;
    const computed = window.getComputedStyle(sourceElement);
    SVG_EXPORT_STYLE_PROPERTIES.forEach((property) => {
      const value = computed.getPropertyValue(property);
      if (value) {
        clonedElement.style.setProperty(property, value);
      }
    });
  });

  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  return new XMLSerializer().serializeToString(clone);
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

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
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

function decodedArc(topology: Topology, arcIndex: number) {
  const sourceIndex = arcIndex >= 0 ? arcIndex : -arcIndex - 1;
  const source = topology.arcs[sourceIndex] ?? [];
  let x = 0;
  let y = 0;
  const coordinates = source.map(([deltaX = 0, deltaY = 0]) => {
    x += deltaX;
    y += deltaY;
    return [
      x * topology.transform.scale[0] + topology.transform.translate[0],
      y * topology.transform.scale[1] + topology.transform.translate[1],
    ] as const;
  });
  return arcIndex >= 0 ? coordinates : coordinates.reverse();
}

function ringCoordinates(topology: Topology, ring: number[]) {
  return ring.flatMap((arcIndex, index) => {
    const coordinates = decodedArc(topology, arcIndex);
    return index === 0 ? coordinates : coordinates.slice(1);
  });
}

function usStatePaths(
  point: (
    longitude: number,
    latitude: number,
  ) => {
    x: number;
    y: number;
  },
  includeNonContiguous = true,
) {
  const topology = usStatesTopology as unknown as Topology;
  return topology.objects.states.geometries
    .filter(
      (geometry) =>
        (geometry.type === "Polygon" || geometry.type === "MultiPolygon") &&
        (includeNonContiguous ||
          !NON_CONTIGUOUS_US_STATE_IDS.has(String(geometry.id))),
    )
    .flatMap((geometry, geometryIndex) => {
      const polygons =
        geometry.type === "Polygon"
          ? [geometry.arcs as number[][]]
          : (geometry.arcs as number[][][]);
      return polygons.map((polygon, polygonIndex) => {
        const path = polygon
          .map((ring) => {
            const coordinates = ringCoordinates(topology, ring);
            if (!coordinates.length) return "";
            const [firstLongitude, firstLatitude] = coordinates[0]!;
            const start = point(firstLongitude, firstLatitude);
            const segments = coordinates
              .slice(1)
              .map(([longitude, latitude]) => {
                const projected = point(longitude, latitude);
                return `L${projected.x.toFixed(1)} ${projected.y.toFixed(1)}`;
              })
              .join(" ");
            return `M${start.x.toFixed(1)} ${start.y.toFixed(1)} ${segments} Z`;
          })
          .filter(Boolean)
          .join(" ");
        return {
          id: `${geometryIndex}-${polygonIndex}`,
          path,
        };
      });
    })
    .filter((shape) => shape.path);
}

function clusterLocations(
  locations: ProximityPair["benchmark"][],
  point: (longitude: number, latitude: number) => { x: number; y: number },
  bucketSize: number,
) {
  const clusters = new Map<
    string,
    { count: number; ids: Set<string>; label: string; x: number; y: number }
  >();
  locations.forEach((location) => {
    const rendered = point(location.longitude, location.latitude);
    const key = `${Math.round(rendered.x / bucketSize)}:${Math.round(rendered.y / bucketSize)}`;
    const existing = clusters.get(key);
    if (existing) {
      existing.count += 1;
      existing.ids.add(location.id);
      existing.x += (rendered.x - existing.x) / existing.count;
      existing.y += (rendered.y - existing.y) / existing.count;
      return;
    }
    clusters.set(key, {
      count: 1,
      ids: new Set([location.id]),
      label: location.state || location.city || "cluster",
      x: rendered.x,
      y: rendered.y,
    });
  });
  return Array.from(clusters.values()).filter((cluster) => cluster.count > 1);
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
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [showLinks, setShowLinks] = useState(true);
  const [showRings, setShowRings] = useState(true);
  const [showWalmart, setShowWalmart] = useState(true);
  const [showCompetitors, setShowCompetitors] = useState(true);
  const [showClusters, setShowClusters] = useState(true);
  const [showSelectedDetail, setShowSelectedDetail] = useState(false);
  const [onlySaved, setOnlySaved] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => initialTheme());
  const [mapStyle, setMapStyle] = useState<MapStyle>("insight");
  const [mapZoom, setMapZoom] = useState(1);
  const [mapOffset, setMapOffset] = useState({ x: 0, y: 0 });
  const [dragStart, setDragStart] = useState<{
    clientX: number;
    clientY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalKind>(null);
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
    initialView?.pairs[0]?.benchmark.id ?? null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const mapAreaRef = useRef<HTMLDivElement>(null);
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
      setOnlySaved(false);
      setMapOffset({ x: 0, y: 0 });
      setMapZoom(1);
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
    filteredPairs.find((pair) => pair.benchmark.id === selectedKey) ??
    filteredPairs[0] ??
    null;

  const mapPairs = useMemo(
    () =>
      country === "USA" && stateFilter === "all"
        ? filteredPairs.filter(
            (pair) => !NON_CONTIGUOUS_US_STATES.has(pair.benchmark.state ?? ""),
          )
        : filteredPairs,
    [country, filteredPairs, stateFilter],
  );
  const map = useMemo(() => projection(mapPairs), [mapPairs]);
  const selectedMapPair =
    selectedPair &&
    mapPairs.some((pair) => pair.benchmark.id === selectedPair.benchmark.id)
      ? selectedPair
      : null;
  const competitorPoints = useMemo(
    () =>
      Array.from(
        new Map(
          mapPairs.map((pair) => [pair.competitor.id, pair.competitor]),
        ).values(),
      ),
    [mapPairs],
  );
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
    coverageBands.find((band) => band.miles === radius) ?? coverageBands.at(-1);
  const furthestVisiblePair = mapPairs.reduce<ProximityPair | null>(
    (current, pair) =>
      current === null || pair.distance_miles > current.distance_miles
        ? pair
        : current,
    null,
  );
  const hiddenMapPairCount = Math.max(
    0,
    filteredPairs.length - mapPairs.length,
  );
  const visibleCompetitorSites = competitorPoints.length;
  const stateOptions = view?.state_options ?? [];
  const visibleShare = filteredPairs.length
    ? filteredWithin / filteredPairs.length
    : null;
  const stateShapes = useMemo(
    () =>
      country === "USA" ? usStatePaths(map.point, stateFilter !== "all") : [],
    [country, map, stateFilter],
  );
  const clusterBucket = clamp(72 / mapZoom, 24, 90);
  const walmartClusters = useMemo(
    () =>
      showClusters
        ? clusterLocations(
            mapPairs.map((pair) => pair.benchmark),
            map.point,
            clusterBucket,
          )
        : [],
    [clusterBucket, mapPairs, map.point, showClusters],
  );
  const competitorClusters = useMemo(
    () =>
      showClusters
        ? clusterLocations(competitorPoints, map.point, clusterBucket)
        : [],
    [clusterBucket, competitorPoints, map.point, showClusters],
  );
  const selectedRadiusPixels = selectedMapPair
    ? Math.abs(
        map.point(
          selectedMapPair.benchmark.longitude,
          selectedMapPair.benchmark.latitude + radius / 69,
        ).y -
          map.point(
            selectedMapPair.benchmark.longitude,
            selectedMapPair.benchmark.latitude,
          ).y,
      )
    : 0;
  const selectedPeers = selectedPair
    ? filteredPairs
        .filter(
          (pair) =>
            pair.competitor.id === selectedPair.competitor.id &&
            pair.benchmark.id !== selectedPair.benchmark.id,
        )
        .slice(0, 4)
    : [];
  const hoveredPair =
    filteredPairs.find((pair) => pairKey(pair) === hoveredKey) ?? null;
  const hoveredPoint = hoveredPair
    ? map.point(hoveredPair.benchmark.longitude, hoveredPair.benchmark.latitude)
    : null;
  const transformedHoverPoint = hoveredPoint
    ? {
        x: clamp(
          ((mapOffset.x + hoveredPoint.x * mapZoom) / 1000) * 100,
          4,
          96,
        ),
        y: clamp(((mapOffset.y + hoveredPoint.y * mapZoom) / 640) * 100, 5, 95),
      }
    : null;
  const mapTransform = `translate(${mapOffset.x} ${mapOffset.y}) scale(${mapZoom})`;

  function resetView() {
    setQuery("");
    setStateFilter("all");
    setRelation("all");
    setSort("nearest");
    setOnlySaved(false);
    setMapOffset({ x: 0, y: 0 });
    setMapZoom(1);
  }

  function zoomMap(multiplier: number) {
    setMapZoom((current) => clamp(current * multiplier, 0.7, 8));
  }

  function handleWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    zoomMap(event.deltaY < 0 ? 1.15 : 0.87);
  }

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    setDragStart({
      clientX: event.clientX,
      clientY: event.clientY,
      originX: mapOffset.x,
      originY: mapOffset.y,
    });
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    if (!dragStart) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setMapOffset({
      x:
        dragStart.originX +
        ((event.clientX - dragStart.clientX) / rect.width) * 1000,
      y:
        dragStart.originY +
        ((event.clientY - dragStart.clientY) / rect.height) * 640,
    });
  }

  function handleKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomMap(1.18);
    } else if (event.key === "-") {
      event.preventDefault();
      zoomMap(0.84);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      setMapOffset((current) => ({ ...current, x: current.x + 24 }));
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setMapOffset((current) => ({ ...current, x: current.x - 24 }));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setMapOffset((current) => ({ ...current, y: current.y + 24 }));
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setMapOffset((current) => ({ ...current, y: current.y - 24 }));
    }
  }

  function toggleSaved(pair: ProximityPair) {
    const key = pairKey(pair);
    setSavedByComparison((current) => {
      const currentKeys = new Set(current[shortlistStorageKey] ?? []);
      if (currentKeys.has(key)) {
        currentKeys.delete(key);
      } else {
        currentKeys.add(key);
      }
      return {
        ...current,
        [shortlistStorageKey]: Array.from(currentKeys),
      };
    });
  }

  function exportSvg() {
    if (!svgRef.current) return;
    const serialized = serializeSvgForExport(svgRef.current);
    download("proximity-map.svg", "image/svg+xml;charset=utf-8", serialized);
  }

  function exportPng() {
    const svg = svgRef.current;
    if (!svg) return;

    const serialized = serializeSvgForExport(svg);
    const sourceUrl = URL.createObjectURL(
      new Blob([serialized], { type: "image/svg+xml;charset=utf-8" }),
    );
    const image = new Image();
    image.onload = () => {
      const bounds = svg.getBoundingClientRect();
      const scale = Math.max(1, window.devicePixelRatio || 1);
      const width = Math.max(1, Math.round(bounds.width * scale));
      const height = Math.max(1, Math.round(bounds.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");

      if (!context) {
        URL.revokeObjectURL(sourceUrl);
        return;
      }

      context.fillStyle =
        window.getComputedStyle(svg).backgroundColor || "#f8fafc";
      context.fillRect(0, 0, width, height);
      context.drawImage(image, 0, 0, width, height);
      URL.revokeObjectURL(sourceUrl);
      canvas.toBlob((blob) => {
        if (blob) {
          downloadBlob("proximity-map.png", blob);
        }
      }, "image/png");
    };
    image.onerror = () => URL.revokeObjectURL(sourceUrl);
    image.src = sourceUrl;
  }

  const shellActions = useMemo(
    () => (
      <div className={styles.shellActions} aria-label="Proximity page actions">
        <button
          className={styles.btn}
          onClick={() => setModal("shortlist")}
          type="button"
        >
          Shortlist <span className={styles.pill}>{savedKeys.size}</span>
        </button>
        <button
          className={styles.btn}
          onClick={() => setModal("notes")}
          type="button"
        >
          Notes
        </button>
        <div className={styles.menuWrap}>
          <button
            className={styles.btn}
            onClick={() => setShowExportMenu((current) => !current)}
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
                type="button"
              >
                Visible rows · CSV
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
                type="button"
              >
                Map layer · GeoJSON
              </button>
              <button
                onClick={() => {
                  exportSvg();
                  setShowExportMenu(false);
                }}
                type="button"
              >
                Current map · SVG
              </button>
              <button
                onClick={() => {
                  exportPng();
                  setShowExportMenu(false);
                }}
                type="button"
              >
                Current map · PNG
              </button>
            </div>
          ) : null}
        </div>
        <button
          className={styles.btn}
          onClick={() => setShowFilters(true)}
          type="button"
        >
          Controls
        </button>
        <button
          className={`${styles.btn} ${styles.primary}`}
          onClick={() => setShowTable(true)}
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
            Source-backed nearest-store relationships from the location master.
            Straight-line Haversine miles; not drive time, inventory,
            assortment, or product distribution.
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
        <article className={styles.kpi}>
          <div>
            <span>Walmart locations in scope</span>
            <strong>{count(scopedPairs.length)}</strong>
            <small>
              {view
                ? `${count(filteredPairs.length)} currently shown after relationship filters`
                : "No comparison loaded"}
            </small>
          </div>
          <b className={`${styles.kpiIcon} ${styles.blue}`}>W</b>
        </article>
        <article className={styles.kpi}>
          <div>
            <span>Have competitor ≤ {radius} miles</span>
            <strong>{percent(selectedCoverage?.share ?? visibleShare)}</strong>
            <small>
              {count(selectedCoverage?.within ?? filteredWithin)} of{" "}
              {count(scopedPairs.length)} Walmart locations in scope
            </small>
          </div>
          <b className={`${styles.kpiIcon} ${styles.green}`}>≤</b>
        </article>
        <article className={styles.kpi}>
          <div>
            <span>No competitor ≤ {radius} miles</span>
            <strong>
              {count(selectedCoverage?.outside ?? filteredOutside)}
            </strong>
            <small>
              {percent(
                scopedPairs.length
                  ? (selectedCoverage?.outside ?? filteredOutside) /
                      scopedPairs.length
                  : null,
              )}{" "}
              of Walmart locations in scope
            </small>
          </div>
          <b className={`${styles.kpiIcon} ${styles.red}`}>gap</b>
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
        <section className={styles.mapSection} aria-label="Proximity map">
          <div className={styles.mapArea} ref={mapAreaRef}>
            <div className={styles.mapToolbar}>
              <div className={styles.quickViews}>
                <button
                  className={relation === "all" ? styles.active : undefined}
                  onClick={() => setRelation("all")}
                  type="button"
                >
                  <strong>All stores</strong>
                  <small>Show covered and gap locations</small>
                </button>
                <button
                  className={relation === "within" ? styles.active : undefined}
                  onClick={() => setRelation("within")}
                  type="button"
                >
                  <strong>Covered stores</strong>
                  <small>Walmarts with a nearby competitor</small>
                </button>
                <button
                  className={relation === "outside" ? styles.active : undefined}
                  onClick={() => setRelation("outside")}
                  type="button"
                >
                  <strong>Gap stores</strong>
                  <small>No selected competitor nearby</small>
                </button>
              </div>
              <div className={styles.mapTools}>
                <button
                  className={styles.mapToolButton}
                  onClick={() => setShowFilters(true)}
                  type="button"
                >
                  Controls
                </button>
                <select
                  aria-label="Map style"
                  className={styles.baseSelect}
                  onChange={(event) =>
                    setMapStyle(event.target.value as MapStyle)
                  }
                  value={mapStyle}
                >
                  <option value="insight">Insight map</option>
                  <option value="outline">Outline map</option>
                </select>
                <button
                  className={styles.iconButton}
                  onClick={() => {
                    setMapOffset({ x: 0, y: 0 });
                    setMapZoom(1);
                  }}
                  title="Fit visible network"
                  type="button"
                >
                  ⤢
                </button>
                <button
                  className={styles.iconButton}
                  onClick={() => void mapAreaRef.current?.requestFullscreen()}
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
                  title="Open full table"
                  type="button"
                >
                  ⇩
                </button>
              </div>
            </div>

            {mapPairs.length ? (
              <svg
                className={`${styles.mapSvg} ${
                  mapStyle === "outline" ? styles.outlineMap : ""
                }`}
                onKeyDown={handleKeyDown}
                onPointerDown={handlePointerDown}
                onPointerLeave={() => {
                  setDragStart(null);
                  setHoveredKey(null);
                }}
                onPointerMove={handlePointerMove}
                onPointerUp={() => setDragStart(null)}
                onWheel={handleWheel}
                ref={svgRef}
                role="img"
                tabIndex={0}
                viewBox="0 0 1000 640"
              >
                <title>Retailer proximity map</title>
                <defs>
                  <radialGradient id="proximityWater" cx="50%" cy="42%" r="72%">
                    <stop className={styles.waterStopStart} offset="0%" />
                    <stop className={styles.waterStopMiddle} offset="58%" />
                    <stop className={styles.waterStopEnd} offset="100%" />
                  </radialGradient>
                  <filter
                    id="selectedGlow"
                    height="240%"
                    width="240%"
                    x="-70%"
                    y="-70%"
                  >
                    <feDropShadow
                      dx="0"
                      dy="0"
                      floodColor="#087d72"
                      floodOpacity="0.52"
                      stdDeviation="4"
                    />
                  </filter>
                </defs>
                <rect className={styles.water} height="640" width="1000" />
                <path
                  className={styles.mapVignette}
                  d="M60 72 C186 22 304 58 421 38 C564 13 681 31 801 82 C921 133 966 254 940 384 C914 514 779 590 635 601 C502 611 394 569 280 590 C158 613 55 553 44 423 C31 278 -44 145 60 72 Z"
                />
                <g transform={mapTransform}>
                  {stateShapes.length ? (
                    <g className={styles.stateLayer}>
                      {stateShapes.map((shape) => (
                        <path d={shape.path} key={shape.id} />
                      ))}
                    </g>
                  ) : (
                    <rect
                      className={styles.landMass}
                      height="520"
                      rx="120"
                      width="850"
                      x="75"
                      y="70"
                    />
                  )}
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
                        <text
                          className={styles.gridLabel}
                          x={top.x + 4}
                          y="622"
                        >
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
                        <text
                          className={styles.gridLabel}
                          x="18"
                          y={left.y - 4}
                        >
                          {Math.abs(Math.round(latitude))}°N
                        </text>
                      </g>
                    );
                  })}
                  <text className={styles.mapLabel} x="78" y="112">
                    {country === "CANADA" ? "CANADA" : "UNITED STATES"}
                  </text>
                  {showLinks
                    ? mapPairs.slice(0, 1800).map((pair) => {
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
                      })
                    : null}
                  {showRings && selectedMapPair ? (
                    <circle
                      className={styles.radiusRing}
                      cx={
                        map.point(
                          selectedMapPair.benchmark.longitude,
                          selectedMapPair.benchmark.latitude,
                        ).x
                      }
                      cy={
                        map.point(
                          selectedMapPair.benchmark.longitude,
                          selectedMapPair.benchmark.latitude,
                        ).y
                      }
                      r={selectedRadiusPixels}
                    />
                  ) : null}
                  {showCompetitors && !showClusters
                    ? competitorPoints.map((location) => {
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
                      })
                    : null}
                  {showWalmart && !showClusters
                    ? mapPairs.map((pair) => {
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
                            onClick={() => {
                              setSelectedKey(pair.benchmark.id);
                              setShowSelectedDetail(true);
                            }}
                            onPointerEnter={() => setHoveredKey(pairKey(pair))}
                            onPointerLeave={() => setHoveredKey(null)}
                            r={selected ? 7 : 3.6}
                          />
                        );
                      })
                    : null}
                  {showClusters && showCompetitors
                    ? competitorClusters.map((cluster, index) => (
                        <g
                          className={styles.competitorCluster}
                          key={`competitor-cluster-${index}`}
                        >
                          <circle
                            cx={cluster.x}
                            cy={cluster.y}
                            r={clamp(8 + Math.log(cluster.count) * 4, 10, 28)}
                          />
                          <text x={cluster.x} y={cluster.y + 3}>
                            {cluster.count}
                          </text>
                        </g>
                      ))
                    : null}
                  {showClusters && showWalmart
                    ? walmartClusters.map((cluster, index) => (
                        <g
                          className={styles.walmartCluster}
                          key={`walmart-cluster-${index}`}
                        >
                          <circle
                            cx={cluster.x}
                            cy={cluster.y}
                            r={clamp(8 + Math.log(cluster.count) * 4, 10, 30)}
                          />
                          <text x={cluster.x} y={cluster.y + 3}>
                            {cluster.count}
                          </text>
                        </g>
                      ))
                    : null}
                  {showClusters && selectedMapPair ? (
                    <g className={styles.selectedPairLayer}>
                      <rect
                        className={styles.competitorPoint}
                        height="8"
                        rx="2.2"
                        width="8"
                        x={
                          map.point(
                            selectedMapPair.competitor.longitude,
                            selectedMapPair.competitor.latitude,
                          ).x - 4
                        }
                        y={
                          map.point(
                            selectedMapPair.competitor.longitude,
                            selectedMapPair.competitor.latitude,
                          ).y - 4
                        }
                      />
                      <circle
                        className={styles.selectedPoint}
                        cx={
                          map.point(
                            selectedMapPair.benchmark.longitude,
                            selectedMapPair.benchmark.latitude,
                          ).x
                        }
                        cy={
                          map.point(
                            selectedMapPair.benchmark.longitude,
                            selectedMapPair.benchmark.latitude,
                          ).y
                        }
                        r="7"
                      />
                    </g>
                  ) : null}
                </g>
              </svg>
            ) : (
              <div className={styles.mapEmpty}>
                No mappable retailer relationships match the current filters.
              </div>
            )}

            {hoveredPair && transformedHoverPoint ? (
              <div
                className={styles.mapTooltip}
                style={{
                  left: `${transformedHoverPoint.x}%`,
                  top: `${transformedHoverPoint.y}%`,
                }}
              >
                <strong>
                  Walmart #{hoveredPair.benchmark.store_number} ·{" "}
                  {miles(hoveredPair.distance_miles)}
                </strong>
                <span>
                  {hoveredPair.benchmark.city || "Unknown city"},{" "}
                  {hoveredPair.benchmark.state || "—"} nearest{" "}
                  {hoveredPair.competitor.retailer_display_name} #
                  {hoveredPair.competitor.store_number}
                </span>
              </div>
            ) : null}

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
              <span>Map view</span>
              <strong>
                {count(mapPairs.length)} Walmart locations rendered
              </strong>
              <small>
                {hiddenMapPairCount
                  ? `${count(hiddenMapPairCount)} non-contiguous U.S. locations are in the metrics and available by state filter. `
                  : ""}
                Furthest rendered:{" "}
                {furthestVisiblePair
                  ? `${miles(furthestVisiblePair.distance_miles)} · #${furthestVisiblePair.benchmark.store_number} ${furthestVisiblePair.benchmark.city || ""} ${furthestVisiblePair.benchmark.state || ""}`.trim()
                  : "—"}
              </small>
            </div>

            <div
              className={styles.mapCoverageCard}
              aria-label="Walmart coverage by selected competitor radius"
            >
              <div className={styles.coverageHead}>
                <h2>Radius coverage</h2>
                <button onClick={() => setShowTable(true)} type="button">
                  Store details
                </button>
              </div>
              <p>
                Of {count(scopedPairs.length)} Walmart locations in the current
                scope before the covered/gap display toggle.
              </p>
              <div className={styles.mapCoverageRows}>
                {coverageBands.map((band) => (
                  <button
                    aria-pressed={radius === band.miles}
                    className={styles.mapCoverageRow}
                    key={band.miles}
                    onClick={() => void load({ radius: band.miles })}
                    type="button"
                  >
                    <span>{band.label}</span>
                    <i>
                      <b
                        style={{
                          width: `${band.share === null ? 0 : band.share * 100}%`,
                        }}
                      />
                    </i>
                    <strong>{count(band.within)}</strong>
                    <small>{percent(band.share)}</small>
                  </button>
                ))}
              </div>
            </div>

            <div className={styles.zoomControl} aria-label="Map zoom controls">
              <button onClick={() => zoomMap(1.2)} type="button">
                +
              </button>
              <button onClick={() => zoomMap(0.84)} type="button">
                −
              </button>
              <span>{Math.round(mapZoom * 100)}%</span>
            </div>
            <div className={styles.northControl} aria-hidden="true">
              N<i />
            </div>

            {selectedPair ? (
              <button
                className={styles.selectionToast}
                onClick={() => setShowSelectedDetail(true)}
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
              Drag, wheel, keyboard, fit, and fullscreen controls ·
              location-master source
            </span>
            <span>
              Scope coverage 1/3/5/10 mi:{" "}
              {coverageBands.map((band) => count(band.within)).join(" / ")}
              {hiddenMapPairCount
                ? ` · map defaults to continental U.S.; ${count(hiddenMapPairCount)} locations remain in details/filters`
                : ""}
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
                type="button"
              >
                ×
              </button>
            </div>
            <button
              className={styles.saveButton}
              onClick={() => toggleSaved(selectedPair)}
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
                    onClick={() => setSelectedKey(pair.benchmark.id)}
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
              <button onClick={() => setShowFilters(false)} type="button">
                ×
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
              <span>Competition radius</span>
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
            <label className={styles.checkRow}>
              <input
                checked={onlySaved}
                onChange={(event) => setOnlySaved(event.target.checked)}
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
                  ["Radius ring", showRings, setShowRings],
                  ["Clusters", showClusters, setShowClusters],
                  ["Saved only", onlySaved, setOnlySaved],
                ].map(([label, value, setter]) => (
                  <button
                    aria-pressed={Boolean(value)}
                    key={String(label)}
                    onClick={() =>
                      (setter as (next: boolean) => void)(!Boolean(value))
                    }
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
                Exports, list, and map all use this same filtered population.
              </small>
            </div>
            <button className={styles.btn} onClick={resetView} type="button">
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
            <div className={styles.tableSummary}>
              <article>
                <span>Walmart locations in scope</span>
                <strong>{count(scopedPairs.length)}</strong>
              </article>
              <article>
                <span>Covered ≤ {radius} mi</span>
                <strong>
                  {count(selectedCoverage?.within ?? filteredWithin)}
                </strong>
              </article>
              <article>
                <span>Gaps ≤ {radius} mi</span>
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
              <button
                className={styles.btn}
                onClick={() =>
                  downloadGeoJson(
                    filteredPairs,
                    radius,
                    "proximity-filtered.geojson",
                  )
                }
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

      {modal ? (
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
                <span>
                  {modal === "method"
                    ? "Data method"
                    : modal === "shortlist"
                      ? "Saved relationships"
                      : "Workspace notes"}
                </span>
                <h2>
                  {modal === "method"
                    ? "How this proximity view is calculated"
                    : modal === "shortlist"
                      ? "Shortlisted retailer relationships"
                      : "How to use this page"}
                </h2>
              </div>
              <button onClick={() => setModal(null)} type="button">
                ×
              </button>
            </div>

            {modal === "method" ? (
              <div className={styles.modalBody}>
                <p>
                  Each row starts with a Walmart US or CA location from the
                  location master and pairs it to the nearest selected
                  competitor location with valid latitude and longitude.
                </p>
                <p>
                  Distances are Haversine straight-line miles. They are useful
                  for footprint and white-space analysis, but they are not drive
                  time, traffic-aware distance, inventory, item distribution, or
                  store operating status.
                </p>
                <p>
                  The visible KPIs, list, map, drawer table, and downloads all
                  use the same filtered set: country, competitor, radius, state,
                  relationship type, search, and shortlist status.
                </p>
              </div>
            ) : null}

            {modal === "shortlist" ? (
              <div className={styles.modalBody}>
                {filteredPairs.filter((pair) => savedKeys.has(pairKey(pair)))
                  .length ? (
                  filteredPairs
                    .filter((pair) => savedKeys.has(pairKey(pair)))
                    .map((pair) => (
                      <button
                        className={styles.savedRow}
                        key={pairKey(pair)}
                        onClick={() => {
                          setSelectedKey(pair.benchmark.id);
                          setModal(null);
                        }}
                        type="button"
                      >
                        <span>
                          Walmart #{pair.benchmark.store_number} ·{" "}
                          {pair.benchmark.city || "Unknown city"},{" "}
                          {pair.benchmark.state || "—"}
                        </span>
                        <b>{miles(pair.distance_miles)}</b>
                      </button>
                    ))
                ) : (
                  <p>
                    No saved relationships yet. Select a relationship on the map
                    or list and use Save in the detail panel.
                  </p>
                )}
              </div>
            ) : null}

            {modal === "notes" ? (
              <div className={styles.modalBody}>
                <p>
                  Use the left rail for competitor and radius slicing, the map
                  controls for spatial exploration, and the location details
                  drawer for the complete downloadable evidence table.
                </p>
                <p>
                  Suggested workflow: choose one competitor, select a radius,
                  review the coverage-by-radius matrix, toggle between covered
                  and white-space views, save notable relationships, then export
                  CSV/JSON/GeoJSON for follow-up analysis or future app
                  features.
                </p>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
