"use client";

import { useState } from "react";

import { DataTable } from "@/app/components/data-table";
import type {
  AnalysisRecord,
  AnalysisReportView,
  JsonObject,
  ReportSectionView,
} from "@/lib/api";
import {
  asObject,
  asRows,
  displayDate,
  displayLabel,
  displayValue,
} from "@/lib/presentation";
import {
  formatMetric,
  groupReportSections,
  metricBarWidth,
} from "@/lib/report-presentation";

const tabs = [
  "Executive Summary",
  "Geographic Coverage",
  "Price Position",
  "Segment Analysis",
  "Product Matches",
  "Assortment",
  "Data Quality / QA",
  "Methodology",
  "Exports",
] as const;

type Tab = (typeof tabs)[number];

export function AnalysisWorkspace({
  analysis,
  reportView,
}: Readonly<{
  analysis: AnalysisRecord;
  reportView: AnalysisReportView | null;
}>) {
  return reportView ? (
    <BlueprintAnalysisWorkspace analysis={analysis} reportView={reportView} />
  ) : (
    <LegacyAnalysisWorkspace analysis={analysis} />
  );
}

function LegacyAnalysisWorkspace({
  analysis,
}: Readonly<{ analysis: AnalysisRecord }>) {
  const [activeTab, setActiveTab] = useState<Tab>(tabs[0]);
  const result = analysis.result as unknown as JsonObject;
  const productPack = asObject(result.product_pack);
  const validation = asObject(result.validation);
  return (
    <>
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Analysis workspace</p>
          <h1>
            {displayLabel(String(productPack.id ?? analysis.product_pack_id))}
          </h1>
          <p className="workspace-meta">
            {analysis.analysis_id} · Generated{" "}
            {displayDate(String(result.generated_at))}
          </p>
        </div>
        <div className="workspace-status">
          <span className={`status-badge ${analysis.status}`}>
            {displayLabel(analysis.status)}
          </span>
          <small>Schema {analysis.schema_version}</small>
        </div>
      </header>
      <div className="tab-list" role="tablist" aria-label="Analysis sections">
        {tabs.map((tab) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "active" : ""}
            onClick={() => setActiveTab(tab)}
            key={tab}
          >
            {tab}
          </button>
        ))}
      </div>
      <section className="workspace-panel" role="tabpanel">
        {activeTab === "Executive Summary" && (
          <ExecutiveSummary result={result} validation={validation} />
        )}
        {activeTab === "Geographic Coverage" && (
          <Section
            title="Geographic coverage"
            note="Fresh ZIP and store coverage supplied by the canonical result."
          >
            <DataTable rows={asRows(result.coverage)} />
          </Section>
        )}
        {activeTab === "Price Position" && (
          <Section
            title="Price position"
            note="Persisted competitive metrics by retailer and segment."
          >
            <DataTable rows={asRows(result.comparisons)} />
          </Section>
        )}
        {activeTab === "Segment Analysis" && (
          <>
            <Section
              title="Configured segments"
              note="Product Pack attributes that define comparable groups."
            >
              <DataTable rows={asRows(result.segments)} />
            </Section>
            <Section title="Segment outcomes">
              <DataTable rows={asRows(result.comparisons)} />
            </Section>
          </>
        )}
        {activeTab === "Product Matches" && (
          <MatchDrilldown
            comparisons={asRows(result.comparisons)}
            provenance={asObject(result.provenance)}
          />
        )}
        {activeTab === "Assortment" && (
          <>
            <Section
              title="Source assortment"
              note="Collection inputs and available canonical segment detail."
            >
              <ObjectGrid value={asObject(result.source_summary)} />
            </Section>
            <Section title="Classified segments">
              <DataTable rows={asRows(result.segments)} />
            </Section>
          </>
        )}
        {activeTab === "Data Quality / QA" && (
          <>
            <Section
              title="Data quality"
              note="Authoritative flags emitted by the analytics pipeline."
            >
              <ObjectGrid value={asObject(result.data_quality)} />
            </Section>
            <Section title="Validation evidence">
              <ObjectGrid value={validation} />
              <DataTable rows={asRows(validation.checks)} />
            </Section>
          </>
        )}
        {activeTab === "Methodology" && (
          <>
            <Section title="Product Pack">
              <ObjectGrid value={productPack} />
            </Section>
            <Section
              title="Provenance"
              note="Source and benchmark lineage persisted with this result."
            >
              <ObjectGrid value={asObject(result.provenance)} />
            </Section>
          </>
        )}
        {activeTab === "Exports" && (
          <Section
            title="Delivery artifacts"
            note="Generated from this immutable AnalysisResult; renderers do not recalculate metrics."
          >
            <ArtifactActions analysisId={analysis.analysis_id} />
          </Section>
        )}
      </section>
    </>
  );
}

