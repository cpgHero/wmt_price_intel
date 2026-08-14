"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { GeometryCollection, Topology } from "topojson-specification";
import { feature } from "topojson-client";
import statesTopologySource from "us-atlas/states-10m.json";

import { DataTable } from "@/app/components/data-table";
import {
  type ApplicationContextDefinition,
  useApplicationContextDefinition,
} from "@/app/components/application-context";
import { ComparableCohortExplorer } from "./cohort-explorer";
import { ProductLeadershipWorkspace } from "./product-leadership-workspace";
import type {
  AnalysisRecord,
  AnalysisReportView,
  AssortmentAnalysis,
  AssortmentBrand,
  AssortmentBreadthGap,
  AssortmentProduct,
  JsonObject,
  MapPoint,
  ProductDecision,
  ProductEvidenceResponse,
  ProductHighlight,
  QualityObservation,
  ReportSectionView,
  RetailerOption,
  RetailerScorecard,
} from "@/lib/api";
import {
  asObject,
  asRows,
  displayDate,
  displayLabel,
  displayValue,
} from "@/lib/presentation";
import {
  comparisonBasisDescription,
  compactMetricName,
  formatMapValueLabel,
  formatPriceForBasis,
  formatMetric,
  governedOutcomeCounts,
  groupReportSections,
  metricBarWidth,
  priceUnitLabel,
  primaryComparisonRows,
  productDecisionStance,
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
  const router = useRouter();
  const groupedSections = useMemo(
    () => groupReportSections(reportView.sections, reportView.groups),
    [reportView.groups, reportView.sections],
  );
  const firstPopulatedGroup =
    groupedSections.find((group) => group.sections.length > 0)?.id ??
    "overview";
  const [activeGroup, setActiveGroup] = useState<string>(firstPopulatedGroup);
  const competitorOptions = reportView.retailer_scope.competitors;
  const [selectedCompetitor, setSelectedCompetitor] = useState("all");
  const preferredBasis =
    reportView.comparison_bases.find(
      (basis) => basis.scorecard_role === "preferred",
    )?.profile_id ??
    reportView.comparison_bases[0]?.profile_id ??
    "";
  const [selectedLens, setSelectedLens] = useState(preferredBasis);
  const leadershipProductOptions = useMemo(() => {
    const options = new Map<
      string,
      { id: string; name: string; imageUrl?: string | null }
    >();
    const activeCandidates = (reportView.match_candidates ?? []).filter(
      (row) =>
        (row.relationship_status === "suggested" ||
          row.relationship_status === "confirmed") &&
        (row.qa_status ?? "ready") === "ready" &&
        (selectedCompetitor === "all" ||
          row.competitor === selectedCompetitor) &&
        (!selectedLens || row.profile_id === selectedLens),
    );
    const rows = activeCandidates.length
      ? activeCandidates
      : (reportView.product_decisions ?? []).filter(
          (row) =>
            (selectedCompetitor === "all" ||
              row.competitor === selectedCompetitor) &&
            (!selectedLens ||
              !row.profile_id ||
              row.profile_id === selectedLens),
        );
    for (const row of rows) {
      options.set(row.benchmark_product_id, {
        id: row.benchmark_product_id,
        name: row.benchmark_product_name,
        imageUrl: row.benchmark_image_url,
      });
    }
    return [...options.values()];
  }, [
    reportView.match_candidates,
    reportView.product_decisions,
    selectedCompetitor,
    selectedLens,
  ]);
  const [selectedLeadershipProduct, setSelectedLeadershipProduct] = useState<
    string | null
  >(leadershipProductOptions[0]?.id ?? null);
  const [leadershipRadius, setLeadershipRadius] = useState<1 | 3 | 5>(3);
  const [leadershipState, setLeadershipState] = useState<string | null>(null);
  const [leadershipCity, setLeadershipCity] = useState<string | null>(null);
  const [leadershipStateOptions, setLeadershipStateOptions] = useState<
    { value: string; label: string; count: number }[]
  >([]);
  const [leadershipCityOptions, setLeadershipCityOptions] = useState<
    { value: string; label: string; count: number; state: string }[]
  >([]);
  useEffect(() => {
    const applyLocation = () => {
      const parameters = new URL(window.location.href).searchParams;
      const requested = parameters.get("competitor");
      setSelectedCompetitor(
        requested && competitorOptions.some((option) => option.id === requested)
          ? requested
          : "all",
      );
      const requestedTab = parameters.get("tab");
      setActiveGroup(
        requestedTab &&
          (requestedTab === "product-leadership" ||
            groupedSections.some((group) => group.id === requestedTab))
          ? requestedTab
          : firstPopulatedGroup,
      );
      const requestedLens = parameters.get("lens");
      setSelectedLens(
        requestedLens &&
          reportView.comparison_bases.some(
            (basis) => basis.profile_id === requestedLens,
          )
          ? requestedLens
          : preferredBasis,
      );
      const requestedProduct = parameters.get("product");
      setSelectedLeadershipProduct(
        requestedProduct &&
          leadershipProductOptions.some(
            (option) => option.id === requestedProduct,
          )
          ? requestedProduct
          : (leadershipProductOptions[0]?.id ?? null),
      );
      const requestedRadius = Number(parameters.get("radius") ?? 3);
      setLeadershipRadius(
        requestedRadius === 1 || requestedRadius === 5 ? requestedRadius : 3,
      );
      const requestedState = parameters.get("state");
      const requestedCity = parameters.get("city");
      setLeadershipState(requestedState || null);
      setLeadershipCity(requestedState && requestedCity ? requestedCity : null);
    };
    applyLocation();
    window.addEventListener("popstate", applyLocation);
    return () => window.removeEventListener("popstate", applyLocation);
  }, [
    competitorOptions,
    firstPopulatedGroup,
    groupedSections,
    leadershipProductOptions,
    preferredBasis,
    reportView.comparison_bases,
  ]);
  const updateRoute = (updates: Record<string, string | null>) => {
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries(updates)) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history.replaceState(window.history.state, "", url);
  };
  const selectCompetitor = (competitorId: string) => {
    const valid =
      competitorId === "all" ||
      competitorOptions.some((option) => option.id === competitorId);
    const next = valid ? competitorId : "all";
    setSelectedCompetitor(next);
    updateRoute({ competitor: next === "all" ? null : next });
  };
  const selectGroup = (groupId: string) => {
    setActiveGroup(groupId);
    updateRoute({
      tab: groupId === firstPopulatedGroup ? null : groupId,
      pair: null,
    });
  };
  const selectLens = (profileId: string) => {
    const valid = reportView.comparison_bases.some(
      (basis) => basis.profile_id === profileId,
    );
    const next = valid ? profileId : preferredBasis;
    setSelectedLens(next);
    updateRoute({ lens: next === preferredBasis ? null : next });
  };
  const receiveLeadershipGeography = useCallback(
    (
      states: { value: string; label: string; count: number }[],
      cities: { value: string; label: string; count: number; state: string }[],
    ) => {
      if (states.length) setLeadershipStateOptions(states);
      setLeadershipCityOptions(cities);
    },
    [],
  );
  const reviewDecision = (decision: ProductDecision) => {
    const pairReference =
      decision.relationship_id ||
      `${decision.benchmark_product_id}::${decision.competitor_product_id}`;
    const parameters = new URLSearchParams();
    const competitor = competitorOptions.find((option) =>
      matchesRetailer(decision.competitor, option),
    )?.id;
    if (competitor) parameters.set("competitor", competitor);
    if (decision.profile_id) parameters.set("lens", decision.profile_id);
    parameters.set("pair", pairReference);
    router.push(
      `/workspace/matches/${encodeURIComponent(analysis.analysis_id)}?${parameters.toString()}`,
    );
  };
  const openMatchWorkbench = () => {
    const parameters = new URLSearchParams();
    if (selectedCompetitor !== "all")
      parameters.set("competitor", selectedCompetitor);
    if (selectedLens) parameters.set("lens", selectedLens);
    router.push(
      `/workspace/matches/${encodeURIComponent(analysis.analysis_id)}?${parameters.toString()}`,
    );
  };
  const selectedRetailer =
    competitorOptions.find((option) => option.id === selectedCompetitor) ??
    null;
  const scopedSections = groupedSections.map((group) => ({
    ...group,
    sections: group.sections.map((section) => ({
      ...section,
      records: scopeReportRows(
        section,
        selectedRetailer,
        reportView.retailer_scope.benchmark,
        selectedLens,
      ),
      evidence_sets: scopeEvidenceRows(
        section.evidence_sets,
        selectedRetailer,
        competitorOptions,
      ),
    })),
  }));
  const selectedGroup = scopedSections.find(
    (group) => group.id === activeGroup,
  );
  const cohortRecords =
    selectedGroup?.sections
      .filter((section) => section.kind === "segment_analysis")
      .flatMap((section) => section.records) ?? [];
  const publication = reportView.publication;
  const recommendedCharts = reportView.product_pack.recommended_charts ?? [];
  const selectedScorecards = selectedRetailer
    ? reportView.retailer_scorecards.filter(
        (scorecard) => scorecard.competitor_id === selectedRetailer.id,
      )
    : reportView.retailer_scorecards;
  const selectedBasis =
    reportView.comparison_bases.find(
      (basis) => basis.profile_id === selectedLens,
    ) ?? null;
  const scopedDecisions = scopeRetailerRows(
    reportView.product_decisions ?? [],
    selectedRetailer,
    (row) => row.competitor,
  ).filter(
    (row) =>
      !selectedLens || !row.profile_id || row.profile_id === selectedLens,
  );
  const scopedPoints = scopeRetailerRows(
    reportView.map_points ?? [],
    selectedRetailer,
    (row) => row.competitor,
  ).filter(
    (row) =>
      !selectedLens || !row.profile_id || row.profile_id === selectedLens,
  );
  const scopedHighlights = scopeReferenceAndRetailerRows(
    reportView.product_highlights ?? [],
    selectedRetailer,
    reportView.retailer_scope.benchmark,
    (row) => row.retailer,
  );
  const scopedQuality = scopeReferenceAndRetailerRows(
    reportView.quality_observations ?? [],
    selectedRetailer,
    reportView.retailer_scope.benchmark,
    (row) => row.retailer,
  );
  const primaryComparisons = primaryComparisonRows(
    scopedSections.flatMap((group) => group.sections),
  );
  const visibleStatus =
    reportView.report_readiness.status === "review_required"
      ? "review_required"
      : reportView.report_readiness.status === "limited"
        ? "limited_evidence"
        : (publication?.status ?? analysis.status);
  const readiness = reportView.report_readiness;
  const contextDefinition = useMemo<ApplicationContextDefinition>(() => {
    const selectedRetailerName =
      competitorOptions.find(
        (competitor) => competitor.id === selectedCompetitor,
      )?.name ?? null;
    const readinessLabel =
      readiness.status === "ready"
        ? "Ready for decision use"
        : readiness.status === "review_required"
          ? "Match review required"
          : "Use with limitations";
    return {
      label: "Competitive report context",
      controls: [
        {
          id: "competitive-view",
          label: "Competitive View",
          title: "Choose the competitive view",
          description:
            "Scope every report tab to the complete competitor portfolio or one benchmark-versus-competitor view.",
          value: selectedRetailerName
            ? `${reportView.retailer_scope.benchmark.name} vs. ${selectedRetailerName}`
            : `${reportView.retailer_scope.benchmark.name} vs. all competitors`,
          options: [
            {
              value: "all",
              label: `All competitors (${competitorOptions.length})`,
              description: `Portfolio view across every configured competitor against ${reportView.retailer_scope.benchmark.name}.`,
            },
            ...competitorOptions.map((competitor) => ({
              value: competitor.id,
              label: `${reportView.retailer_scope.benchmark.name} vs. ${competitor.name}`,
              description:
                "Apply this retailer pair consistently to all report tabs and evidence.",
            })),
          ],
          queryParameter: "competitor",
          defaultValue: "all",
          selectedValue: selectedCompetitor,
        },
        {
          id: "comparison-basis",
          label: "Comparison Basis",
          title: "Choose the governed comparison basis",
          description:
            "Change the deterministic eligibility, geography, and price unit used by the report. This selection is persisted in the URL.",
          value: selectedBasis?.label ?? "Configured comparison basis",
          options: reportView.comparison_bases.map((basis) => ({
            value: basis.profile_id,
            label: `${basis.label}${basis.scorecard_role === "preferred" ? " · preferred" : ""}`,
            description: comparisonBasisDescription(basis),
          })),
          queryParameter: "lens",
          defaultValue: preferredBasis,
          selectedValue: selectedLens,
        },
        ...(activeGroup === "product-leadership"
          ? [
              {
                id: "benchmark-product",
                label: "Benchmark Product",
                title: `Choose the ${reportView.retailer_scope.benchmark.name} product`,
                description:
                  "Select one governed benchmark product to score at benchmark-store grain. PDP identity and imagery do not replace Search price.",
                value:
                  leadershipProductOptions.find(
                    (option) => option.id === selectedLeadershipProduct,
                  )?.name ?? "Select a product",
                options: leadershipProductOptions.map((option) => ({
                  value: option.id,
                  label: option.name,
                  description: `Benchmark product ID ${option.id}`,
                })),
                queryParameter: "product",
                selectedValue: selectedLeadershipProduct ?? undefined,
                resetQueryParameters: ["state", "city"],
              },
              {
                id: "store-radius",
                label: "Store Radius",
                title: "Choose the local competitor radius",
                description:
                  "A physical competitor store must fall inside this radius of the benchmark store. Service-area retailers use the same ZIP.",
                value: `${leadershipRadius} mile${leadershipRadius === 1 ? "" : "s"}`,
                options: ([1, 3, 5] as const).map((radius) => ({
                  value: String(radius),
                  label: `${radius} mile${radius === 1 ? "" : "s"}`,
                  description:
                    radius === 1
                      ? "Immediate local trade area."
                      : radius === 3
                        ? "Balanced neighborhood comparison."
                        : "Broader local trade area.",
                })),
                queryParameter: "radius",
                defaultValue: "3",
                selectedValue: String(leadershipRadius),
              },
              {
                id: "benchmark-geography",
                label: "Benchmark Geography",
                title: `Choose the ${reportView.retailer_scope.benchmark.name} store geography`,
                description:
                  "Scope every product-leadership workspace to all observed benchmark stores or one state. Select a state to unlock city drill-down.",
                value: leadershipState ?? "All benchmark stores",
                options: [
                  {
                    value: "all",
                    label: "All benchmark stores",
                    description:
                      "Use the complete observed benchmark footprint.",
                  },
                  ...leadershipStateOptions.map((option) => ({
                    value: option.value,
                    label: option.label,
                    description: `${option.count.toLocaleString()} observed benchmark stores`,
                  })),
                ],
                queryParameter: "state",
                defaultValue: "all",
                selectedValue: leadershipState ?? "all",
                resetQueryParameters: ["city"],
              },
              ...(leadershipState && leadershipCityOptions.length
                ? [
                    {
                      id: "benchmark-city",
                      label: "Benchmark City",
                      title: `Choose a city in ${leadershipState}`,
                      description:
                        "Optionally narrow the product-leadership workspaces to one benchmark-store city.",
                      value: leadershipCity ?? `All ${leadershipState} cities`,
                      options: [
                        {
                          value: "all",
                          label: `All ${leadershipState} cities`,
                          description: `Use every observed benchmark store in ${leadershipState}.`,
                        },
                        ...leadershipCityOptions.map((option) => ({
                          value: option.value,
                          label: option.label,
                          description: `${option.count.toLocaleString()} observed benchmark stores`,
                        })),
                      ],
                      queryParameter: "city",
                      defaultValue: "all",
                      selectedValue: leadershipCity ?? "all",
                    },
                  ]
                : []),
            ]
          : []),
        {
          id: "decision-readiness",
          label: "Decision Readiness",
          title: readinessLabel,
          description:
            "Readiness is calculated from deterministic evidence and match-governance checks. It is context, not a user-selectable status.",
          value: readinessLabel,
          tone: readiness.status === "ready" ? "ready" : "attention",
          facts: [
            {
              label: "Confirmed matches",
              value: reportView.match_governance.confirmed.toLocaleString(),
            },
            {
              label: "Suggested matches",
              value: reportView.match_governance.suggested.toLocaleString(),
            },
            {
              label: "Ambiguous matches",
              value: reportView.match_governance.ambiguous.toLocaleString(),
            },
            {
              label: "Suppressed decisions",
              value: readiness.suppressed_decisions.toLocaleString(),
            },
          ],
          messages: [
            ...readiness.blocking_reasons.map((reason) => reason.message),
            ...readiness.warnings.map((warning) => warning.message),
          ],
          action: reportView.match_governance.ambiguous
            ? {
                label: `Review ${reportView.match_governance.ambiguous.toLocaleString()} ambiguous matches`,
                href: `/workspace/matches/${encodeURIComponent(analysis.analysis_id)}`,
                parameters: {
                  competitor:
                    selectedCompetitor === "all" ? null : selectedCompetitor,
                  lens: selectedLens || null,
                },
              }
            : undefined,
        },
      ],
    };
  }, [
    competitorOptions,
    analysis.analysis_id,
    activeGroup,
    leadershipProductOptions,
    leadershipRadius,
    leadershipState,
    leadershipCity,
    leadershipStateOptions,
    leadershipCityOptions,
    readiness,
    reportView.comparison_bases,
    reportView.match_governance,
    reportView.retailer_scope.benchmark.name,
    preferredBasis,
    selectedBasis,
    selectedCompetitor,
    selectedLeadershipProduct,
    selectedLens,
  ]);
  useApplicationContextDefinition(contextDefinition);
  return (
    <>
      <header className="workspace-header report-header">
        <div>
          <p className="eyebrow">Competitive intelligence report</p>
          <h1>{reportView.product_pack.name}</h1>
          <p className="report-deck">
            Where the price war is being won, where it is being lost, and which
            targeted moves matter most.
          </p>
          <p className="workspace-meta">
            {analysis.analysis_id} · Generated{" "}
            {displayDate(reportView.generated_at)}
          </p>
          <div className="trust-strip" aria-label="Result integrity">
            <span>Deterministic metrics</span>
            <span>Evidence linked</span>
            {publication ? <span>Published v{publication.version}</span> : null}
            <span title={reportView.result_checksum}>
              Checksum {reportView.result_checksum.slice(0, 12)}…
            </span>
          </div>
        </div>
        <div className="workspace-status">
          <span className={`status-badge ${visibleStatus}`}>
            {displayLabel(visibleStatus)}
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
            onClick={() => selectGroup(group.id)}
            key={group.id}
          >
            {group.label}
          </button>
        ))}
        <button
          type="button"
          role="tab"
          aria-selected={activeGroup === "product-leadership"}
          className={activeGroup === "product-leadership" ? "active" : ""}
          onClick={() => selectGroup("product-leadership")}
        >
          Product Leadership
        </button>
      </div>
      <section className="workspace-panel" role="tabpanel">
        {activeGroup === "product-leadership" ? (
          <ProductLeadershipWorkspace
            analysisId={analysis.analysis_id}
            competitorId={selectedCompetitor}
            profileId={selectedLens}
            productId={selectedLeadershipProduct}
            radiusMiles={leadershipRadius}
            stateFilter={leadershipState}
            cityFilter={leadershipCity}
            onGeographyOptions={receiveLeadershipGeography}
          />
        ) : activeGroup === "assortment" && reportView.assortment_analysis ? (
          <AssortmentAnalysisPanel
            data={reportView.assortment_analysis}
            benchmark={reportView.retailer_scope.benchmark}
            competitors={competitorOptions}
            selected={selectedRetailer}
          />
        ) : selectedGroup && selectedGroup.sections.length > 0 ? (
          <>
            {activeGroup === "overview" && selectedScorecards.length ? (
              <RetailerScorecardPanel
                benchmark={reportView.retailer_scope.benchmark}
                rows={selectedScorecards}
                onSelect={selectCompetitor}
              />
            ) : null}
            {activeGroup === "price-segments" ? (
              <ComparableCohortExplorer
                records={cohortRecords}
                benchmarkName={reportView.retailer_scope.benchmark.name}
                cohortDimensions={
                  reportView.product_pack.cohort_dimensions ?? []
                }
                minimumGeographies={
                  reportView.product_pack.minimum_cohort_geographies ?? 1
                }
                ambiguousMatches={reportView.match_governance.ambiguous}
                onReviewMatches={openMatchWorkbench}
              />
            ) : null}
            {activeGroup === "geography" && scopedPoints.length ? (
              <AnalysisMap
                benchmarkRetailer={reportView.retailer_scope.benchmark.name}
                points={scopedPoints}
                decisions={scopedDecisions}
                coverageRows={primaryComparisons}
                comparisonBasis={selectedBasis}
              />
            ) : null}
            {activeGroup === "products" && scopedHighlights.length ? (
              <ProductHighlights products={scopedHighlights} />
            ) : null}
            {activeGroup === "products" && scopedDecisions.length ? (
              <ProductDecisionBoard
                analysisId={analysis.analysis_id}
                benchmarkRetailer={reportView.benchmark_retailer}
                rows={scopedDecisions}
                title="Product-level price evidence"
                comparisonBasis={selectedBasis}
                onReviewMatch={reviewDecision}
              />
            ) : null}
            {selectedGroup.sections
              .filter((section) => section.kind !== "kpi_strip")
              .map((section) => (
                <Fragment key={section.id}>
                  <BlueprintSection
                    section={section}
                    recommendedCharts={recommendedCharts}
                    benchmarkRetailer={reportView.benchmark_retailer}
                    productDecisions={scopedDecisions}
                    qualityObservations={scopedQuality}
                    showPortfolioNarrative={selectedRetailer === null}
                    selectedRetailerName={selectedRetailer?.name ?? null}
                  />
                  {activeGroup === "overview" &&
                  section.kind === "executive_summary" ? (
                    <>
                      {scopedDecisions.length ? (
                        <ProductDecisionBoard
                          analysisId={analysis.analysis_id}
                          benchmarkRetailer={reportView.benchmark_retailer}
                          rows={scopedDecisions.slice(0, 6)}
                          title="Products changing the competitive picture"
                          comparisonBasis={selectedBasis}
                          onReviewMatch={reviewDecision}
                        />
                      ) : null}
                    </>
                  ) : null}
                </Fragment>
              ))}
          </>
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

function AssortmentProductList({
  title,
  note,
  products,
}: Readonly<{
  title: string;
  note: string;
  products: AssortmentProduct[];
}>) {
  return (
    <section className="assortment-product-list">
      <header>
        <h4>{title}</h4>
        <p>{note}</p>
      </header>
      <div>
        {products.slice(0, 8).map((product) => (
          <article key={product.canonical_product_id}>
            <span className="assortment-product-image">
              {product.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={product.image_url} alt="" />
              ) : (
                <b>{product.name.slice(0, 1)}</b>
              )}
            </span>
            <span>
              <small>{product.brand || product.product_id}</small>
              <strong>{product.name}</strong>
              <em>
                Seen at {product.observed_locations.toLocaleString()} locations
                · {product.observed_zipcodes.toLocaleString()} ZIPs
              </em>
            </span>
          </article>
        ))}
        {!products.length ? (
          <p className="empty-copy">No products meet this definition.</p>
        ) : null}
      </div>
    </section>
  );
}

function AssortmentBrandPanel({
  retailerName,
  distinctBrands,
  topBrands,
  concentratedBrands,
}: Readonly<{
  retailerName: string;
  distinctBrands: number;
  topBrands: AssortmentBrand[];
  concentratedBrands: AssortmentBrand[];
}>) {
  if (!topBrands.length) return null;
  const maxLocations = Math.max(
    ...topBrands.map((brand) => brand.observed_locations),
    1,
  );
  return (
    <section className="assortment-brand-panel">
      <header>
        <div>
          <small>{retailerName}</small>
          <h4>Observed brand breadth</h4>
        </div>
        <strong>{distinctBrands.toLocaleString()} brands</strong>
      </header>
      <div className="assortment-brand-bars">
        {topBrands.slice(0, 6).map((brand) => (
          <div key={brand.brand}>
            <span>
              <b>{brand.brand}</b>
              <small>
                {brand.distinct_products.toLocaleString()} products ·{" "}
                {brand.observed_locations.toLocaleString()} locations
              </small>
            </span>
            <i>
              <b
                style={{
                  width: `${Math.max(2, (brand.observed_locations / maxLocations) * 100)}%`,
                }}
              />
            </i>
          </div>
        ))}
      </div>
      {concentratedBrands.length ? (
        <div className="assortment-regional-signals">
          <small>Geographically concentrated brand signals</small>
          <p>
            Observed in no more than 25% of this retailer&apos;s collected
            locations. Concentration is a review signal—not proof of local
            distribution.
          </p>
          <div>
            {concentratedBrands.slice(0, 6).map((brand) => (
              <span key={brand.brand}>
                <b>{brand.brand}</b>
                {new Intl.NumberFormat("en-US", {
                  style: "percent",
                  maximumFractionDigits: 1,
                }).format(brand.location_share)}{" "}
                of locations
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function AssortmentBreadthGaps({
  rows,
  benchmarkName,
  competitorName,
  leader,
}: Readonly<{
  rows: AssortmentBreadthGap[];
  benchmarkName: string;
  competitorName: string;
  leader: "benchmark" | "competitor";
}>) {
  if (!rows.length) return null;
  const leaderName = leader === "benchmark" ? benchmarkName : competitorName;
  return (
    <section className="assortment-gap-table">
      <header>
        <small>Largest shared-ZIP breadth gaps</small>
        <h4>{leaderName} carries more observed products</h4>
      </header>
      <div>
        <span>ZIP</span>
        <span>{benchmarkName}</span>
        <span>{competitorName}</span>
        <span>Gap</span>
      </div>
      {rows.slice(0, 6).map((row) => (
        <div key={row.zipcode}>
          <strong>{row.zipcode}</strong>
          <span>{row.benchmark_products.toLocaleString()}</span>
          <span>{row.competitor_products.toLocaleString()}</span>
          <b>
            {row.product_count_gap > 0 ? "+" : ""}
            {row.product_count_gap}
          </b>
        </div>
      ))}
    </section>
  );
}

function AssortmentAnalysisPanel({
  data,
  benchmark,
  competitors,
  selected,
}: Readonly<{
  data: AssortmentAnalysis;
  benchmark: RetailerOption;
  competitors: RetailerOption[];
  selected: RetailerOption | null;
}>) {
  const comparisons = selected
    ? data.comparisons.filter((row) =>
        matchesRetailer(row.competitor, selected),
      )
    : data.comparisons;
  const benchmarkSummary = data.retailers.find((row) =>
    matchesRetailer(row.retailer, benchmark),
  );
  return (
    <div className="assortment-analysis">
      <div className="specialist-context-strip assortment-context-strip">
        <p>
          <strong>{benchmark.name} assortment scope</strong>
          Product counts come from in-scope Search results. Product Pack rules
          admit relationships across the available comparison lenses; unmatched
          products are whitespace signals for review, not assumed substitutes.
        </p>
        <aside>
          <small>{benchmark.name} observed assortment</small>
          <strong>
            {benchmarkSummary?.distinct_products.toLocaleString() ?? "—"}
          </strong>
          <span>
            products across{" "}
            {benchmarkSummary?.observed_locations.toLocaleString() ?? "—"}{" "}
            locations
          </span>
        </aside>
      </div>
      <div className="assortment-model-guide">
        <article>
          <small>Item relationship</small>
          <strong>One primary product ↔ one competitor product</strong>
          <span>
            Governed in Match Review and used for auditable price evidence.
          </span>
        </article>
        <article>
          <small>Comparable cohort</small>
          <strong>
            Multiple one-to-one pairs with the same specifications
          </strong>
          <span>
            Used for category price rollups without changing match cardinality.
          </span>
        </article>
        <article className="active">
          <small>Assortment rollup</small>
          <strong>Range, brand breadth, whitespace, and geography</strong>
          <span>
            Describes observed choice; it does not declare substitute products.
          </span>
        </article>
      </div>
      {comparisons.map((comparison) => {
        const competitor =
          competitors.find((row) =>
            matchesRetailer(comparison.competitor, row),
          ) ??
          ({
            id: comparison.competitor,
            name: displayLabel(comparison.competitor),
          } satisfies RetailerOption);
        const competitorSummary = data.retailers.find((row) =>
          matchesRetailer(row.retailer, competitor),
        );
        return (
          <section
            className="assortment-competitor"
            key={comparison.competitor}
          >
            <header>
              <div>
                <p className="eyebrow">
                  {benchmark.name} vs. {competitor.name}
                </p>
                <h3>Product relationship and whitespace scorecard</h3>
              </div>
              <span>
                {comparison.geography.shared_zipcodes.toLocaleString()} shared
                ZIPs
              </span>
            </header>
            <div className="assortment-kpis">
              <article>
                <small>{benchmark.name} products</small>
                <strong>
                  {benchmarkSummary?.distinct_products.toLocaleString() ?? "—"}
                </strong>
                <span>Distinct in-scope IDs</span>
              </article>
              <article>
                <small>{competitor.name} products</small>
                <strong>
                  {competitorSummary?.distinct_products.toLocaleString() ?? "—"}
                </strong>
                <span>Distinct in-scope IDs</span>
              </article>
              <article>
                <small>1:1 item relationships</small>
                <strong>
                  {comparison.product_relationships.toLocaleString()}
                </strong>
                <span>Unique admitted pairs across all lenses</span>
              </article>
              <article>
                <small>{benchmark.name} unmatched</small>
                <strong>
                  {comparison.benchmark_only_products.toLocaleString()}
                </strong>
                <span>No admitted item relationship</span>
              </article>
              <article>
                <small>{competitor.name} whitespace</small>
                <strong>
                  {comparison.competitor_whitespace_products.toLocaleString()}
                </strong>
                <span>No admitted {benchmark.name} match</span>
              </article>
              {comparison.ambiguous_candidate_groups ? (
                <article className="review">
                  <small>Needs match review</small>
                  <strong>
                    {comparison.ambiguous_candidate_groups.toLocaleString()}
                  </strong>
                  <span>Ambiguous candidate groups</span>
                </article>
              ) : null}
            </div>
            <div className="assortment-middle">
              <section className="assortment-coverage-card">
                <h4>Item-relationship coverage</h4>
                <p>
                  Share of each retailer&apos;s distinct observed products in an
                  admitted pair.
                </p>
                {[
                  [benchmark.name, comparison.benchmark_match_coverage],
                  [competitor.name, comparison.competitor_match_coverage],
                ].map(([label, rawValue]) => {
                  const value = Number(rawValue);
                  return (
                    <div
                      className="assortment-coverage-row"
                      key={String(label)}
                    >
                      <span>{label}</span>
                      <b>
                        <i style={{ width: `${Math.max(1, value * 100)}%` }} />
                      </b>
                      <strong>
                        {new Intl.NumberFormat("en-US", {
                          style: "percent",
                          maximumFractionDigits: 1,
                        }).format(value)}
                      </strong>
                    </div>
                  );
                })}
                <div className="assortment-lenses">
                  {comparison.profiles.map((profile) => (
                    <span key={profile.profile_id}>
                      <b>{profile.relationships.toLocaleString()}</b>
                      {profile.profile_label}
                    </span>
                  ))}
                </div>
                <small className="assortment-lens-note">
                  Relationship counts by comparison lens. The same one-to-one
                  pair may be eligible in more than one lens.
                </small>
              </section>
              <section className="assortment-geography-card">
                <h4>Store-market breadth</h4>
                <p>Distinct product counts compared within shared ZIPs.</p>
                <div>
                  <span>
                    <b>
                      {comparison.geography.benchmark_broader_zipcodes.toLocaleString()}
                    </b>
                    {benchmark.name} broader
                  </span>
                  <span>
                    <b>
                      {comparison.geography.competitor_broader_zipcodes.toLocaleString()}
                    </b>
                    {competitor.name} broader
                  </span>
                  <span>
                    <b>
                      {comparison.geography.parity_zipcodes.toLocaleString()}
                    </b>
                    Same breadth
                  </span>
                </div>
                <small>
                  Median primary-minus-competitor product-count gap:{" "}
                  {comparison.geography.median_product_count_gap > 0 ? "+" : ""}
                  {comparison.geography.median_product_count_gap}
                </small>
              </section>
              <section className="assortment-key-points">
                <h4>Key points</h4>
                <ul>
                  {comparison.key_points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </section>
            </div>
            {benchmarkSummary?.top_brands?.length ||
            competitorSummary?.top_brands?.length ? (
              <div className="assortment-brand-grid">
                <AssortmentBrandPanel
                  retailerName={benchmark.name}
                  distinctBrands={benchmarkSummary?.distinct_brands ?? 0}
                  topBrands={benchmarkSummary?.top_brands ?? []}
                  concentratedBrands={
                    benchmarkSummary?.geographically_concentrated_brands ?? []
                  }
                />
                <AssortmentBrandPanel
                  retailerName={competitor.name}
                  distinctBrands={competitorSummary?.distinct_brands ?? 0}
                  topBrands={competitorSummary?.top_brands ?? []}
                  concentratedBrands={
                    competitorSummary?.geographically_concentrated_brands ?? []
                  }
                />
              </div>
            ) : null}
            {comparison.geography.top_benchmark_breadth_gaps?.length ||
            comparison.geography.top_competitor_breadth_gaps?.length ? (
              <div className="assortment-gap-grid">
                <AssortmentBreadthGaps
                  rows={comparison.geography.top_benchmark_breadth_gaps ?? []}
                  benchmarkName={benchmark.name}
                  competitorName={competitor.name}
                  leader="benchmark"
                />
                <AssortmentBreadthGaps
                  rows={comparison.geography.top_competitor_breadth_gaps ?? []}
                  benchmarkName={benchmark.name}
                  competitorName={competitor.name}
                  leader="competitor"
                />
              </div>
            ) : null}
            <div className="assortment-product-columns">
              <AssortmentProductList
                title={`${benchmark.name} products without an admitted match`}
                note="Broadest observed products available for relationship review."
                products={comparison.top_benchmark_only}
              />
              <AssortmentProductList
                title={`${competitor.name} whitespace`}
                note={`Broadest observed products without an admitted ${benchmark.name} match.`}
                products={comparison.top_competitor_whitespace}
              />
            </div>
          </section>
        );
      })}
      <footer className="assortment-source-note">
        <strong>Definition.</strong> {data.source}. {data.grain}. Search remains
        the authority for store presence and price; PDP supplies identity and
        imagery where available.
      </footer>
    </div>
  );
}

function retailerToken(value: unknown) {
  return displayLabel(String(value ?? ""))
    .toLocaleLowerCase("en-US")
    .replace(/\(us\)/g, "")
    .replace(/[^a-z0-9]/g, "");
}

function matchesRetailer(value: unknown, retailer: RetailerOption) {
  const token = retailerToken(value);
  return (
    token === retailerToken(retailer.id) ||
    token === retailerToken(retailer.name)
  );
}

function scopeRetailerRows<T>(
  rows: T[],
  selected: RetailerOption | null,
  retailer: (row: T) => unknown,
) {
  return selected
    ? rows.filter((row) => matchesRetailer(retailer(row), selected))
    : rows;
}

function scopeReferenceAndRetailerRows<T>(
  rows: T[],
  selected: RetailerOption | null,
  benchmark: RetailerOption,
  retailer: (row: T) => unknown,
) {
  if (!selected) return rows;
  return rows.filter(
    (row) =>
      matchesRetailer(retailer(row), benchmark) ||
      matchesRetailer(retailer(row), selected),
  );
}

function scopeReportRows(
  section: ReportSectionView,
  selected: RetailerOption | null,
  benchmark: RetailerOption,
  selectedProfileId?: string,
) {
  return section.records.filter((row) => {
    if (
      selectedProfileId &&
      row._profile_id &&
      String(row._profile_id) !== selectedProfileId
    )
      return false;
    if (!selected) return true;
    if (row._competitor_id)
      return matchesRetailer(row._competitor_id, selected);
    if (row._retailer_id) {
      return (
        matchesRetailer(row._retailer_id, benchmark) ||
        matchesRetailer(row._retailer_id, selected)
      );
    }
    if (
      ["price_position", "segment_analysis", "geographic_sensitivity"].includes(
        section.kind,
      ) &&
      row.competitor
    ) {
      return matchesRetailer(row.competitor, selected);
    }
    return true;
  });
}

function rowReferencesRetailer(row: JsonObject, retailer: RetailerOption) {
  const aliases = [retailer.id, retailer.name]
    .map(retailerToken)
    .filter((alias) => alias.length >= 3);
  return Object.values(row).some((value) => {
    if (typeof value !== "string") return false;
    const token = retailerToken(value);
    return aliases.some((alias) => token.includes(alias));
  });
}

function scopeEvidenceRows(
  rows: JsonObject[],
  selected: RetailerOption | null,
  competitors: RetailerOption[],
) {
  if (!selected) return rows;
  return rows.filter((row) => {
    if (row._competitor_id)
      return matchesRetailer(row._competitor_id, selected);
    if (row._retailer_id) return true;
    const referencedCompetitor = competitors.find((competitor) =>
      rowReferencesRetailer(row, competitor),
    );
    if (referencedCompetitor) return referencedCompetitor.id === selected.id;
    return true;
  });
}

function formatScorecardRate(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  });
}

function RetailerScorecardPanel({
  benchmark,
  rows,
  onSelect,
}: Readonly<{
  benchmark: RetailerOption;
  rows: RetailerScorecard[];
  onSelect: (retailerId: string) => void;
}>) {
  const ranked = [...rows].sort(
    (left, right) => (right.matches ?? 0) - (left.matches ?? 0),
  );
  return (
    <Section
      title={
        rows.length === 1
          ? `${rows[0].competitor} scorecard`
          : "Retailer scorecard"
      }
      note={`Each row names its governed Product Pack comparison basis. Lower-price shares include ${benchmark.name}, the competitor, and parity; the price-position statement uses the paired median gap.`}
    >
      <div className="retailer-scorecard-table">
        <div className="retailer-scorecard-head">
          <span>Competitor</span>
          <span>Matched evidence</span>
          <span>Lower-price share</span>
          <span>Paired median price position</span>
          <span>Status</span>
        </div>
        {ranked.map((row) => (
          <div className="retailer-scorecard-row" key={row.competitor_id}>
            <button type="button" onClick={() => onSelect(row.competitor_id)}>
              <strong>{row.competitor}</strong>
              <span>{row.comparison_lens}</span>
              <small>
                {displayLabel(row.comparison_metric)} ·{" "}
                {priceUnitLabel(row.price_unit)} · {displayLabel(row.geography)}
              </small>
            </button>
            <div>
              <strong>{(row.matches ?? 0).toLocaleString()}</strong>
              <span>matched observations</span>
              <small>
                {row.matched_geographies === null
                  ? "Matched ZIP count unavailable"
                  : `${row.matched_geographies.toLocaleString()} matched ZIP markets`}
              </small>
            </div>
            <div className="retailer-share-bars">
              <span>
                {benchmark.name}
                <b>{formatScorecardRate(row.benchmark_lower_rate)}</b>
              </span>
              <i>
                <b
                  className="benchmark"
                  style={{
                    width: `${Math.max((row.benchmark_lower_rate ?? 0) * 100, 1)}%`,
                  }}
                />
              </i>
              <span>
                {row.competitor}
                <b>{formatScorecardRate(row.competitor_lower_rate)}</b>
              </span>
              <i>
                <b
                  className="competitor"
                  style={{
                    width: `${Math.max((row.competitor_lower_rate ?? 0) * 100, 1)}%`,
                  }}
                />
              </i>
              <span>
                Parity
                <b>{formatScorecardRate(row.parity_rate)}</b>
              </span>
              <i>
                <b
                  className="parity"
                  style={{
                    width: `${Math.max((row.parity_rate ?? 0) * 100, 1)}%`,
                  }}
                />
              </i>
            </div>
            <strong className="retailer-price-position">
              {row.price_position}
            </strong>
            <span
              className={`retailer-score-status ${row.status}`}
              title={row.readiness_reason}
            >
              <b>{row.status === "ready" ? "Ready" : "Limited evidence"}</b>
              <small>{row.readiness_reason}</small>
            </span>
          </div>
        ))}
      </div>
      {rows.length === 1 ? (
        <button
          className="retailer-show-all"
          type="button"
          onClick={() => onSelect("all")}
        >
          Return to all competitors
        </button>
      ) : null}
    </Section>
  );
}

function BlueprintSection({
  section,
  recommendedCharts,
  benchmarkRetailer,
  productDecisions,
  qualityObservations,
  showPortfolioNarrative,
  selectedRetailerName,
}: Readonly<{
  section: ReportSectionView;
  recommendedCharts: string[];
  benchmarkRetailer: string;
  productDecisions: ProductDecision[];
  qualityObservations: QualityObservation[];
  showPortfolioNarrative: boolean;
  selectedRetailerName: string | null;
}>) {
  const narrative = asObject(section.narrative);
  const visibleMetrics = [
    "coverage",
    "executive_summary",
    "geographic_sensitivity",
    "price_position",
    "segment_analysis",
    "recommendations",
    "data_quality",
  ].includes(section.kind)
    ? []
    : section.metrics.slice(0, 6);
  const metricValues = visibleMetrics.map((metric) => metric.value);
  const comparisonChart = shouldShowComparisonChart(section, recommendedCharts);
  const narrativeLeads =
    Boolean(narrative.body) &&
    ["executive_summary", "recommendations"].includes(section.kind);
  const narrativeBullets = Array.isArray(narrative.bullets)
    ? narrative.bullets.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const supportingRows =
    section.kind === "recommendations"
      ? uniqueDecisionRows(section.records)
      : section.records;
  const hasStructuredNarrative =
    Boolean(narrative.subtitle) ||
    narrativeBullets.length > 0 ||
    Boolean(narrative.implication);
  const hidesPortfolioNarrative =
    !showPortfolioNarrative &&
    !["data_quality", "methodology"].includes(section.kind) &&
    (hasStructuredNarrative || Boolean(narrative.body));
  const sectionTitle = hidesPortfolioNarrative
    ? `${selectedRetailerName ?? "Selected competitor"}: ${displayLabel(section.kind)}`
    : section.title;
  return (
    <Section
      title={sectionTitle}
      note={`${displayLabel(section.kind)} · ${displayLabel(section.visualization)}`}
    >
      {hidesPortfolioNarrative ? (
        <p className="retailer-scope-note">
          Portfolio commentary is hidden in a retailer-only view. The scorecard,
          product evidence, map, and tables below reflect the selected retailer.
        </p>
      ) : hasStructuredNarrative ? (
        <div className="section-narrative">
          {narrative.subtitle ? (
            <p className="narrative-subtitle">
              {displayValue(narrative.subtitle)}
            </p>
          ) : null}
          {narrativeBullets.length ? (
            <ul>
              {narrativeBullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
          ) : null}
          {narrative.implication ? (
            <aside>
              <b>Key point</b>
              <span>{displayValue(narrative.implication)}</span>
            </aside>
          ) : null}
        </div>
      ) : narrative.body ? (
        <div className="section-narrative">
          {displayValue(narrative.body)
            .split(/\n{2,}/)
            .map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
        </div>
      ) : null}
      {visibleMetrics.length > 0 && section.visualization === "bar" ? (
        <div className="metric-bars" aria-label={`${section.title} metrics`}>
          {visibleMetrics.map((metric) => (
            <div className="metric-bar" key={String(metric.metric_id)}>
              <div>
                <span>{compactMetricName(metric, benchmarkRetailer)}</span>
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
      ) : visibleMetrics.length > 0 ? (
        <div className="metric-grid">
          {visibleMetrics.map((metric) => (
            <Metric
              key={String(metric.metric_id)}
              label={compactMetricName(metric, benchmarkRetailer)}
              value={formatMetric(metric.value, metric.unit)}
            />
          ))}
        </div>
      ) : null}
      {comparisonChart ? (
        <CompetitivePositionChart
          rows={section.records}
          title={sectionTitle}
          benchmarkRetailer={benchmarkRetailer}
          productDecisions={productDecisions}
        />
      ) : null}
      {section.kind === "segment_analysis" && section.records.length > 0 ? (
        <SegmentPositionMatrix
          benchmarkRetailer={benchmarkRetailer}
          rows={section.records}
        />
      ) : null}
      {section.kind === "data_quality" ? (
        <QualityEvidence rows={qualityObservations} />
      ) : null}
      {section.records.length > 0 &&
      section.visualization === "ranked_cards" &&
      !narrativeLeads &&
      !["recommendations", "data_quality"].includes(section.kind) ? (
        <KeyPointCards rows={section.records} />
      ) : section.records.length > 0 &&
        section.kind !== "kpi_strip" &&
        section.kind !== "coverage" &&
        section.kind !== "geographic_sensitivity" &&
        section.kind !== "segment_analysis" &&
        section.kind !== "recommendations" &&
        section.kind !== "data_quality" &&
        !narrativeLeads &&
        !comparisonChart ? (
        <DataTable rows={section.records} />
      ) : null}
      {comparisonChart || (narrativeLeads && supportingRows.length > 0) ? (
        <details className="evidence-disclosure report-detail">
          <summary>View supporting detail</summary>
          <DataTable rows={supportingRows} />
        </details>
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

function ProductDecisionBoard({
  analysisId,
  benchmarkRetailer,
  rows,
  title,
  comparisonBasis,
  onReviewMatch,
}: Readonly<{
  analysisId: string;
  benchmarkRetailer: string;
  rows: ProductDecision[];
  title: string;
  comparisonBasis: AnalysisReportView["comparison_bases"][number] | null;
  onReviewMatch: (decision: ProductDecision) => void;
}>) {
  const [selected, setSelected] = useState<ProductDecision | null>(null);
  return (
    <Section
      title={title}
      note={`Each card states its comparison unit and separates directional share from the paired median gap. ${comparisonBasisDescription(comparisonBasis)}. Search controls price and location; PDP supplies identity, attributes, and imagery.`}
    >
      <div className="product-decision-grid">
        {rows.map((row) => {
          const competitor = displayLabel(row.competitor);
          const parityShare = row.matches ? row.parity / row.matches : 0;
          const stance = productDecisionStance(row);
          const dominantShare =
            stance === "attention"
              ? row.competitor_lower_share
              : stance === "protect"
                ? row.benchmark_lower_share
                : parityShare;
          const position =
            stance === "attention"
              ? `${competitor} is lower in ${formatScorecardRate(dominantShare)} of matched observations`
              : stance === "protect"
                ? `${displayLabel(benchmarkRetailer)} is lower in ${formatScorecardRate(dominantShare)} of matched observations`
                : stance === "parity"
                  ? `Price parity in ${formatScorecardRate(dominantShare)} of matched observations`
                  : `Mixed result: ${competitor} is lower in ${formatScorecardRate(row.competitor_lower_share)}, ${displayLabel(benchmarkRetailer)} is lower in ${formatScorecardRate(row.benchmark_lower_share)}, and ${formatScorecardRate(parityShare)} are tied`;
          const gap = formatPriceForBasis(
            Math.abs(row.median_gap),
            comparisonBasis?.price_unit,
          );
          const gapPosition =
            row.median_gap < 0
              ? `${competitor} is ${gap} lower at the paired median`
              : row.median_gap > 0
                ? `${displayLabel(benchmarkRetailer)} is ${gap} lower at the paired median`
                : "Paired median price difference: $0.00";
          const evidence = row.evidence_summary;
          return (
            <button
              type="button"
              className={`product-decision-card ${stance}`}
              key={row.id}
              onClick={() => setSelected(row)}
            >
              <div className="product-pair-visual" aria-hidden="true">
                <ProductImage
                  imageUrl={row.benchmark_image_url}
                  name={row.benchmark_product_name}
                  retailer={displayLabel(benchmarkRetailer)}
                />
                <span className="product-pair-vs">vs</span>
                <ProductImage
                  imageUrl={row.competitor_image_url}
                  name={row.competitor_product_name}
                  retailer={competitor}
                />
              </div>
              <div className="product-decision-copy">
                <span className="product-decision-status">
                  {stance === "attention"
                    ? "Needs attention"
                    : stance === "protect"
                      ? "Position to protect"
                      : stance === "parity"
                        ? "Price parity"
                        : "Mixed price position"}
                </span>
                <h3>{row.benchmark_product_name}</h3>
                <h3>{row.competitor_product_name}</h3>
                <div className="product-price-pair">
                  <span>
                    {displayLabel(benchmarkRetailer)}
                    <b>
                      {formatPriceForBasis(
                        row.median_benchmark_price,
                        comparisonBasis?.price_unit,
                      )}
                    </b>
                  </span>
                  <span>
                    {competitor}
                    <b>
                      {formatPriceForBasis(
                        row.median_competitor_price,
                        comparisonBasis?.price_unit,
                      )}
                    </b>
                  </span>
                </div>
                <strong className="product-decision-conclusion">
                  {position}
                </strong>
                <p className="product-decision-statistic">{gapPosition}</p>
                <p>
                  {evidence?.benchmark_store_observations
                    ? `${evidence.benchmark_store_observations.toLocaleString()} observed benchmark stores across ${evidence.matched_zip_markets?.toLocaleString() ?? row.geographies.toLocaleString()} matched ZIP markets.`
                    : `${row.geographies.toLocaleString()} matched ZIP markets in the analytical comparison.`}
                </p>
                <span className="product-card-action">
                  View stores and download evidence →
                </span>
              </div>
            </button>
          );
        })}
      </div>
      {selected ? (
        <ProductEvidenceDrawer
          key={selected.id}
          analysisId={analysisId}
          benchmarkRetailer={benchmarkRetailer}
          decision={selected}
          comparisonBasis={comparisonBasis}
          onClose={() => setSelected(null)}
          onReviewMatch={() => onReviewMatch(selected)}
        />
      ) : null}
    </Section>
  );
}

function formatCurrency(value: number) {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function ProductImage({
  imageUrl,
  name,
  retailer,
}: Readonly<{
  imageUrl?: string | null;
  name: string;
  retailer: string;
}>) {
  return (
    <span className="product-pair-image">
      <i>{retailer}</i>
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imageUrl} alt="" loading="lazy" />
      ) : (
        <b>{name.slice(0, 1)}</b>
      )}
    </span>
  );
}

function ProductThumbnailStack({
  products,
}: Readonly<{ products: ProductDecision[] }>) {
  const images = products
    .flatMap((product) => [
      {
        url: product.benchmark_image_url,
        name: product.benchmark_product_name,
      },
      {
        url: product.competitor_image_url,
        name: product.competitor_product_name,
      },
    ])
    .filter((item): item is { url: string; name: string } => Boolean(item.url))
    .filter(
      (item, index, values) =>
        values.findIndex((candidate) => candidate.url === item.url) === index,
    )
    .slice(0, 3);
  if (images.length === 0) return null;
  return (
    <span className="product-thumbnail-stack" aria-hidden="true">
      {images.map((item) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={item.url} alt="" key={item.url} loading="lazy" />
      ))}
    </span>
  );
}

function ProductEvidenceDrawer({
  analysisId,
  benchmarkRetailer,
  decision,
  comparisonBasis,
  onClose,
  onReviewMatch,
}: Readonly<{
  analysisId: string;
  benchmarkRetailer: string;
  decision: ProductDecision;
  comparisonBasis: AnalysisReportView["comparison_bases"][number] | null;
  onClose: () => void;
  onReviewMatch: () => void;
}>) {
  const [evidence, setEvidence] = useState<ProductEvidenceResponse | null>(
    null,
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(
      `/api/analyses/${encodeURIComponent(analysisId)}/product-decisions/${encodeURIComponent(decision.id)}/evidence`,
    )
      .then(async (response) => {
        const body = (await response.json()) as ProductEvidenceResponse & {
          error?: string;
        };
        if (!response.ok)
          throw new Error(body.error ?? "Evidence is unavailable.");
        if (!cancelled) setEvidence(body);
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setError(
            cause instanceof Error ? cause.message : "Evidence is unavailable.",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, decision.id]);

  return (
    <div
      className="evidence-drawer-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <aside
        className="evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span className="eyebrow">Store-level evidence</span>
            <h2 id="evidence-title">Where this product pair wins and loses</h2>
            <p>
              {decision.benchmark_product_name} vs.{" "}
              {decision.competitor_product_name}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close evidence panel"
          >
            ×
          </button>
        </header>
        {loading ? (
          <p className="drawer-status">Loading exact store evidence…</p>
        ) : null}
        {error ? <p className="drawer-status error">{error}</p> : null}
        {evidence
          ? (() => {
              const comparisonMetric =
                evidence.comparison_metric ??
                comparisonBasis?.comparison_metric ??
                decision.comparison_metric ??
                "package_price";
              const comparisonUnit =
                evidence.comparison_unit ??
                comparisonBasis?.price_unit ??
                "USD/package";
              const normalizedEvidence = comparisonMetric !== "package_price";
              return (
                <>
                  <div className="evidence-basis-bridge">
                    <div>
                      <small>Analytical comparison</small>
                      <strong>
                        {comparisonBasisDescription(comparisonBasis)}
                      </strong>
                      <span>
                        Card medians: {displayLabel(benchmarkRetailer)}{" "}
                        {formatPriceForBasis(
                          decision.median_benchmark_price,
                          comparisonUnit,
                        )}{" "}
                        · {displayLabel(decision.competitor)}{" "}
                        {formatPriceForBasis(
                          decision.median_competitor_price,
                          comparisonUnit,
                        )}
                      </span>
                    </div>
                    <div>
                      <small>Paired median gap</small>
                      <strong>
                        {formatPriceForBasis(
                          decision.median_gap,
                          comparisonUnit,
                        )}
                      </strong>
                      <span>
                        Competitor minus {displayLabel(benchmarkRetailer)}
                      </span>
                    </div>
                    <div>
                      <small>Store evidence below</small>
                      <strong>
                        {normalizedEvidence
                          ? "Package price + normalized comparison"
                          : "Package-price comparison"}
                      </strong>
                      <span>
                        All price fields come from retailer Search results.
                      </span>
                    </div>
                  </div>
                  <div className="evidence-summary-grid">
                    <EvidenceStat
                      label="Benchmark stores compared"
                      value={evidence.summary.benchmark_store_observations ?? 0}
                    />
                    <EvidenceStat
                      label={`${displayLabel(decision.competitor)} lower`}
                      value={evidence.summary.benchmark_stores_undercut ?? 0}
                    />
                    <EvidenceStat
                      label={`${displayLabel(benchmarkRetailer)} lower`}
                      value={evidence.summary.benchmark_stores_lower ?? 0}
                    />
                    <EvidenceStat
                      label="Matched ZIP markets"
                      value={evidence.summary.matched_zip_markets ?? 0}
                    />
                  </div>
                  <div className="evidence-toolbar">
                    <p>
                      {evidence.comparison_grain} · outcomes use{" "}
                      {displayLabel(comparisonMetric)} (
                      {priceUnitLabel(comparisonUnit)})
                    </p>
                    <span>
                      <button type="button" onClick={onReviewMatch}>
                        Open in Match Workbench
                      </button>
                      <a
                        href={`/api/analyses/${encodeURIComponent(analysisId)}/product-decisions/${encodeURIComponent(decision.id)}/evidence?format=csv`}
                        download
                      >
                        Download store evidence (.csv)
                      </a>
                    </span>
                  </div>
                  <div className="evidence-table-wrap">
                    <table className="evidence-table">
                      <thead>
                        <tr>
                          <th>Outcome</th>
                          <th>ZIP</th>
                          <th>{displayLabel(benchmarkRetailer)} store</th>
                          <th>
                            {displayLabel(benchmarkRetailer)} package price
                          </th>
                          {normalizedEvidence ? (
                            <th>
                              {displayLabel(benchmarkRetailer)} comparison value
                            </th>
                          ) : null}
                          <th>{displayLabel(decision.competitor)} store</th>
                          <th>
                            {displayLabel(decision.competitor)} package price
                          </th>
                          {normalizedEvidence ? (
                            <th>
                              {displayLabel(decision.competitor)} comparison
                              value
                            </th>
                          ) : null}
                          <th>
                            Paired difference ({priceUnitLabel(comparisonUnit)})
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {evidence.rows.map((row) => (
                          <tr key={row.id}>
                            <td>
                              <span className={`outcome-pill ${row.outcome}`}>
                                {row.outcome === "competitor_lower"
                                  ? `${displayLabel(decision.competitor)} lower`
                                  : row.outcome === "benchmark_lower"
                                    ? `${displayLabel(benchmarkRetailer)} lower`
                                    : "Parity"}
                              </span>
                            </td>
                            <td>{row.zipcode}</td>
                            <td>{row.benchmark_store ?? "ZIP-level"}</td>
                            <td>{formatCurrency(row.benchmark_price)}</td>
                            {normalizedEvidence ? (
                              <td>
                                {formatPriceForBasis(
                                  row.benchmark_comparison_value ??
                                    row.benchmark_price,
                                  comparisonUnit,
                                )}
                              </td>
                            ) : null}
                            <td>{row.competitor_store ?? "ZIP-level"}</td>
                            <td>{formatCurrency(row.competitor_price)}</td>
                            {normalizedEvidence ? (
                              <td>
                                {formatPriceForBasis(
                                  row.competitor_comparison_value ??
                                    row.competitor_price,
                                  comparisonUnit,
                                )}
                              </td>
                            ) : null}
                            <td>
                              {formatPriceForBasis(
                                row.comparison_gap ??
                                  row.competitor_minus_benchmark,
                                comparisonUnit,
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="evidence-method-note">
                    Search observations are authoritative for price and
                    location. Each benchmark store is compared with the lowest
                    observed {priceUnitLabel(comparisonUnit)} value for this
                    exact competitor product in the same ZIP. Package prices
                    remain visible for reconciliation; the outcome and paired
                    difference use the stated analytical comparison value.
                  </p>
                </>
              );
            })()
          : null}
      </aside>
    </div>
  );
}

function EvidenceStat({
  label,
  value,
}: Readonly<{ label: string; value: number }>) {
  return (
    <div>
      <strong>{value.toLocaleString()}</strong>
      <span>{label}</span>
    </div>
  );
}

const chartCapabilityBySection: Record<string, string[]> = {
  price_position: ["package_price_gap", "exact_match", "price_position"],
};

function shouldShowComparisonChart(
  section: ReportSectionView,
  recommendedCharts: string[],
) {
  const capabilities = chartCapabilityBySection[section.kind];
  if (!capabilities || section.records.length === 0) return false;
  return capabilities.some((capability) =>
    recommendedCharts.includes(capability),
  );
}

function parseRate(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value <= 1 ? value * 100 : value;
  }
  if (typeof value !== "string") return null;
  const parsed = Number.parseFloat(value.replace(/[%,$]/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function parseCount(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return 0;
  const parsed = Number.parseFloat(value.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function CompetitivePositionChart({
  rows,
  title,
  benchmarkRetailer,
  productDecisions,
}: Readonly<{
  rows: JsonObject[];
  title: string;
  benchmarkRetailer: string;
  productDecisions: ProductDecision[];
}>) {
  const chartRows = rows
    .map((row) => ({
      row,
      competitorRate: parseRate(row["competitor lower"]),
      benchmarkRate: parseRate(row["benchmark lower"]),
      parityRate: parseRate(row.parity),
      matches: parseCount(row.matches),
      geographies: parseCount(row["matched geographies"]),
    }))
    .filter(
      (item) =>
        item.competitorRate !== null ||
        item.benchmarkRate !== null ||
        item.parityRate !== null,
    )
    .sort((left, right) => right.matches - left.matches)
    .slice(0, 8);
  if (chartRows.length === 0) return null;
  return (
    <figure className="comparison-chart" aria-label={`${title} comparison`}>
      <figcaption>
        <div>
          <strong>Lower-price share</strong>
          <span>
            Complete directional outcomes with market coverage and paired median
            price difference
          </span>
        </div>
        <div className="chart-legend" aria-label="Chart legend">
          <span className="benchmark">{displayLabel(benchmarkRetailer)}</span>
          <span className="competitor">Competitor</span>
          <span className="parity">Parity</span>
        </div>
      </figcaption>
      <div className="comparison-chart-body">
        {chartRows.map(
          (
            {
              row,
              benchmarkRate,
              competitorRate,
              parityRate,
              matches,
              geographies,
            },
            index,
          ) => (
            <div className="comparison-chart-row" key={String(row.id ?? index)}>
              <div className="comparison-chart-label">
                <div className="comparison-label-heading">
                  <ProductThumbnailStack
                    products={productDecisions.filter(
                      (decision) =>
                        displayLabel(decision.competitor) ===
                        displayValue(row.competitor),
                    )}
                  />
                  <strong>{displayValue(row.segment ?? row.competitor)}</strong>
                </div>
                <span>
                  {displayValue(row.competitor)} · {matches.toLocaleString()}{" "}
                  matched observations
                  {geographies > 0
                    ? ` · ${geographies.toLocaleString()} geographies`
                    : ""}
                  {(row["paired median gap"] ??
                  row["competitor - benchmark gap"])
                    ? ` · paired median gap ${displayValue(row["paired median gap"] ?? row["competitor - benchmark gap"])}`
                    : ""}
                </span>
              </div>
              <div className="paired-bars">
                <div>
                  <i>
                    <b
                      className="benchmark"
                      style={{ width: `${Math.max(benchmarkRate ?? 0, 1)}%` }}
                    />
                  </i>
                  <span>
                    {benchmarkRate === null
                      ? "—"
                      : `${benchmarkRate.toFixed(1)}%`}
                  </span>
                </div>
                <div>
                  <i>
                    <b
                      className="competitor"
                      style={{ width: `${Math.max(competitorRate ?? 0, 1)}%` }}
                    />
                  </i>
                  <span>
                    {competitorRate === null
                      ? "—"
                      : `${competitorRate.toFixed(1)}%`}
                  </span>
                </div>
                <div>
                  <i>
                    <b
                      className="parity"
                      style={{ width: `${Math.max(parityRate ?? 0, 1)}%` }}
                    />
                  </i>
                  <span>
                    {parityRate === null ? "—" : `${parityRate.toFixed(1)}%`}
                  </span>
                </div>
              </div>
            </div>
          ),
        )}
      </div>
      <p className="chart-note">
        One retained lowest-price observation per matched ZIP and configured
        comparison basis. Product cards provide the store-level supporting
        evidence.
      </p>
    </figure>
  );
}

function ProductHighlights({
  products,
}: Readonly<{ products: ProductHighlight[] }>) {
  return (
    <Section
      title="Products to know"
      note="PDP-enriched identity and imagery; search observations remain authoritative for price."
    >
      <div className="product-highlight-grid">
        {products.slice(0, 8).map((product) => {
          const content = (
            <>
              <div className="product-image" aria-hidden="true">
                {product.image_url ? (
                  // External retailer images are presentation-only and intentionally unoptimized.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={product.image_url} alt="" loading="lazy" />
                ) : (
                  <span>{product.name.slice(0, 1)}</span>
                )}
              </div>
              <div>
                <span className="product-retailer">{product.retailer}</span>
                <h3>{product.name}</h3>
                {product.brand ? <p>{product.brand}</p> : null}
                {product.role ? <b>{product.role}</b> : null}
              </div>
            </>
          );
          return product.url ? (
            <a
              className="product-highlight"
              href={product.url}
              target="_blank"
              rel="noreferrer"
              key={product.canonical_product_id}
            >
              {content}
            </a>
          ) : (
            <article
              className="product-highlight"
              key={product.canonical_product_id}
            >
              {content}
            </article>
          );
        })}
      </div>
    </Section>
  );
}

const statesTopology = statesTopologySource as Topology;
const continentalStateFeatures = (
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
  return {
    x: ((longitude + 125) / 59) * 900 + 30,
    y: ((50 - latitude) / 26) * 460 + 30,
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

function AnalysisMap({
  benchmarkRetailer,
  points,
  decisions,
  coverageRows,
  comparisonBasis,
}: Readonly<{
  benchmarkRetailer: string;
  points: MapPoint[];
  decisions: ProductDecision[];
  coverageRows: JsonObject[];
  comparisonBasis: AnalysisReportView["comparison_bases"][number] | null;
}>) {
  const products = Array.from(
    new Map(
      points
        .filter((point) => point.benchmark_product_id)
        .map((point) => [
          String(point.benchmark_product_id),
          point.benchmark_product_name ?? point.label,
        ]),
    ),
  ).sort((left, right) => left[1].localeCompare(right[1]));
  const [selectedProduct, setSelectedProduct] = useState("all");
  const [selectedOutcome, setSelectedOutcome] = useState("all");
  const [selectedPoint, setSelectedPoint] = useState<MapPoint | null>(null);
  const displayPopulation = useMemo(
    () =>
      points
        .filter(
          (point) =>
            Number.isFinite(point.latitude) &&
            Number.isFinite(point.longitude) &&
            point.latitude >= 24 &&
            point.latitude <= 50 &&
            point.longitude >= -125 &&
            point.longitude <= -66 &&
            (selectedProduct === "all" ||
              point.benchmark_product_id === selectedProduct),
        )
        .slice(0, 3000),
    [points, selectedProduct],
  );
  const positioned = useMemo(
    () =>
      displayPopulation.filter(
        (point) =>
          selectedOutcome === "all" || point.outcome === selectedOutcome,
      ),
    [displayPopulation, selectedOutcome],
  );
  const displayOutcomeCounts = displayPopulation.reduce(
    (counts, point) => {
      const outcome = point.outcome ?? "parity";
      counts[outcome] = (counts[outcome] ?? 0) + (point.matches ?? 1);
      return counts;
    },
    {} as Record<string, number>,
  );
  const governedCounts = governedOutcomeCounts(decisions, selectedProduct);
  const outcomeCounts = governedCounts.total
    ? governedCounts
    : {
        benchmark_lower: displayOutcomeCounts.benchmark_lower ?? 0,
        competitor_lower: displayOutcomeCounts.competitor_lower ?? 0,
        parity: displayOutcomeCounts.parity ?? 0,
        total: Object.values(displayOutcomeCounts).reduce(
          (total, value) => total + value,
          0,
        ),
      };
  const clusters = useMemo(() => {
    const grouped = new Map<
      string,
      { point: MapPoint; count: number; x: number; y: number }
    >();
    for (const point of positioned) {
      const projected = projectCoordinate(point.longitude, point.latitude);
      const key = `${Math.round(projected.x / 14)}:${Math.round(projected.y / 14)}:${point.outcome ?? "parity"}`;
      const current = grouped.get(key);
      if (current) current.count += point.matches ?? 1;
      else grouped.set(key, { point, count: point.matches ?? 1, ...projected });
    }
    return [...grouped.values()];
  }, [positioned]);
  const selectedDecision =
    selectedProduct === "all"
      ? null
      : (decisions.find(
          (decision) => decision.benchmark_product_id === selectedProduct,
        ) ?? null);
  const coverage = coverageRows
    .map((row) => ({
      competitor: displayValue(row.competitor),
      geographies: parseCount(row["matched geographies"]),
    }))
    .filter((row) => row.geographies > 0)
    .sort((left, right) => right.geographies - left.geographies);
  return (
    <Section
      title={`Where ${displayLabel(benchmarkRetailer)} products win and lose`}
      note={`Outcome totals use the full governed product-decision population. Plotted points are a deterministic browser-safe display sample. ${comparisonBasisDescription(comparisonBasis)}.`}
    >
      <div className="map-controls">
        <label>
          <span>{displayLabel(benchmarkRetailer)} product</span>
          <select
            value={selectedProduct}
            onChange={(event) => setSelectedProduct(event.target.value)}
          >
            <option value="all">
              All mapped {displayLabel(benchmarkRetailer)} products
            </option>
            {products.map(([id, name]) => (
              <option value={id} key={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Price outcome</span>
          <select
            value={selectedOutcome}
            onChange={(event) => setSelectedOutcome(event.target.value)}
          >
            <option value="all">All outcomes</option>
            <option value="competitor_lower">Competitor lower</option>
            <option value="benchmark_lower">
              {displayLabel(benchmarkRetailer)} lower
            </option>
            <option value="parity">Price parity</option>
          </select>
        </label>
        <div className="map-legend" aria-label="Map outcome legend">
          <span className="benchmark_lower">
            {displayLabel(benchmarkRetailer)} lower ·{" "}
            {(outcomeCounts.benchmark_lower ?? 0).toLocaleString()}
          </span>
          <span className="competitor_lower">
            Competitor lower ·{" "}
            {(outcomeCounts.competitor_lower ?? 0).toLocaleString()}
          </span>
          <span className="parity">
            Parity · {(outcomeCounts.parity ?? 0).toLocaleString()}
          </span>
        </div>
        <p className="map-population-note">
          Full governed population: {outcomeCounts.total.toLocaleString()}{" "}
          matched observations · display sample:{" "}
          {displayPopulation.length.toLocaleString()} map points
          {selectedOutcome === "all"
            ? ""
            : ` · ${positioned.length.toLocaleString()} points visible for this outcome`}
        </p>
      </div>
      <div className="map-stage">
        <figure className="analysis-map">
          <svg
            viewBox="0 0 960 520"
            role="img"
            aria-label="Analysis-linked geographic price outcomes"
          >
            <rect width="960" height="520" rx="22" />
            <g className="state-layer">
              {continentalStateFeatures.map((state) => (
                <path d={geometryPath(state.geometry)} key={String(state.id)} />
              ))}
            </g>
            <g className="map-point-layer">
              {clusters.map(({ point, count, x, y }) => (
                <circle
                  cx={x}
                  cy={y}
                  r={Math.min(11, 4 + Math.sqrt(count))}
                  className={point.outcome ?? "parity"}
                  key={`${point.id}-${x}-${y}`}
                  onClick={() => setSelectedPoint(point)}
                  tabIndex={0}
                  role="button"
                  aria-label={`${point.benchmark_product_name ?? point.label}, ZIP ${point.zipcode ?? "unknown"}, ${formatMapValueLabel(point.value_label, comparisonBasis?.price_unit) ?? "price evidence"}`}
                >
                  <title>
                    {point.benchmark_product_name ?? point.label}
                    {point.zipcode ? ` · ZIP ${point.zipcode}` : ""}
                    {point.competitor
                      ? ` · vs. ${displayLabel(point.competitor)}`
                      : ""}
                    {point.value_label
                      ? ` · ${formatMapValueLabel(point.value_label, comparisonBasis?.price_unit)}`
                      : ""}
                    {count > 1 ? ` · ${count} nearby observations` : ""}
                  </title>
                </circle>
              ))}
            </g>
          </svg>
          <figcaption>
            Circle size reflects nearby sampled observations. Click a point for
            its product, ZIP, retailer, and{" "}
            {priceUnitLabel(comparisonBasis?.price_unit)} price difference.
            Legend and KPI totals remain full-population counts.
          </figcaption>
        </figure>
        <aside className="map-insight-rail">
          {selectedDecision ? (
            <div className="map-selected-product">
              <ProductThumbnailStack products={[selectedDecision]} />
              <span>Selected {displayLabel(benchmarkRetailer)} product</span>
              <strong>{selectedDecision.benchmark_product_name}</strong>
            </div>
          ) : (
            <div className="map-selected-product">
              <span>Current view</span>
              <strong>
                All mapped {displayLabel(benchmarkRetailer)} products
              </strong>
            </div>
          )}
          <EvidenceStat
            label="Full governed observations"
            value={outcomeCounts.total}
          />
          <EvidenceStat
            label="Map points in display sample"
            value={displayPopulation.length}
          />
          <EvidenceStat
            label="Competitor lower"
            value={outcomeCounts.competitor_lower ?? 0}
          />
          <EvidenceStat
            label={`${displayLabel(benchmarkRetailer)} lower`}
            value={outcomeCounts.benchmark_lower ?? 0}
          />
          <EvidenceStat
            label="Price parity"
            value={outcomeCounts.parity ?? 0}
          />
          {selectedPoint ? (
            <div className="map-point-detail">
              <span>Selected evidence</span>
              <strong>
                {selectedPoint.benchmark_product_name ?? selectedPoint.label}
              </strong>
              <p>
                ZIP {selectedPoint.zipcode ?? "—"} · vs.{" "}
                {displayLabel(selectedPoint.competitor ?? "competitor")}
              </p>
              <b>
                {formatMapValueLabel(
                  selectedPoint.value_label,
                  comparisonBasis?.price_unit,
                ) ?? "Price evidence"}
              </b>
            </div>
          ) : null}
          {coverage.slice(0, 3).map((row) => (
            <div className="map-coverage-row" key={row.competitor}>
              <span>{row.competitor}</span>
              <b>{row.geographies.toLocaleString()} matched ZIP markets</b>
            </div>
          ))}
        </aside>
      </div>
    </Section>
  );
}

function SegmentPositionMatrix({
  benchmarkRetailer,
  rows,
}: Readonly<{ benchmarkRetailer: string; rows: JsonObject[] }>) {
  const matrix = rows
    .map((row) => ({
      row,
      benchmarkRate: parseRate(row["benchmark lower"]),
      competitorRate: parseRate(row["competitor lower"]),
      matches: parseCount(row.matches),
      gap: displayValue(
        row["paired median gap"] ?? row["competitor - benchmark gap"],
      ),
    }))
    .filter(
      (item) => item.benchmarkRate !== null || item.competitorRate !== null,
    )
    .sort((left, right) => right.matches - left.matches);
  return (
    <div className="segment-matrix">
      <div className="segment-matrix-head">
        <span>Comparable product segment</span>
        <span>Lower-price leader</span>
        <span>Matched evidence</span>
        <span>Paired median difference</span>
      </div>
      {matrix
        .slice(0, 16)
        .map(({ row, benchmarkRate, competitorRate, matches, gap }, index) => {
          const benchmarkWins = (benchmarkRate ?? 0) >= (competitorRate ?? 0);
          return (
            <div className="segment-matrix-row" key={String(row.id ?? index)}>
              <div>
                <strong>
                  {displayValue(row.segment ?? "Comparable items")}
                </strong>
                <span>{displayValue(row.competitor)}</span>
              </div>
              <div>
                <span
                  className={`segment-leader ${benchmarkWins ? "benchmark" : "competitor"}`}
                >
                  {benchmarkWins
                    ? displayLabel(benchmarkRetailer)
                    : displayValue(row.competitor)}
                </span>
                <b>
                  {Math.max(benchmarkRate ?? 0, competitorRate ?? 0).toFixed(1)}
                  %
                </b>
              </div>
              <div>
                <strong>{matches.toLocaleString()}</strong>
                <span>matched observations</span>
              </div>
              <strong>{gap}</strong>
            </div>
          );
        })}
    </div>
  );
}

function uniqueDecisionRows(rows: JsonObject[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = JSON.stringify([
      row.summary,
      row.action,
      row.title,
      row.text,
      row.rationale,
    ]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function KeyPointCards({ rows }: Readonly<{ rows: JsonObject[] }>) {
  return (
    <div className="key-point-list">
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
          <article className="key-point-card" key={String(row.id ?? index)}>
            <span>
              {typeof rank === "number"
                ? `0${rank}`.slice(-2)
                : displayValue(rank)}
            </span>
            <div>
              <h3>{displayValue(headline)}</h3>
              {detail ? <p>{displayValue(detail)}</p> : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function QualityEvidence({ rows }: Readonly<{ rows: QualityObservation[] }>) {
  const issueCounts = rows.reduce(
    (counts, row) => {
      counts[row.issue] = (counts[row.issue] ?? 0) + 1;
      return counts;
    },
    {} as Record<string, number>,
  );
  return (
    <div className="quality-evidence">
      <div className="quality-explainer">
        <span>What this page contains</span>
        <strong>Source search records behind the quality counts</strong>
        <p>
          This is a representative, deterministic sample of rejected or
          incomplete search observations—not PDP data. Product, retailer, ZIP,
          store, source price, and the exact exclusion reason stay together so a
          reviewer can judge what the pipeline omitted.
        </p>
      </div>
      {rows.length ? (
        <>
          <div
            className="quality-issue-strip"
            aria-label="Displayed quality records"
          >
            {Object.entries(issueCounts).map(([issue, count]) => (
              <span key={issue}>
                <b>{count.toLocaleString()}</b> {issue}
              </span>
            ))}
          </div>
          <div className="table-scroll quality-observation-table">
            <table>
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Retailer</th>
                  <th>Search product</th>
                  <th>Price</th>
                  <th>ZIP</th>
                  <th>Store</th>
                  <th>Reason</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr
                    key={`${row.issue}-${row.retailer}-${row.product_id ?? index}-${row.zipcode ?? ""}-${row.store ?? ""}`}
                  >
                    <td>
                      <span className="quality-issue-label">{row.issue}</span>
                    </td>
                    <td>{displayLabel(row.retailer)}</td>
                    <td>
                      <div className="quality-product-cell">
                        {row.image_url ? (
                          // Search-result imagery is referential evidence and remains unoptimized.
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={row.image_url} alt="" loading="lazy" />
                        ) : null}
                        <span>
                          <b>{row.product}</b>
                          {row.product_id ? (
                            <small>{row.product_id}</small>
                          ) : null}
                        </span>
                      </div>
                    </td>
                    <td>
                      {typeof row.price === "number"
                        ? formatCurrency(row.price)
                        : displayValue(row.price)}
                    </td>
                    <td>{displayValue(row.zipcode)}</td>
                    <td>{displayValue(row.store)}</td>
                    <td>{row.reason}</td>
                    <td>
                      {row.source_url ? (
                        <a
                          href={row.source_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open result
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="quality-sample-note">
            Showing {rows.length.toLocaleString()} representative source
            observations. The authoritative issue totals remain in the governed
            narrative above.
          </p>
        </>
      ) : (
        <div className="empty-inline">
          No source search observations were retained for this publication.
        </div>
      )}
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
