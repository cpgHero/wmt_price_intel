"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  MatchReview,
  MatchReviewConnection,
  MatchReviewProduct,
} from "@/lib/api";

type Decision = "confirmed" | "rejected" | "reset";

function ProductCard({
  product,
  selected,
  onSelect,
  draggable = false,
  onDropProduct,
}: Readonly<{
  product: MatchReviewProduct;
  selected: boolean;
  onSelect: () => void;
  draggable?: boolean;
  onDropProduct?: (productId: string) => void;
}>) {
  return (
    <button
      type="button"
      className={`match-product-card ${selected ? "selected" : ""}`}
      onClick={onSelect}
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
      <span className="match-product-image">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt="" />
        ) : (
          <b>{product.name.slice(0, 1)}</b>
        )}
      </span>
      <span>
        <small>{product.brand || product.retailer_id}</small>
        <strong>{product.name}</strong>
        <em>{product.product_id}</em>
      </span>
      {typeof product.price === "number" ? (
        <b>${product.price.toFixed(2)}</b>
      ) : null}
    </button>
  );
}

function statusCopy(status: MatchReviewConnection["status"]) {
  if (status === "confirmed") return "User confirmed";
  if (status === "rejected") return "User rejected";
  return "Suggested by analysis";
}

export function MatchReviewWorkbench({
  analysisId,
  scopedCompetitorId,
}: Readonly<{ analysisId: string; scopedCompetitorId: string | null }>) {
  const [review, setReview] = useState<MatchReview | null>(null);
  const [competitorId, setCompetitorId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [benchmarkId, setBenchmarkId] = useState<string | null>(null);
  const [competitorProductId, setCompetitorProductId] = useState<string | null>(
    null,
  );
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Loading governed match review…");

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
    setProfileId((current) =>
      body.profiles.some((row) => row.id === current)
        ? current
        : body.profiles[0]?.id || "",
    );
    setMessage("");
  }, [analysisId, scopedCompetitorId]);

  useEffect(() => {
    // Loading is the external synchronization performed by this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load().catch((error: unknown) =>
      setMessage(
        error instanceof Error ? error.message : "Match review failed to load.",
      ),
    );
  }, [load]);

  const benchmarkProducts = useMemo(
    () =>
      (review?.products ?? []).filter(
        (row) => row.retailer_id === review?.benchmark_retailer.id,
      ),
    [review],
  );
  const competitorProducts = useMemo(
    () =>
      (review?.products ?? []).filter(
        (row) => row.retailer_id === competitorId,
      ),
    [review, competitorId],
  );
  const connections = useMemo(
    () =>
      (review?.connections ?? []).filter(
        (row) =>
          row.competitor_retailer_id === competitorId &&
          row.profile_id === profileId &&
          (status === "all" || row.status === status) &&
          (!query ||
            `${row.benchmark_product_id} ${row.competitor_product_id}`
              .toLowerCase()
              .includes(query.toLowerCase())),
      ),
    [review, competitorId, profileId, query, status],
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

  async function decide(
    decision: Decision,
    benchmarkProductId = benchmarkId,
    selectedCompetitorProductId = competitorProductId,
    replaceConflicts = false,
  ) {
    if (!review || !benchmarkProductId || !selectedCompetitorProductId) return;
    setBusy(true);
    setMessage("");
    const body = {
      expected_revision: review.revision,
      competitor_retailer_id: competitorId,
      profile_id: profileId,
      benchmark_product_id: benchmarkProductId,
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
      const replace = window.confirm(
        "One of these products already has a confirmed match. Replace that match with this one?",
      );
      setBusy(false);
      if (replace)
        await decide(
          decision,
          benchmarkProductId,
          selectedCompetitorProductId,
          true,
        );
      return;
    }
    const responseBody = (await response.json()) as { error?: string };
    if (!response.ok) {
      setMessage(
        responseBody.error || "The match decision could not be saved.",
      );
      setBusy(false);
      return;
    }
    setBenchmarkId(null);
    setCompetitorProductId(null);
    await load();
    setMessage("Decision saved as a new immutable revision.");
    setBusy(false);
  }

  async function recompute() {
    if (!review || review.revision < 1) return;
    setBusy(true);
    const response = await fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/match-review/recompute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_revision: review.revision }),
      },
    );
    const body = (await response.json()) as {
      error?: string;
      analysis_run_id?: string;
    };
    setMessage(
      response.ok
        ? `Reanalysis queued (${body.analysis_run_id?.slice(0, 8)}…). Search and PDP calls: 0.`
        : body.error || "Reanalysis could not be queued.",
    );
    setBusy(false);
  }

  if (!review)
    return (
      <section className="match-review-shell">
        <p className="empty-copy">{message}</p>
      </section>
    );

  const competitorName =
    review.competitors.find((row) => row.id === competitorId)?.name ||
    competitorId;
  return (
    <section className="match-review-shell">
      <div className="match-review-intro">
        <div>
          <p className="eyebrow">Governed one-to-one matching</p>
          <h2>Confirm exactly which products should be compared</h2>
          <p>
            Search evidence remains authoritative for store-level price.
            Confirmed and rejected relationships persist across later runs of
            this Product Pack; every edit creates an auditable revision.
          </p>
        </div>
        <div className="match-revision-card">
          <small>Current decision set</small>
          <strong>Revision {review.revision}</strong>
          <button
            type="button"
            onClick={recompute}
            disabled={busy || review.revision < 1}
          >
            Update analysis
          </button>
          <span>No Search or PDP calls</span>
        </div>
      </div>

      <div className="match-summary-strip">
        <span>
          <b>{review.summary.suggested}</b> suggested
        </span>
        <span>
          <b>{review.summary.confirmed}</b> confirmed
        </span>
        <span>
          <b>{review.summary.rejected}</b> rejected
        </span>
        <span>
          <b>{review.summary.unmatched}</b> unmatched products
        </span>
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
              onClick={() => setCompetitorId(retailer.id)}
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
            onChange={(event) => setProfileId(event.target.value)}
          >
            {review.profiles.map((profile) => (
              <option value={profile.id} key={profile.id}>
                {profile.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="match-builder">
        <div>
          <header>
            <span>Competitor products</span>
            <strong>{competitorName}</strong>
          </header>
          <div className="match-product-list">
            {competitorProducts.map((product) => (
              <ProductCard
                key={product.product_id}
                product={product}
                selected={competitorProductId === product.product_id}
                onSelect={() => setCompetitorProductId(product.product_id)}
                draggable
              />
            ))}
          </div>
        </div>
        <div className="match-builder-center">
          <span className="match-line" />
          <strong>
            {competitorProductId && benchmarkId
              ? "Ready to connect"
              : "Select two products"}
          </strong>
          <button
            type="button"
            disabled={busy || !competitorProductId || !benchmarkId}
            onClick={() => decide("confirmed")}
          >
            Confirm match
          </button>
          <small>
            One product on either side can belong to only one confirmed pair.
          </small>
        </div>
        <div>
          <header>
            <span>Reference products</span>
            <strong>{review.benchmark_retailer.name}</strong>
          </header>
          <div className="match-product-list">
            {benchmarkProducts.map((product) => (
              <ProductCard
                key={product.product_id}
                product={product}
                selected={benchmarkId === product.product_id}
                onSelect={() => setBenchmarkId(product.product_id)}
                onDropProduct={(productId) => {
                  setBenchmarkId(product.product_id);
                  setCompetitorProductId(productId);
                }}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="match-connections">
        <div className="match-connections-head">
          <div>
            <h3>Current relationships</h3>
            <p>Review suggestions, user decisions, and evidence volume.</p>
          </div>
          <input
            aria-label="Search product IDs"
            placeholder="Search product IDs"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <select
            aria-label="Filter match status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="all">All statuses</option>
            <option value="suggested">Suggested</option>
            <option value="confirmed">Confirmed</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
        {connections.map((connection) => {
          const benchmark = productByKey.get(
            `${review.benchmark_retailer.id}:${connection.benchmark_product_id}`,
          );
          const competitor = productByKey.get(
            `${connection.competitor_retailer_id}:${connection.competitor_product_id}`,
          );
          return (
            <article
              className={`match-connection-row ${connection.status}`}
              key={`${connection.profile_id}:${connection.benchmark_product_id}:${connection.competitor_product_id}`}
            >
              <span>
                <strong>
                  {competitor?.name || connection.competitor_product_id}
                </strong>
                <small>{connection.competitor_product_id}</small>
              </span>
              <span className="connection-path">
                <i />
                <b>{statusCopy(connection.status)}</b>
                <em>{connection.geographies ?? 0} markets</em>
              </span>
              <span>
                <strong>
                  {benchmark?.name || connection.benchmark_product_id}
                </strong>
                <small>{connection.benchmark_product_id}</small>
              </span>
              <span className="match-row-actions">
                {connection.status !== "confirmed" ? (
                  <button
                    type="button"
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
          <p className="empty-copy">No relationships match this filter.</p>
        ) : null}
      </div>
      {message ? (
        <p className="match-review-message" role="status">
          {message}
        </p>
      ) : null}
    </section>
  );
}
