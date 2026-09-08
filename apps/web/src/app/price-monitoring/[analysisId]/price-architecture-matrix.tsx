"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { hasVerifiedArchitectureRetailerEvidence } from "@/lib/availability-presentation";
import type { PriceArchitectureMatrix } from "@/lib/api";

type MatrixRung = PriceArchitectureMatrix["rungs"][number];
type MatrixCell = MatrixRung["cells"][number];
type MatrixProduct = MatrixCell["products"][number];
type CellMetric =
  | "products"
  | "sku_count"
  | "assortment_share"
  | "store_coverage"
  | "average_price"
  | "price_density";
type RungMethod = "benchmark" | "fixed-050" | "fixed-100";

const metricLabels: Record<CellMetric, string> = {
  products: "Verified products + prices",
  sku_count: "Verified-available SKU count",
  assortment_share: "% of verified assortment",
  store_coverage: "Verified availability coverage",
  average_price: "Verified local average price",
  price_density: "Verified price density",
};

const brandLabels: Record<string, string> = {
  all: "All brand types",
  private_label: "Private label",
  regional: "Regional",
  national: "National",
  unclassified: "Unclassified",
};

const sellerLabels: Record<string, string> = {
  verified_first_party: "Verified first-party seller",
  seller_unverified: "Seller not supplied",
  not_governed: "Seller policy not required",
};

function currency(value: number | null) {
  return value === null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(value);
}

function percent(value: number | null) {
  return value === null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(value);
}

function count(value: number) {
  return value.toLocaleString("en-US");
}

function sellerCoverage(
  retailer: PriceArchitectureMatrix["retailers"][number],
) {
  if (retailer.verified_first_party_skus || retailer.seller_unverified_skus) {
    return `${count(retailer.verified_first_party_skus)} verified 1P · ${count(retailer.seller_unverified_skus)} seller unknown`;
  }
  if (retailer.seller_not_governed_skus) return "Seller policy not required";
  return "No eligible seller evidence";
}

function footprintLabel(
  product: MatrixProduct,
  retailer: PriceArchitectureMatrix["retailers"][number],
) {
  const locationLabel =
    retailer.location_dimension === "service_area" ? "service areas" : "stores";
  const coverage = retailer.eligible_locations
    ? ` · ${percent(product.verified_available_locations / retailer.eligible_locations)}`
    : "";
  return `${count(product.verified_available_locations)} verified in-stock ${locationLabel}${coverage} · ${count(product.search_observed_locations)} Search-observed`;
}

function methodQuery(method: RungMethod) {
  if (method === "fixed-050") return "mode=fixed_range&fixed_increment=0.5";
  if (method === "fixed-100") return "mode=fixed_range&fixed_increment=1";
  return "mode=benchmark_anchored&fixed_increment=0.5";
}

function numericMetric(cell: MatrixCell, metric: CellMetric) {
  if (metric === "products" || metric === "sku_count") return cell.sku_count;
  return cell[metric] ?? 0;
}

function metricValue(cell: MatrixCell, metric: CellMetric) {
  if (metric === "sku_count") return `${count(cell.sku_count)} SKUs`;
  if (metric === "assortment_share") return percent(cell.assortment_share);
  if (metric === "store_coverage") return percent(cell.store_coverage);
  if (metric === "average_price") return currency(cell.average_price);
  if (metric === "price_density")
    return cell.price_density === null
      ? "Open-ended band"
      : `${cell.price_density.toFixed(1)} SKUs / $1`;
  return `${count(cell.sku_count)} ${cell.sku_count === 1 ? "product" : "products"}`;
}

