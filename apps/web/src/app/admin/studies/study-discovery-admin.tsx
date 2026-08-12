"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

interface AdminSession {
  configured: boolean;
  authenticated: boolean;
}

interface RetailerOption {
  id: string;
  display_name: string;
  credits_per_page: number;
}

interface CollectionOptions {
  retailers: RetailerOption[];
}

interface Approval {
  status: "not_requested" | "estimated" | "approved" | "consumed";
  maximum_cost: number | null;
  unit: "credits" | "usd" | null;
}

interface Study {
  id: string;
  name: string;
  status: string;
  intake: {
    benchmark_retailer_id: string;
    competitor_retailer_ids: string[];
    category_context: string;
    max_search_pages: number;
  };
  query_plan: {
    keyword: string;
    target_terms: string[];
    exclusion_terms: string[];
    revision: number;
  };
  query_plan_checksum: string;
  approval_state: { search: Approval; pdp: Approval; ai: Approval };
  geography_resolution_id: string | null;
  search_scope_estimate_id: string | null;
  collection_run_id: string | null;
  pdp_estimate: {
    eligible_products: number;
    planned_calls: number;
    estimated_credits: number;
    invalid_candidates: unknown[];
    policy: string;
  } | null;
  pdp_plan_checksum: string | null;
  pdp_run_id: string | null;
  product_pack_draft_id: string | null;
  profile_summary: {
    raw_observations?: number;
    unique_products?: number;
    provisionally_admitted_products?: number;
    excluded_products?: number;
    review_required_products?: number;
    unknown_brands?: number;
    price_variant_contexts?: number;
    pdp_contexts?: number;
  };
  last_error: string | null;
  updated_at: string;
}

interface StudyProduct {
  retailer_id: string;
  retailer_product_id: string;
  title: string;
  brand: string | null;
  image_url: string | null;
  admission_status: string;
  admission_reason: string;
  observation_count: number;
  store_count: number;
  zipcode_count: number;
  price_min: number | null;
  price_max: number | null;
  price_contexts: unknown[];
  brand_resolution: { status?: string; role?: string };
}

interface PdpAuditCall {
  retailer_id: string;
  retailer_product_id: string;
  product_name: string;
  status: string;
  http_status: number | null;
  billable_credits: number;
  request_context: {
    zipcode?: string | null;
    store?: string | null;
    fulfillment_type?: string | null;
  };
  error: string | null;
}

interface PdpAudit {
  status: string;
  max_credits: number;
  planned_credits: number;
  actual_credits: number;
  planned_calls: number;
  succeeded_calls: number;
  failed_calls: number;
  http_status_counts: Record<string, number>;
  calls: PdpAuditCall[];
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  const body = (await response.json()) as T & {
    error?: string;
    detail?: string;
  };
  if (!response.ok) {
    throw new Error(
      body.error ?? body.detail ?? `Request failed (${response.status})`,
    );
  }
  return body;
}

const STATUS_COPY: Record<string, string> = {
  query_review:
    "Review the proposed query before estimating any paid Search calls.",
  search_estimated:
    "Search cost is estimated and waiting for explicit approval.",
  collecting: "The approved Search sample is being collected.",
  profiling:
    "Search results are being deduplicated and screened for category fit.",
  profile_ready:
    "The candidate population is ready for review and PDP planning.",
  pdp_estimated: "PDP cost is estimated and waiting for explicit approval.",
  enriching: "Approved unique products and price variants are being enriched.",
  draft_ready: "Evidence is ready in Product Pack authoring.",
  failed: "The workflow stopped after a recorded error.",
};

