"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import type { CostEstimate, ProductPackCatalog, RunRecord } from "@/lib/api";
import {
  buildCollectionDefinition,
  normalizeZipcodes,
  RETAILER_OPTIONS,
  type RetailerId,
  validateCollectionValues,
} from "@/lib/collection-definition";
import { displayLabel } from "@/lib/presentation";

function createDefinitionId(): string {
  return `collection-${Date.now().toString(36)}`;
}

async function errorFrom(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string };
    return body.error ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

export function CollectionWizard({
  catalog,
}: Readonly<{ catalog: ProductPackCatalog }>) {
  const router = useRouter();
  const defaultPack =
    catalog.packs.find((pack) => pack.id === catalog.default_pack_id) ??
    catalog.packs[0]!;
  const [definitionId] = useState(createDefinitionId);
  const [productPackId, setProductPackId] = useState(defaultPack.id);
  const [name, setName] = useState(`${defaultPack.name} Vertical Slice`);
  const [keyword, setKeyword] = useState(defaultPack.default_keyword);
  const [zipcodeText, setZipcodeText] = useState("44906");
  const [retailerIds, setRetailerIds] = useState<RetailerId[]>([
    "walmart_us",
    "aldi_us",
    "amazon_us_same_day",
  ]);
  const [maxPages, setMaxPages] = useState(1);
  const [maxCredits, setMaxCredits] = useState(5);
  const [gateEnabled, setGateEnabled] = useState(true);
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [estimatedSignature, setEstimatedSignature] = useState("");
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState<"estimate" | "launch" | null>(null);
  const [error, setError] = useState("");
  const selectedPack =
    catalog.packs.find((pack) => pack.id === productPackId) ?? defaultPack;

  const values = useMemo(
    () => ({
      definitionId,
      name,
      productPackId: selectedPack.id,
      productPackVersion: selectedPack.version,
      keyword,
      zipcodes: normalizeZipcodes(zipcodeText),
      retailerIds,
      maxPages,
      maxCredits,
      availabilityGateEnabled: gateEnabled,
    }),
    [
      definitionId,
      gateEnabled,
      keyword,
      maxCredits,
      maxPages,
      name,
      selectedPack.id,
      selectedPack.version,
      retailerIds,
      zipcodeText,
    ],
  );
  const config = useMemo(() => buildCollectionDefinition(values), [values]);
  const signature = JSON.stringify(config);
  const estimateCurrent = estimate !== null && estimatedSignature === signature;
  const overBudget =
    estimateCurrent && estimate.estimated_total_credits > maxCredits;

  function toggleRetailer(retailerId: RetailerId) {
    setRetailerIds((current) =>
      current.includes(retailerId)
        ? current.filter((value) => value !== retailerId)
        : [...current, retailerId],
    );
    setApproved(false);
  }

  function selectProductPack(packId: string) {
    const pack = catalog.packs.find((value) => value.id === packId);
    if (!pack) return;
    setProductPackId(pack.id);
    setName(`${pack.name} Vertical Slice`);
    setKeyword(pack.default_keyword);
    setApproved(false);
  }

  async function calculateEstimate() {
    const validationError = validateCollectionValues(values);
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy("estimate");
    setError("");
    setApproved(false);
    try {
      const response = await fetch("/api/collections/estimate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: signature,
      });
      if (!response.ok) throw new Error(await errorFrom(response));
      setEstimate((await response.json()) as CostEstimate);
      setEstimatedSignature(signature);
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
    if (!estimateCurrent || !approved || overBudget) return;
    setBusy("launch");
    setError("");
    try {
      const response = await fetch("/api/collections/launch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: signature,
      });
      if (!response.ok) throw new Error(await errorFrom(response));
      const run = (await response.json()) as RunRecord;
      router.push(`/collections/runs/${encodeURIComponent(run.id)}`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The run could not be launched.",
      );
      setBusy(null);
    }
  }

  return (
    <div className="wizard-layout">
      <section className="wizard-card">
        <header>
          <span className="section-kicker">1 · Scope</span>
          <h2>Configure a collection</h2>
          <p>
            Select a versioned Product Pack. Collection, matching, analytics,
            and delivery use the same category-neutral engine for every pack.
          </p>
        </header>
        <div className="form-grid">
          <label className="full-field">
            <span>Run name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            <span>Product Pack</span>
            <select
              value={selectedPack.id}
              onChange={(event) => selectProductPack(event.target.value)}
            >
              {catalog.packs.map((pack) => (
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
          <label className="full-field">
            <span>ZIP codes</span>
            <textarea
              rows={3}
              value={zipcodeText}
              onChange={(event) => setZipcodeText(event.target.value)}
              placeholder="One or more five-digit ZIPs, separated by commas or new lines"
            />
            <small>Leading zeros are preserved.</small>
          </label>
        </div>
        <fieldset>
          <legend>Retailers</legend>
          <div className="retailer-options">
            {RETAILER_OPTIONS.map((retailer) => (
              <label key={retailer.id} className="check-card">
                <input
                  type="checkbox"
                  checked={retailerIds.includes(retailer.id)}
                  onChange={() => toggleRetailer(retailer.id)}
                />
                <span>
                  <b>{retailer.label}</b>
                  <small>
                    {retailer.credits} credit{retailer.credits === 1 ? "" : "s"}{" "}
                    / page
                  </small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="form-grid compact-fields">
          <label>
            <span>Maximum pages / location</span>
            <input
              type="number"
              min={1}
              max={10}
              value={maxPages}
              onChange={(event) => setMaxPages(Number(event.target.value))}
            />
          </label>
          <label>
            <span>Hard credit cap</span>
            <input
              type="number"
              min={0}
              value={maxCredits}
              onChange={(event) => setMaxCredits(Number(event.target.value))}
            />
          </label>
        </div>
        <label className="inline-check">
          <input
            type="checkbox"
            checked={gateEnabled}
            disabled={!retailerIds.includes("aldi_us")}
            onChange={(event) => setGateEnabled(event.target.checked)}
          />
          <span>
            <b>Run the ALDI availability gate first</b>
            <small>
              Sample up to five ALDI locations and stop remaining work when more
              than half return billable 404s.
            </small>
          </span>
        </label>
        <button
          className="button secondary"
          type="button"
          disabled={busy !== null}
          onClick={() => void calculateEstimate()}
        >
          {busy === "estimate" ? "Calculating…" : "Calculate exact estimate"}
        </button>
      </section>

      <aside className="wizard-card approval-card">
        <header>
          <span className="section-kicker">2 · Estimate & approve</span>
          <h2>Review spend before launch</h2>
        </header>
        {!estimateCurrent ? (
          <div className="estimate-placeholder">
            <strong>No current estimate</strong>
            <p>
              Calculate the exact location expansion and maximum billable
              credits.
            </p>
          </div>
        ) : (
          <>
            <div className="estimate-total">
              <span>Maximum estimated credits</span>
              <strong>{estimate.estimated_total_credits}</strong>
              <small>{estimate.estimated_total_pages} maximum pages</small>
            </div>
            <div className="estimate-breakdown">
              {estimate.retailers.map((retailer) => (
                <div key={retailer.retailer_id}>
                  <span>
                    <b>{displayLabel(retailer.retailer_id)}</b>
                    <small>{retailer.location_units} location units</small>
                  </span>
                  <strong>{retailer.estimated_credits}</strong>
                </div>
              ))}
            </div>
            {overBudget && (
              <p className="form-error" role="alert">
                The estimate exceeds the hard cap of {maxCredits} credits.
                Increase the cap or reduce the scope, then estimate again.
              </p>
            )}
            <label className="inline-check approval-check">
              <input
                type="checkbox"
                checked={approved}
                disabled={overBudget}
                onChange={(event) => setApproved(event.target.checked)}
              />
              <span>
                <b>
                  I approve up to {estimate.estimated_total_credits} billable
                  credits
                </b>
                <small>
                  Actual credits are recorded from billable 2xx and 404
                  responses.
                </small>
              </span>
            </label>
            <button
              className="button primary launch-button"
              type="button"
              disabled={!approved || overBudget || busy !== null}
              onClick={() => void launch()}
            >
              {busy === "launch" ? "Launching…" : "Launch collection"}
            </button>
          </>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </aside>
    </div>
  );
}
