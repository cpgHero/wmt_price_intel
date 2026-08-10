"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  MatchReview,
  MatchReviewConnection,
  MatchReviewProduct,
} from "@/lib/api";
import {
  type CrossLensMembership,
  connectionSearchText,
  evidenceForProfile,
  productDetailRows,
  scopeMatchReview,
} from "@/lib/match-review-model";

type Decision = "confirmed" | "rejected" | "reset";
type StatusFilter = "all" | MatchReviewConnection["status"];

interface DetailSelection {
  benchmark?: MatchReviewProduct;
  competitor?: MatchReviewProduct;
  connection?: MatchReviewConnection;
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

function priceCopy(product: MatchReviewProduct) {
  if (typeof product.price !== "number") return null;
  const role = typeof product.role === "string" ? product.role : "";
  return `${role.startsWith("PDP") ? "PDP reference" : "Matched search median"}: $${product.price.toFixed(2)}`;
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
}: Readonly<{
  product: MatchReviewProduct;
  retailerName: string;
  selected: boolean;
  onSelect: () => void;
  onView: () => void;
  draggable?: boolean;
  onDropProduct?: (productId: string) => void;
  crossLensMemberships?: CrossLensMembership[];
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
        onClick={onSelect}
      >
        <ProductImage product={product} retailerName={retailerName} />
        <span className="match-product-copy">
          <small>{product.brand || retailerName}</small>
          <strong>{product.name}</strong>
          <em>{product.product_id}</em>
          {priceCopy(product) ? <b>{priceCopy(product)}</b> : null}
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
        {priceCopy(product) ? <b>{priceCopy(product)}</b> : null}
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
) {
  if (typeof gap !== "number") return "Price difference unavailable";
  if (Math.abs(gap) < 0.005) return "Typical matched prices are tied";
  const amount = `$${Math.abs(gap).toFixed(2)}`;
  return gap < 0
    ? `${competitorName} is typically ${amount} lower`
    : `${benchmarkName} is typically ${amount} lower`;
}

function ProductEvidencePanel({
  product,
  retailerName,
}: Readonly<{
  product: MatchReviewProduct;
  retailerName: string;
}>) {
  const rows = productDetailRows(product);
  const description =
    typeof product.description === "string" && product.description.trim()
      ? product.description
      : null;
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
      {priceCopy(product) ? (
        <p className="match-price-reference">{priceCopy(product)}</p>
      ) : null}
      <p className="match-product-description">
        {description || "No PDP description is persisted for this product."}
      </p>
      {product.url ? (
        <a href={product.url} target="_blank" rel="noreferrer">
          Open retailer product page ↗
        </a>
      ) : null}
      {rows.length ? (
        <dl className="match-detail-list">
          {rows.slice(0, 24).map((row) => (
            <div key={`${row.section}:${row.label}`}>
              <dt>
                <small>{row.section}</small>
                {row.label}
              </dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="match-detail-empty">
          No additional PDP specifications are persisted for this product.
        </p>
      )}
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
  onDecide,
}: Readonly<{
  selection: DetailSelection;
  profileId: string;
  benchmarkName: string;
  competitorName: string;
  onClose: () => void;
  busy: boolean;
  onDecide: (decision: Decision) => void;
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
              <small>Typical price position</small>
              <strong>
                {gapCopy(evidence?.median_gap, benchmarkName, competitorName)}
              </strong>
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
          <p>
            Store-specific price and location evidence comes from Search. PDP
            evidence is used for product identity, descriptions, specifications,
            URLs, and imagery.
          </p>
          {selection.connection ? (
            <span>
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
}: Readonly<{
  analysisId: string;
  scopedCompetitorId: string | null;
  scopedProfileId: string | null;
  focusedRelationshipId: string | null;
  onCompetitorSelect?: (competitorId: string) => void;
  onProfileSelect?: (profileId: string) => void;
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
  const [details, setDetails] = useState<DetailSelection | null>(null);
  const [busy, setBusy] = useState(false);
  const [showRecompute, setShowRecompute] = useState(false);
  const [message, setMessage] = useState("Loading governed match review…");
  const [openedFocus, setOpenedFocus] = useState<string | null>(null);

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
      if (
        scopedProfileId &&
        body.profiles.some((row) => row.id === scopedProfileId)
      )
        return scopedProfileId;
      return body.profiles.some((row) => row.id === current)
        ? current
        : body.profiles[0]?.id || "";
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
    return scoped.connections.filter((connection) => {
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
    });
  }, [productByKey, query, review, scoped, status]);

  /* eslint-disable react-hooks/set-state-in-effect -- URL deep links synchronize the governed workbench selection. */
  useEffect(() => {
    if (
      !review ||
      !focusedRelationshipId ||
      openedFocus === focusedRelationshipId
    )
      return;
    const connection = review.connections.find(
      (row) =>
        row.relationship_id === focusedRelationshipId ||
        row.id === focusedRelationshipId,
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
    const body = {
      expected_revision: review.revision,
      competitor_retailer_id: competitorId,
      profile_id: profileId,
      benchmark_product_id: selectedBenchmarkId,
      competitor_product_id: selectedCompetitorProductId,
      decision,
      replace_conflicts: replaceConflicts,
    };
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
      setBusy(false);
      return;
    }
    setBenchmarkId(null);
    setCompetitorProductId(null);
    setDetails(null);
    await load();
    setMessage(
      "Decision staged in a new immutable revision. The current report has not changed.",
    );
    setBusy(false);
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
      <div className="match-review-intro">
        <div>
          <p className="eyebrow">Governed one-to-one matching</p>
          <h2>Review exactly which products should be compared</h2>
          <p>
            Suggested pairs are the deterministic Product Pack relationships
            used by the current automated analysis. Confirm a pair to lock it,
            or reject it to remove it from the next governed analysis.
          </p>
        </div>
        <div className="match-revision-card">
          <small>Current decision set</small>
          <strong>Revision {review.revision}</strong>
          <button
            type="button"
            onClick={() => setShowRecompute(true)}
            disabled={busy || review.revision < 1}
          >
            Re-evaluate report
          </button>
          <span>
            {review.future_application
              ? `Future collections use revision ${review.future_application.revision}`
              : "No revision is applied to future collections"}
          </span>
        </div>
      </div>

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
          {selectedProfile?.label}. One approval governs this product
          relationship across every lens where Product Pack evidence says it is
          eligible.
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
                  )}
                </p>
                <small>{eligibleLabels}</small>
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
                {connection.status !== "confirmed" ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      decide(
                        "confirmed",
                        connection.benchmark_product_id,
                        connection.competitor_product_id,
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
                      )
                    }
                  >
                    Reset
                  </button>
                ) : null}
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
            <strong>Create a relationship from unmatched products</strong>
          </span>
          <em>
            {unmatchedBenchmark.length} {review.benchmark_retailer.name} ·{" "}
            {unmatchedCompetitor.length} {competitorName}
          </em>
        </summary>
        <p className="manual-match-explainer">
          These lists contain only products without a suggested or confirmed
          relationship for the selected competitor and lens. Their alphabetical
          positions do not imply a pairing.
        </p>
        <div className="match-builder">
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
                  onDropProduct={(productId) => {
                    setBenchmarkId(product.product_id);
                    setCompetitorProductId(productId);
                  }}
                />
              ))}
              {!unmatchedBenchmark.length ? (
                <p className="empty-copy">
                  All primary products have active relationships.
                </p>
              ) : null}
            </div>
          </div>
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
              A product can belong to only one confirmed pair with this
              competitor.
            </small>
          </div>
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
                  draggable
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

      {message ? (
        <p className="match-review-message" role="status">
          {message}
        </p>
      ) : null}
      {details ? (
        <MatchEvidenceDrawer
          selection={details}
          profileId={profileId}
          benchmarkName={review.benchmark_retailer.name}
          competitorName={competitorName}
          onClose={() => setDetails(null)}
          busy={busy}
          onDecide={(decision) => {
            if (!details.connection) return;
            void decide(
              decision,
              details.connection.benchmark_product_id,
              details.connection.competitor_product_id,
            );
          }}
        />
      ) : null}
      {showRecompute ? (
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