function splitTerms(value: string): string[] {
  return [
    ...new Set(
      value
        .split(/[,\n]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ];
}

function displayDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function metric(value: number | undefined): string {
  return new Intl.NumberFormat("en-US").format(value ?? 0);
}

export function StudyDiscoveryAdmin() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [password, setPassword] = useState("");
  const [studies, setStudies] = useState<Study[]>([]);
  const [retailers, setRetailers] = useState<RetailerOption[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [products, setProducts] = useState<StudyProduct[]>([]);
  const [pdpAudit, setPdpAudit] = useState<PdpAudit | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [categoryContext, setCategoryContext] = useState("");
  const [inclusions, setInclusions] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [benchmark, setBenchmark] = useState("walmart_us");
  const [competitor, setCompetitor] = useState("aldi_us");
  const [states, setStates] = useState("AR");
  const [perState, setPerState] = useState(3);
  const [radius, setRadius] = useState<1 | 3 | 5>(5);
  const [pages, setPages] = useState(1);
  const [amazonUrl, setAmazonUrl] = useState("");

  const selected = useMemo(
    () => studies.find((study) => study.id === selectedId) ?? null,
    [selectedId, studies],
  );
  const productsVisible = Boolean(
    selected &&
    ["profile_ready", "pdp_estimated", "enriching", "draft_ready"].includes(
      selected.status,
    ),
  );
  const visibleProducts = productsVisible ? products : [];

  const load = useCallback(async () => {
    const [studyRows, options] = await Promise.all([
      jsonRequest<Study[]>("/api/admin/studies"),
      jsonRequest<CollectionOptions>("/api/collections/options"),
    ]);
    setStudies(studyRows);
    setRetailers(options.retailers);
    setSelectedId((value) => value ?? studyRows[0]?.id ?? null);
  }, []);

  useEffect(() => {
    void jsonRequest<AdminSession>("/api/admin/session")
      .then((value) => {
        setSession(value);
        if (value.authenticated) return load();
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to load admin access.",
        ),
      );
  }, [load]);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    const status = studies.find((study) => study.id === selectedId)?.status;
    if (
      !["profile_ready", "pdp_estimated", "enriching", "draft_ready"].includes(
        status ?? "",
      )
    ) {
      return;
    }
    void jsonRequest<StudyProduct[]>(
      `/api/admin/studies/${selectedId}/products`,
    )
      .then(setProducts)
      .catch((cause: unknown) =>
        setError(
          cause instanceof Error ? cause.message : "Unable to load products.",
        ),
      );
  }, [selectedId, studies]);

  useEffect(() => {
    if (!selectedId || !selected?.pdp_run_id) return;
    void jsonRequest<PdpAudit>(`/api/admin/studies/${selectedId}/pdp-audit`)
      .then(setPdpAudit)
      .catch(() => setPdpAudit(null));
  }, [selected?.pdp_run_id, selectedId, selected?.status]);

  useEffect(() => {
    if (
      !selected ||
      !["collecting", "profiling", "enriching"].includes(selected.status)
    )
      return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [load, selected]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await jsonRequest("/api/admin/session", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setSession({ configured: true, authenticated: true });
      setPassword("");
      await load();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to authenticate.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function createStudy(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const stateValues = splitTerms(states).map((value) =>
        value.toUpperCase(),
      );
      const study = await jsonRequest<Study>("/api/admin/studies", {
        method: "POST",
        body: JSON.stringify({
          name,
          benchmark_retailer_id: benchmark,
          competitor_retailer_ids: [competitor],
          category_context: categoryContext,
          known_inclusions: splitTerms(inclusions),
          known_exclusions: splitTerms(exclusions),
          geography_request: {
            primary_retailer_id: benchmark,
            competitor_retailer_ids: [competitor],
            country: "USA",
            primary_selection: {
              mode: "per_state",
              states: stateValues,
              locations_per_state: perState,
            },
            competitor_correspondence: {
              mode: "radius",
              radius_miles: radius,
            },
          },
          max_search_pages: pages,
          amazon_same_day_url_template:
            competitor === "amazon_us_same_day" ? amazonUrl : null,
        }),
      });
      await load();
      setSelectedId(study.id);
      setShowCreate(false);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to create the study.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function action(path: string, body?: unknown) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const study = await jsonRequest<Study>(
        `/api/admin/studies/${selected.id}/${path}`,
        {
          method: "POST",
          body: JSON.stringify(body ?? {}),
        },
      );
      setStudies((rows) =>
        rows.map((row) => (row.id === study.id ? study : row)),
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to complete the action.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const study = await jsonRequest<Study>(
        `/api/admin/studies/${selected.id}/query-plan`,
        {
          method: "PATCH",
          body: JSON.stringify({
            keyword: String(data.get("keyword") ?? ""),
            target_terms: splitTerms(String(data.get("targets") ?? "")),
            exclusion_terms: splitTerms(String(data.get("exclusions") ?? "")),
            alternate_queries: [],
            rationale: "Reviewed by an authenticated study administrator.",
          }),
        },
      );
      setStudies((rows) =>
        rows.map((row) => (row.id === study.id ? study : row)),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to save the query.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function refineProfileScope(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const study = await jsonRequest<Study>(
        `/api/admin/studies/${selected.id}/profile-scope`,
        {
          method: "POST",
          body: JSON.stringify({
            target_terms: splitTerms(String(data.get("targets") ?? "")),
            exclusion_terms: splitTerms(String(data.get("exclusions") ?? "")),
            rationale:
              "Refined after reviewing the collected Search population; saved evidence was re-profiled without new provider calls.",
          }),
        },
      );
      setStudies((rows) =>
        rows.map((row) => (row.id === study.id ? study : row)),
      );
      setProducts([]);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to re-profile the saved Search evidence.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function changeDisposition(
    product: StudyProduct,
    admissionStatus: string,
  ) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const study = await jsonRequest<Study>(
        `/api/admin/studies/${selected.id}/products`,
        {
          method: "PATCH",
          body: JSON.stringify({
            retailer_id: product.retailer_id,
            retailer_product_id: product.retailer_product_id,
            admission_status: admissionStatus,
            reason: `Human review set disposition to ${admissionStatus.replaceAll("_", " ")}.`,
          }),
        },
      );
      setStudies((rows) =>
        rows.map((row) => (row.id === study.id ? study : row)),
      );
      setProducts(
        await jsonRequest<StudyProduct[]>(
          `/api/admin/studies/${selected.id}/products`,
        ),
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to update the product.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (session === null)
    return (
      <div className="builder-loading">Checking administrator access…</div>
    );
  if (!session.authenticated) {
    return (
      <section className="admin-auth-card">
        <span className="section-kicker">Restricted workspace</span>
        <h2>Administrator authentication required</h2>
        <p>
          Study approvals can spend provider credits, so access uses the Product
          Pack admin session.
        </p>
        {session.configured ? (
          <form onSubmit={signIn}>
            <label>
              <span>Administrator password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? "Checking…" : "Open Study Discovery"}
            </button>
          </form>
        ) : (
          <div className="builder-alert warning">
            Admin authentication is not configured.
          </div>
        )}
        {error ? <p className="form-error">{error}</p> : null}
      </section>
    );
  }

  return (
    <div className="study-admin-shell">
      {error ? (
        <div className="builder-alert error">
          <b>Action stopped</b>
          <span>{error}</span>
        </div>
      ) : null}
      <section className="study-command-bar">
        <div>
          <span className="section-kicker">Search-first governance</span>
          <h2>Category learning before certification</h2>
          <p>
            Search supplies the population and store price. PDP supplies
            reusable identity evidence.
          </p>
        </div>
        <button
          className="button primary"
          onClick={() => setShowCreate((value) => !value)}
        >
          {showCreate ? "Close" : "New discovery study"}
        </button>
      </section>

      {showCreate ? (
        <form className="study-create-form" onSubmit={createStudy}>
          <header>
            <div>
              <span className="section-kicker">Step zero</span>
              <h3>Frame a small, representative sample</h3>
            </div>
          </header>
          <div className="product-pack-form-grid">
            <label>
              <span>Study name</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Fresh category discovery"
                required
              />
            </label>
            <label>
              <span>Seed Search term</span>
              <input
                value={inclusions}
                onChange={(event) => setInclusions(event.target.value)}
                placeholder="category search phrase"
                required
              />
            </label>
            <label className="wide">
              <span>Category context</span>
              <textarea
                value={categoryContext}
                onChange={(event) => setCategoryContext(event.target.value)}
                rows={3}
                placeholder="What belongs, what varies, and what business question should this Product Pack answer?"
                required
              />
            </label>
            <label className="wide">
              <span>Known exclusions</span>
              <input
                value={exclusions}
                onChange={(event) => setExclusions(event.target.value)}
                placeholder="unrelated products, accessories"
              />
            </label>
            <label>
              <span>Primary retailer</span>
              <select
                value={benchmark}
                onChange={(event) => setBenchmark(event.target.value)}
              >
                {retailers.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Competitor</span>
              <select
                value={competitor}
                onChange={(event) => setCompetitor(event.target.value)}
              >
                {retailers
                  .filter((item) => item.id !== benchmark)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              <span>Sample states</span>
              <input
                value={states}
                onChange={(event) => setStates(event.target.value)}
                placeholder="AR, TX"
                required
              />
            </label>
            <label>
              <span>Primary stores per state</span>
              <input
                type="number"
                min={1}
                max={20}
                value={perState}
                onChange={(event) => setPerState(Number(event.target.value))}
              />
            </label>
            <label>
              <span>Competitor radius</span>
              <select
                value={radius}
                onChange={(event) =>
                  setRadius(Number(event.target.value) as 1 | 3 | 5)
                }
              >
                <option value={1}>1 mile</option>
                <option value={3}>3 miles</option>
                <option value={5}>5 miles</option>
              </select>
            </label>
            <label>
              <span>Maximum Search pages</span>
              <select
                value={pages}
                onChange={(event) => setPages(Number(event.target.value))}
              >
                <option value={1}>1 page</option>
                <option value={2}>2 pages</option>
                <option value={3}>3 pages</option>
              </select>
            </label>
            {competitor === "amazon_us_same_day" ? (
              <label className="wide">
                <span>Amazon Same Day Search URL template</span>
                <input
                  value={amazonUrl}
                  onChange={(event) => setAmazonUrl(event.target.value)}
                  placeholder="https://www.amazon.com/s?k={{keyword}}…"
                  required
                />
              </label>
            ) : null}
          </div>
          <div className="builder-alert">
            <b>No paid work happens here</b>
            <span>
              The next screen resolves locations and shows the maximum Search
              credits before approval.
            </span>
          </div>
          <div className="builder-actions">
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create reviewable study"}
            </button>
          </div>
        </form>
      ) : null}

      <div className="study-workspace">
        <aside className="study-list" aria-label="Discovery studies">
          {studies.length ? (
            studies.map((study) => (
              <button
                key={study.id}
                className={study.id === selectedId ? "active" : ""}
                onClick={() => setSelectedId(study.id)}
              >
                <span>{study.name}</span>
                <small>
                  {study.status.replaceAll("_", " ")} ·{" "}
                  {displayDate(study.updated_at)}
                </small>
              </button>
            ))
          ) : (
            <div className="study-empty">
              <b>No studies yet</b>
              <span>
                Start with a small, geographically representative Search sample.
              </span>
            </div>
          )}
        </aside>

        {selected ? (
          <section className="study-detail">
            <header>
              <div>
                <span className="section-kicker">
                  {selected.status.replaceAll("_", " ")}
                </span>
                <h2>{selected.name}</h2>
                <p>
                  {STATUS_COPY[selected.status] ??
                    "Continue through governed evidence review."}
                </p>
              </div>
              {selected.collection_run_id ? (
                <Link
                  className="text-link"
                  href={`/collections/runs/${selected.collection_run_id}`}
                >
                  Open collection run ↗
                </Link>
              ) : null}
            </header>
            <div className="study-stage-rail" aria-label="Study progress">
              <span className="complete">1 Query</span>
              <span
                className={
                  ["query_review", "search_estimated"].includes(selected.status)
                    ? "active"
                    : "complete"
                }
              >
                2 Search
              </span>
              <span
                className={
                  ["collecting", "profiling"].includes(selected.status)
                    ? "active"
                    : selected.profile_summary.unique_products
                      ? "complete"
                      : ""
                }
              >
                3 Profile
              </span>
              <span
                className={
                  ["pdp_estimated", "enriching"].includes(selected.status)
                    ? "active"
                    : selected.product_pack_draft_id
                      ? "complete"
                      : ""
                }
              >
                4 Enrich
              </span>
              <span className={selected.product_pack_draft_id ? "active" : ""}>
                5 Certify
              </span>
            </div>

            {["query_review", "search_estimated"].includes(selected.status) ? (
              <form className="study-query-editor" onSubmit={saveQuery}>
                <label>
                  <span>Search query</span>
                  <input
                    name="keyword"
                    defaultValue={selected.query_plan.keyword}
                    required
                  />
                </label>
                <label>
                  <span>Target terms</span>
                  <input
                    name="targets"
                    defaultValue={selected.query_plan.target_terms.join(", ")}
                    required
                  />
                </label>
                <label>
                  <span>Exclusion terms</span>
                  <input
                    name="exclusions"
                    defaultValue={selected.query_plan.exclusion_terms.join(
                      ", ",
                    )}
                  />
                </label>
                <div>
                  <small>
                    Revision {selected.query_plan.revision} · changing this
                    invalidates any Search estimate.
                  </small>
                  <button
                    className="button secondary"
                    disabled={busy}
                    type="submit"
                  >
                    Save reviewed query
                  </button>
                </div>
              </form>
            ) : (
              <>
                <section className="study-query-card">
                  <div>
                    <span>Reviewed Search query</span>
                    <strong>{selected.query_plan.keyword}</strong>
                    <small>
                      Target: {selected.query_plan.target_terms.join(", ")} ·
                      Exclude:{" "}
                      {selected.query_plan.exclusion_terms.join(", ") || "none"}
                    </small>
                  </div>
                  <div>
                    <span>Revision</span>
                    <strong>{selected.query_plan.revision}</strong>
                    <small>
                      Approval checksum{" "}
                      {selected.query_plan_checksum.slice(0, 10)}…
                    </small>
                  </div>
                </section>
                {["profile_ready", "pdp_estimated"].includes(
                  selected.status,
                ) ? (
                  <form
                    className="study-query-editor"
                    onSubmit={refineProfileScope}
                  >
                    <label>
                      <span>Refine target terms</span>
                      <input
                        name="targets"
                        defaultValue={selected.query_plan.target_terms.join(
                          ", ",
                        )}
                        required
                      />
                    </label>
                    <label>
                      <span>Refine exclusion concepts</span>
                      <input
                        name="exclusions"
                        defaultValue={selected.query_plan.exclusion_terms.join(
                          ", ",
                        )}
                      />
                    </label>
                    <div>
                      <small>
                        Re-runs deterministic screening against the saved Search
                        pages. No MetricsCart calls or credits are used.
                      </small>
                      <button
                        className="button secondary"
                        disabled={busy}
                        type="submit"
                      >
                        Re-profile saved evidence
                      </button>
                    </div>
                  </form>
                ) : null}
              </>
            )}

            {selected.status === "query_review" ? (
              <div className="study-action-card">
                <div>
                  <h3>Resolve sample geography and price the Search</h3>
                  <p>
                    Creates a frozen 1/3/5-mile location set and a
                    maximum-credit estimate. It does not call MetricsCart.
                  </p>
                </div>
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={() => action("search-estimate")}
                >
                  Estimate Search
                </button>
              </div>
            ) : null}
            {selected.status === "search_estimated" ? (
              <div className="study-action-card paid">
                <div>
                  <span className="section-kicker">Paid approval</span>
                  <h3>
                    Up to{" "}
                    {metric(selected.approval_state.search.maximum_cost ?? 0)}{" "}
                    Search credits
                  </h3>
                  <p>
                    The estimate is bound to query revision{" "}
                    {selected.query_plan.revision} and the approved location
                    snapshot.
                  </p>
                </div>
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={() =>
                    action("search-launch", {
                      estimate_id: selected.search_scope_estimate_id,
                      query_plan_checksum: selected.query_plan_checksum,
                    })
                  }
                >
                  Approve and collect
                </button>
              </div>
            ) : null}

            {selected.profile_summary.unique_products ? (
              <div className="study-metric-grid">
                <article>
                  <span>Search observations</span>
                  <strong>
                    {metric(selected.profile_summary.raw_observations)}
                  </strong>
                  <small>Store-level price evidence</small>
                </article>
                <article>
                  <span>Unique products</span>
                  <strong>
                    {metric(selected.profile_summary.unique_products)}
                  </strong>
                  <small>Retailer + product ID</small>
                </article>
                <article>
                  <span>Provisionally admitted</span>
                  <strong>
                    {metric(
                      selected.profile_summary.provisionally_admitted_products,
                    )}
                  </strong>
                  <small>Eligible for PDP planning</small>
                </article>
                <article>
                  <span>Needs scope review</span>
                  <strong>
                    {metric(selected.profile_summary.review_required_products)}
                  </strong>
                  <small>
                    {metric(selected.profile_summary.unknown_brands)} unknown
                    brands routed separately
                  </small>
                </article>
              </div>
            ) : null}

            {selected.status === "profile_ready" ? (
              <div className="study-action-row">
                {!selected.pdp_run_id ? (
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => action("pdp-estimate")}
                  >
                    Estimate admitted-product PDPs
                  </button>
                ) : null}
                {selected.pdp_run_id && !selected.product_pack_draft_id ? (
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={() => action("product-pack-draft", {})}
                  >
                    Create evidence-informed draft
                  </button>
                ) : null}
              </div>
            ) : null}
            {selected.status === "pdp_estimated" && selected.pdp_estimate ? (
              <div className="study-action-card paid">
                <div>
                  <span className="section-kicker">Paid approval</span>
                  <h3>
                    {metric(selected.pdp_estimate.planned_calls)} PDP calls · up
                    to {metric(selected.pdp_estimate.estimated_credits)} credits
                  </h3>
                  <p>
                    {metric(selected.pdp_estimate.eligible_products)} admitted
                    products. Extra contexts exist only for distinct Search
                    price states.
                  </p>
                </div>
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={() =>
                    action("pdp-launch", {
                      plan_checksum: selected.pdp_plan_checksum,
                      max_credits: selected.pdp_estimate?.estimated_credits,
                    })
                  }
                >
                  Approve enrichment
                </button>
              </div>
            ) : null}
            {selected.status === "profile_ready" &&
            selected.pdp_run_id &&
            !selected.product_pack_draft_id ? (
              <section className="study-pdp-audit">
                <div className="study-pdp-audit-summary">
                  <div>
                    <span className="section-kicker">PDP call ledger</span>
                    <h3>
                      {pdpAudit
                        ? `${metric(pdpAudit.succeeded_calls)} enriched · ${metric(pdpAudit.failed_calls)} unavailable`
                        : "PDP enrichment complete"}
                    </h3>
                    <p>
                      Search remains authoritative for store price and location.
                      PDP data supports identity, attributes, imagery, and
                      Product Pack design.
                    </p>
                  </div>
                  {pdpAudit ? (
                    <div className="study-pdp-audit-cost">
                      <strong>
                        {metric(pdpAudit.actual_credits)} /{" "}
                        {metric(pdpAudit.max_credits)}
                      </strong>
                      <small>credits used</small>
                    </div>
                  ) : null}
                </div>
                {pdpAudit ? (
                  <details>
                    <summary>
                      Review all {metric(pdpAudit.planned_calls)} request
                      contexts and statuses
                    </summary>
                    <div className="study-product-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Product</th>
                            <th>Retailer</th>
                            <th>Observed request context</th>
                            <th>Result</th>
                            <th>Credits</th>
                          </tr>
                        </thead>
                        <tbody>
                          {pdpAudit.calls.map((call) => (
                            <tr
                              key={`${call.retailer_id}:${call.retailer_product_id}:${call.request_context.zipcode}:${call.request_context.store}`}
                            >
                              <td>
                                <b>{call.product_name}</b>
                                <small>{call.retailer_product_id}</small>
                              </td>
                              <td>
                                {retailers.find(
                                  (item) => item.id === call.retailer_id,
                                )?.display_name ?? call.retailer_id}
                              </td>
                              <td>
                                ZIP {call.request_context.zipcode ?? "—"} ·
                                store {call.request_context.store ?? "—"}
                                <small>
                                  {call.request_context.fulfillment_type ??
                                    "unspecified fulfillment"}
                                </small>
                              </td>
                              <td>
                                <span
                                  className={`study-disposition ${call.status === "succeeded" ? "provisionally_admitted" : "excluded"}`}
                                >
                                  {call.http_status ?? call.status}
                                </span>
                                {call.error ? (
                                  <small>{call.error}</small>
                                ) : null}
                              </td>
                              <td>{metric(call.billable_credits)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                ) : null}
              </section>
            ) : null}
            {selected.product_pack_draft_id ? (
              <div className="study-action-card success">
                <div>
                  <span className="section-kicker">
                    Human certification next
                  </span>
                  <h3>Product Pack draft is ready</h3>
                  <p>
                    Review scope, attributes, matching lenses, evidence, and
                    golden tests before publication.
                  </p>
                </div>
                <Link
                  className="button primary"
                  href={`/admin/product-packs/drafts/${selected.product_pack_draft_id}`}
                >
                  Open Product Pack draft
                </Link>
              </div>
            ) : null}

            {visibleProducts.length ? (
              <section className="study-products">
                <header>
                  <div>
                    <span className="section-kicker">Candidate population</span>
                    <h3>Every unique product has an evidence disposition</h3>
                  </div>
                </header>
                <div className="study-product-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Retailer</th>
                        <th>Disposition</th>
                        <th>Coverage</th>
                        <th>Search price range</th>
                        <th>Review</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleProducts.slice(0, 100).map((product) => (
                        <tr
                          key={`${product.retailer_id}:${product.retailer_product_id}`}
                        >
                          <td>
                            <div className="study-product-cell">
                              {product.image_url ? (
                                <Image
                                  src={product.image_url}
                                  alt=""
                                  width={48}
                                  height={48}
                                  unoptimized
                                />
                              ) : (
                                <span className="study-product-placeholder">
                                  No image
                                </span>
                              )}
                              <div>
                                <b>{product.title}</b>
                                <small>
                                  {product.brand ?? "Brand not supplied"} ·{" "}
                                  {product.retailer_product_id}
                                </small>
                              </div>
                            </div>
                          </td>
                          <td>
                            {retailers.find(
                              (item) => item.id === product.retailer_id,
                            )?.display_name ?? product.retailer_id}
                          </td>
                          <td>
                            <span
                              className={`study-disposition ${product.admission_status}`}
                            >
                              {product.admission_status.replaceAll("_", " ")}
                            </span>
                            <small>{product.admission_reason}</small>
                          </td>
                          <td>
                            {metric(product.store_count)} stores
                            <br />
                            <small>
                              {metric(product.observation_count)} observations
                            </small>
                          </td>
                          <td>
                            {product.price_min === null
                              ? "—"
                              : product.price_min === product.price_max
                                ? `$${product.price_min.toFixed(2)}`
                                : `$${product.price_min.toFixed(2)}–$${product.price_max?.toFixed(2)}`}
                          </td>
                          <td>
                            {["profile_ready", "pdp_estimated"].includes(
                              selected.status,
                            ) ? (
                              <div className="study-row-actions">
                                <button
                                  disabled={
                                    busy ||
                                    product.admission_status ===
                                      "provisionally_admitted"
                                  }
                                  onClick={() =>
                                    changeDisposition(
                                      product,
                                      "provisionally_admitted",
                                    )
                                  }
                                >
                                  Admit
                                </button>
                                <button
                                  disabled={
                                    busy ||
                                    product.admission_status === "excluded"
                                  }
                                  onClick={() =>
                                    changeDisposition(product, "excluded")
                                  }
                                >
                                  Exclude
                                </button>
                              </div>
                            ) : (
                              <small>Locked after PDP launch</small>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {visibleProducts.length > 100 ? (
                  <p className="study-table-note">
                    Showing the first 100 of {metric(visibleProducts.length)}{" "}
                    products. The API retains the full population.
                  </p>
                ) : null}
              </section>
            ) : null}
          </section>
        ) : (
          <section className="study-detail study-empty">
            <b>Select or create a study</b>
            <span>
              The workflow begins with a reviewable query, not an API call.
            </span>
          </section>
        )}
      </div>
    </div>
  );
}