function BlueprintAnalysisWorkspace({
  analysis,
  reportView,
}: Readonly<{
  analysis: AnalysisRecord;
  reportView: AnalysisReportView;
}>) {
  const groupedSections = groupReportSections(reportView.sections);
  const firstPopulatedGroup =
    groupedSections.find((group) => group.sections.length > 0)?.id ?? "summary";
  const [activeGroup, setActiveGroup] = useState<string>(firstPopulatedGroup);
  const selectedGroup = groupedSections.find(
    (group) => group.id === activeGroup,
  );
  return (
    <>
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Analysis workspace</p>
          <h1>{reportView.product_pack.name}</h1>
          <p className="workspace-meta">
            {analysis.analysis_id} · Generated{" "}
            {displayDate(reportView.generated_at)}
          </p>
          <div className="trust-strip" aria-label="Result integrity">
            <span>Deterministic metrics</span>
            <span>Evidence linked</span>
            <span title={analysis.checksum}>
              Checksum {analysis.checksum.slice(0, 12)}…
            </span>
          </div>
        </div>
        <div className="workspace-status">
          <span className={`status-badge ${analysis.status}`}>
            {displayLabel(analysis.status)}
          </span>
          <small>
            Blueprint {reportView.blueprint.id} · {reportView.blueprint.version}
          </small>
        </div>
      </header>
      <div className="tab-list" role="tablist" aria-label="Analysis sections">
        {groupedSections.map((group) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeGroup === group.id}
            className={activeGroup === group.id ? "active" : ""}
            onClick={() => setActiveGroup(group.id)}
            key={group.id}
          >
            {group.label}
          </button>
        ))}
        <button
          type="button"
          role="tab"
          aria-selected={activeGroup === "exports"}
          className={activeGroup === "exports" ? "active" : ""}
          onClick={() => setActiveGroup("exports")}
        >
          Exports
        </button>
      </div>
      <section className="workspace-panel" role="tabpanel">
        {activeGroup === "exports" ? (
          <Section
            title="Delivery artifacts"
            note="Every format presents the same immutable AnalysisResult and carries its shared result checksum."
          >
            <ArtifactActions analysisId={analysis.analysis_id} />
          </Section>
        ) : selectedGroup && selectedGroup.sections.length > 0 ? (
          selectedGroup.sections.map((section) => (
            <BlueprintSection section={section} key={section.id} />
          ))
        ) : (
          <Section
            title={selectedGroup?.label ?? "Analysis section"}
            note="This Product Pack does not define content for this workspace section."
          >
            <p className="empty-copy">
              No decision-ready records were supplied for this section.
            </p>
          </Section>
        )}
      </section>
    </>
  );
}

function BlueprintSection({
  section,
}: Readonly<{ section: ReportSectionView }>) {
  const narrative = asObject(section.narrative);
  const metricValues = section.metrics.map((metric) => metric.value);
  return (
    <Section
      title={section.title}
      note={`${displayLabel(section.kind)} · ${displayLabel(section.visualization)}`}
    >
      {narrative.body ? (
        <p className="section-narrative">{displayValue(narrative.body)}</p>
      ) : null}
      {section.metrics.length > 0 && section.visualization === "bar" ? (
        <div className="metric-bars" aria-label={`${section.title} metrics`}>
          {section.metrics.map((metric) => (
            <div className="metric-bar" key={String(metric.metric_id)}>
              <div>
                <span>{String(metric.name)}</span>
                <strong>{formatMetric(metric.value, metric.unit)}</strong>
              </div>
              <i aria-hidden="true">
                <b
                  style={{
                    width: `${metricBarWidth(metric.value, metricValues)}%`,
                  }}
                />
              </i>
            </div>
          ))}
        </div>
      ) : section.metrics.length > 0 ? (
        <div className="metric-grid">
          {section.metrics.map((metric) => (
            <Metric
              key={String(metric.metric_id)}
              label={String(metric.name)}
              value={formatMetric(metric.value, metric.unit)}
            />
          ))}
        </div>
      ) : null}
      {section.records.length > 0 &&
      section.visualization === "ranked_cards" ? (
        <DecisionCards rows={section.records} />
      ) : section.records.length > 0 && section.kind !== "kpi_strip" ? (
        <DataTable rows={section.records} />
      ) : null}
      {section.evidence_sets.length > 0 ? (
        <details className="evidence-disclosure">
          <summary>Evidence manifests</summary>
          <DataTable rows={section.evidence_sets} />
        </details>
      ) : null}
      {section.empty ? (
        <p className="empty-copy">
          {section.empty_state ?? "No records were supplied for this section."}
        </p>
      ) : null}
    </Section>
  );
}

