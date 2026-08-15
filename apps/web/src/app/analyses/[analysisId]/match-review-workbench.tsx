"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  MatchReview,
  MatchReviewConnection,
  MatchReviewProduct,
  MatchingV2ShadowView,
  ProductMatchScope,
} from "@/lib/api";
import {
  type CrossLensMembership,
  compareProductDetails,
  connectionSearchText,
  evidenceForProfile,
  productDetailRows,
  productEvidenceSummary,
  rankMatchReviewConnections,
  scopeMatchReview,
} from "@/lib/match-review-model";
import { formatPriceForBasis, priceUnitLabel } from "@/lib/report-presentation";

type Decision = "confirmed" | "rejected" | "reset";
type StatusFilter = "all" | MatchReviewConnection["status"];
type ScopeMode = ProductMatchScope["mode"];

interface DetailSelection {
  benchmark?: MatchReviewProduct;
  competitor?: MatchReviewProduct;
  connection?: MatchReviewConnection;
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value))
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function sha256(value: string) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

async function proposedScope(
  analysisId: string,
  profileId: string,
  mode: ScopeMode,
  connection?: MatchReviewConnection,
): Promise<ProductMatchScope> {
  if (connection?.scope) return connection.scope;
  const evidence = connection
    ? evidenceForProfile(connection, profileId)
    : undefined;
  const familySource = {
    profile_id: profileId,
    match_attributes: evidence?.match_attributes ?? {},
  };
  const familyHash = await sha256(canonicalJson(familySource));
  const definition =
    mode === "global"
      ? { future_location_policy: "review" as const }
      : {
          source_analysis_id: analysisId,
          benchmark_location_scope_keys: [] as string[],
          excluded_benchmark_location_scope_keys: [] as string[],
          future_location_policy: "follow_unique_product_footprint" as const,
        };
  const payload = {
    mode,
    relationship_role: "primary" as const,
    comparison_family_key: `${profileId}:${familyHash.slice(0, 20)}`,
    definition,
    artifact_id: null,
  };
  return { ...payload, checksum: await sha256(canonicalJson(payload)) };
}

function scopeLabel(scope: MatchReviewConnection["scope"]) {
  if (!scope || scope.mode === "global") return "All observed locations";
  const count = scope.definition.benchmark_location_scope_keys?.length ?? 0;
  if (scope.mode === "explicit_benchmark_locations")
    return `${count} selected primary locations`;
  return count
    ? `Primary product footprint · ${count} locations`
    : "Primary product footprint";
}

function ProductImage({
  product,
  retailerName,
}: Readonly<{ product: MatchReviewProduct; retailerName: string }>) {
  return (
    <span className="match-product-image">
      {product.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={product.image_url} alt={`${product.name} product`} />
      ) : (
        <b>{retailerName.slice(0, 1)}</b>
      )}
    </span>
  );
}

function MatchBuilderProduct({
  product,
  retailerName,
  selected,
  onSelect,
  onView,
  draggable = false,
  onDropProduct,
  crossLensMemberships = [],
  readOnly = false,
}: Readonly<{
  product: MatchReviewProduct;
  retailerName: string;
  selected: boolean;
  onSelect: () => void;
  onView: () => void;
  draggable?: boolean;
  onDropProduct?: (productId: string) => void;
  crossLensMemberships?: CrossLensMembership[];
  readOnly?: boolean;
}>) {
  return (
    <article
      className={`match-product-card ${selected ? "selected" : ""}`}
      draggable={draggable}
      onDragStart={(event) => {
        event.dataTransfer.setData("text/product-id", product.product_id);
        event.dataTransfer.effectAllowed = "link";
      }}
      onDragOver={(event) => {
        if (onDropProduct) event.preventDefault();
      }}
      onDrop={(event) => {
        if (!onDropProduct) return;
        event.preventDefault();
        onDropProduct(event.dataTransfer.getData("text/product-id"));
      }}
    >
      <button
        type="button"
        className="match-product-select"
        aria-pressed={selected}
        onClick={readOnly ? onView : onSelect}
      >
        <ProductImage product={product} retailerName={retailerName} />
        <span className="match-product-copy">
          <small>{product.brand || retailerName}</small>
          <strong>{product.name}</strong>
          <em>{product.product_id}</em>
          <b className="match-identity-source">
            PDP identity · Search price evidence
          </b>
          {crossLensMemberships.length ? (
            <span className="match-cross-lens-badges">
              {crossLensMemberships.map((membership) => (
                <i
                  key={`${membership.profileId}:${membership.counterpartProductId}`}
                >
                  {membership.status === "confirmed"
                    ? "Confirmed"
                    : "Suggested"}{" "}
                  in {membership.profileLabel}
                </i>
              ))}
            </span>
          ) : null}
        </span>
      </button>
      <button type="button" className="match-details-link" onClick={onView}>
        View details
      </button>
    </article>
  );
}

function RelationshipProduct({
  product,
  retailerName,
  role,
  onView,
}: Readonly<{
  product: MatchReviewProduct | undefined;
  retailerName: string;
  role: string;
  onView: () => void;
}>) {
  if (!product)
    return <span className="match-product-missing">Product unavailable</span>;
  return (
    <button type="button" className="relationship-product" onClick={onView}>
      <ProductImage product={product} retailerName={retailerName} />
      <span>
        <small>
          {retailerName} · {role}
        </small>
        <strong>{product.name}</strong>
        <em>{product.product_id}</em>
        <b className="match-identity-source">
          PDP identity · Search price evidence
        </b>
      </span>
    </button>
  );
}

function statusCopy(status: MatchReviewConnection["status"]) {
  if (status === "confirmed") return "Confirmed and locked";
  if (status === "rejected") return "Rejected by user";
  if (status === "ambiguous") return "Needs a human decision";
  return "Suggested by Product Pack";
}

