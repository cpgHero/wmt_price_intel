"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { BrandWorkbench, BrandWorkbenchBrand } from "@/lib/api";

type BrandRole = BrandWorkbenchBrand["role"];
type BrandDecision = "confirmed" | "rejected" | "reset";
type BrandStatus = "all" | BrandWorkbenchBrand["status"];

const roleLabels: Record<BrandRole, string> = {
  private_label: "Private label",
  regional: "Regional brand",
  national: "National brand",
  unclassified: "Unclassified",
};

const distributionLabels: Record<
  BrandWorkbenchBrand["distribution_tier"],
  string
> = {
  unknown: "Distribution pending",
  single_location: "Single location",
  concentrated: "Concentrated footprint",
  multi_market: "Multi-market footprint",
  broad: "Broad footprint",
};

function statusLabel(status: BrandWorkbenchBrand["status"]) {
  if (status === "confirmed") return "Human confirmed";
  if (status === "rejected") return "Classification rejected";
  if (status === "suggested") return "Product Pack suggestion";
  return "Needs classification";
}

function originLabel(origin: BrandWorkbenchBrand["origin"]) {
  if (origin === "product_pack") return "Product Pack";
  if (origin === "user") return "Human governance";
  return "Observed data";
}

function candidateRationale(
  rationale: BrandWorkbenchBrand["candidate_matches"][number]["rationale"],
) {
  if (rationale === "quarantined_alias_conflict")
    return "The approved foundation contains a known alias conflict; choose the correct identity.";
  if (rationale === "same_core_name")
    return "The observed and canonical names share the same core brand name.";
  if (rationale === "name_prefix")
    return "One name is a qualified form of the other.";
  if (rationale === "token_overlap")
    return "The names share a strong set of brand-name terms.";
  return "The normalized names are similar enough to warrant human review.";
}