function DecisionCards({ rows }: Readonly<{ rows: JsonObject[] }>) {
  return (
    <div className="decision-card-grid">
      {rows.map((row, index) => {
        const rank = row.priority ?? row.severity ?? index + 1;
        const headline =
          row.summary ??
          row.action ??
          row.title ??
          row.text ??
          "Decision signal";
        const detail = row.detail ?? row.rationale ?? row.description;
        return (
          <article className="decision-card" key={String(row.id ?? index)}>
            <span>{displayValue(rank)}</span>
            <h3>{displayValue(headline)}</h3>
            {detail ? <p>{displayValue(detail)}</p> : null}
          </article>
        );
      })}
    </div>
  );
}

function ExecutiveSummary({
  result,
  validation,
}: Readonly<{ result: JsonObject; validation: JsonObject }>) {
  const findings = asRows(result.findings);
  const recommendations = asRows(result.recommendations);
  const source = asObject(result.source_summary);
  return (
    <>
      <div className="metric-grid">
        <Metric label="Validation" value={validation.status} />
        <Metric label="Benchmark" value={result.benchmark_retailer} />
        <Metric label="Source rows" value={source.total_rows} />
        <Metric
          label="Competitors"
          value={
            Array.isArray(result.competitors) ? result.competitors.length : 0
          }
        />
      </div>
      <Section title="What matters">
        <div className="finding-grid">
          {findings.map((finding, index) => (
            <article className="finding" key={String(finding.id ?? index)}>
              <span>{displayValue(finding.severity)}</span>
              <p>{displayValue(finding.text)}</p>
            </article>
          ))}
        </div>
      </Section>
      <Section title="Recommended actions">
        <ol className="recommendations">
          {recommendations.map((recommendation, index) => (
            <li key={index}>
              <b>{displayValue(recommendation.priority)}</b>
              <span>{displayValue(recommendation.text)}</span>
            </li>
          ))}
        </ol>
      </Section>
    </>
  );
}

function MatchDrilldown({
  comparisons,
  provenance,
}: Readonly<{ comparisons: JsonObject[]; provenance: JsonObject }>) {
  return (
    <Section
      title="Match drilldown"
      note="One row per persisted competitor/segment comparison, with lineage alongside it."
    >
      <div className="match-grid">
        {comparisons.map((comparison, index) => (
          <article className="match-card" key={index}>
            <header>
              <span>
                {displayLabel(String(comparison.competitor_id ?? "competitor"))}
              </span>
              <b>{displayLabel(String(comparison.segment_id ?? "segment"))}</b>
            </header>
            <ObjectGrid value={comparison} />
          </article>
        ))}
      </div>
      <div className="provenance-strip">
        <b>Evidence provenance</b>
        <span>{displayValue(provenance)}</span>
      </div>
    </Section>
  );
}

function Section({
  title,
  note,
  children,
}: Readonly<{ title: string; note?: string; children: React.ReactNode }>) {
  return (
    <section className="workspace-section">
      <header>
        <div>
          <h2>{title}</h2>
          {note && <p>{note}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

function Metric({ label, value }: Readonly<{ label: string; value: unknown }>) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  );
}

function ObjectGrid({ value }: Readonly<{ value: JsonObject }>) {
  return (
    <dl className="object-grid">
      {Object.entries(value)
        .filter(([key]) => key !== "checks")
        .map(([key, item]) => (
          <div key={key}>
            <dt>{displayLabel(key)}</dt>
            <dd>{displayValue(item)}</dd>
          </div>
        ))}
    </dl>
  );
}

function ArtifactActions({ analysisId }: Readonly<{ analysisId: string }>) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const artifacts = [
    ["html", "Leadership HTML"],
    ["xlsx", "Excel audit workbook"],
    ["leadership_email", "Leadership email draft"],
    ["audit_zip", "Complete audit package"],
  ] as const;
  async function generate(type: string) {
    setBusy(type);
    setMessage("");
    try {
      const response = await fetch(
        `/api/analyses/${encodeURIComponent(analysisId)}/artifacts/${type}`,
        { method: "POST" },
      );
      const body = (await response.json()) as {
        download_url?: string;
        error?: string;
      };
      if (!response.ok || !body.download_url)
        throw new Error(body.error ?? "Artifact generation failed.");
      window.location.assign(body.download_url);
      setMessage("Artifact generated. Your secure download is opening now.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Artifact generation failed.",
      );
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="export-grid">
      {artifacts.map(([type, label]) => (
        <button
          type="button"
          onClick={() => void generate(type)}
          disabled={Boolean(busy)}
          key={type}
        >
          <span>{label}</span>
          <b>{busy === type ? "Generating…" : "Generate & download"}</b>
        </button>
      ))}
      {message && (
        <p className="action-message" role="status">
          {message}
        </p>
      )}
    </div>
  );
}
