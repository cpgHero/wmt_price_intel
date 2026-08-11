"use client";

import Link from "next/link";
import {
  FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

type JsonObject = Record<string, unknown>;

interface Draft {
  id: string;
  product_pack_id: string;
  base_version: string | null;
  proposed_version: string;
  status: string;
  revision: number;
  config: JsonObject;
  report_blueprint: JsonObject;
  checksum: string;
  updated_at: string;
}

interface Evidence {
  id: string;
  kind: string;
  label: string;
  storage_uri: string;
  checksum: string;
  byte_size: number;
  row_count: number | null;
  created_at: string;
}

interface Validation {
  id: string;
  suite: "quick" | "compact" | "full" | "publication";
  status: string;
  gates: Array<{ id: string; label: string; status: string; message: string }>;
  attempt_count: number;
  last_error: string | null;
  created_at: string;
}

interface Capability {
  id: string;
  label: string;
  description: string;
  status: string;
}

interface Capabilities {
  attribute_data_types: Capability[];
  attribute_roles: Capability[];
  extraction_rules: Capability[];
  geographies: Capability[];
  brand_policies: Capability[];
  unknown_policies: Capability[];
  price_selection_policies: Capability[];
  package_equivalence_policies: Capability[];
  report_sections: Capability[];
  visualizations: Capability[];
}

const steps = [
  ["overview", "Overview"],
  ["scope", "Scope"],
  ["attributes", "Attributes"],
  ["normalization", "Normalization"],
  ["lenses", "Comparison lenses"],
  ["retailers", "Retailer catalog"],
  ["reporting", "Reporting"],
  ["certification", "Certification"],
] as const;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function rows(value: unknown): JsonObject[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is JsonObject =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
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
  if (!response.ok)
    throw new Error(
      body.error ?? body.detail ?? `Request failed (${response.status})`,
    );
  return body;
}

function compactChecksum(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function FieldNote({ children }: { children: ReactNode }) {
  return <small className="field-note">{children}</small>;
}

export function ProductPackDraftWorkspace({ draftId }: { draftId: string }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [config, setConfig] = useState<JsonObject>({});
  const [blueprint, setBlueprint] = useState<JsonObject>({});
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [validations, setValidations] = useState<Validation[]>([]);
  const [activeStep, setActiveStep] =
    useState<(typeof steps)[number][0]>("overview");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [evidenceKind, setEvidenceKind] = useState("serp");
  const [evidenceLabel, setEvidenceLabel] = useState("");
  const [evidenceUri, setEvidenceUri] = useState("");
  const [evidenceChecksum, setEvidenceChecksum] = useState("");
  const [evidenceBytes, setEvidenceBytes] = useState("");
  const [evidenceRows, setEvidenceRows] = useState("");
  const [defaultKeyword, setDefaultKeyword] = useState("");
  const [releaseNotes, setReleaseNotes] = useState("");
  const [activate, setActivate] = useState(false);

  const load = useCallback(async () => {
    const [draftValue, capabilityValue, evidenceValue, validationValue] =
      await Promise.all([
        jsonRequest<Draft>(`/api/admin/product-packs/drafts/${draftId}`),
        jsonRequest<Capabilities>("/api/admin/product-packs/capabilities"),
        jsonRequest<Evidence[]>(
          `/api/admin/product-packs/drafts/${draftId}/evidence`,
        ),
        jsonRequest<Validation[]>(
          `/api/admin/product-packs/drafts/${draftId}/validations`,
        ),
      ]);
    setDraft(draftValue);
    setConfig(draftValue.config);
    setBlueprint(draftValue.report_blueprint);
    setCapabilities(capabilityValue);
    setEvidence(evidenceValue);
    setValidations(validationValue);
    const targetTerms = strings(object(draftValue.config.scope).target_terms);
    setDefaultKeyword((current) => current || targetTerms[0] || "");
    setDirty(false);
  }, [draftId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Unable to load the Product Pack draft.",
        ),
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (
      !validations.some((validation) =>
        ["queued", "running"].includes(validation.status),
      )
    )
      return;
    const timer = window.setTimeout(() => {
      void load().catch(() => undefined);
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [load, validations]);

  const attributes = useMemo(
    () => rows(config.attributes),
    [config.attributes],
  );
  const profiles = useMemo(
    () => rows(config.matching_profiles),
    [config.matching_profiles],
  );
  const retailerOverrides = useMemo(
    () => object(config.retailer_overrides),
    [config.retailer_overrides],
  );

  function updateConfig(key: string, value: unknown) {
    setConfig((current) => ({ ...current, [key]: value }));
    setDirty(true);
  }

  function updateNested(section: string, key: string, value: unknown) {
    setConfig((current) => ({
      ...current,
      [section]: { ...object(current[section]), [key]: value },
    }));
    setDirty(true);
  }

  function updateAttribute(index: number, key: string, value: unknown) {
    updateConfig(
      "attributes",
      attributes.map((attribute, position) =>
        position === index ? { ...attribute, [key]: value } : attribute,
      ),
    );
  }

  function updateProfile(index: number, key: string, value: unknown) {
    updateConfig(
      "matching_profiles",
      profiles.map((profile, position) =>
        position === index ? { ...profile, [key]: value } : profile,
      ),
    );
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await jsonRequest<Draft>(
        `/api/admin/product-packs/drafts/${draft.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: draft.revision,
            config,
            report_blueprint: blueprint,
            reason: "Saved from the guided Product Pack workspace",
          }),
        },
      );
      setDraft(saved);
      setConfig(saved.config);
      setBlueprint(saved.report_blueprint);
      setDirty(false);
      setNotice(
        `Revision ${saved.revision} saved. Prior revisions remain immutable.`,
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to save the draft.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function requestValidation(suite: Validation["suite"]) {
    if (dirty) {
      setError("Save the current revision before requesting validation.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await jsonRequest(
        `/api/admin/product-packs/drafts/${draftId}/validations`,
        {
          method: "POST",
          body: JSON.stringify({ suite }),
        },
      );
      setNotice(
        `${suite[0].toUpperCase()}${suite.slice(1)} validation queued without paid calls.`,
      );
      await load();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to request validation.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function cancelValidation(validation: Validation) {
    setBusy(true);
    setError(null);
    try {
      await jsonRequest(
        `/api/admin/product-packs/drafts/${draftId}/validations/${validation.id}/cancel`,
        { method: "POST", body: "{}" },
      );
      setNotice(`${validation.suite} validation cancellation requested.`);
      await load();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to cancel validation.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function attachEvidence(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await jsonRequest(`/api/admin/product-packs/drafts/${draftId}/evidence`, {
        method: "POST",
        body: JSON.stringify({
          kind: evidenceKind,
          label: evidenceLabel,
          storage_uri: evidenceUri,
          content_type: evidenceUri.endsWith(".parquet")
            ? "application/vnd.apache.parquet"
            : "text/csv",
          checksum: evidenceChecksum,
          byte_size: Number(evidenceBytes),
          row_count: evidenceRows ? Number(evidenceRows) : null,
          metadata: {
            authority:
              evidenceKind === "pdp" ? "identity" : "configured_evidence",
          },
        }),
      });
      setEvidenceLabel("");
      setEvidenceUri("");
      setEvidenceChecksum("");
      setEvidenceBytes("");
      setEvidenceRows("");
      setNotice("Immutable evidence manifest attached.");
      await load();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to attach evidence.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    const certification = validations.find(
      (validation) =>
        validation.suite === "publication" && validation.status === "passed",
    );
    if (!draft || !certification) {
      setError("A passing publication validation is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await jsonRequest(`/api/admin/product-packs/drafts/${draft.id}/publish`, {
        method: "POST",
        body: JSON.stringify({
          validation_run_id: certification.id,
          activate,
          default_keyword: defaultKeyword,
          release_notes: releaseNotes || null,
        }),
      });
      setNotice(
        `Published ${draft.product_pack_id}@${draft.proposed_version}${activate ? " and activated it for new collections" : " as an inactive immutable version"}.`,
      );
      await load();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to publish the Product Pack.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!draft || !capabilities) {
    return (
      <div className="admin-auth-card">
        <span className="section-kicker">Governed authoring workspace</span>
        <h2>
          {error
            ? "The Product Pack draft is unavailable"
            : "Loading Product Pack draft…"}
        </h2>
        <p>
          {error ??
            "Loading the immutable revision, capability registry, evidence manifests, and validation history."}
        </p>
        {error ? (
          <Link className="button secondary" href="/admin/product-packs">
            Return to Product Packs
          </Link>
        ) : null}
      </div>
    );
  }

  const scope = object(config.scope);
  const normalization = object(config.normalization);
  const reporting = object(config.reporting);
  const narrative = object(reporting.narrative_playbook);
  const decisions = object(reporting.decision_rules);
  const latestValidation = validations[0];

  return (
    <main className="product-pack-draft-page">
      <header className="product-pack-draft-header">
        <div>
          <Link className="text-link" href="/admin/product-packs">
            ← Product Packs
          </Link>
          <p className="eyebrow">Governed authoring workspace</p>
          <h1>{String(config.name ?? draft.product_pack_id)}</h1>
          <p>
            {draft.product_pack_id} · proposed v{draft.proposed_version} ·
            revision {draft.revision}
          </p>
        </div>
        <div className="product-pack-draft-actions">
          <span
            className={`status-badge ${draft.status === "certified" || draft.status === "published" ? "succeeded" : draft.status === "validating" ? "running" : "queued"}`}
          >
            {draft.status}
          </span>
          <button
            className="button primary"
            type="button"
            disabled={!dirty || busy || draft.status === "published"}
            onClick={() => void save()}
          >
            {busy ? "Working…" : dirty ? "Save new revision" : "Revision saved"}
          </button>
        </div>
      </header>

      {error ? (
        <div className="builder-alert error">
          <b>Action required</b>
          <span>{error}</span>
        </div>
      ) : null}
      {notice ? (
        <div className="builder-alert">
          <b>Workspace updated</b>
          <span>{notice}</span>
        </div>
      ) : null}

      <div className="product-pack-workspace-layout">
        <nav
          className="product-pack-step-nav"
          aria-label="Product Pack authoring stages"
        >
          {steps.map(([id, label], index) => (
            <button
              key={id}
              type="button"
              className={activeStep === id ? "active" : ""}
              onClick={() => setActiveStep(id)}
            >
              <span>{index + 1}</span>
              {label}
            </button>
          ))}
        </nav>

        <section className="product-pack-stage">
          {activeStep === "overview" ? (
            <div className="product-pack-editor-panel">
              <header>
                <span className="section-kicker">Identity</span>
                <h2>What intelligence does this pack govern?</h2>
                <p>
                  Names support people; stable IDs and versions preserve
                  reproducibility.
                </p>
              </header>
              <div className="product-pack-form-grid">
                <label>
                  <span>Name</span>
                  <input
                    value={String(config.name ?? "")}
                    onChange={(event) =>
                      updateConfig("name", event.target.value)
                    }
                  />
                </label>
                <label>
                  <span>Stable ID</span>
                  <input value={String(config.id ?? "")} disabled />
                  <FieldNote>Immutable after draft creation.</FieldNote>
                </label>
                <label>
                  <span>Version</span>
                  <input value={String(config.version ?? "")} disabled />
                  <FieldNote>
                    Published versions cannot be overwritten.
                  </FieldNote>
                </label>
                <label>
                  <span>Category family</span>
                  <input
                    value={String(config.category_family ?? "")}
                    onChange={(event) =>
                      updateConfig("category_family", event.target.value)
                    }
                  />
                </label>
                <label className="wide">
                  <span>Description</span>
                  <textarea
                    rows={4}
                    value={String(config.description ?? "")}
                    onChange={(event) =>
                      updateConfig("description", event.target.value)
                    }
                  />
                </label>
              </div>
              <div className="product-pack-integrity-strip">
                <div>
                  <span>Draft checksum</span>
                  <code>{compactChecksum(draft.checksum)}</code>
                </div>
                <div>
                  <span>Base version</span>
                  <b>{draft.base_version ?? "New category"}</b>
                </div>
                <div>
                  <span>Current validation</span>
                  <b>{latestValidation?.status ?? "Not run"}</b>
                </div>
              </div>
            </div>
          ) : null}

          {activeStep === "scope" ? (
            <div className="product-pack-editor-panel">
              <header>
                <span className="section-kicker">Admission rules</span>
                <h2>Define what belongs in the analysis</h2>
                <p>
                  Scope decisions occur before matching. Labeled product
                  evidence will measure whether these rules admit the right
                  products.
                </p>
              </header>
              <div className="product-pack-form-grid">
                <label className="wide">
                  <span>Target terms · one per line</span>
                  <textarea
                    rows={5}
                    value={strings(scope.target_terms).join("\n")}
                    onChange={(event) =>
                      updateNested(
                        "scope",
                        "target_terms",
                        lines(event.target.value),
                      )
                    }
                  />
                </label>
                <label className="wide">
                  <span>Supporting include terms</span>
                  <textarea
                    rows={4}
                    value={strings(scope.include).join("\n")}
                    onChange={(event) =>
                      updateNested(
                        "scope",
                        "include",
                        lines(event.target.value),
                      )
                    }
                  />
                </label>
                <label className="wide">
                  <span>Exclusions</span>
                  <textarea
                    rows={5}
                    value={strings(scope.exclude).join("\n")}
                    onChange={(event) =>
                      updateNested(
                        "scope",
                        "exclude",
                        lines(event.target.value),
                      )
                    }
                  />
                </label>
                <label className="wide">
                  <span>Hard exclusion patterns</span>
                  <textarea
                    rows={4}
                    value={strings(scope.hard_exclusion_patterns).join("\n")}
                    onChange={(event) =>
                      updateNested(
                        "scope",
                        "hard_exclusion_patterns",
                        lines(event.target.value),
                      )
                    }
                  />
                  <FieldNote>
                    Patterns are compiled and length-bounded during
                    certification.
                  </FieldNote>
                </label>
                <label>
                  <span>Availability authority</span>
                  <select
                    value={String(
                      scope.availability_policy ?? "search_presence",
                    )}
                    onChange={(event) =>
                      updateNested(
                        "scope",
                        "availability_policy",
                        event.target.value,
                      )
                    }
                  >
                    <option value="search_presence">Observed in search</option>
                    <option value="in_stock_only">Explicitly in stock</option>
                    <option value="retailer_specific">
                      Retailer-specific policy
                    </option>
                  </select>
                </label>
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={Boolean(scope.require_positive_price)}
                    onChange={(event) =>
                      updateNested(
                        "scope",
                        "require_positive_price",
                        event.target.checked,
                      )
                    }
                  />
                  <span>Require a positive search price</span>
                </label>
              </div>
            </div>
          ) : null}

          {activeStep === "attributes" ? (
            <div className="product-pack-editor-panel">
              <header>
                <span className="section-kicker">Product meaning</span>
                <h2>Define the attributes that make products comparable</h2>
                <p>
                  PDP may complete identity and package semantics. Search
                  remains authoritative for store price and availability.
                </p>
                <button
                  className="button secondary"
                  type="button"
                  onClick={() =>
                    updateConfig("attributes", [
                      ...attributes,
                      {
                        name: `attribute_${attributes.length + 1}`,
                        label: "New attribute",
                        data_type: "string",
                        role: "matching",
                        required_for_strict: false,
                        unknown_policy: "review",
                        extractors: ["manual"],
                        extraction_rules: [],
                      },
                    ])
                  }
                >
                  Add attribute
                </button>
              </header>
              <div className="product-pack-attribute-list">
                {attributes.map((attribute, index) => {
                  const extractionRules = rows(attribute.extraction_rules);
                  return (
                    <article key={`${String(attribute.name)}-${index}`}>
                      <div className="attribute-card-heading">
                        <span>{index + 1}</span>
                        <div>
                          <input
                            aria-label="Attribute label"
                            value={String(attribute.label ?? "")}
                            onChange={(event) =>
                              updateAttribute(
                                index,
                                "label",
                                event.target.value,
                              )
                            }
                          />
                          <code>{String(attribute.name)}</code>
                        </div>
                        <button
                          type="button"
                          className="text-link danger"
                          onClick={() =>
                            updateConfig(
                              "attributes",
                              attributes.filter(
                                (_, position) => position !== index,
                              ),
                            )
                          }
                        >
                          Remove
                        </button>
                      </div>
                      <div className="product-pack-form-grid compact">
                        <label>
                          <span>Stable name</span>
                          <input
                            value={String(attribute.name ?? "")}
                            onChange={(event) =>
                              updateAttribute(
                                index,
                                "name",
                                event.target.value
                                  .toLowerCase()
                                  .replace(/[^a-z0-9_]/g, "_"),
                              )
                            }
                          />
                        </label>
                        <label>
                          <span>Data type</span>
                          <select
                            value={String(attribute.data_type ?? "string")}
                            onChange={(event) =>
                              updateAttribute(
                                index,
                                "data_type",
                                event.target.value,
                              )
                            }
                          >
                            {capabilities.attribute_data_types
                              .filter((item) => item.status === "available")
                              .map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.label}
                                </option>
                              ))}
                          </select>
                        </label>
                        <label>
                          <span>Role</span>
                          <select
                            value={String(attribute.role ?? "matching")}
                            onChange={(event) =>
                              updateAttribute(index, "role", event.target.value)
                            }
                          >
                            {capabilities.attribute_roles.map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>Unit</span>
                          <input
                            value={String(attribute.unit ?? "")}
                            onChange={(event) =>
                              updateAttribute(
                                index,
                                "unit",
                                event.target.value || undefined,
                              )
                            }
                            placeholder="oz, lb, count…"
                          />
                        </label>
                        <label>
                          <span>Unknown handling</span>
                          <select
                            value={String(attribute.unknown_policy ?? "review")}
                            onChange={(event) =>
                              updateAttribute(
                                index,
                                "unknown_policy",
                                event.target.value,
                              )
                            }
                          >
                            <option value="reject_strict">
                              Reject strict match
                            </option>
                            <option value="allow_compatible">
                              Allow compatible lens
                            </option>
                            <option value="infer">
                              Infer deterministically
                            </option>
                            <option value="review">Require review</option>
                            <option value="not_applicable">
                              Not applicable
                            </option>
                          </select>
                        </label>
                        <label className="inline-check">
                          <input
                            type="checkbox"
                            checked={Boolean(attribute.required_for_strict)}
                            onChange={(event) =>
                              updateAttribute(
                                index,
                                "required_for_strict",
                                event.target.checked,
                              )
                            }
                          />
                          <span>Required for strict matching</span>
                        </label>
                      </div>
                      <div className="extraction-rule-strip">
                        <div>
                          <b>{extractionRules.length} extraction rules</b>
                          <span>
                            {extractionRules
                              .map((rule) => String(rule.type))
                              .join(" · ") || "Manual evidence only"}
                          </span>
                        </div>
                        <button
                          type="button"
                          className="button tertiary"
                          onClick={() =>
                            updateAttribute(index, "extraction_rules", [
                              ...extractionRules,
                              { type: "field", sources: ["title"] },
                            ])
                          }
                        >
                          Add source-field rule
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>
          ) : null}

          {activeStep === "normalization" ? (
            <div className="product-pack-editor-panel">
              <header>
                <span className="section-kicker">Comparable value</span>
                <h2>
                  Choose how value is expressed without changing source price
                </h2>
                <p>
                  Safe formulas create derived metrics. They never overwrite the
                  observed SERP price.
                </p>
              </header>
              <div className="product-pack-form-grid">
                <label>
                  <span>Primary display metric</span>
                  <input
                    value={String(normalization.primary_display_metric ?? "")}
                    onChange={(event) =>
                      updateNested(
                        "normalization",
                        "primary_display_metric",
                        event.target.value,
                      )
                    }
                  />
                </label>
                <label>
                  <span>Package equivalence</span>
                  <select
                    value={String(
                      normalization.package_equivalence_policy ??
                        "exact_package_first",
                    )}
                    onChange={(event) =>
                      updateNested(
                        "normalization",
                        "package_equivalence_policy",
                        event.target.value,
                      )
                    }
                  >
                    {capabilities.package_equivalence_policies
                      .filter((item) => item.status === "available")
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                  </select>
                </label>
                <label className="wide">
                  <span>Secondary metrics · one per line</span>
                  <textarea
                    rows={3}
                    value={strings(normalization.secondary_metrics).join("\n")}
                    onChange={(event) =>
                      updateNested(
                        "normalization",
                        "secondary_metrics",
                        lines(event.target.value),
                      )
                    }
                  />
                </label>
                <label className="wide">
                  <span>Forbidden metrics · one per line</span>
                  <textarea
                    rows={3}
                    value={strings(normalization.forbidden_metrics).join("\n")}
                    onChange={(event) =>
                      updateNested(
                        "normalization",
                        "forbidden_metrics",
                        lines(event.target.value),
                      )
                    }
                  />
                  <FieldNote>
                    Useful when a familiar unit would create misleading category
                    comparisons.
                  </FieldNote>
                </label>
              </div>
              <div className="conversion-rule-list">
                <h3>Safe conversion formulas</h3>
                {rows(normalization.conversion_rules).length ? (
                  rows(normalization.conversion_rules).map((rule, index) => (
                    <article key={index}>
                      <code>
                        {String(rule.from)} → {String(rule.to)}
                      </code>
                      <b>{String(rule.formula)}</b>
                    </article>
                  ))
                ) : (
                  <div className="positive-empty-state">
                    <span>—</span>
                    <div>
                      <b>No derived conversion is configured</b>
                      <p>
                        Package price remains the authoritative display metric.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : null}

          {activeStep === "lenses" ? (
            <div className="product-pack-editor-panel">
              <header>
                <span className="section-kicker">Eligibility</span>
                <h2>Define each comparison lens explicitly</h2>
                <p>
                  A lens answers one comparison question. Products may
                  participate in several lenses while governed relationships
                  remain one-to-one within a lens.
                </p>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() =>
                    updateConfig("matching_profiles", [
                      ...profiles,
                      {
                        id: `profile_${profiles.length + 1}`,
                        label: "New comparison lens",
                        geography: "exact_zip",
                        dimensions: [],
                        brand_policy: "ignore_brand",
                        unknown_policy: "reject",
                        price_selection: "lowest_positive",
                        comparison_metric: String(
                          normalization.primary_display_metric ??
                            "package_price",
                        ),
                        availability_policy: "search_presence",
                      },
                    ])
                  }
                >
                  Add comparison lens
                </button>
              </header>
              <div className="comparison-lens-editor-list">
                {profiles.map((profile, index) => (
                  <article key={`${String(profile.id)}-${index}`}>
                    <header>
                      <div>
                        <span>Lens {index + 1}</span>
                        <input
                          value={String(profile.label ?? "")}
                          onChange={(event) =>
                            updateProfile(index, "label", event.target.value)
                          }
                        />
                      </div>
                      <button
                        type="button"
                        className="text-link danger"
                        onClick={() =>
                          updateConfig(
                            "matching_profiles",
                            profiles.filter(
                              (_, position) => position !== index,
                            ),
                          )
                        }
                      >
                        Remove
                      </button>
                    </header>
                    <div className="product-pack-form-grid compact">
                      <label>
                        <span>Stable ID</span>
                        <input
                          value={String(profile.id ?? "")}
                          onChange={(event) =>
                            updateProfile(
                              index,
                              "id",
                              event.target.value
                                .toLowerCase()
                                .replace(/[^a-z0-9_]/g, "_"),
                            )
                          }
                        />
                      </label>
                      <label>
                        <span>Geography</span>
                        <select
                          value={String(profile.geography ?? "exact_zip")}
                          onChange={(event) =>
                            updateProfile(
                              index,
                              "geography",
                              event.target.value,
                            )
                          }
                        >
                          {capabilities.geographies.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Brand policy</span>
                        <select
                          value={String(profile.brand_policy ?? "ignore_brand")}
                          onChange={(event) =>
                            updateProfile(
                              index,
                              "brand_policy",
                              event.target.value,
                            )
                          }
                        >
                          {capabilities.brand_policies
                            .filter((item) => item.status === "available")
                            .map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.label}
                              </option>
                            ))}
                        </select>
                      </label>
                      <label>
                        <span>Unknown policy</span>
                        <select
                          value={String(profile.unknown_policy ?? "reject")}
                          onChange={(event) =>
                            updateProfile(
                              index,
                              "unknown_policy",
                              event.target.value,
                            )
                          }
                        >
                          {capabilities.unknown_policies.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Price selection</span>
                        <select
                          value={String(
                            profile.price_selection ?? "lowest_positive",
                          )}
                          onChange={(event) =>
                            updateProfile(
                              index,
                              "price_selection",
                              event.target.value,
                            )
                          }
                        >
                          {capabilities.price_selection_policies.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Comparison metric</span>
                        <input
                          value={String(profile.comparison_metric ?? "")}
                          onChange={(event) =>
                            updateProfile(
                              index,
                              "comparison_metric",
                              event.target.value,
                            )
                          }
                        />
                      </label>
                      <label className="wide">
                        <span>Matching dimensions · comma separated</span>
                        <input
                          value={strings(profile.dimensions).join(", ")}
                          onChange={(event) =>
                            updateProfile(
                              index,
                              "dimensions",
                              event.target.value
                                .split(",")
                                .map((item) => item.trim())
                                .filter(Boolean),
                            )
                          }
                        />
                        <FieldNote>
                          Available:{" "}
                          {attributes
                            .map((attribute) => String(attribute.name))
                            .join(", ")}
                        </FieldNote>
                      </label>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {activeStep === "retailers" ? (
            <div className="product-pack-editor-panel">
              <header>
                <span className="section-kicker">Curated evidence</span>
                <h2>Review retailer-specific scope and attribute decisions</h2>
                <p>
                  Overrides handle known product IDs deterministically. Unseen
                  products continue through generic rules and review conditions.
                </p>
              </header>
              <div className="retailer-override-grid">
                {Object.entries(retailerOverrides).map(
                  ([retailerId, rawOverride]) => {
                    const override = object(rawOverride);
                    const products = object(override.products);
                    const included = Object.values(products).filter(
                      (raw) => object(raw).scope === "include",
                    ).length;
                    const excluded = Object.values(products).filter(
                      (raw) => object(raw).scope === "exclude",
                    ).length;
                    return (
                      <article key={retailerId}>
                        <header>
                          <div>
                            <span className="status-badge succeeded">
                              Configured
                            </span>
                            <h3>{retailerId.replaceAll("_", " ")}</h3>
                          </div>
                          <strong>
                            {Object.keys(products).length.toLocaleString()}
                          </strong>
                        </header>
                        <dl>
                          <div>
                            <dt>Included</dt>
                            <dd>{included.toLocaleString()}</dd>
                          </div>
                          <div>
                            <dt>Excluded</dt>
                            <dd>{excluded.toLocaleString()}</dd>
                          </div>
                          <div>
                            <dt>Policy</dt>
                            <dd>
                              {String(
                                override.catalog_policy ?? "rule fallback",
                              )}
                            </dd>
                          </div>
                        </dl>
                        <details>
                          <summary>Preview governed products</summary>
                          <div className="retailer-product-preview">
                            {Object.entries(products)
                              .slice(0, 20)
                              .map(([productId, rawRule]) => (
                                <div key={productId}>
                                  <code>{productId}</code>
                                  <span
                                    className={`status-badge ${object(rawRule).scope === "include" ? "succeeded" : "cancelled"}`}
                                  >
                                    {String(object(rawRule).scope ?? "review")}
                                  </span>
                                  <small>
                                    {
                                      Object.keys(
                                        object(object(rawRule).attributes),
                                      ).length
                                    }{" "}
                                    attributes
                                  </small>
                                </div>
                              ))}
                          </div>
                        </details>
                      </article>
                    );
                  },
                )}
                {!Object.keys(retailerOverrides).length ? (
                  <div className="positive-empty-state">
                    <span>✓</span>
                    <div>
                      <b>No retailer overrides</b>
                      <p>
                        All products currently use the generic scope and
                        extraction rules.
                      </p>
                    </div>
                  </div>
                ) : null}
              </div>
              <div className="builder-alert">
                <b>Large catalogs stay manageable</b>
                <span>
                  Bulk CSV import/export and virtualized product review will use
                  the same override contract; full evidence files remain in the
                  private bucket.
                </span>
              </div>
            </div>
          ) : null}

          {activeStep === "reporting" ? (
            <div className="product-pack-editor-panel">
              <header>
                <span className="section-kicker">Decision communication</span>
                <h2>Shape the questions—not the answers</h2>
                <p>
                  The Product Pack selects evidence and narrative questions.
                  Deterministic metrics and governed AI produce the eventual
                  answer.
                </p>
              </header>
              <div className="product-pack-form-grid">
                <label className="wide">
                  <span>Leadership objective</span>
                  <textarea
                    rows={4}
                    value={String(narrative.leadership_objective ?? "")}
                    onChange={(event) =>
                      updateNested("reporting", "narrative_playbook", {
                        ...narrative,
                        leadership_objective: event.target.value,
                      })
                    }
                  />
                </label>
                <label className="wide">
                  <span>Headline segments · one per line</span>
                  <textarea
                    rows={4}
                    value={strings(reporting.headline_segments).join("\n")}
                    onChange={(event) =>
                      updateNested(
                        "reporting",
                        "headline_segments",
                        lines(event.target.value),
                      )
                    }
                  />
                </label>
                <label className="wide">
                  <span>Required caveats · one per line</span>
                  <textarea
                    rows={5}
                    value={strings(reporting.required_caveats).join("\n")}
                    onChange={(event) =>
                      updateNested(
                        "reporting",
                        "required_caveats",
                        lines(event.target.value),
                      )
                    }
                  />
                </label>
                <label>
                  <span>Minimum observations</span>
                  <input
                    type="number"
                    min="1"
                    value={Number(decisions.minimum_observations ?? 1)}
                    onChange={(event) =>
                      updateNested("reporting", "decision_rules", {
                        ...decisions,
                        minimum_observations: Number(event.target.value),
                      })
                    }
                  />
                </label>
                <label>
                  <span>Minimum geographies</span>
                  <input
                    type="number"
                    min="1"
                    value={Number(decisions.minimum_geographies ?? 1)}
                    onChange={(event) =>
                      updateNested("reporting", "decision_rules", {
                        ...decisions,
                        minimum_geographies: Number(event.target.value),
                      })
                    }
                  />
                </label>
              </div>
              <div className="report-blueprint-summary">
                <div>
                  <span>Blueprint</span>
                  <b>
                    {String(blueprint.id)} · v{String(blueprint.version)}
                  </b>
                </div>
                <div>
                  <span>Application sections</span>
                  <b>{rows(blueprint.sections).length}</b>
                </div>
                <div>
                  <span>Artifact profiles</span>
                  <b>{rows(blueprint.artifact_profiles).length}</b>
                </div>
                <div>
                  <span>Insight rules</span>
                  <b>{rows(reporting.insight_rules).length}</b>
                </div>
              </div>
              <div className="report-section-preview">
                {rows(blueprint.sections).map((section) => (
                  <article key={String(section.id)}>
                    <span>{String(section.kind).replaceAll("_", " ")}</span>
                    <b>{String(section.title)}</b>
                    <small>
                      {String(section.visualization ?? "none").replaceAll(
                        "_",
                        " ",
                      )}
                    </small>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {activeStep === "certification" ? (
            <div className="product-pack-editor-panel certification-panel">
              <header>
                <span className="section-kicker">Release integrity</span>
                <h2>Prove the pack before it reaches a collection</h2>
                <p>
                  Validation is checksum-bound, leased, retry-safe, and free of
                  provider calls. Published versions are immutable.
                </p>
              </header>
              <section className="certification-evidence">
                <h3>Evidence manifests</h3>
                <form onSubmit={attachEvidence}>
                  <label>
                    <span>Evidence kind</span>
                    <select
                      value={evidenceKind}
                      onChange={(event) => setEvidenceKind(event.target.value)}
                    >
                      <option value="serp">Representative SERP</option>
                      <option value="pdp">PDP identity</option>
                      <option value="classification">Scope labels</option>
                      <option value="attribute">Attribute labels</option>
                      <option value="comparison">Comparison labels</option>
                      <option value="compact_golden">Compact golden</option>
                      <option value="full_golden">Full-source golden</option>
                    </select>
                  </label>
                  <label>
                    <span>Label</span>
                    <input
                      value={evidenceLabel}
                      onChange={(event) => setEvidenceLabel(event.target.value)}
                      required
                    />
                  </label>
                  <label className="wide">
                    <span>Private storage URI</span>
                    <input
                      value={evidenceUri}
                      onChange={(event) => setEvidenceUri(event.target.value)}
                      placeholder="s3://bucket/product-pack-authoring/…"
                      required
                    />
                  </label>
                  <label className="wide">
                    <span>SHA-256</span>
                    <input
                      value={evidenceChecksum}
                      onChange={(event) =>
                        setEvidenceChecksum(event.target.value.toLowerCase())
                      }
                      pattern="[a-f0-9]{64}"
                      required
                    />
                  </label>
                  <label>
                    <span>File size in bytes</span>
                    <input
                      type="number"
                      min="0"
                      value={evidenceBytes}
                      onChange={(event) => setEvidenceBytes(event.target.value)}
                      required
                    />
                  </label>
                  <label>
                    <span>Rows</span>
                    <input
                      type="number"
                      min="0"
                      value={evidenceRows}
                      onChange={(event) => setEvidenceRows(event.target.value)}
                    />
                  </label>
                  <button className="button secondary" disabled={busy}>
                    Attach manifest
                  </button>
                </form>
                <div className="evidence-manifest-list">
                  {evidence.map((item) => (
                    <article key={item.id}>
                      <span className="status-badge succeeded">
                        {item.kind.replaceAll("_", " ")}
                      </span>
                      <div>
                        <b>{item.label}</b>
                        <code>{compactChecksum(item.checksum)}</code>
                      </div>
                      <strong>
                        {item.row_count?.toLocaleString() ?? "—"} rows
                      </strong>
                    </article>
                  ))}
                </div>
              </section>
              <section className="validation-suite-grid">
                <h3>Certification suites</h3>
                <div>
                  {(["quick", "compact", "full", "publication"] as const).map(
                    (suite) => {
                      const latest = validations.find(
                        (validation) => validation.suite === suite,
                      );
                      return (
                        <article key={suite}>
                          <span>{suite}</span>
                          <strong>{latest?.status ?? "Not run"}</strong>
                          <p>
                            {suite === "quick"
                              ? "Contracts, references, formulas, and capability safety."
                              : suite === "compact"
                                ? "Quick gates plus compact golden evidence."
                                : suite === "full"
                                  ? "Full-source manifest and regression identity."
                                  : "Exact revision release gate."}
                          </p>
                          <button
                            className="button tertiary"
                            type="button"
                            disabled={
                              busy || dirty || draft.status === "published"
                            }
                            onClick={() => void requestValidation(suite)}
                          >
                            {latest?.status === "queued" ||
                            latest?.status === "running"
                              ? "Running…"
                              : "Run suite"}
                          </button>
                          {latest &&
                          ["queued", "running"].includes(latest.status) ? (
                            <button
                              className="text-link danger"
                              type="button"
                              disabled={busy}
                              onClick={() => void cancelValidation(latest)}
                            >
                              Cancel validation
                            </button>
                          ) : null}
                        </article>
                      );
                    },
                  )}
                </div>
              </section>
              <section className="validation-history">
                <h3>Latest gate results</h3>
                {latestValidation?.gates.length ? (
                  latestValidation.gates.map((gate) => (
                    <article key={gate.id} className={gate.status}>
                      <span>
                        {gate.status === "passed"
                          ? "✓"
                          : gate.status === "warning"
                            ? "!"
                            : "×"}
                      </span>
                      <div>
                        <b>{gate.label}</b>
                        <p>{gate.message}</p>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="positive-empty-state">
                    <span>—</span>
                    <div>
                      <b>No validation results yet</b>
                      <p>
                        Start with the quick suite after saving the current
                        revision.
                      </p>
                    </div>
                  </div>
                )}
              </section>
              <section className="publication-gate">
                <h3>Publish immutable version</h3>
                <div className="product-pack-form-grid">
                  <label>
                    <span>Default collection keyword</span>
                    <input
                      value={defaultKeyword}
                      onChange={(event) =>
                        setDefaultKeyword(event.target.value)
                      }
                    />
                  </label>
                  <label className="wide">
                    <span>Release notes</span>
                    <textarea
                      rows={3}
                      value={releaseNotes}
                      onChange={(event) => setReleaseNotes(event.target.value)}
                    />
                  </label>
                  <label className="inline-check">
                    <input
                      type="checkbox"
                      checked={activate}
                      onChange={(event) => setActivate(event.target.checked)}
                    />
                    <span>Activate for new collection definitions</span>
                  </label>
                </div>
                <button
                  className="button primary"
                  type="button"
                  disabled={
                    busy ||
                    dirty ||
                    draft.status !== "certified" ||
                    !defaultKeyword
                  }
                  onClick={() => void publish()}
                >
                  {draft.status === "published"
                    ? "Version published"
                    : activate
                      ? "Publish and activate"
                      : "Publish inactive version"}
                </button>
                <FieldNote>
                  Existing collection definitions stay pinned to their original
                  Product Pack version.
                </FieldNote>
              </section>
            </div>
          ) : null}
        </section>

        <aside className="product-pack-health-rail">
          <span className="section-kicker">Draft health</span>
          <dl>
            <div>
              <dt>Attributes</dt>
              <dd>{attributes.length}</dd>
            </div>
            <div>
              <dt>Comparison lenses</dt>
              <dd>{profiles.length}</dd>
            </div>
            <div>
              <dt>Retailer catalogs</dt>
              <dd>{Object.keys(retailerOverrides).length}</dd>
            </div>
            <div>
              <dt>Evidence sets</dt>
              <dd>{evidence.length}</dd>
            </div>
          </dl>
          <div className="health-rail-status">
            <span>Revision state</span>
            <b>{dirty ? "Unsaved changes" : "Checksum locked"}</b>
            <small>
              {dirty
                ? "Save before validation."
                : compactChecksum(draft.checksum)}
            </small>
          </div>
          <div className="health-rail-rule">
            <b>Authority boundary</b>
            <p>
              Search owns price and store presence. PDP supports identity.
              Deterministic code owns metrics and match eligibility.
            </p>
          </div>
          <details>
            <summary>Available generic capabilities</summary>
            <p>
              {capabilities.extraction_rules
                .filter((item) => item.status === "available")
                .map((item) => item.label)
                .join(" · ")}
            </p>
          </details>
        </aside>
      </div>
    </main>
  );
}