export function BrandWorkbenchPanel({
  analysisId,
  readOnly = false,
  scopedRetailerId,
  focusedBrand,
  routeBasePath,
}: Readonly<{
  analysisId: string;
  readOnly?: boolean;
  scopedRetailerId?: string | null;
  focusedBrand?: string | null;
  routeBasePath?: string;
}>) {
  const [workbench, setWorkbench] = useState<BrandWorkbench | null>(null);
  const [retailerId, setRetailerId] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<BrandStatus>("all");
  const [roles, setRoles] = useState<Record<string, BrandRole>>({});
  const [canonicalSelections, setCanonicalSelections] = useState<
    Record<string, string>
  >({});
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState("Loading brand governance…");
  const [showRecompute, setShowRecompute] = useState(false);

  const load = useCallback(async () => {
    const response = await fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/brand-workbench`,
      { cache: "no-store" },
    );
    const body = (await response.json()) as BrandWorkbench & { error?: string };
    if (!response.ok)
      throw new Error(body.error || "Brand governance is unavailable.");
    setWorkbench(body);
    setRetailerId((current) =>
      scopedRetailerId &&
      body.retailers.some((row) => row.id === scopedRetailerId)
        ? scopedRetailerId
        : body.retailers.some((row) => row.id === current)
          ? current
          : body.retailers[0]?.id || "",
    );
    setRoles(
      Object.fromEntries(
        body.brands.map((brand) => [
          `${brand.retailer_id}:${brand.normalized_brand}`,
          brand.role,
        ]),
      ),
    );
    setCanonicalSelections(
      Object.fromEntries(
        body.brands.map((brand) => {
          const key = `${brand.retailer_id}:${brand.normalized_brand}`;
          const selected =
            brand.candidate_status === "candidate"
              ? brand.candidate_matches[0]?.canonical_brand_id || ""
              : "";
          return [key, selected];
        }),
      ),
    );
    setMessage("");
  }, [analysisId, scopedRetailerId]);

  function updateWorkbenchRoute(retailer: string) {
    if (!routeBasePath) return;
    const url = new URL(window.location.href);
    url.pathname = routeBasePath;
    url.searchParams.set("retailer", retailer);
    url.searchParams.delete("brand");
    window.history.replaceState(window.history.state, "", url);
  }

  function brandWorkbenchHref(brand?: BrandWorkbenchBrand) {
    const base =
      routeBasePath ?? `/workspace/brands/${encodeURIComponent(analysisId)}`;
    const parameters = new URLSearchParams();
    if (retailerId) parameters.set("retailer", retailerId);
    if (brand) parameters.set("brand", brand.normalized_brand);
    return `${base}?${parameters.toString()}`;
  }

  useEffect(() => {
    // Loading is the external synchronization performed by this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load().catch((error: unknown) =>
      setMessage(
        error instanceof Error
          ? error.message
          : "Brand governance failed to load.",
      ),
    );
  }, [load]);

  const retailerBrands = useMemo(
    () =>
      (workbench?.brands ?? []).filter(
        (brand) => brand.retailer_id === retailerId,
      ),
    [retailerId, workbench],
  );
  const visibleBrands = useMemo(() => {
    const needle = (query || focusedBrand || "").trim().toLocaleLowerCase();
    return retailerBrands.filter((brand) => {
      if (status !== "all" && brand.status !== status) return false;
      if (!needle) return true;
      return [
        brand.display_brand,
        brand.canonical_brand_name || "",
        ...brand.candidate_matches.map((candidate) =>
          [candidate.canonical_brand_name, candidate.role].join(" "),
        ),
        roleLabels[brand.role],
        distributionLabels[brand.distribution_tier],
        ...brand.product_examples.map((product) => product.name),
      ]
        .join(" ")
        .toLocaleLowerCase()
        .includes(needle);
    });
  }, [focusedBrand, query, retailerBrands, status]);
  const retailerName =
    workbench?.retailers.find((retailer) => retailer.id === retailerId)?.name ||
    retailerId;
  const retailerSummary = useMemo(
    () => ({
      total: retailerBrands.length,
      privateLabel: retailerBrands.filter(
        (brand) =>
          brand.role === "private_label" && brand.status !== "rejected",
      ).length,
      regional: retailerBrands.filter(
        (brand) => brand.role === "regional" && brand.status !== "rejected",
      ).length,
      needsReview: retailerBrands.filter((brand) =>
        ["suggested", "unclassified"].includes(brand.status),
      ).length,
      candidateMatches: retailerBrands.filter(
        (brand) => brand.candidate_status === "candidate",
      ).length,
    }),
    [retailerBrands],
  );

  async function decide(
    brand: BrandWorkbenchBrand,
    decision: BrandDecision,
    canonicalBrandId?: string,
  ) {
    if (!workbench) return;
    const key = `${brand.retailer_id}:${brand.normalized_brand}`;
    setBusyKey(key);
    setMessage("");
    const candidate = brand.candidate_matches.find(
      (value) => value.canonical_brand_id === canonicalBrandId,
    );
    const response = await fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/brand-workbench/decisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          expected_revision: workbench.revision,
          retailer_id: brand.retailer_id,
          normalized_brand: brand.normalized_brand,
          role: candidate?.role || roles[key] || brand.role,
          decision,
          canonical_brand_id: canonicalBrandId || null,
        }),
      },
    );
    const body = (await response.json()) as {
      error?: string;
      detail?: string;
    };
    if (!response.ok) {
      setMessage(
        body.error || body.detail || "The brand decision was not saved.",
      );
      setBusyKey(null);
      return;
    }
    await load();
    setMessage(
      "Brand decision staged in a new immutable revision. The current report has not changed.",
    );
    setBusyKey(null);
  }

  async function recompute(applyToFutureRuns: boolean) {
    if (!workbench || workbench.revision < 1) return;
    setBusyKey("recompute");
    const response = await fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/brand-workbench/recompute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          expected_revision: workbench.revision,
          apply_to_future_runs: applyToFutureRuns,
        }),
      },
    );
    const body = (await response.json()) as {
      error?: string;
      detail?: string;
      analysis_run_id?: string;
    };
    setMessage(
      response.ok
        ? `Report re-evaluation queued (${body.analysis_run_id?.slice(0, 8)}…). ${
            applyToFutureRuns
              ? "This brand revision will also govern later collections."
              : "Future collection policy was not changed."
          } Search, PDP, and AI calls: 0.`
        : body.error || body.detail || "Reanalysis could not be queued.",
    );
    setBusyKey(null);
    if (response.ok) {
      setShowRecompute(false);
      await load();
    }
  }

  if (!workbench)
    return (
      <section className="brand-workbench-shell">
        <p className="empty-copy">{message}</p>
      </section>
    );

  return (
    <section className="brand-workbench-shell">
      <div className="specialist-context-strip">
        <p>
          <strong>Human-governed brand intelligence</strong>
          Product Packs propose private-label, regional, and national brand
          roles. Search evidence determines where each brand is actually
          distributed; a broad footprint alone never proves a national role.{" "}
          {readOnly
            ? "This report view is read-only; open the Administration Brand Workbench to govern classifications."
            : ""}
        </p>
        <div className="brand-revision-card">
          <small>Current decision set</small>
          <strong>Revision {workbench.revision}</strong>
          {readOnly ? (
            <Link className="button secondary" href={brandWorkbenchHref()}>
              Open Brand Workbench
            </Link>
          ) : (
            <button
              type="button"
              disabled={busyKey !== null || workbench.revision < 1}
              onClick={() => setShowRecompute(true)}
            >
              Re-evaluate report
            </button>
          )}
          <span>
            {workbench.future_application
              ? `Future collections use revision ${workbench.future_application.revision}`
              : "No revision is applied to future collections"}
          </span>
        </div>
      </div>

      {message ? (
        <p className="brand-workbench-message" role="status">
          {message}
        </p>
      ) : null}

      <div className="brand-workbench-toolbar">
        <div
          className="brand-retailer-tabs"
          role="tablist"
          aria-label="Retailer"
        >
          {workbench.retailers.map((retailer) => (
            <button
              type="button"
              role="tab"
              aria-selected={retailer.id === retailerId}
              className={retailer.id === retailerId ? "active" : ""}
              onClick={() => {
                setRetailerId(retailer.id);
                updateWorkbenchRoute(retailer.id);
              }}
              key={retailer.id}
            >
              {retailer.name}
            </button>
          ))}
        </div>
        <input
          aria-label="Search brands"
          placeholder="Search brands or products"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <div className="brand-summary-strip">
        <span>
          <b>{retailerSummary.total}</b>
          Observed brands at {retailerName}
        </span>
        <span>
          <b>{retailerSummary.privateLabel}</b>
          Private-label portfolios
        </span>
        <span>
          <b>{retailerSummary.regional}</b>
          Regional brands
        </span>
        <span className={retailerSummary.needsReview ? "review" : ""}>
          <b>{retailerSummary.needsReview}</b>
          Classifications to review
        </span>
        <span className={retailerSummary.candidateMatches ? "ready" : ""}>
          <b>{retailerSummary.candidateMatches}</b>
          Foundation matches ready
        </span>
      </div>

      <div className="brand-status-tabs" role="group" aria-label="Brand status">
        {(
          [
            ["all", "All"],
            ["unclassified", "Needs classification"],
            ["suggested", "Suggested"],
            ["confirmed", "Confirmed"],
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

      <div className="brand-card-grid">
        {visibleBrands.map((brand) => {
          const key = `${brand.retailer_id}:${brand.normalized_brand}`;
          const selectedCandidate = brand.candidate_matches.find(
            (candidate) =>
              candidate.canonical_brand_id === canonicalSelections[key],
          );
          return (
            <article className={`brand-card ${brand.status}`} key={key}>
              <header>
                <div className="brand-product-images">
                  {brand.product_examples.slice(0, 3).map((product) => (
                    <span key={product.product_id} title={product.name}>
                      {product.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={product.image_url} alt="" />
                      ) : (
                        <b>{brand.display_brand.slice(0, 1)}</b>
                      )}
                    </span>
                  ))}
                  {!brand.product_examples.length ? (
                    <span className="empty">
                      <b>{brand.display_brand.slice(0, 1)}</b>
                    </span>
                  ) : null}
                </div>
                <div>
                  <small>{statusLabel(brand.status)}</small>
                  <h3>{brand.display_brand}</h3>
                  <p>{originLabel(brand.origin)} classification</p>
                </div>
              </header>

              <div className="brand-evidence-grid">
                <span>
                  <b>{brand.observed_products.toLocaleString()}</b>
                  products
                </span>
                <span>
                  <b>
                    {(brand.distribution_evidence === "search_brand_field"
                      ? brand.observed_locations
                      : brand.observed_zipcodes
                    ).toLocaleString()}
                  </b>
                  {brand.distribution_evidence === "search_brand_field"
                    ? "locations"
                    : brand.observed_zipcodes === 1
                      ? "matched ZIP"
                      : "matched ZIPs"}
                </span>
                <span>
                  <b>
                    {brand.distribution_evidence === "search_brand_field"
                      ? brand.observed_zipcodes.toLocaleString()
                      : "PDP + Search"}
                  </b>
                  {brand.distribution_evidence === "search_brand_field"
                    ? "ZIPs"
                    : "evidence"}
                </span>
              </div>
              <div className="brand-footprint">
                <span>
                  <b>{distributionLabels[brand.distribution_tier]}</b>
                  <em>
                    {brand.distribution_evidence === "search_brand_field"
                      ? `${(brand.location_share * 100).toFixed(1)}% of observed retailer locations`
                      : brand.distribution_evidence ===
                          "pdp_identity_joined_to_matched_search"
                        ? `At least ${brand.observed_zipcodes.toLocaleString()} matched ZIP${brand.observed_zipcodes === 1 ? "" : "s"}; full footprint will refine on the next analysis`
                        : "PDP identity is available; Search footprint is not resolved in this publication"}
                  </em>
                </span>
                <i>
                  <b
                    style={{
                      width: `${brand.location_share ? Math.max(2, brand.location_share * 100) : 0}%`,
                    }}
                  />
                </i>
              </div>

              {brand.product_examples.length ? (
                <ul className="brand-product-examples">
                  {brand.product_examples.slice(0, 3).map((product) => (
                    <li key={product.product_id}>{product.name}</li>
                  ))}
                </ul>
              ) : (
                <p className="brand-no-pdp">
                  No PDP image is persisted; Search distribution evidence is
                  still available.
                </p>
              )}

              {brand.candidate_matches.length ? (
                <div
                  className={`brand-candidate-panel ${brand.candidate_status}`}
                >
                  <small>
                    {brand.candidate_status === "ambiguous"
                      ? "Identity needs a choice"
                      : "Canonical match candidate"}
                  </small>
                  <label>
                    Approved Brand Foundation identity
                    <select
                      value={canonicalSelections[key] || ""}
                      disabled={readOnly}
                      onChange={(event) =>
                        setCanonicalSelections((current) => ({
                          ...current,
                          [key]: event.target.value,
                        }))
                      }
                    >
                      <option value="">Select a canonical brand</option>
                      {brand.candidate_matches.map((candidate) => (
                        <option
                          value={candidate.canonical_brand_id}
                          key={candidate.canonical_brand_id}
                        >
                          {candidate.canonical_brand_name} ·{" "}
                          {candidate.confidence_score}%
                        </option>
                      ))}
                    </select>
                  </label>
                  {selectedCandidate ? (
                    <div>
                      <strong>{selectedCandidate.canonical_brand_name}</strong>
                      <span>
                        {roleLabels[selectedCandidate.role]} ·{" "}
                        {selectedCandidate.brand_bucket} ·{" "}
                        {selectedCandidate.confidence_score}% name confidence
                      </span>
                      <p>{candidateRationale(selectedCandidate.rationale)}</p>
                      {!readOnly ? (
                        <button
                          type="button"
                          disabled={busyKey !== null}
                          onClick={() =>
                            void decide(
                              brand,
                              "confirmed",
                              selectedCandidate.canonical_brand_id,
                            )
                          }
                        >
                          Confirm canonical match
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <p>
                      Review the candidates and select the identity supported by
                      the product evidence. No mapping is applied automatically.
                    </p>
                  )}
                </div>
              ) : brand.canonical_brand_name ? (
                <div
                  className={`brand-canonical-resolution ${brand.candidate_status}`}
                >
                  <small>
                    {brand.candidate_status === "governed"
                      ? "Human-governed canonical identity"
                      : "Resolved by Brand Foundation"}
                  </small>
                  <strong>{brand.canonical_brand_name}</strong>
                  <span>{roleLabels[brand.role]}</span>
                </div>
              ) : null}

              <footer className={readOnly ? "read-only" : undefined}>
                {readOnly ? (
                  <Link
                    className="button secondary"
                    href={brandWorkbenchHref(brand)}
                  >
                    Open in Brand Workbench
                  </Link>
                ) : (
                  <>
                    <label>
                      Classify without canonical mapping
                      <select
                        value={roles[key] || brand.role}
                        onChange={(event) =>
                          setRoles((current) => ({
                            ...current,
                            [key]: event.target.value as BrandRole,
                          }))
                        }
                      >
                        {Object.entries(roleLabels).map(([value, label]) => (
                          <option value={value} key={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span>
                      <button
                        type="button"
                        disabled={busyKey !== null}
                        onClick={() => void decide(brand, "confirmed")}
                      >
                        Confirm role only
                      </button>
                      <button
                        type="button"
                        className="quiet"
                        disabled={busyKey !== null}
                        onClick={() => void decide(brand, "rejected")}
                      >
                        Reject
                      </button>
                      {brand.origin === "user" ? (
                        <button
                          type="button"
                          className="quiet"
                          disabled={busyKey !== null}
                          onClick={() => void decide(brand, "reset")}
                        >
                          Reset
                        </button>
                      ) : null}
                    </span>
                  </>
                )}
              </footer>
            </article>
          );
        })}
      </div>
      {!visibleBrands.length ? (
        <div className="brand-empty-state">
          <strong>No brands match this view.</strong>
          <p>Try another retailer, status, or search phrase.</p>
        </div>
      ) : null}

      <p className="brand-authority-note">
        Price and store distribution remain authoritative from Search. PDP
        enrichment supplies identity, descriptions, specifications, URLs, and
        imagery. Role changes are staged until a user explicitly re-evaluates.
      </p>

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
            aria-labelledby="brand-recompute-title"
          >
            <p className="eyebrow">Explicit re-evaluation</p>
            <h3 id="brand-recompute-title">
              How should brand revision {workbench.revision} be applied?
            </h3>
            <p>
              Saved classifications are staged and never change a report
              automatically. Re-evaluation reuses persisted evidence and queues
              no provider calls.
            </p>
            <div className="match-recompute-options">
              <button
                type="button"
                disabled={busyKey !== null}
                onClick={() => void recompute(false)}
              >
                <strong>Re-evaluate this report only</strong>
                <span>Leave later collection policy unchanged.</span>
              </button>
              <button
                type="button"
                disabled={busyKey !== null}
                onClick={() => void recompute(true)}
              >
                <strong>Re-evaluate and govern future collections</strong>
                <span>
                  Apply revision {workbench.revision} to later updates.
                </span>
              </button>
            </div>
            <button
              type="button"
              className="quiet"
              disabled={busyKey !== null}
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