function gapCopy(
  gap: number | null | undefined,
  benchmarkName: string,
  competitorName: string,
  priceUnit?: string,
) {
  if (typeof gap !== "number")
    return "Paired median price difference unavailable";
  if (Math.abs(gap) < 0.005) return "Paired median price difference: $0.00";
  const amount = formatPriceForBasis(Math.abs(gap), priceUnit);
  return gap < 0
    ? `${competitorName} is ${amount} lower at the paired median`
    : `${benchmarkName} is ${amount} lower at the paired median`;
}

function shadowLabel(value: string | null) {
  if (!value) return "Unresolved";
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shadowValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function MatchingV2ShadowPanel({
  view,
  productByKey,
  benchmarkRetailerId,
  competitorId,
}: Readonly<{
  view: MatchingV2ShadowView;
  productByKey: Map<string, MatchReviewProduct>;
  benchmarkRetailerId: string;
  competitorId: string;
}>) {
  const artifact = view.artifacts.find(
    (candidate) => candidate.retailer_id === competitorId,
  );
  const summary = artifact?.summary ?? {};
  return (
    <details className="matching-v2-preview">
      <summary>
        <span>
          <small>Evidence architecture preview</small>
          <strong>Matching v2 · governed, read-only shadow results</strong>
        </span>
        <em>{view.total_edges} candidate edges</em>
      </summary>
      <div className="matching-v2-notice">
        <strong>Not used in this report yet</strong>
        <p>
          These results test tiered product evidence before certification. They
          cannot change match decisions, scorecards, price math, or reporting.
        </p>
      </div>
      <div className="matching-v2-metrics">
        <span>
          <b>{Number(summary.benchmark_listings ?? 0).toLocaleString()}</b>
          Primary listings
        </span>
        <span>
          <b>{Number(summary.competitor_listings ?? 0).toLocaleString()}</b>
          Competitor listings
        </span>
        <span>
          <b>{Number(summary.evaluated_pairs ?? 0).toLocaleString()}</b>
          Evidence pairs evaluated
        </span>
        <span>
          <b>{Number(summary.blocked_pairs ?? 0).toLocaleString()}</b>
          Known conflicts blocked
        </span>
      </div>
      <div className="matching-v2-edge-list">
        {view.edges.slice(0, 25).map((edge) => {
          const benchmarkProductId = edge.benchmark_listing_id.replace(
            `${benchmarkRetailerId}:`,
            "",
          );
          const competitorProductId = edge.competitor_listing_id.replace(
            `${competitorId}:`,
            "",
          );
          const benchmark = productByKey.get(
            `${benchmarkRetailerId}:${benchmarkProductId}`,
          );
          const competitor = productByKey.get(
            `${competitorId}:${competitorProductId}`,
          );
          return (
            <details className="matching-v2-edge" key={edge.edge_id}>
              <summary>
                <span>
                  <strong>{benchmark?.name || benchmarkProductId}</strong>
                  <small>with {competitor?.name || competitorProductId}</small>
                </span>
                <span
                  className={`matching-v2-tier ${edge.tier || "unresolved"}`}
                >
                  {shadowLabel(edge.tier)}
                </span>
                <em>
                  {Math.round(edge.evidence_coverage.critical_coverage * 100)}%
                  evidence coverage
                </em>
              </summary>
              <p className="matching-v2-reason">{edge.decision.reason}</p>
              <dl className="matching-v2-edge-meta">
                <div>
                  <dt>Status</dt>
                  <dd>{shadowLabel(edge.status)}</dd>
                </div>
                <div>
                  <dt>Brand relationship</dt>
                  <dd>{shadowLabel(edge.brand_relationship)}</dd>
                </div>
                <div>
                  <dt>Eligible price bases</dt>
                  <dd>
                    {edge.eligible_price_bases.length
                      ? edge.eligible_price_bases.map(shadowLabel).join(" · ")
                      : "None until resolved"}
                  </dd>
                </div>
              </dl>
              <div className="matching-v2-evidence-table" role="table">
                <div role="row" className="matching-v2-evidence-head">
                  <span role="columnheader">Attribute</span>
                  <span role="columnheader">Primary</span>
                  <span role="columnheader">Competitor</span>
                  <span role="columnheader">Evidence result</span>
                </div>
                {edge.attribute_evidence.map((evidence) => (
                  <div role="row" key={evidence.attribute}>
                    <span role="cell">
                      <strong>{shadowLabel(evidence.attribute)}</strong>
                      <small>{shadowLabel(evidence.role)}</small>
                    </span>
                    <span role="cell">
                      {shadowValue(evidence.benchmark_value)}
                    </span>
                    <span role="cell">
                      {shadowValue(evidence.competitor_value)}
                    </span>
                    <span
                      role="cell"
                      className={`evidence-${evidence.outcome}`}
                    >
                      {shadowLabel(evidence.outcome)}
                      {evidence.rationale ? (
                        <small>{evidence.rationale}</small>
                      ) : null}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          );
        })}
      </div>
      {view.total_edges > 25 ? (
        <p className="matching-v2-more">
          Showing the first 25 deterministic edges. Use product filters in the
          governed inspection API for the complete population.
        </p>
      ) : null}
    </details>
  );
}

function ProductEvidencePanel({
  product,
  retailerName,
}: Readonly<{
  product: MatchReviewProduct;
  retailerName: string;
}>) {
  const rows = productDetailRows(product);
  const summary = productEvidenceSummary(product);
  return (
    <section className="match-drawer-product">
      <div className="match-drawer-product-head">
        <ProductImage product={product} retailerName={retailerName} />
        <div>
          <span>{retailerName}</span>
          <h4>{product.name}</h4>
          <p>{product.brand || "Brand not provided"}</p>
          <code>{product.product_id}</code>
        </div>
      </div>
      <div className="match-pdp-status-line">
        <span className={summary.enriched ? "enriched" : "missing"}>
          {summary.enriched ? "PDP enriched" : "PDP not available"}
        </span>
        <small>
          {summary.sourceFieldCount
            ? `${summary.sourceFieldCount} retained provider fields`
            : summary.enriched
              ? "PDP identity retained"
              : "Search identity fallback"}
        </small>
      </div>
      <div className="match-pdp-summary-grid">
        <div>
          <span>Seller</span>
          <strong>{summary.seller || "Not supplied"}</strong>
          <small>Never inferred from retailer name</small>
        </div>
        <div>
          <span>Category</span>
          <strong>{summary.category || "Not supplied"}</strong>
          <small>{summary.condition || "Condition not supplied"}</small>
        </div>
        <div>
          <span>Ratings</span>
          <strong>
            {summary.rating === null
              ? "Not supplied"
              : `${summary.rating.toFixed(1)} rating`}
          </strong>
          <small>
            {summary.reviewCount === null
              ? "Review count not supplied"
              : `${summary.reviewCount.toLocaleString()} reviews/ratings`}
          </small>
        </div>
        <div>
          <span>Fulfillment</span>
          <strong>{summary.fulfillment[0] || "Not supplied"}</strong>
          <small>
            {summary.fulfillment.slice(1).join(" · ") || "PDP context only"}
          </small>
        </div>
        <div>
          <span>Content depth</span>
          <strong>
            {summary.imageCount} images · {summary.videoCount} videos
          </strong>
          <small>{summary.relationshipCount} related product references</small>
        </div>
        <div>
          <span>Demand context</span>
          <strong>{summary.demand || "Not supplied"}</strong>
          <small>PDP reference; not Search demand</small>
        </div>
      </div>
      <p className="match-product-description">
        {summary.description ||
          "No PDP description is persisted for this product."}
      </p>
      {product.url ? (
        <a href={product.url} target="_blank" rel="noreferrer">
          Open retailer product page ↗
        </a>
      ) : null}
      {rows.length ? (
        <details className="match-pdp-details">
          <summary>View identifiers and all retained attributes</summary>
          <dl className="match-detail-list">
            {rows.slice(0, 36).map((row) => (
              <div key={`${row.section}:${row.label}`}>
                <dt>
                  <small>{row.section}</small>
                  {row.label}
                </dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : (
        <p className="match-detail-empty">
          No additional PDP specifications are persisted for this product.
        </p>
      )}
      {summary.unmappedFields.length ? (
        <p className="match-pdp-governance-note">
          {summary.unmappedFields.length} newly observed provider field
          {summary.unmappedFields.length === 1 ? " is" : "s are"} retained in
          the immutable raw payload and queued for schema review.
        </p>
      ) : null}
    </section>
  );
}

function ProductComparisonChecklist({
  benchmark,
  competitor,
  benchmarkName,
  competitorName,
}: Readonly<{
  benchmark: MatchReviewProduct;
  competitor: MatchReviewProduct;
  benchmarkName: string;
  competitorName: string;
}>) {
  const rows = compareProductDetails(benchmark, competitor).filter(
    (row) =>
      ["Product", "Specifications", "Physical properties", "Variant"].includes(
        row.section,
      ) && row.label !== "Seller",
  );
  if (!rows.length) return null;
  const aligned = rows.filter((row) => row.status === "aligned").length;
  const needsReview = rows.length - aligned;
  return (
    <section className="match-comparison-checklist">
      <header>
        <div>
          <p className="eyebrow">PDP comparison checklist</p>
          <h4>See exactly where identity evidence aligns or differs</h4>
          <p>
            PDP attributes inform comparability; Product Pack rules and Search
            observations still govern the relationship and price result.
          </p>
        </div>
        <span>
          <b>{aligned} aligned</b>
          <em>{needsReview} incomplete or different</em>
        </span>
      </header>
      <div className="match-comparison-table" role="table">
        <div className="match-comparison-head" role="row">
          <strong role="columnheader">Attribute</strong>
          <strong role="columnheader">{benchmarkName}</strong>
          <strong role="columnheader">{competitorName}</strong>
          <strong role="columnheader">Assessment</strong>
        </div>
        {rows.slice(0, 18).map((row) => (
          <div
            className={`match-comparison-row ${row.status}`}
            role="row"
            key={`${row.section}:${row.label}`}
          >
            <span role="cell">
              <small>{row.section}</small>
              {row.label}
            </span>
            <span role="cell">{row.value}</span>
            <span role="cell">{row.counterpartValue || "Not supplied"}</span>
            <b role="cell">
              {row.status === "aligned"
                ? "Aligned"
                : row.status === "different"
                  ? "Review difference"
                  : "Incomplete"}
            </b>
          </div>
        ))}
      </div>
    </section>
  );
}

function MatchEvidenceDrawer({
  selection,
  profileId,
  benchmarkName,
  competitorName,
  onClose,
  busy,
  message,
  onDecide,
  readOnly,
  workbenchHref,
}: Readonly<{
  selection: DetailSelection;
  profileId: string;
  benchmarkName: string;
  competitorName: string;
  onClose: () => void;
  busy: boolean;
  message: string;
  onDecide: (decision: Decision) => void;
  readOnly: boolean;
  workbenchHref: string;
}>) {
  const evidence = selection.connection
    ? evidenceForProfile(selection.connection, profileId)
    : undefined;
  const attributes = evidence ? Object.entries(evidence.match_attributes) : [];

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      className="match-drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <aside
        className="match-evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="match-evidence-title"
      >
        <header>
          <div>
            <p className="eyebrow">Product evidence</p>
            <h3 id="match-evidence-title">
              {selection.connection
                ? "Why these products are comparable"
                : "Product identity and specifications"}
            </h3>
          </div>
          <button
            type="button"
            aria-label="Close product evidence"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        {selection.connection ? (
          <section className="match-drawer-evidence">
            <div>
              <small>Decision state</small>
              <strong>{statusCopy(selection.connection.status)}</strong>
            </div>
            <div>
              <small>Search evidence</small>
              <strong>
                {evidence?.matches ?? 0} observations ·{" "}
                {evidence?.geographies ?? 0} markets
              </strong>
            </div>
            <div>
              <small>Paired median price position</small>
              <strong>
                {gapCopy(
                  evidence?.median_gap,
                  benchmarkName,
                  competitorName,
                  evidence?.price_unit,
                )}
              </strong>
            </div>
            <div className="match-search-price-grid">
              <span>
                <small>{benchmarkName} marginal median</small>
                <strong>
                  {formatPriceForBasis(
                    evidence?.benchmark_median,
                    evidence?.price_unit,
                  )}
                </strong>
              </span>
              <span>
                <small>{competitorName} marginal median</small>
                <strong>
                  {formatPriceForBasis(
                    evidence?.competitor_median,
                    evidence?.price_unit,
                  )}
                </strong>
              </span>
              <em>
                Search-derived · {evidence?.profile_label ?? profileId} ·{" "}
                {priceUnitLabel(evidence?.price_unit)} · medians and paired gap
                are distinct statistics
              </em>
            </div>
            <p>{evidence?.rationale || selection.connection.reason}</p>
            {attributes.length ? (
              <div className="match-attribute-chips">
                {attributes.map(([name, value]) => (
                  <span key={name}>
                    {name.replaceAll("_", " ")}: {String(value)}
                  </span>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}

        {selection.benchmark && selection.competitor ? (
          <ProductComparisonChecklist
            benchmark={selection.benchmark}
            competitor={selection.competitor}
            benchmarkName={benchmarkName}
            competitorName={competitorName}
          />
        ) : null}
        <div className="match-drawer-products">
          {selection.benchmark ? (
            <ProductEvidencePanel
              product={selection.benchmark}
              retailerName={benchmarkName}
            />
          ) : null}
          {selection.competitor ? (
            <ProductEvidencePanel
              product={selection.competitor}
              retailerName={competitorName}
            />
          ) : null}
        </div>
        <footer className="match-drawer-footer">
          {message ? (
            <p className="match-drawer-message" role="status">
              {message}
            </p>
          ) : null}
          <p>
            Store-specific price and location evidence comes from Search. PDP
            evidence is used for product identity, descriptions, specifications,
            URLs, and imagery.
          </p>
          {selection.connection ? (
            <span>
              {readOnly ? (
                <Link className="button primary" href={workbenchHref}>
                  Open relationship in Match Workbench
                </Link>
              ) : (
                <>
                  {selection.connection.status !== "confirmed" ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onDecide("confirmed")}
                    >
                      Confirm relationship
                    </button>
                  ) : null}
                  {selection.connection.status !== "rejected" ? (
                    <button
                      type="button"
                      className="quiet"
                      disabled={busy}
                      onClick={() => onDecide("rejected")}
                    >
                      Reject relationship
                    </button>
                  ) : null}
                  {selection.connection.origin === "user" ? (
                    <button
                      type="button"
                      className="quiet"
                      disabled={busy}
                      onClick={() => onDecide("reset")}
                    >
                      Reset to automatic
                    </button>
                  ) : null}
                </>
              )}
            </span>
          ) : null}
        </footer>
      </aside>
    </div>
  );
}

export function MatchReviewWorkbench({
  analysisId,
  scopedCompetitorId,
  scopedProfileId,
  focusedRelationshipId,
  onCompetitorSelect,
  onProfileSelect,
  readOnly = false,
  routeBasePath,
}: Readonly<{
  analysisId: string;
  scopedCompetitorId: string | null;
  scopedProfileId: string | null;
  focusedRelationshipId: string | null;
  onCompetitorSelect?: (competitorId: string) => void;
  onProfileSelect?: (profileId: string) => void;
  readOnly?: boolean;
  routeBasePath?: string;
}>) {
  const [review, setReview] = useState<MatchReview | null>(null);
  const [competitorId, setCompetitorId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [benchmarkId, setBenchmarkId] = useState<string | null>(null);
  const [competitorProductId, setCompetitorProductId] = useState<string | null>(
    null,
  );
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [scopeMode, setScopeMode] = useState<ScopeMode>("global");
  const [details, setDetails] = useState<DetailSelection | null>(null);
  const [busy, setBusy] = useState(false);
  const [showRecompute, setShowRecompute] = useState(false);
  const [message, setMessage] = useState("Loading governed match review…");
  const [openedFocus, setOpenedFocus] = useState<string | null>(null);
  const [matchingV2Shadow, setMatchingV2Shadow] =
    useState<MatchingV2ShadowView | null>(null);

  function updateWorkbenchRoute(updates: Record<string, string | null>) {
    if (!routeBasePath) return;
    const url = new URL(window.location.href);
    url.pathname = routeBasePath;
    for (const [key, value] of Object.entries(updates)) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history.replaceState(window.history.state, "", url);
  }

  function workbenchHref(connection?: MatchReviewConnection) {
    const base =
      routeBasePath ?? `/workspace/matches/${encodeURIComponent(analysisId)}`;
    const parameters = new URLSearchParams();
    if (competitorId) parameters.set("competitor", competitorId);
    if (profileId) parameters.set("lens", profileId);
    if (connection) {
      parameters.set(
        "pair",
        connection.relationship_id ||
          connection.id ||
          `${connection.benchmark_product_id}::${connection.competitor_product_id}`,
      );
    }
    return `${base}?${parameters.toString()}`;
  }

  const load = useCallback(async () => {
    const response = await fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/match-review`,
      { cache: "no-store" },
    );
    const body = (await response.json()) as MatchReview & { error?: string };
    if (!response.ok)
      throw new Error(body.error || "Match review is unavailable.");
    setReview(body);
    setCompetitorId((current) => {
      if (
        scopedCompetitorId &&
        body.competitors.some((row) => row.id === scopedCompetitorId)
      )
        return scopedCompetitorId;
      return body.competitors.some((row) => row.id === current)
        ? current
        : body.competitors[0]?.id || "";
    });
    setProfileId((current) => {
      let next: string;
      if (
        scopedProfileId &&
        body.profiles.some((row) => row.id === scopedProfileId)
      )
        next = scopedProfileId;
      else
        next = body.profiles.some((row) => row.id === current)
          ? current
          : body.profiles[0]?.id || "";
      setScopeMode(
        body.profiles.find((profile) => profile.id === next)
          ?.default_scope_mode || "global",
      );
      return next;
    });
    setMessage("");
  }, [analysisId, scopedCompetitorId, scopedProfileId]);

  useEffect(() => {
    // Loading is the external synchronization performed by this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load().catch((error: unknown) =>
      setMessage(
        error instanceof Error ? error.message : "Match review failed to load.",
      ),
    );
  }, [load]);

  useEffect(() => {
    if (!competitorId) return;
    const controller = new AbortController();
    const parameters = new URLSearchParams({
      competitor_retailer_id: competitorId,
      limit: "100",
    });
    fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/matching-v2-shadow?${parameters}`,
      { cache: "no-store", signal: controller.signal },
    )
      .then(async (response) => {
        if (response.status === 404) return null;
        if (!response.ok)
          throw new Error("Matching v2 shadow evidence is unavailable.");
        return (await response.json()) as MatchingV2ShadowView;
      })
      .then((view) => setMatchingV2Shadow(view))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setMatchingV2Shadow(null);
      });
    return () => controller.abort();
  }, [analysisId, competitorId]);

  const scoped = useMemo(
    () =>
      review && competitorId && profileId
        ? scopeMatchReview(review, competitorId, profileId)
        : null,
    [review, competitorId, profileId],
  );
  const productByKey = useMemo(
    () =>
      new Map(
        (review?.products ?? []).map((row) => [
          `${row.retailer_id}:${row.product_id}`,
          row,
        ]),
      ),
    [review],
  );

  const connections = useMemo(() => {
    if (!review || !scoped) return [];
    const needle = query.trim().toLowerCase();
    return rankMatchReviewConnections(
      scoped.connections.filter((connection) => {
        if (status !== "all" && connection.status !== status) return false;
        if (!needle) return true;
        return connectionSearchText(
          connection,
          productByKey.get(
            `${review.benchmark_retailer.id}:${connection.benchmark_product_id}`,
          ),
          productByKey.get(
            `${connection.competitor_retailer_id}:${connection.competitor_product_id}`,
          ),
        ).includes(needle);
      }),
    );
  }, [productByKey, query, review, scoped, status]);

  /* eslint-disable react-hooks/set-state-in-effect -- URL deep links synchronize the governed workbench selection. */
  useEffect(() => {
    if (
      !review ||
      !focusedRelationshipId ||
      openedFocus === focusedRelationshipId
    )
      return;
    const [focusedBenchmarkId, focusedCompetitorId] =
      focusedRelationshipId.split("::", 2);
    const connection = review.connections.find(
      (row) =>
        row.relationship_id === focusedRelationshipId ||
        row.id === focusedRelationshipId ||
        (focusedCompetitorId !== undefined &&
          row.benchmark_product_id === focusedBenchmarkId &&
          row.competitor_product_id === focusedCompetitorId),
    );
    if (!connection) return;
    const nextProfile = connection.eligible_profile_ids.includes(profileId)
      ? profileId
      : connection.source_profile_id;
    setCompetitorId(connection.competitor_retailer_id);
    setProfileId(nextProfile);
    setDetails({
      benchmark: productByKey.get(
        `${review.benchmark_retailer.id}:${connection.benchmark_product_id}`,
      ),
      competitor: productByKey.get(
        `${connection.competitor_retailer_id}:${connection.competitor_product_id}`,
      ),
      connection,
    });
    setOpenedFocus(focusedRelationshipId);
  }, [focusedRelationshipId, openedFocus, productByKey, profileId, review]);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function decide(
    decision: Decision,
    selectedBenchmarkId = benchmarkId,
    selectedCompetitorProductId = competitorProductId,
    replaceConflicts = false,
    connection?: MatchReviewConnection,
  ) {
    if (
      !review ||
      !selectedBenchmarkId ||
      !selectedCompetitorProductId ||
      !profileId
    )
      return;
    setBusy(true);
    setMessage("");
    const scope = await proposedScope(
      analysisId,
      profileId,
      scopeMode,
      connection,
    );
    const body = {
      expected_revision: review.revision,
      competitor_retailer_id: competitorId,
      profile_id: profileId,
      benchmark_product_id: selectedBenchmarkId,
      competitor_product_id: selectedCompetitorProductId,
      decision,
      replace_conflicts: replaceConflicts,
      scope,
    };
    setMessage(
      `${decision === "confirmed" ? "Confirming" : decision === "rejected" ? "Rejecting" : "Resetting"} relationship…`,
    );
    try {
      const response = await fetch(
        `/api/analyses/${encodeURIComponent(analysisId)}/match-review/decisions`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (
        response.status === 409 &&
        decision === "confirmed" &&
        !replaceConflicts
      ) {
        const replaceExisting = window.confirm(
          "One of these products already has a confirmed match. Replace that relationship across its eligible comparison lenses?",
        );
        setBusy(false);
        if (replaceExisting)
          await decide(
            decision,
            selectedBenchmarkId,
            selectedCompetitorProductId,
            true,
            connection,
          );
        return;
      }
      const responseBody = (await response.json()) as {
        error?: string;
        detail?: string | { message?: string };
      };
      if (!response.ok) {
        const detail =
          typeof responseBody.detail === "string"
            ? responseBody.detail
            : responseBody.detail?.message;
        setMessage(
          responseBody.error ||
            detail ||
            "The match decision could not be saved.",
        );
        return;
      }
      setBenchmarkId(null);
      setCompetitorProductId(null);
      setDetails(null);
      await load();
      setMessage(
        "Decision staged in a new immutable revision. The current report has not changed.",
      );
    } catch {
      setMessage(
        "The match decision could not be saved because the service did not return a valid response.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function recompute(applyToFutureRuns: boolean) {
    if (!review || review.revision < 1) return;
    setBusy(true);
    const response = await fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/match-review/recompute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          expected_revision: review.revision,
          apply_to_future_runs: applyToFutureRuns,
        }),
      },
    );
    const body = (await response.json()) as {
      error?: string;
      analysis_run_id?: string;
    };
    setMessage(
      response.ok
        ? `Report re-evaluation queued (${body.analysis_run_id?.slice(0, 8)}…). ${
            applyToFutureRuns
              ? "This revision will also govern subsequent collections."
              : "The policy for subsequent collections was left unchanged."
          } Search, PDP, and AI calls: 0.`
        : body.error || "Reanalysis could not be queued.",
    );
    setBusy(false);
    if (response.ok) {
      setShowRecompute(false);
      await load();
    }
  }

  if (!review || !scoped)
    return (
      <section className="match-review-shell">
        <p className="empty-copy">{message}</p>
      </section>
    );

  const competitorName =
    review.competitors.find((row) => row.id === competitorId)?.name ||
    competitorId;
  const selectedProfile = review.profiles.find((row) => row.id === profileId);
  const unmatchedBenchmark = scoped.unmatchedBenchmarkProducts;
  const unmatchedCompetitor = scoped.unmatchedCompetitorProducts;

  return (
    <section className="match-review-shell">
      <div className="specialist-context-strip">
        <p>
          <strong>Governed product relationships</strong>
          Suggested pairs are the deterministic Product Pack relationships used
          by the current analysis.{" "}
          {readOnly
            ? "This report view is read-only; open the Administration Match Workbench to change governed relationships."
            : "Confirm a pair to lock it, or reject it to remove it from the next governed analysis."}
        </p>
        <div className="match-revision-card">
          <small>Current decision set</small>
          <strong>Revision {review.revision}</strong>
          {readOnly ? (
            <Link className="button secondary" href={workbenchHref()}>
              Open Match Workbench
            </Link>
          ) : (
            <button
              type="button"
              onClick={() => setShowRecompute(true)}
              disabled={busy || review.revision < 1}
            >
              Re-evaluate report
            </button>
          )}
          <span>
            {review.future_application
              ? `Future collections use revision ${review.future_application.revision}`
              : "No revision is applied to future collections"}
          </span>
        </div>
      </div>

      {message ? (
        <p
          className="match-review-message match-review-message-top"
          role="status"
        >
          {message}
        </p>
      ) : null}

      <div className="match-review-toolbar">
        <div
          className="match-retailer-tabs"
          role="tablist"
          aria-label="Competitor retailer"
        >
          {review.competitors.map((retailer) => (
            <button
              type="button"
              role="tab"
              aria-selected={competitorId === retailer.id}
              className={competitorId === retailer.id ? "active" : ""}
              onClick={() => {
                setCompetitorId(retailer.id);
                onCompetitorSelect?.(retailer.id);
                updateWorkbenchRoute({ competitor: retailer.id, pair: null });
                setBenchmarkId(null);
                setCompetitorProductId(null);
              }}
              key={retailer.id}
            >
              {retailer.name}
            </button>
          ))}
        </div>
        <label>
          Comparison lens
          <select
            value={profileId}
            onChange={(event) => {
              setProfileId(event.target.value);
              onProfileSelect?.(event.target.value);
              updateWorkbenchRoute({ lens: event.target.value, pair: null });
              const next = review.profiles.find(
                (profile) => profile.id === event.target.value,
              );
              setScopeMode(next?.default_scope_mode || "global");
              setBenchmarkId(null);
              setCompetitorProductId(null);
            }}
          >
            {review.profiles.map((profile) => (
              <option value={profile.id} key={profile.id}>
                {profile.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Match scope
          <select
            value={scopeMode}
            onChange={(event) => setScopeMode(event.target.value as ScopeMode)}
          >
            <option value="observed_benchmark_product_footprint">
              Primary product footprint
            </option>
            <option value="global">All observed locations</option>
          </select>
        </label>
      </div>

      <div className="match-scope-banner">
        <div>
          <small>Primary retailer</small>
          <strong>{review.benchmark_retailer.name}</strong>
        </div>
        <span>compared with</span>
        <div>
          <small>Competitor</small>
          <strong>{competitorName}</strong>
        </div>
        <p>
          {selectedProfile?.label}. New decisions default to the primary
          product&apos;s observed store footprint, allowing the same competitor
          item to map to different regional primary products only where their
          footprints do not overlap.
        </p>
      </div>

      <div className="match-summary-strip">
        <span>
          <b>{scoped.summary.suggested}</b>
          Pairs awaiting review
        </span>
        <span>
          <b>{scoped.summary.confirmed}</b>
          Confirmed relationships
        </span>
        <span>
          <b>{scoped.summary.unmatched}</b>
          Unmatched products
        </span>
        <span>
          <b>{scoped.summary.rejected}</b>
          Rejected relationships
        </span>
        <span>
          <b>{scoped.summary.ambiguous}</b>
          Ambiguous candidates
        </span>
      </div>

      {matchingV2Shadow ? (
        <MatchingV2ShadowPanel
          view={matchingV2Shadow}
          productByKey={productByKey}
          benchmarkRetailerId={review.benchmark_retailer.id}
          competitorId={competitorId}
        />
      ) : null}

      {scoped.summary.ambiguous ? (
        <section className="match-priority-callout">
          <div>
            <small>Highest-value review queue</small>
            <strong>
              Resolve {scoped.summary.ambiguous} ambiguous one-to-one candidate
              {scoped.summary.ambiguous === 1 ? "" : "s"} first
            </strong>
            <p>
              These candidates are ordered by matched-market breadth, retained
              observations, and then price-gap magnitude. They remain excluded
              from decision-ready product reporting until a reviewer chooses a
              single relationship.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setStatus("ambiguous");
              setQuery("");
            }}
          >
            Review needs-decision pairs
          </button>
        </section>
      ) : null}

      <div className="match-connections">
        <div className="match-connections-head">
          <div>
            <p className="eyebrow">Review queue</p>
            <h3>Suggested and reviewed product pairs</h3>
            <p>
              Ranked by retained search evidence. Select either product to
              inspect PDP identity and matching attributes.
            </p>
          </div>
          <input
            aria-label="Search products"
            placeholder="Search names, brands, or IDs"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div
          className="match-status-tabs"
          role="group"
          aria-label="Match status"
        >
          {(
            [
              ["all", "All"],
              ["suggested", "Suggested"],
              ["confirmed", "Confirmed"],
              ["ambiguous", "Needs decision"],
              ["rejected", "Rejected"],
            ] as const
          ).map(([value, label]) => (
            <button
              type="button"
              className={status === value ? "active" : ""}
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
              key={value}
            >
              {label}
            </button>
          ))}
        </div>

        {connections.map((connection) => {
          const benchmark = productByKey.get(
            `${review.benchmark_retailer.id}:${connection.benchmark_product_id}`,
          );
          const competitor = productByKey.get(
            `${connection.competitor_retailer_id}:${connection.competitor_product_id}`,
          );
          const evidence = evidenceForProfile(connection, profileId);
          const eligibleLabels = connection.eligible_profile_ids
            .map(
              (eligibleId) =>
                review.profiles.find((profile) => profile.id === eligibleId)
                  ?.label || eligibleId,
            )
            .join(" · ");
          return (
            <article
              className={`match-connection-row ${connection.status}`}
              key={`${connection.benchmark_product_id}:${connection.competitor_product_id}`}
            >
              <RelationshipProduct
                product={benchmark}
                retailerName={review.benchmark_retailer.name}
                role="Primary"
                onView={() => setDetails({ benchmark, competitor, connection })}
              />
              <div className="connection-path">
                {connection.status === "ambiguous" ? (
                  <span className="match-priority-badge">Priority review</span>
                ) : null}
                <span className={`match-status-badge ${connection.status}`}>
                  {statusCopy(connection.status)}
                </span>
                <strong>
                  {evidence?.matches ?? 0} observations across{" "}
                  {evidence?.geographies ?? 0} markets
                </strong>
                <p>
                  {gapCopy(
                    evidence?.median_gap,
                    review.benchmark_retailer.name,
                    competitorName,
                    evidence?.price_unit,
                  )}
                </p>
                <small>
                  Price evidence: {evidence?.profile_label ?? profileId} ·{" "}
                  {priceUnitLabel(evidence?.price_unit)}
                </small>
                <small>Eligible lenses: {eligibleLabels || "None"}</small>
                <small className="match-scope-chip">
                  {scopeLabel(connection.scope)}
                </small>
                <button
                  type="button"
                  className="match-why-link"
                  onClick={() =>
                    setDetails({ benchmark, competitor, connection })
                  }
                >
                  Why this match
                </button>
              </div>
              <RelationshipProduct
                product={competitor}
                retailerName={competitorName}
                role="Competitor"
                onView={() => setDetails({ benchmark, competitor, connection })}
              />
              <span className="match-row-actions">
                {readOnly ? (
                  <Link href={workbenchHref(connection)}>
                    Open in Match Workbench
                  </Link>
                ) : (
                  <>
                    {connection.status !== "confirmed" ? (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          decide(
                            "confirmed",
                            connection.benchmark_product_id,
                            connection.competitor_product_id,
                            false,
                            connection,
                          )
                        }
                      >
                        Confirm
                      </button>
                    ) : null}
                    {connection.status !== "rejected" ? (
                      <button
                        type="button"
                        className="quiet"
                        disabled={busy}
                        onClick={() =>
                          decide(
                            "rejected",
                            connection.benchmark_product_id,
                            connection.competitor_product_id,
                            false,
                            connection,
                          )
                        }
                      >
                        Reject
                      </button>
                    ) : null}
                    {connection.origin === "user" ? (
                      <button
                        type="button"
                        className="quiet"
                        disabled={busy}
                        onClick={() =>
                          decide(
                            "reset",
                            connection.benchmark_product_id,
                            connection.competitor_product_id,
                            false,
                            connection,
                          )
                        }
                      >
                        Reset
                      </button>
                    ) : null}
                  </>
                )}
              </span>
            </article>
          );
        })}
        {!connections.length ? (
          <div className="match-empty-state">
            <strong>No relationships match this view.</strong>
            <p>
              Try another status, or use the manual match builder for products
              without an active relationship in this lens.
            </p>
          </div>
        ) : null}
        {scoped.confirmedOutsideProfile.length ? (
          <div className="match-locked-note">
            <strong>
              {scoped.confirmedOutsideProfile.length} confirmed relationship
              {scoped.confirmedOutsideProfile.length === 1
                ? " is"
                : "s are"}{" "}
              locked in another comparison lens.
            </strong>
            <p>
              Those products remain unavailable for a different pairing. Switch
              lenses to inspect or reset the confirmed relationship.
            </p>
          </div>
        ) : null}
      </div>

      <details className="manual-match-section">
        <summary>
          <span>
            <small>Manual matching</small>
            <strong>
              {readOnly
                ? "View products without an active relationship"
                : "Create a relationship from unmatched products"}
            </strong>
          </span>
          <em>
            {unmatchedBenchmark.length} {review.benchmark_retailer.name} ·{" "}
            {unmatchedCompetitor.length} {competitorName}
          </em>
        </summary>
        <p className="manual-match-explainer">
          These lists contain only products without a suggested or confirmed
          relationship for the selected competitor and lens. Their alphabetical
          positions do not imply a pairing.{" "}
          {readOnly
            ? "Open a product for identity details or continue to the Match Workbench to create a relationship."
            : ""}
        </p>
        <div className={`match-builder ${readOnly ? "read-only" : ""}`}>
          <div>
            <header>
              <span>Primary retailer products</span>
              <strong>{review.benchmark_retailer.name}</strong>
            </header>
            <div className="match-product-list">
              {unmatchedBenchmark.map((product) => (
                <MatchBuilderProduct
                  key={product.product_id}
                  product={product}
                  retailerName={review.benchmark_retailer.name}
                  selected={benchmarkId === product.product_id}
                  onSelect={() => setBenchmarkId(product.product_id)}
                  onView={() => setDetails({ benchmark: product })}
                  crossLensMemberships={
                    scoped.crossLensMemberships[
                      `${review.benchmark_retailer.id}:${product.product_id}`
                    ]
                  }
                  onDropProduct={
                    readOnly
                      ? undefined
                      : (productId) => {
                          setBenchmarkId(product.product_id);
                          setCompetitorProductId(productId);
                        }
                  }
                  readOnly={readOnly}
                />
              ))}
              {!unmatchedBenchmark.length ? (
                <p className="empty-copy">
                  All primary products have active relationships.
                </p>
              ) : null}
            </div>
          </div>
          {!readOnly ? (
            <div className="match-builder-center">
              <span className="match-line" />
              <strong>
                {competitorProductId && benchmarkId
                  ? "Ready to connect"
                  : "Select one product on each side"}
              </strong>
              <button
                type="button"
                disabled={busy || !competitorProductId || !benchmarkId}
                onClick={() => decide("confirmed")}
              >
                Confirm relationship
              </button>
              <small>
                One primary match is allowed per overlapping store footprint.
                The same item may support another relationship only where the
                primary-product footprints are disjoint.
              </small>
            </div>
          ) : null}
          <div>
            <header>
              <span>Competitor products</span>
              <strong>{competitorName}</strong>
            </header>
            <div className="match-product-list">
              {unmatchedCompetitor.map((product) => (
                <MatchBuilderProduct
                  key={product.product_id}
                  product={product}
                  retailerName={competitorName}
                  selected={competitorProductId === product.product_id}
                  onSelect={() => setCompetitorProductId(product.product_id)}
                  onView={() => setDetails({ competitor: product })}
                  crossLensMemberships={
                    scoped.crossLensMemberships[
                      `${competitorId}:${product.product_id}`
                    ]
                  }
                  draggable={!readOnly}
                  readOnly={readOnly}
                />
              ))}
              {!unmatchedCompetitor.length ? (
                <p className="empty-copy">
                  All competitor products have active relationships.
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </details>

      {details ? (
        <MatchEvidenceDrawer
          selection={details}
          profileId={profileId}
          benchmarkName={review.benchmark_retailer.name}
          competitorName={competitorName}
          onClose={() => setDetails(null)}
          busy={busy}
          message={message}
          readOnly={readOnly}
          workbenchHref={
            details.connection
              ? workbenchHref(details.connection)
              : workbenchHref()
          }
          onDecide={(decision) => {
            if (!details.connection) return;
            void decide(
              decision,
              details.connection.benchmark_product_id,
              details.connection.competitor_product_id,
              false,
              details.connection,
            );
          }}
        />
      ) : null}
      {!readOnly && showRecompute ? (
        <div
          className="match-drawer-backdrop match-recompute-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setShowRecompute(false);
          }}
        >
          <section
            className="match-recompute-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="match-recompute-title"
          >
            <p className="eyebrow">Explicit re-evaluation</p>
            <h3 id="match-recompute-title">
              How should revision {review.revision} be applied?
            </h3>
            <p>
              Saved decisions are staged and never change a report
              automatically. Re-evaluation uses the existing Search and PDP
              evidence and queues no new provider calls.
            </p>
            <div className="match-recompute-options">
              <button
                type="button"
                disabled={busy}
                onClick={() => recompute(false)}
              >
                <strong>Re-evaluate this report only</strong>
                <span>
                  Leave the policy for subsequent collections unchanged.
                </span>
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => recompute(true)}
              >
                <strong>Re-evaluate and use for future collections</strong>
                <span>
                  Make revision {review.revision} the governed match policy for
                  later collection updates.
                </span>
              </button>
            </div>
            <button
              type="button"
              className="quiet"
              disabled={busy}
              onClick={() => setShowRecompute(false)}
            >
              Cancel
            </button>
          </section>
        </div>
      ) : null}
    </section>
  );
}
