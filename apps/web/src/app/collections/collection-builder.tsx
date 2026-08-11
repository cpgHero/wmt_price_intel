"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { GeometryCollection, Topology } from "topojson-specification";
import { feature } from "topojson-client";
import statesTopologySource from "us-atlas/states-10m.json";

import type {
  CollectionBuilderOptions,
  CollectionGeographyRequest,
  CollectionGeographyResolution,
  CollectionLocationFacet,
  CollectionScopeEstimate,
  JsonObject,
  RunRecord,
} from "@/lib/api";
import {
  buildApprovedCollectionDefinition,
  type BuilderDefinitionValues,
  validateBuilderDefinition,
} from "@/lib/collection-builder-definition";
import { displayLabel } from "@/lib/presentation";

const steps = [
  "Purpose & retailers",
  "Primary geography",
  "Competitor coverage",
  "Review geography",
  "Collection controls",
  "Estimate & approve",
] as const;

type PrimaryMode = CollectionGeographyRequest["primary_selection"]["mode"];
type CorrespondenceMode =
  CollectionGeographyRequest["competitor_correspondence"]["mode"];
type GeographyLocation = CollectionGeographyResolution["locations"][number];

function createDefinitionId(): string {
  return `collection-${Date.now().toString(36)}`;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function normalizeList(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\s,;]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

async function errorFrom(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string };
    return body.error ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

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
  if (latitude > 50 && longitude < -129) {
    return {
      x: 35 + ((longitude + 180) / 51) * 205,
      y: 355 + ((72 - latitude) / 22) * 125,
    };
  }
  if (latitude < 24 && longitude < -150) {
    return {
      x: 250 + ((longitude + 161) / 7) * 105,
      y: 420 + ((23 - latitude) / 5) * 65,
    };
  }
  if (latitude < 20 && longitude > -70) {
    return {
      x: 790 + ((longitude + 68) / 3) * 105,
      y: 430 + ((19.5 - latitude) / 3) * 55,
    };
  }
  return {
    x: ((longitude + 125) / 59) * 900 + 30,
    y: ((50 - latitude) / 26) * 455 + 25,
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

function GeographyPreviewMap({
  locations,
  primaryRetailerId,
}: Readonly<{
  locations: GeographyLocation[];
  primaryRetailerId: string;
}>) {
  const [selected, setSelected] = useState<GeographyLocation | null>(null);
  const positioned = useMemo(
    () =>
      locations.filter(
        (item) =>
          typeof item.latitude === "number" &&
          typeof item.longitude === "number",
      ),
    [locations],
  );
  const clusters = useMemo(() => {
    const values = new Map<
      string,
      { location: GeographyLocation; count: number; x: number; y: number }
    >();
    for (const location of positioned) {
      const point = projectCoordinate(
        Number(location.longitude),
        Number(location.latitude),
      );
      const key = `${Math.round(point.x / 8)}:${Math.round(point.y / 8)}:${location.retailer_id}`;
      const current = values.get(key);
      if (current) current.count += 1;
      else values.set(key, { location, count: 1, ...point });
    }
    return Array.from(values.values());
  }, [positioned]);
  return (
    <div className="builder-map-layout">
      <figure className="builder-map">
        <svg
          viewBox="0 0 960 520"
          role="img"
          aria-label="Approved collection geography"
        >
          <rect width="960" height="520" rx="22" />
          <g className="state-layer">
            {stateFeatures.map((state) => (
              <path d={geometryPath(state.geometry)} key={String(state.id)} />
            ))}
          </g>
          <g className="builder-point-layer">
            {clusters.map(({ location, count, x, y }) => (
              <circle
                cx={x}
                cy={y}
                r={Math.min(8, 2.5 + Math.sqrt(count))}
                className={
                  location.retailer_id === primaryRetailerId
                    ? "primary"
                    : "competitor"
                }
                key={`${location.id}-${x}-${y}`}
                onClick={() => setSelected(location)}
                tabIndex={0}
                role="button"
              >
                <title>
                  {displayLabel(location.retailer_id)} ·{" "}
                  {location.store_name ??
                    location.store_number ??
                    location.zipcode}
                  {count > 1 ? ` · ${count} nearby locations` : ""}
                </title>
              </circle>
            ))}
          </g>
        </svg>
        <figcaption>
          Store markers are clustered visually. Alaska, Hawaii, and Puerto Rico
          are shown as insets; ZIP-only retailer scopes are counted but do not
          receive fabricated store markers.
        </figcaption>
      </figure>
      <aside className="builder-map-legend">
        <span className="primary">Primary retailer</span>
        <span className="competitor">Competitor stores</span>
        <b>{positioned.length.toLocaleString()} mapped stores</b>
        {selected ? (
          <div>
            <small>Selected location</small>
            <strong>
              {selected.store_name ?? `Store ${selected.store_number}`}
            </strong>
            <span>
              {selected.city ? `${selected.city}, ` : ""}
              {selected.state ?? ""} {selected.zipcode}
            </span>
            <em>{displayLabel(selected.retailer_id)}</em>
          </div>
        ) : null}
      </aside>
    </div>
  );
}

export function CollectionBuilder({
  options,
  initialDefinition,
  initialResolution,
}: Readonly<{
  options: CollectionBuilderOptions;
  initialDefinition?: JsonObject | null;
  initialResolution?: CollectionGeographyResolution | null;
}>) {
  const router = useRouter();
  const initialPackConfig = object(initialDefinition?.product_pack);
  const defaultPack =
    options.product_packs.find(
      (pack) => pack.id === String(initialPackConfig.id ?? ""),
    ) ??
    options.product_packs.find(
      (pack) => pack.id === options.default_product_pack_id,
    ) ??
    options.product_packs[0]!;
  const initialRetailers = Array.isArray(initialDefinition?.retailers)
    ? (initialDefinition.retailers as JsonObject[])
        .filter((item) => item.enabled !== false)
        .map((item) => String(item.retailer_id))
    : [];
  const initialPrimary = String(
    initialDefinition?.benchmark_retailer ??
      (options.retailers.some((item) => item.id === "walmart_us")
        ? "walmart_us"
        : options.retailers[0]!.id),
  );
  const initialRequest = initialResolution?.request;
  const [step, setStep] = useState(initialResolution ? 4 : 1);
  const [definitionId] = useState(
    String(initialDefinition?.id ?? createDefinitionId()),
  );
  const [name, setName] = useState(
    String(initialDefinition?.name ?? `${defaultPack.name} Collection`),
  );
  const [productPackId, setProductPackId] = useState(defaultPack.id);
  const [keyword, setKeyword] = useState(
    String(
      object(initialDefinition?.query).keyword ?? defaultPack.default_keyword,
    ),
  );
  const [primaryRetailerId, setPrimaryRetailerId] = useState(initialPrimary);
  const [competitorRetailerIds, setCompetitorRetailerIds] = useState<string[]>(
    initialRetailers.length > 0
      ? initialRetailers.filter((item) => item !== initialPrimary)
      : options.retailers
          .filter((item) => item.id !== initialPrimary)
          .map((item) => item.id),
  );
  const [primaryMode, setPrimaryMode] = useState<PrimaryMode>(
    initialRequest?.primary_selection.mode ?? "custom_zips",
  );
  const [selectedStates, setSelectedStates] = useState<string[]>(
    initialRequest?.primary_selection.states ?? [],
  );
  const [selectedCities, setSelectedCities] = useState<string[]>(
    (initialRequest?.primary_selection.cities ?? []).map(
      (item) => `${item.state}|${item.city}`,
    ),
  );
  const [locationsPerState, setLocationsPerState] = useState(
    initialRequest?.primary_selection.locations_per_state ?? 1,
  );
  const [zipcodeText, setZipcodeText] = useState(
    (initialRequest?.primary_selection.zipcodes ?? ["44906"]).join("\n"),
  );
  const [locationIdText, setLocationIdText] = useState(
    (initialRequest?.primary_selection.location_ids ?? []).join("\n"),
  );
  const [correspondenceMode, setCorrespondenceMode] =
    useState<CorrespondenceMode>(
      initialRequest?.competitor_correspondence.mode ?? "same_zip",
    );
  const [radiusMiles, setRadiusMiles] = useState<1 | 3 | 5>(
    initialRequest?.competitor_correspondence.radius_miles ?? 3,
  );
  const [exclusions, setExclusions] = useState<
    NonNullable<CollectionGeographyRequest["exclusions"]>
  >(initialRequest?.exclusions ?? []);
  const [facets, setFacets] = useState<CollectionLocationFacet[]>([]);
  const [facetsBusy, setFacetsBusy] = useState(true);
  const [resolution, setResolution] =
    useState<CollectionGeographyResolution | null>(initialResolution ?? null);
  const [resolvedSignature, setResolvedSignature] = useState(
    initialResolution ? JSON.stringify(initialResolution.request) : "",
  );
  const initialPagination = object(initialDefinition?.pagination);
  const [maxPagesByRetailer, setMaxPagesByRetailer] = useState<
    Record<string, number>
  >(
    Object.fromEntries(
      options.retailers.map((retailer) => {
        const configured = Array.isArray(initialDefinition?.retailers)
          ? (initialDefinition.retailers as JsonObject[]).find(
              (item) => item.retailer_id === retailer.id,
            )
          : undefined;
        return [
          retailer.id,
          Number(
            configured?.max_pages_override ?? initialPagination.max_pages ?? 1,
          ),
        ];
      }),
    ),
  );
  const initialBudget = object(initialDefinition?.budget);
  const [maxCredits, setMaxCredits] = useState(
    Number(initialBudget.max_credits_per_run ?? 5),
  );
  const [gateEnabled, setGateEnabled] = useState(
    object(initialDefinition?.availability_gate).enabled !== false,
  );
  const initialSchedule = object(initialDefinition?.schedule);
  const [scheduleType, setScheduleType] = useState<"manual" | "cron">(
    initialSchedule.type === "cron" ? "cron" : "manual",
  );
  const [cronExpression, setCronExpression] = useState(
    String(initialSchedule.cron ?? "0 6 * * 1"),
  );
  const [timezone, setTimezone] = useState(
    String(initialSchedule.timezone ?? "America/Chicago"),
  );
  const initialDelivery = object(initialDefinition?.delivery);
  const [delivery, setDelivery] = useState({
    webReport: initialDelivery.web_report !== false,
    excel: initialDelivery.excel !== false,
    leadershipEmail: initialDelivery.leadership_email !== false,
    auditPackage: initialDelivery.audit_package !== false,
  });
  const initialPdp = object(initialDefinition?.product_detail_enrichment);
  const [productDetailPolicy, setProductDetailPolicy] = useState<
    BuilderDefinitionValues["productDetailPolicy"]
  >(
    (initialPdp.policy as BuilderDefinitionValues["productDetailPolicy"]) ??
      "new_or_changed",
  );
  const [estimate, setEstimate] = useState<CollectionScopeEstimate | null>(
    null,
  );
  const [estimatedSignature, setEstimatedSignature] = useState("");
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState<"geography" | "estimate" | "launch" | null>(
    null,
  );
  const [error, setError] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const selectedPack =
    options.product_packs.find((pack) => pack.id === productPackId) ??
    defaultPack;

  const geographyRequest = useMemo<CollectionGeographyRequest>(() => {
    const primarySelection: CollectionGeographyRequest["primary_selection"] = {
      mode: primaryMode,
    };
    if (["states", "per_state"].includes(primaryMode)) {
      primarySelection.states = selectedStates;
    }
    if (primaryMode === "per_state") {
      primarySelection.locations_per_state = locationsPerState;
    }
    if (primaryMode === "state_cities") {
      primarySelection.cities = selectedCities.map((value) => {
        const [state, ...cityParts] = value.split("|");
        return { state: state!, city: cityParts.join("|") };
      });
    }
    if (primaryMode === "custom_zips") {
      primarySelection.zipcodes = normalizeList(zipcodeText);
    }
    if (primaryMode === "custom_locations") {
      primarySelection.location_ids = normalizeList(locationIdText);
    }
    return {
      primary_retailer_id: primaryRetailerId,
      competitor_retailer_ids: competitorRetailerIds as [string, ...string[]],
      country: "USA",
      primary_selection: primarySelection,
      competitor_correspondence: {
        mode: correspondenceMode,
        radius_miles: correspondenceMode === "radius" ? radiusMiles : null,
      },
      exclusions,
    };
  }, [
    competitorRetailerIds,
    correspondenceMode,
    exclusions,
    locationIdText,
    locationsPerState,
    primaryMode,
    primaryRetailerId,
    radiusMiles,
    selectedCities,
    selectedStates,
    zipcodeText,
  ]);
  const geographySignature = JSON.stringify(geographyRequest);
  const resolutionCurrent =
    resolution !== null && resolvedSignature === geographySignature;

  const values = useMemo<BuilderDefinitionValues>(
    () => ({
      definitionId,
      name,
      productPackId: selectedPack.id,
      productPackVersion: selectedPack.version,
      keyword,
      primaryRetailerId,
      competitorRetailerIds,
      maxPagesByRetailer,
      maxCredits,
      availabilityGateEnabled: gateEnabled,
      scheduleType,
      cronExpression,
      timezone,
      delivery,
      productDetailPolicy,
    }),
    [
      competitorRetailerIds,
      cronExpression,
      definitionId,
      delivery,
      gateEnabled,
      keyword,
      maxCredits,
      maxPagesByRetailer,
      name,
      primaryRetailerId,
      productDetailPolicy,
      scheduleType,
      selectedPack.id,
      selectedPack.version,
      timezone,
    ],
  );
  const config = useMemo(
    () =>
      resolutionCurrent && resolution
        ? buildApprovedCollectionDefinition(values, options, resolution)
        : null,
    [options, resolution, resolutionCurrent, values],
  );
  const configSignature = config ? JSON.stringify(config) : "";
  const estimateCurrent =
    estimate !== null && estimatedSignature === configSignature;
  const overBudget =
    estimateCurrent && estimate.estimated_total_credits > maxCredits;

  useEffect(() => {
    const controller = new AbortController();
    fetch(
      `/api/collections/location-facets?retailer_id=${encodeURIComponent(primaryRetailerId)}&country=USA`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw new Error(await errorFrom(response));
        return (await response.json()) as CollectionLocationFacet[];
      })
      .then(setFacets)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError")
          return;
        setError(
          reason instanceof Error
            ? reason.message
            : "Locations could not be loaded.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setFacetsBusy(false);
      });
    return () => controller.abort();
  }, [primaryRetailerId]);

  const stateCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const facet of facets) {
      counts.set(
        facet.state,
        (counts.get(facet.state) ?? 0) + facet.location_count,
      );
    }
    return Array.from(counts, ([state, count]) => ({ state, count })).sort(
      (left, right) => left.state.localeCompare(right.state),
    );
  }, [facets]);
  const cityOptions = facets.filter(
    (facet) =>
      facet.city &&
      (selectedStates.length === 0 || selectedStates.includes(facet.state)),
  );
  const filteredLocations = (resolution?.locations ?? []).filter((item) => {
    const query = locationFilter.trim().toLowerCase();
    return (
      !query ||
      [
        item.retailer_id,
        item.store_number,
        item.store_name,
        item.zipcode,
        item.city,
        item.state,
      ].some((value) =>
        String(value ?? "")
          .toLowerCase()
          .includes(query),
      )
    );
  });

  function selectPack(packId: string) {
    const pack = options.product_packs.find((item) => item.id === packId);
    if (!pack) return;
    setProductPackId(pack.id);
    setName(`${pack.name} Collection`);
    setKeyword(pack.default_keyword);
    setApproved(false);
  }

  function changePrimary(retailerId: string) {
    setFacetsBusy(true);
    setPrimaryRetailerId(retailerId);
    setCompetitorRetailerIds((current) =>
      Array.from(
        new Set(
          current
            .filter((item) => item !== retailerId)
            .concat(primaryRetailerId),
        ),
      ),
    );
    setSelectedStates([]);
    setSelectedCities([]);
    setExclusions([]);
  }

  function toggleCompetitor(retailerId: string) {
    setCompetitorRetailerIds((current) =>
      current.includes(retailerId)
        ? current.filter((item) => item !== retailerId)
        : [...current, retailerId],
    );
    setExclusions([]);
  }

  function toggleState(state: string) {
    setSelectedStates((current) =>
      current.includes(state)
        ? current.filter((item) => item !== state)
        : [...current, state].sort(),
    );
    setSelectedCities((current) =>
      current.filter((item) => !item.startsWith(`${state}|`)),
    );
  }

  function validateGeography(): string | null {
    if (competitorRetailerIds.length === 0)
      return "Select at least one competitor.";
    if (
      ["states", "per_state"].includes(primaryMode) &&
      selectedStates.length === 0
    ) {
      return "Select at least one state.";
    }
    if (primaryMode === "state_cities" && selectedCities.length === 0) {
      return "Select at least one city.";
    }
    if (primaryMode === "custom_zips") {
      const zipcodes = normalizeList(zipcodeText);
      if (
        zipcodes.length === 0 ||
        zipcodes.some((item) => !/^\d{5}$/.test(item))
      ) {
        return "Enter one or more five-digit ZIP codes; leading zeros are preserved.";
      }
    }
    if (
      primaryMode === "custom_locations" &&
      normalizeList(locationIdText).length === 0
    ) {
      return "Enter one or more location IDs.";
    }
    return null;
  }

  async function previewGeography() {
    const validationError = validateGeography();
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy("geography");
    setError("");
    setApproved(false);
    setEstimate(null);
    try {
      const response = await fetch("/api/collections/geography", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: geographySignature,
      });
      if (!response.ok) throw new Error(await errorFrom(response));
      setResolution((await response.json()) as CollectionGeographyResolution);
      setResolvedSignature(geographySignature);
      setStep(4);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The geography preview failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  function excludeLocation(location: GeographyLocation) {
    setExclusions((current) => [
      ...current.filter(
        (item) =>
          !(
            item.retailer_id === location.retailer_id &&
            item.scope_key === location.scope_key
          ),
      ),
      {
        retailer_id: location.retailer_id,
        retailer_location_id: location.retailer_location_id ?? null,
        scope_key: location.scope_key,
      },
    ]);
    setApproved(false);
  }

  function restoreLocation(retailerId: string, scopeKey: string) {
    setExclusions((current) =>
      current.filter(
        (item) =>
          !(item.retailer_id === retailerId && item.scope_key === scopeKey),
      ),
    );
    setApproved(false);
  }

  async function calculateEstimate() {
    const validationError = validateBuilderDefinition(values);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!config || !resolutionCurrent) {
      setError("Refresh and approve the geography preview before estimating.");
      return;
    }
    setBusy("estimate");
    setError("");
    setApproved(false);
    try {
      const response = await fetch("/api/collections/estimate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: configSignature,
      });
      if (!response.ok) throw new Error(await errorFrom(response));
      setEstimate((await response.json()) as CollectionScopeEstimate);
      setEstimatedSignature(configSignature);
      setStep(6);
    } catch (reason) {
      setEstimate(null);
      setEstimatedSignature("");
      setError(
        reason instanceof Error ? reason.message : "The estimate failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function launch() {
    if (!config || !estimateCurrent || !estimate || !approved || overBudget)
      return;
    setBusy("launch");
    setError("");
    try {
      const response = await fetch("/api/collections/launch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ config, estimate_id: estimate.id }),
      });
      if (!response.ok) throw new Error(await errorFrom(response));
      const run = (await response.json()) as RunRecord;
      router.push(`/collections/runs/${encodeURIComponent(run.id)}`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The collection could not be launched.",
      );
      setBusy(null);
    }
  }

  return (
    <div className="collection-builder-shell">
      <nav className="builder-steps" aria-label="Collection builder progress">
        {steps.map((label, index) => {
          const number = index + 1;
          return (
            <button
              type="button"
              className={
                step === number ? "active" : step > number ? "complete" : ""
              }
              onClick={() => setStep(number)}
              key={label}
            >
              <span>{step > number ? "✓" : number}</span>
              {label}
            </button>
          );
        })}
      </nav>

      {error ? (
        <div className="builder-alert error" role="alert">
          <b>Review needed</b>
          <span>{error}</span>
          <button type="button" onClick={() => setError("")}>
            Dismiss
          </button>
        </div>
      ) : null}

      <section className="builder-stage">
        {step === 1 ? (
          <div className="builder-panel">
            <header>
              <span className="section-kicker">Step 1</span>
              <h2>Name the business question</h2>
              <p>
                Choose the category intelligence rules, keyword, primary
                retailer, and competitors. Only certified retailer adapters are
                selectable.
              </p>
            </header>
            <div className="form-grid">
              <label className="full-field">
                <span>Collection name</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label>
                <span>Product Pack</span>
                <select
                  value={selectedPack.id}
                  onChange={(event) => selectPack(event.target.value)}
                >
                  {options.product_packs.map((pack) => (
                    <option value={pack.id} key={pack.id}>
                      {pack.name} · v{pack.version}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Search keyword</span>
                <input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
              </label>
            </div>
            <div className="retailer-role-grid">
              <fieldset>
                <legend>Primary retailer</legend>
                {options.retailers
                  .filter(
                    (retailer) => retailer.location_dimension === "store_zip",
                  )
                  .map((retailer) => (
                    <label className="retailer-role-card" key={retailer.id}>
                      <input
                        type="radio"
                        name="primary-retailer"
                        checked={primaryRetailerId === retailer.id}
                        onChange={() => changePrimary(retailer.id)}
                      />
                      <span>
                        <b>{retailer.display_name}</b>
                        <small>Primary price position and assortment</small>
                      </span>
                    </label>
                  ))}
              </fieldset>
              <fieldset>
                <legend>Competitor retailers</legend>
                {options.retailers
                  .filter((retailer) => retailer.id !== primaryRetailerId)
                  .map((retailer) => (
                    <label className="retailer-role-card" key={retailer.id}>
                      <input
                        type="checkbox"
                        checked={competitorRetailerIds.includes(retailer.id)}
                        onChange={() => toggleCompetitor(retailer.id)}
                      />
                      <span>
                        <b>{retailer.display_name}</b>
                        <small>
                          {retailer.location_dimension === "zipcode"
                            ? "ZIP-level"
                            : "Store-level"}{" "}
                          · {retailer.credits_per_page} credits/page
                        </small>
                      </span>
                    </label>
                  ))}
              </fieldset>
            </div>
            <div className="builder-actions">
              <span />
              <button
                className="button primary"
                type="button"
                onClick={() => setStep(2)}
              >
                Define geography →
              </button>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="builder-panel">
            <header>
              <span className="section-kicker">Step 2</span>
              <h2>Choose {displayLabel(primaryRetailerId)} locations</h2>
              <p>
                Build a reproducible primary footprint. Population, county, and
                demographic modes remain disabled until governed source data is
                loaded.
              </p>
            </header>
            <div className="mode-card-grid">
              {(
                [
                  [
                    "all_locations",
                    "All locations",
                    "Every active primary-retailer store in the country.",
                  ],
                  [
                    "states",
                    "All stores in states",
                    "Every primary store in one or more selected states.",
                  ],
                  [
                    "per_state",
                    "X stores per state",
                    "A deterministic, geographically dispersed sample in each state.",
                  ],
                  [
                    "state_cities",
                    "Selected cities",
                    "Every primary store in the chosen state and city pairs.",
                  ],
                  [
                    "custom_zips",
                    "Custom ZIPs",
                    "Primary stores in an explicit ZIP list; leading zeros are preserved.",
                  ],
                  [
                    "custom_locations",
                    "Manual locations",
                    "An explicit list of canonical location UUIDs.",
                  ],
                ] as Array<[PrimaryMode, string, string]>
              ).map(([mode, label, description]) => (
                <label
                  className={
                    primaryMode === mode ? "mode-card selected" : "mode-card"
                  }
                  key={mode}
                >
                  <input
                    type="radio"
                    name="primary-mode"
                    checked={primaryMode === mode}
                    onChange={() => setPrimaryMode(mode)}
                  />
                  <span>
                    <b>{label}</b>
                    <small>{description}</small>
                  </span>
                </label>
              ))}
            </div>
            {facetsBusy ? (
              <p className="builder-loading">Loading location facets…</p>
            ) : null}
            {["states", "per_state"].includes(primaryMode) ? (
              <fieldset className="state-picker">
                <legend>States</legend>
                <div>
                  {stateCounts.map(({ state, count }) => (
                    <label key={state}>
                      <input
                        type="checkbox"
                        checked={selectedStates.includes(state)}
                        onChange={() => toggleState(state)}
                      />
                      <span>
                        <b>{state}</b>
                        <small>{count.toLocaleString()} stores</small>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}
            {primaryMode === "per_state" ? (
              <label className="builder-inline-field">
                <span>Locations per selected state</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={locationsPerState}
                  onChange={(event) =>
                    setLocationsPerState(Number(event.target.value))
                  }
                />
                <small>
                  The same source data always produces the same dispersed
                  sample.
                </small>
              </label>
            ) : null}
            {primaryMode === "state_cities" ? (
              <div className="city-picker">
                <div className="state-picker compact">
                  <strong>Filter cities by state</strong>
                  <div>
                    {stateCounts.map(({ state }) => (
                      <label key={state}>
                        <input
                          type="checkbox"
                          checked={selectedStates.includes(state)}
                          onChange={() => toggleState(state)}
                        />
                        <span>
                          <b>{state}</b>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
                <label>
                  <span>Cities</span>
                  <select
                    multiple
                    size={12}
                    value={selectedCities}
                    onChange={(event) =>
                      setSelectedCities(
                        Array.from(
                          event.target.selectedOptions,
                          (option) => option.value,
                        ),
                      )
                    }
                  >
                    {cityOptions.map((facet) => {
                      const value = `${facet.state}|${facet.city}`;
                      return (
                        <option value={value} key={value}>
                          {facet.city}, {facet.state} · {facet.location_count}{" "}
                          stores
                        </option>
                      );
                    })}
                  </select>
                  <small>Use Command/Control to select multiple cities.</small>
                </label>
              </div>
            ) : null}
            {primaryMode === "custom_zips" ? (
              <label className="builder-wide-field">
                <span>ZIP codes</span>
                <textarea
                  rows={6}
                  value={zipcodeText}
                  onChange={(event) => setZipcodeText(event.target.value)}
                />
                <small>
                  Comma, space, or line separated. Leading-zero ZIPs remain
                  strings.
                </small>
              </label>
            ) : null}
            {primaryMode === "custom_locations" ? (
              <label className="builder-wide-field">
                <span>Canonical location IDs</span>
                <textarea
                  rows={6}
                  value={locationIdText}
                  onChange={(event) => setLocationIdText(event.target.value)}
                />
              </label>
            ) : null}
            <div className="deferred-mode-note">
              <b>Demographic geography is intentionally unavailable</b>
              <span>
                The current location master does not contain governed county or
                population measures. Those options will appear only after a
                source, freshness policy, and validation contract are
                established.
              </span>
            </div>
            <div className="builder-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setStep(1)}
              >
                ← Back
              </button>
              <button
                className="button primary"
                type="button"
                onClick={() => setStep(3)}
              >
                Match competitor coverage →
              </button>
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="builder-panel">
            <header>
              <span className="section-kicker">Step 3</span>
              <h2>Define corresponding competitor coverage</h2>
              <p>
                The relationship is computed from the selected{" "}
                {displayLabel(primaryRetailerId)} footprint. Competitor stores
                are deduplicated before cost estimation.
              </p>
            </header>
            <div className="correspondence-grid">
              {(
                [
                  [
                    "same_zip",
                    "Same ZIP",
                    "Include competitor stores in each selected primary ZIP.",
                  ],
                  [
                    "primary_states",
                    "All stores in primary states",
                    "Include all competitor stores across the selected primary states.",
                  ],
                  [
                    "radius",
                    "Within a radius",
                    "Include competitor stores within an exact 1, 3, or 5 miles of a primary store.",
                  ],
                ] as Array<[CorrespondenceMode, string, string]>
              ).map(([mode, label, description]) => (
                <label
                  className={
                    correspondenceMode === mode
                      ? "mode-card selected"
                      : "mode-card"
                  }
                  key={mode}
                >
                  <input
                    type="radio"
                    name="correspondence-mode"
                    checked={correspondenceMode === mode}
                    onChange={() => setCorrespondenceMode(mode)}
                  />
                  <span>
                    <b>{label}</b>
                    <small>{description}</small>
                  </span>
                </label>
              ))}
            </div>
            {correspondenceMode === "radius" ? (
              <fieldset className="radius-picker">
                <legend>Maximum distance</legend>
                {([1, 3, 5] as const).map((miles) => (
                  <label key={miles}>
                    <input
                      type="radio"
                      checked={radiusMiles === miles}
                      onChange={() => setRadiusMiles(miles)}
                    />
                    <span>
                      <b>{miles}</b> mile{miles === 1 ? "" : "s"}
                    </span>
                  </label>
                ))}
                <p>
                  Exact Haversine distance is stored for every
                  primary-to-competitor edge. A selected Product Pack may still
                  use exact-ZIP comparisons only.
                </p>
              </fieldset>
            ) : null}
            <div className="zip-retailer-note">
              <b>ZIP-only retailer behavior</b>
              <span>
                Amazon Same Day receives the deduplicated primary ZIP universe.
                It is not represented as physical stores and will not appear as
                store markers.
              </span>
            </div>
            <div className="builder-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setStep(2)}
              >
                ← Back
              </button>
              <button
                className="button primary"
                type="button"
                disabled={busy !== null}
                onClick={() => void previewGeography()}
              >
                {busy === "geography"
                  ? "Resolving locations…"
                  : "Build geography preview →"}
              </button>
            </div>
          </div>
        ) : null}

        {step === 4 ? (
          <div className="builder-panel wide">
            <header className="builder-review-header">
              <div>
                <span className="section-kicker">Step 4</span>
                <h2>Review the exact collection footprint</h2>
                <p>
                  This candidate is stored as an immutable snapshot. Approval
                  binds its checksum to the new collection-definition version.
                </p>
              </div>
              {resolution ? (
                <a
                  className="button secondary"
                  href={`/api/collections/geography/${resolution.id}/download`}
                >
                  Download CSV
                </a>
              ) : null}
            </header>
            {!resolution ? (
              <div className="estimate-placeholder">
                <strong>No geography preview yet</strong>
                <p>Return to competitor coverage and build the preview.</p>
              </div>
            ) : (
              <>
                {!resolutionCurrent ? (
                  <div className="builder-alert warning">
                    <b>Preview is out of date</b>
                    <span>
                      Your selection or exclusions changed. Refresh before
                      estimating.
                    </span>
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => void previewGeography()}
                    >
                      {busy === "geography" ? "Refreshing…" : "Refresh preview"}
                    </button>
                  </div>
                ) : null}
                {exclusions.length > 0 ? (
                  <div className="builder-exclusion-tray">
                    <div>
                      <b>
                        {exclusions.length.toLocaleString()} location
                        {exclusions.length === 1 ? "" : "s"} excluded
                      </b>
                      <span>
                        Restore an exclusion here, then refresh the preview.
                      </span>
                    </div>
                    <div>
                      {exclusions.map((item) => (
                        <button
                          type="button"
                          key={`${item.retailer_id}:${item.scope_key}`}
                          onClick={() =>
                            restoreLocation(item.retailer_id, item.scope_key)
                          }
                        >
                          {displayLabel(item.retailer_id)} · {item.scope_key} ×
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="geography-summary-strip">
                  <div>
                    <span>{displayLabel(primaryRetailerId)}</span>
                    <strong>
                      {Number(resolution.counts.primary).toLocaleString()}
                    </strong>
                    <small>primary stores</small>
                  </div>
                  {Object.entries(resolution.counts.competitors).map(
                    ([retailerId, count]) => (
                      <div key={retailerId}>
                        <span>{displayLabel(retailerId)}</span>
                        <strong>{Number(count).toLocaleString()}</strong>
                        <small>
                          {options.retailers.find(
                            (item) => item.id === retailerId,
                          )?.location_dimension === "zipcode"
                            ? "ZIP scopes"
                            : "competitor stores"}
                        </small>
                      </div>
                    ),
                  )}
                  <div>
                    <span>Proximity links</span>
                    <strong>{resolution.edges.length.toLocaleString()}</strong>
                    <small>auditable store pairs</small>
                  </div>
                </div>
                <GeographyPreviewMap
                  locations={resolution.locations}
                  primaryRetailerId={primaryRetailerId}
                />
                <div className="builder-location-table-wrap">
                  <header>
                    <div>
                      <h3>Resolved locations</h3>
                      <p>
                        Remove an unnecessary location, then refresh the preview
                        to recalculate correspondence and cost.
                      </p>
                    </div>
                    <label>
                      <span>Filter locations</span>
                      <input
                        type="search"
                        value={locationFilter}
                        onChange={(event) =>
                          setLocationFilter(event.target.value)
                        }
                        placeholder="Retailer, store, ZIP, city, state"
                      />
                    </label>
                  </header>
                  <div className="builder-location-table-scroll">
                    <table className="builder-location-table">
                      <thead>
                        <tr>
                          <th>Role</th>
                          <th>Retailer</th>
                          <th>Location</th>
                          <th>Market</th>
                          <th>Reason</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {filteredLocations.slice(0, 500).map((location) => (
                          <tr key={location.id}>
                            <td>
                              <span className={`role-pill ${location.role}`}>
                                {location.role}
                              </span>
                            </td>
                            <td>{displayLabel(location.retailer_id)}</td>
                            <td>
                              <b>
                                {location.store_name ??
                                  (location.store_number
                                    ? `Store ${location.store_number}`
                                    : "ZIP scope")}
                              </b>
                              {location.store_number ? (
                                <small>ID {location.store_number}</small>
                              ) : null}
                            </td>
                            <td>
                              {location.city ? `${location.city}, ` : ""}
                              {location.state ?? ""} {location.zipcode}
                            </td>
                            <td>{displayLabel(location.selection_reason)}</td>
                            <td>
                              <button
                                type="button"
                                className="text-link"
                                onClick={() => excludeLocation(location)}
                              >
                                Exclude
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {filteredLocations.length > 500 ? (
                    <p className="table-limit-note">
                      Showing the first 500 filtered rows. Download the CSV for
                      the complete {filteredLocations.length.toLocaleString()}
                      -row snapshot.
                    </p>
                  ) : null}
                </div>
              </>
            )}
            <div className="builder-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setStep(3)}
              >
                ← Change coverage
              </button>
              <button
                className="button primary"
                type="button"
                disabled={!resolutionCurrent}
                onClick={() => setStep(5)}
              >
                Set collection controls →
              </button>
            </div>
          </div>
        ) : null}

        {step === 5 ? (
          <div className="builder-panel">
            <header>
              <span className="section-kicker">Step 5</span>
              <h2>Set spend, schedule, and delivery controls</h2>
              <p>
                Search collection is estimated now. Product-detail enrichment
                remains a separate post-Search approval because eligible
                products are unknown until analysis removes search noise.
              </p>
            </header>
            <div className="builder-control-grid">
              <section>
                <h3>Search depth and budget</h3>
                {[primaryRetailerId, ...competitorRetailerIds].map(
                  (retailerId) => (
                    <label key={retailerId}>
                      <span>{displayLabel(retailerId)} pages / location</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={maxPagesByRetailer[retailerId] ?? 1}
                        onChange={(event) =>
                          setMaxPagesByRetailer((current) => ({
                            ...current,
                            [retailerId]: Number(event.target.value),
                          }))
                        }
                      />
                    </label>
                  ),
                )}
                <label>
                  <span>Hard Search credit cap</span>
                  <input
                    type="number"
                    min={0}
                    value={maxCredits}
                    onChange={(event) =>
                      setMaxCredits(Number(event.target.value))
                    }
                  />
                </label>
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={gateEnabled}
                    disabled={!competitorRetailerIds.includes("aldi_us")}
                    onChange={(event) => setGateEnabled(event.target.checked)}
                  />
                  <span>
                    <b>Run ALDI availability gate first</b>
                    <small>
                      Test up to five selected ALDI stores before releasing the
                      remaining queue.
                    </small>
                  </span>
                </label>
              </section>
              <section>
                <h3>Schedule</h3>
                <label>
                  <span>Run cadence</span>
                  <select
                    value={scheduleType}
                    onChange={(event) =>
                      setScheduleType(event.target.value as "manual" | "cron")
                    }
                  >
                    <option value="manual">Manual launch</option>
                    <option value="cron">Recurring schedule</option>
                  </select>
                </label>
                {scheduleType === "cron" ? (
                  <label>
                    <span>Cron expression</span>
                    <input
                      value={cronExpression}
                      onChange={(event) =>
                        setCronExpression(event.target.value)
                      }
                    />
                    <small>Example: 0 6 * * 1 runs Mondays at 6:00 AM.</small>
                  </label>
                ) : null}
                <label>
                  <span>Timezone</span>
                  <select
                    value={timezone}
                    onChange={(event) => setTimezone(event.target.value)}
                  >
                    <option value="America/Chicago">America/Chicago</option>
                    <option value="America/New_York">America/New_York</option>
                    <option value="America/Denver">America/Denver</option>
                    <option value="America/Los_Angeles">
                      America/Los_Angeles
                    </option>
                    <option value="UTC">UTC</option>
                  </select>
                </label>
                <p className="frozen-schedule-note">
                  Scheduled runs keep this frozen geography. Refreshing
                  locations creates a new definition version and requires a new
                  estimate approval.
                </p>
              </section>
              <section>
                <h3>Product detail enrichment</h3>
                <label>
                  <span>Refresh policy</span>
                  <select
                    value={productDetailPolicy}
                    onChange={(event) =>
                      setProductDetailPolicy(
                        event.target
                          .value as BuilderDefinitionValues["productDetailPolicy"],
                      )
                    }
                  >
                    <option value="disabled">Disabled</option>
                    <option value="new_or_changed">
                      New or changed products
                    </option>
                    <option value="refresh_after_7_days">
                      Refresh after 7 days
                    </option>
                    <option value="refresh_after_30_days">
                      Refresh after 30 days
                    </option>
                    <option value="manual">Manual only</option>
                  </select>
                </label>
                <div className="separate-approval-note">
                  <b>Separate approval required</b>
                  <span>
                    Only products admitted to the analysis are eligible. One
                    representative PDP is used unless the same product ID has
                    store-level price variation.
                  </span>
                </div>
              </section>
              <section>
                <h3>Delivery</h3>
                {(
                  [
                    ["webReport", "In-app report"],
                    ["excel", "Excel workbook"],
                    ["leadershipEmail", "Leadership email"],
                    ["auditPackage", "Audit package"],
                  ] as const
                ).map(([key, label]) => (
                  <label className="inline-check" key={key}>
                    <input
                      type="checkbox"
                      checked={delivery[key]}
                      onChange={(event) =>
                        setDelivery((current) => ({
                          ...current,
                          [key]: event.target.checked,
                        }))
                      }
                    />
                    <span>
                      <b>{label}</b>
                    </span>
                  </label>
                ))}
              </section>
            </div>
            <div className="builder-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setStep(4)}
              >
                ← Review geography
              </button>
              <button
                className="button primary"
                type="button"
                disabled={busy !== null || !resolutionCurrent}
                onClick={() => void calculateEstimate()}
              >
                {busy === "estimate"
                  ? "Calculating…"
                  : "Calculate exact Search estimate →"}
              </button>
            </div>
          </div>
        ) : null}

        {step === 6 ? (
          <div className="builder-panel approval-panel">
            <header>
              <span className="section-kicker">Step 6</span>
              <h2>Review and explicitly approve provider spend</h2>
              <p>
                Estimation itself makes no MetricsCart calls. Launching releases
                the durable queue up to the approved maximum; billable 200 and
                404 responses are recorded.
              </p>
            </header>
            {!estimateCurrent || !estimate ? (
              <div className="estimate-placeholder">
                <strong>No current estimate</strong>
                <p>
                  The definition changed or has not been estimated. Return to
                  collection controls and calculate again.
                </p>
              </div>
            ) : (
              <div className="approval-layout">
                <div className="estimate-total">
                  <span>Maximum Search credits</span>
                  <strong>
                    {estimate.estimated_total_credits.toLocaleString()}
                  </strong>
                  <small>
                    {estimate.estimated_total_pages.toLocaleString()} maximum
                    pages · expires{" "}
                    {new Date(estimate.expires_at).toLocaleTimeString()}
                  </small>
                </div>
                <div className="estimate-breakdown">
                  {estimate.retailers.map((retailer) => (
                    <div key={retailer.retailer_id}>
                      <span>
                        <b>{displayLabel(retailer.retailer_id)}</b>
                        <small>
                          {retailer.location_units.toLocaleString()} location
                          units × {retailer.max_pages} page
                          {retailer.max_pages === 1 ? "" : "s"}
                        </small>
                      </span>
                      <strong>
                        {retailer.estimated_credits.toLocaleString()}
                      </strong>
                    </div>
                  ))}
                </div>
                <dl className="approval-audit-grid">
                  <div>
                    <dt>Geography snapshot</dt>
                    <dd>{estimate.resolution_id.slice(0, 8)}…</dd>
                  </div>
                  <div>
                    <dt>Geography checksum</dt>
                    <dd>{estimate.geography_checksum.slice(0, 12)}…</dd>
                  </div>
                  <div>
                    <dt>Configuration checksum</dt>
                    <dd>{estimate.configuration_checksum.slice(0, 12)}…</dd>
                  </div>
                  <div>
                    <dt>PDP spend</dt>
                    <dd>Not included · separately approved later</dd>
                  </div>
                </dl>
                {overBudget ? (
                  <p className="form-error">
                    The estimate exceeds the hard cap of{" "}
                    {maxCredits.toLocaleString()} credits. Reduce scope or raise
                    the cap, then estimate again.
                  </p>
                ) : null}
                <label className="inline-check approval-check">
                  <input
                    type="checkbox"
                    checked={approved}
                    disabled={overBudget}
                    onChange={(event) => setApproved(event.target.checked)}
                  />
                  <span>
                    <b>
                      I approve up to{" "}
                      {estimate.estimated_total_credits.toLocaleString()}{" "}
                      billable Search credits
                    </b>
                    <small>
                      I reviewed the frozen geography, retailer pages, and
                      category keyword shown in this definition.
                    </small>
                  </span>
                </label>
                <div className="launch-warning">
                  <b>This is the paid action</b>
                  <span>
                    Do not launch until the collection is intended to begin. The
                    availability gate and hard cap remain active in the worker.
                  </span>
                </div>
              </div>
            )}
            <div className="builder-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setStep(5)}
              >
                ← Change controls
              </button>
              <button
                className="button primary launch-button"
                type="button"
                disabled={
                  !estimateCurrent || !approved || overBudget || busy !== null
                }
                onClick={() => void launch()}
              >
                {busy === "launch"
                  ? "Launching…"
                  : "Launch approved collection"}
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