function ProductDrawer({
  cell,
  retailer,
  rung,
  onClose,
}: Readonly<{
  cell: MatrixCell;
  retailer: PriceArchitectureMatrix["retailers"][number];
  rung: MatrixRung;
  onClose: () => void;
}>) {
  return (
    <div className="pi-matrix-drawer-backdrop" role="presentation">
      <aside
        aria-label={`${retailer.name} products in ${rung.label}`}
        aria-modal="true"
        className="pi-matrix-drawer"
        role="dialog"
      >
        <header>
          <div>
            <p className="section-kicker">Price-rung evidence</p>
            <h2>{retailer.name}</h2>
            <p>
              {rung.label} · {count(cell.sku_count)} SKUs with verified local
              availability · {percent(cell.store_coverage)} of eligible
              locations verify at least one SKU in this rung
            </p>
          </div>
          <button
            aria-label="Close product evidence"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>
        <div className="pi-matrix-drawer-note">
          Products appear here only when at least one non-sponsored Search row
          explicitly reports in stock; their median verified local Search price
          falls in this band. This view does not assert that any two products
          are substitutes or matches.
        </div>
        <div className="pi-matrix-product-list">
          {cell.products.map((product) => (
            <article key={product.product_id}>
              {product.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img alt="" src={product.image_url} />
              ) : (
                <span
                  className="pi-matrix-image-placeholder"
                  aria-hidden="true"
                >
                  P
                </span>
              )}
              <div>
                <p>{brandLabels[product.brand_type]}</p>
                <h3>{product.name}</h3>
                <span>{product.brand ?? "Brand unresolved"}</span>
                <span>
                  {product.seller
                    ? `Seller: ${product.seller} · ${sellerLabels[product.seller_status]}`
                    : sellerLabels[product.seller_status]}
                </span>
                <dl>
                  <div>
                    <dt>Median verified local price</dt>
                    <dd>{currency(product.median_price)}</dd>
                  </div>
                  <div>
                    <dt>Verified local price range</dt>
                    <dd>
                      {currency(product.minimum_price)}–
                      {currency(product.maximum_price)}
                    </dd>
                  </div>
                  <div>
                    <dt>Availability and Search reach</dt>
                    <dd>{footprintLabel(product, retailer)}</dd>
                  </div>
                  <div>
                    <dt>Retailer product ID</dt>
                    <dd>{product.product_id}</dd>
                  </div>
                </dl>
                {product.url ? (
                  <a href={product.url} rel="noreferrer" target="_blank">
                    Open retailer product ↗
                  </a>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      </aside>
    </div>
  );
}

export function PriceArchitectureMatrixWorkspace({
  analysisId,
  initialBrandType = "all",
  state,
  city,
  zipcode,
}: Readonly<{
  analysisId: string;
  initialBrandType?: string;
  state?: string | null;
  city?: string | null;
  zipcode?: string | null;
}>) {
  const [method, setMethod] = useState<RungMethod>("benchmark");
  const [metric, setMetric] = useState<CellMetric>("products");
  const [brandType, setBrandType] = useState(initialBrandType);
  const [brand, setBrand] = useState("");
  const [matrix, setMatrix] = useState<PriceArchitectureMatrix | null>(null);
  const [settledRequest, setSettledRequest] = useState("");
  const [requestError, setRequestError] = useState<{
    key: string;
    message: string;
  } | null>(null);
  const [selected, setSelected] = useState<{
    rung: MatrixRung;
    cell: MatrixCell;
    retailer: PriceArchitectureMatrix["retailers"][number];
  } | null>(null);

  const requestKey = useMemo(() => {
    const query = new URLSearchParams(methodQuery(method));
    query.set("brand_type", brandType);
    if (brand) query.set("brand", brand);
    if (state) query.set("state", state);
    if (city) query.set("city", city);
    if (zipcode) query.set("zipcode", zipcode);
    return query.toString();
  }, [brand, brandType, city, method, state, zipcode]);
  const loading = settledRequest !== requestKey;
  const error = requestError?.key === requestKey ? requestError.message : null;

  useEffect(() => {
    const controller = new AbortController();
    fetch(
      `/api/price-monitoring/${encodeURIComponent(analysisId)}/architecture-matrix?${requestKey}`,
      { cache: "no-store", signal: controller.signal },
    )
      .then(async (response) => {
        if (response.status === 409) {
          window.location.reload();
          throw new DOMException("Report quarantined", "AbortError");
        }
        if (!response.ok) {
          const body = (await response.json().catch(() => ({}))) as {
            error?: string;
          };
          throw new Error(
            body.error ?? `Price architecture returned ${response.status}`,
          );
        }
        setMatrix((await response.json()) as PriceArchitectureMatrix);
        setRequestError(null);
        setSettledRequest(requestKey);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError")
          return;
        setRequestError({
          key: requestKey,
          message:
            reason instanceof Error
              ? reason.message
              : "The price architecture matrix could not be loaded.",
        });
        setSettledRequest(requestKey);
      });
    return () => controller.abort();
  }, [analysisId, requestKey]);

  const availableRetailers = matrix?.retailers.filter(
    hasVerifiedArchitectureRetailerEvidence,
  );
  const maxima = useMemo(() => {
    const values = new Map<string, number>();
    if (!matrix) return values;
    for (const retailer of matrix.retailers) {
      const maximum = Math.max(
        0,
        ...matrix.rungs.map((rung) => {
          const cell = rung.cells.find(
            (row) => row.retailer_id === retailer.id,
          );
          return cell ? numericMetric(cell, metric) : 0;
        }),
      );
      values.set(retailer.id, maximum);
    }
    return values;
  }, [matrix, metric]);

  if (loading && !matrix) {
    return (
      <section className="pi-matrix-loading" role="status">
        <span aria-hidden="true" />
        <div>
          <strong>Building the price architecture matrix</strong>
          <p>
            Preparing governed product-location populations for every retailer…
          </p>
        </div>
      </section>
    );
  }
  if (error && !matrix) {
    return (
      <section className="pi-matrix-error" role="alert">
        <strong>Price architecture is unavailable</strong>
        <p>{error}</p>
      </section>
    );
  }
  if (!matrix || !availableRetailers) return null;

  const anchor = matrix.retailers.find(
    (retailer) => retailer.id === matrix.filters.anchor_retailer_id,
  );
  if (!anchor) {
    return (
      <section className="pi-matrix-error" role="alert">
        <strong>Price architecture is unavailable</strong>
        <p>The governed anchor-retailer record is missing from this matrix.</p>
      </section>
    );
  }
  const unavailableRetailers = matrix.retailers.filter(
    (retailer) => !hasVerifiedArchitectureRetailerEvidence(retailer),
  );
  const anchorEvidenceAvailable =
    hasVerifiedArchitectureRetailerEvidence(anchor);
  const crowded = matrix.rungs.find(
    (rung) => rung.id === matrix.summary.most_crowded_rung_id,
  );

  return (
    <section className="pi-matrix-workspace">
      <div className="pi-matrix-heading">
        <div>
          <p className="section-kicker">
            Cross-retailer assortment architecture
          </p>
          <h2>Price Architecture Matrix</h2>
          <p>
            {anchor.name} defines the price rungs. Every retailer SKU is placed
            only by its median verified local Search price—never by a product
            match. Sponsored-only or unknown-stock products are excluded.
          </p>
        </div>
        {loading ? (
          <span className="pi-matrix-refreshing">Refreshing…</span>
        ) : null}
      </div>

      <div className="pi-matrix-controls">
        <label>
          <span>Rung method</span>
          <select
            onChange={(event) => setMethod(event.target.value as RungMethod)}
            value={method}
          >
            <option value="benchmark">Walmart-anchored midpoints</option>
            <option value="fixed-050">Fixed $0.50 bands</option>
            <option value="fixed-100">Fixed $1.00 bands</option>
          </select>
        </label>
        <label>
          <span>Cell view</span>
          <select
            onChange={(event) => setMetric(event.target.value as CellMetric)}
            value={metric}
          >
            {Object.entries(metricLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Brand type</span>
          <select
            onChange={(event) => {
              setBrandType(event.target.value);
              setBrand("");
            }}
            value={brandType}
          >
            {Object.entries(brandLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Brand</span>
          <select
            onChange={(event) => setBrand(event.target.value)}
            value={brand}
          >
            <option value="">All brands</option>
            {matrix.brand_options.map((option) => (
              <option key={option.name} value={option.name}>
                {option.name} ({count(option.product_count)})
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="pi-matrix-kpis">
        <article>
          <span>
            {matrix.filters.mode === "benchmark_anchored"
              ? `${anchor.name} verified-local price rungs`
              : "Fixed price bands"}
          </span>
          <strong>{count(matrix.summary.rung_count)}</strong>
          <small>
            {anchorEvidenceAvailable
              ? `${count(matrix.summary.anchor_skus)} verified-available ${anchor.name} SKUs · `
              : `No ${anchor.name} SKU with verified availability under the current product filters · `}
            {count(matrix.summary.anchor_price_points)} distinct price points
          </small>
        </article>
        <article>
          <span>Verified-available competitor SKUs</span>
          <strong>{count(matrix.summary.competitor_skus)}</strong>
          <small>
            {count(Math.max(0, availableRetailers.length - 1))} retailers
          </small>
        </article>
        <article>
          <span>Most crowded rung</span>
          <strong>{crowded?.label ?? "—"}</strong>
          <small>
            {count(crowded?.competitor_sku_count ?? 0)} verified-available
            competitor SKUs
          </small>
        </article>
        <article>
          <span>Competitor white-space rungs</span>
          <strong>{count(matrix.summary.whitespace_rung_count)}</strong>
          <small>
            No competitor SKU with verified availability in the band
          </small>
        </article>
      </div>

      <div className="pi-matrix-method-note">
        <strong>How to read it</strong>
        <span>
          One SKU contributes once, using its verified-local-availability median
          package price. Coverage is the distinct union of verified in-stock
          locations for products in the cell. Search reach is retained
          separately on each product. Known third-party marketplace sellers are
          excluded; products without seller evidence remain labeled seller
          unknown. Empty cells mean no eligible SKU has verified availability in
          the band—not necessarily that the retailer has no such product.
        </span>
      </div>

      <div className="pi-matrix-table-wrap">
        <table className="pi-matrix-table">
          <thead>
            <tr>
              <th>
                <strong>{anchor.name} anchor / price rung</strong>
                <span>
                  {anchorEvidenceAvailable
                    ? `${count(anchor.sku_count)} verified-available SKUs across ${count(anchor.verified_available_locations)} verified local locations`
                    : "No filtered anchor SKU has verified local availability"}
                </span>
                <span>{sellerCoverage(anchor)}</span>
              </th>
              {availableRetailers
                .filter(
                  (retailer) =>
                    retailer.id !== matrix.filters.anchor_retailer_id,
                )
                .map((retailer) => (
                  <th key={retailer.id}>
                    <strong>{retailer.name}</strong>
                    <span>
                      {count(retailer.sku_count)} verified-available SKUs across{" "}
                      {count(retailer.verified_available_locations)} verified
                      local locations
                    </span>
                    <span>{sellerCoverage(retailer)}</span>
                  </th>
                ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rungs.map((rung) => {
              const anchorCell = rung.cells.find(
                (cell) =>
                  cell.retailer_id === matrix.filters.anchor_retailer_id,
              );
              return (
                <tr key={rung.id}>
                  <th scope="row">
                    <span className="pi-matrix-rung">Rung {rung.rank}</span>
                    {rung.anchor_products.length ? (
                      rung.anchor_products.map((product) => (
                        <button
                          key={product.product_id}
                          onClick={() =>
                            anchorCell &&
                            anchor &&
                            setSelected({
                              rung,
                              cell: anchorCell,
                              retailer: anchor,
                            })
                          }
                          type="button"
                        >
                          <strong>{product.name}</strong>
                          <span>
                            {currency(product.median_price)} · ID{" "}
                            {product.product_id}
                          </span>
                          <small>
                            {anchor
                              ? footprintLabel(product, anchor)
                              : `${count(product.verified_available_locations)} verified in-stock locations · ${count(product.search_observed_locations)} Search-observed`}
                          </small>
                          <small>
                            {product.seller
                              ? `Seller: ${product.seller}`
                              : sellerLabels[product.seller_status]}
                          </small>
                        </button>
                      ))
                    ) : (
                      <strong>{rung.label}</strong>
                    )}
                    <small>{rung.label}</small>
                  </th>
                  {availableRetailers
                    .filter(
                      (retailer) =>
                        retailer.id !== matrix.filters.anchor_retailer_id,
                    )
                    .map((retailer) => {
                      const cell = rung.cells.find(
                        (row) => row.retailer_id === retailer.id,
                      );
                      if (!cell || cell.sku_count === 0) {
                        return (
                          <td className="pi-matrix-empty" key={retailer.id}>
                            <span>—</span>
                            <small>
                              No SKU with verified availability in band
                            </small>
                          </td>
                        );
                      }
                      const maximum = maxima.get(retailer.id) ?? 0;
                      const intensity = maximum
                        ? numericMetric(cell, metric) / maximum
                        : 0;
                      return (
                        <td
                          className="pi-matrix-cell"
                          key={retailer.id}
                          style={
                            { "--matrix-intensity": intensity } as CSSProperties
                          }
                        >
                          <button
                            onClick={() =>
                              setSelected({
                                rung,
                                cell,
                                retailer,
                              })
                            }
                            type="button"
                          >
                            {metric === "products" ? (
                              <div className="pi-matrix-cell-products">
                                {cell.products.slice(0, 3).map((product) => (
                                  <span key={product.product_id}>
                                    <b>{product.name}</b>
                                    <i>
                                      {currency(product.median_price)} · ID{" "}
                                      {product.product_id}
                                    </i>
                                    <small>
                                      {footprintLabel(product, retailer)}
                                    </small>
                                    <small>
                                      {product.seller
                                        ? `Seller: ${product.seller}`
                                        : sellerLabels[product.seller_status]}
                                    </small>
                                  </span>
                                ))}
                                {cell.products.length > 3 ? (
                                  <em>+{cell.products.length - 3} more</em>
                                ) : null}
                              </div>
                            ) : (
                              <strong>{metricValue(cell, metric)}</strong>
                            )}
                            <small>View product evidence →</small>
                          </button>
                        </td>
                      );
                    })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {unavailableRetailers.length ? (
        <details className="pi-matrix-unavailable">
          <summary>
            Retailers without verified local evidence in this snapshot
          </summary>
          <ul>
            {unavailableRetailers.map((retailer) => (
              <li key={retailer.id}>
                <strong>{retailer.name}</strong> —{" "}
                {retailer.reason ??
                  "No explicit verified-local assortment and price evidence is available."}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {selected ? (
        <ProductDrawer
          cell={selected.cell}
          onClose={() => setSelected(null)}
          retailer={selected.retailer}
          rung={selected.rung}
        />
      ) : null}
    </section>
  );
}
