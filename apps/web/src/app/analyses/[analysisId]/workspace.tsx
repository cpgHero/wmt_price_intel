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
import {
  comparableCohort,
  comparableCohorts,
  type ComparableCohort,
} from "@/lib/cohort-model";
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
  ProductMatchCandidate,
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
  cohortProductSummaries,
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
  scorecardProductSummaries,
  type ScorecardProductSummary,
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

function brandTypeSummary(
  products: ScorecardProductSummary[],
  side: "benchmark" | "competitor",
) {
  const labels = {
    private_label: "private label",
    regional: "regional",
    national: "national",
    unclassified: "unclassified",
  } as const;
  const counts = new Map<string, number>();
  for (const product of products) {
    const brandType =
      side === "benchmark"
        ? product.benchmark_brand_type
        : product.competitor_brand_type;
    counts.set(brandType, (counts.get(brandType) ?? 0) + 1);
  }
  return (["private_label", "regional", "national", "unclassified"] as const)
    .filter((brandType) => counts.has(brandType))
    .map((brandType) => `${counts.get(brandType)} ${labels[brandType]}`)
    .join(" · ");
}

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
  const reportTabs = useMemo(() => {
    const labels: Record<string, string> = {
      overview: "Executive Overview",
      "price-segments": "Price Architecture",
      assortment: "Assortment & Whitespace",
      "quality-methodology": "Data Integrity",
    };
    return groupedSections
      .filter((group) => Object.prototype.hasOwnProperty.call(labels, group.id))
      .map((group) => ({
        ...group,
        label: labels[group.id] ?? group.label,
      }));
  }, [groupedSections]);
  const firstPopulatedGroup =
    reportTabs.find((group) => group.sections.length > 0)?.id ?? "overview";
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
  const [selectedCohort, setSelectedCohort] = useState<ComparableCohort | null>(
    null,
  );
  const leadershipProductOptions = useMemo(() => {
    const benchmarkRetailerId = reportView.retailer_scope.benchmark.id;
    const governedProducts =
      reportView.assortment_analysis?.retailers.find(
        (row) => row.retailer === benchmarkRetailerId,
      )?.products ?? [];
    if (governedProducts.length > 0) {
      return [...governedProducts]
        .sort(
          (left, right) =>
            right.observed_locations - left.observed_locations ||
            left.name.localeCompare(right.name),
        )
        .map((row) => ({
          id: row.product_id,
          name: row.name,
          imageUrl: row.image_url,
        }));
    }
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
    reportView.assortment_analysis,
    reportView.retailer_scope.benchmark.id,
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
            reportTabs.some((group) => group.id === requestedTab))
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
      const nextLeadershipProduct =
        requestedProduct &&
        leadershipProductOptions.some(
          (option) => option.id === requestedProduct,
        )
          ? requestedProduct
          : (leadershipProductOptions[0]?.id ?? null);
      setSelectedLeadershipProduct(nextLeadershipProduct);
      if (
        requestedTab === "product-leadership" &&
        requestedProduct !== nextLeadershipProduct
      ) {
        if (nextLeadershipProduct)
          parameters.set("product", nextLeadershipProduct);
        else parameters.delete("product");
        parameters.delete("state");
        parameters.delete("city");
        const normalizedUrl = new URL(window.location.href);
        normalizedUrl.search = parameters.toString();
        window.history.replaceState(window.history.state, "", normalizedUrl);
      }
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
    reportTabs,
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
    setSelectedCohort(null);
    updateRoute({ competitor: next === "all" ? null : next });
  };
  const selectGroup = (groupId: string) => {
    setActiveGroup(groupId);
    if (groupId !== "price-segments") setSelectedCohort(null);
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
    setSelectedCohort(null);
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
  const reviewDecision = (
    decision: ProductDecision | ScorecardProductSummary,
  ) => {
    const parameters = new URLSearchParams();
    parameters.set("pack", reportView.product_pack.id);
    const competitor = competitorOptions.find((option) =>
      matchesRetailer(decision.competitor, option),
    )?.id;
    if (competitor) parameters.set("competitor", competitor);
    parameters.set("benchmark_product", decision.benchmark_product_id);
    parameters.set("competitor_product", decision.competitor_product_id);
    router.push(`/admin/matching-v2?${parameters.toString()}`);
  };
  const openMatchWorkbench = () => {
    const parameters = new URLSearchParams();
    parameters.set("pack", reportView.product_pack.id);
    if (selectedCompetitor !== "all")
      parameters.set("competitor", selectedCompetitor);
    router.push(`/admin/matching-v2?${parameters.toString()}`);
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
      .filter(
        (section) =>
          section.kind === "price_position" ||
          section.kind === "segment_analysis",
      )
      .flatMap((section) => section.records) ?? [];
  const publication = reportView.publication;
  const recommendedCharts = reportView.product_pack.recommended_charts ?? [];
  const selectedScorecards = reportView.retailer_scorecards.filter(
    (scorecard) =>
      (!selectedRetailer || scorecard.competitor_id === selectedRetailer.id) &&
      (!selectedLens || scorecard.profile_id === selectedLens),
  );
  const reportedScorecards = selectedScorecards.filter(
    (scorecard) =>
      scorecard.evidence_state === "reported" && (scorecard.matches ?? 0) > 0,
  );
  const readyScorecards = reportedScorecards.filter(
    (scorecard) => scorecard.status === "ready",
  );
  const selectedBasis =
    reportView.comparison_bases.find(
      (basis) => basis.profile_id === selectedLens,
    ) ?? null;
  const selectedCohortBasis = selectedCohort
    ? (reportView.comparison_bases.find(
        (basis) => basis.profile_id === selectedCohort.profileId,
      ) ?? null)
    : null;
  const selectedCohortProducts = useMemo(
    () =>
      selectedCohort
        ? cohortProductSummaries(
            selectedCohort,
            reportView.match_candidates ?? [],
            reportView.product_decisions ?? [],
            reportView.assortment_analysis ?? null,
          )
        : [],
    [
      reportView.assortment_analysis,
      reportView.match_candidates,
      reportView.product_decisions,
      selectedCohort,
    ],
  );
  const cohortPairEvidence = Object.fromEntries(
    comparableCohorts(cohortRecords).map((cohort) => {
      const products = cohortProductSummaries(
        cohort,
        reportView.match_candidates ?? [],
        reportView.product_decisions ?? [],
        reportView.assortment_analysis ?? null,
      );
      return [
        cohort.id,
        {
          pairCount: products.length,
          benchmarkBrandTypes:
            brandTypeSummary(products, "benchmark") || "brand type unresolved",
          competitorBrandTypes:
            brandTypeSummary(products, "competitor") || "brand type unresolved",
        },
      ];
    }),
  );
  const openCohortRecord = (record: JsonObject) => {
    const cohort = comparableCohort(record);
    if (cohort) setSelectedCohort(cohort);
  };
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
  const certificationCoverage = reportView.certification_coverage ?? null;
  const selectedCertificationCoverage =
    selectedCompetitor === "all"
      ? null
      : (certificationCoverage?.retailers?.find(
          (retailer) => retailer.competitor_retailer_id === selectedCompetitor,
        ) ?? null);
  const reportedRelationshipCount = (
    reportView.match_relationships ?? []
  ).filter((relationship) => {
    const competitorId = relationship.competitor_id;
    const eligibleProfiles = relationship.eligible_profile_ids;
    return (
      (selectedCompetitor === "all" || competitorId === selectedCompetitor) &&
      (!selectedLens ||
        (Array.isArray(eligibleProfiles) &&
          eligibleProfiles.includes(selectedLens)))
    );
  }).length;
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
              label: "Reported relationships",
              value: reportedRelationshipCount.toLocaleString(),
            },
            ...(selectedCertificationCoverage
              ? [
                  {
                    label: "Retailer candidates",
                    value:
                      selectedCertificationCoverage.candidate_count.toLocaleString(),
                  },
                  {
                    label: "Certified comparable",
                    value:
                      selectedCertificationCoverage.certified_comparable_count.toLocaleString(),
                  },
                  {
                    label: "Certified not comparable",
                    value:
                      selectedCertificationCoverage.certified_not_comparable_count.toLocaleString(),
                  },
                  {
                    label: "Unresolved candidates",
                    value:
                      selectedCertificationCoverage.unresolved_count.toLocaleString(),
                  },
                ]
              : certificationCoverage
                ? [
                    ...(certificationCoverage.source_candidate_count !==
                    undefined
                      ? [
                          {
                            label: "Source candidates",
                            value:
                              certificationCoverage.source_candidate_count.toLocaleString(),
                          },
                          {
                            label: "Candidates selected",
                            value:
                              certificationCoverage.selected_candidate_count?.toLocaleString() ??
                              certificationCoverage.queue_case_count.toLocaleString(),
                          },
                        ]
                      : []),
                    {
                      label: "Certified decisions",
                      value:
                        certificationCoverage.certified_label_count.toLocaleString(),
                    },
                    {
                      label: "Unresolved candidates",
                      value:
                        certificationCoverage.unresolved_excluded_count.toLocaleString(),
                    },
                  ]
                : []),
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
                href: `/admin/matching-v2?pack=${encodeURIComponent(reportView.product_pack.id)}`,
                parameters: {
                  competitor:
                    selectedCompetitor === "all" ? null : selectedCompetitor,
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
    reportView.product_pack.id,
    certificationCoverage,
    selectedCertificationCoverage,
    reportedRelationshipCount,
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
        {reportTabs.slice(0, 2).map((group) => (
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
        {reportTabs.slice(2).map((group) => (
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
      </div>
      <section className="workspace-panel" role="tabpanel">
        {activeGroup === "product-leadership" ? (
          <ProductLeadershipWorkspace
            analysisId={analysis.analysis_id}
            productPackId={reportView.product_pack.id}
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
              <>
                <PortfolioLeadershipSummary
                  benchmark={reportView.retailer_scope.benchmark}
                  scorecards={selectedScorecards}
                  reported={reportedScorecards}
                  ready={readyScorecards}
                />
                <RetailerScorecardPanel
                  benchmark={reportView.retailer_scope.benchmark}
                  rows={selectedScorecards}
                  candidates={reportView.match_candidates ?? []}
                  decisions={reportView.product_decisions ?? []}
                  relationships={reportView.match_relationships ?? []}
                  assortment={reportView.assortment_analysis ?? null}
                  onSelect={selectCompetitor}
                  onReviewMatch={reviewDecision}
                />
              </>
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
                onOpenCohort={setSelectedCohort}
                pairEvidence={cohortPairEvidence}
              />
            ) : null}
            {activeGroup === "price-segments" && selectedCohort ? (
              <IncludedProductsDrawer
                key={selectedCohort.id}
                benchmark={reportView.retailer_scope.benchmark}
                cohort={{
                  cohort: selectedCohort,
                  comparisonBasis: selectedCohortBasis,
                }}
                products={selectedCohortProducts}
                onClose={() => setSelectedCohort(null)}
                onReviewMatch={reviewDecision}
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
                    onSelectCohort={
                      activeGroup === "price-segments"
                        ? openCohortRecord
                        : undefined
                    }
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
  const [requestedCompetitorId, setRequestedCompetitorId] = useState(
    selected?.id ?? competitors[0]?.id ?? "",
  );
  const activeCompetitorId =
    selected?.id ??
    (competitors.some((competitor) => competitor.id === requestedCompetitorId)
      ? requestedCompetitorId
      : (competitors[0]?.id ?? ""));
  const activeCompetitor =
    competitors.find((competitor) => competitor.id === activeCompetitorId) ??
    competitors[0] ??
    null;
  const comparisons = activeCompetitor
    ? data.comparisons.filter((row) =>
        matchesRetailer(row.competitor, activeCompetitor),
      )
    : [];
  const benchmarkSummary = data.retailers.find((row) =>
    matchesRetailer(row.retailer, benchmark),
  );
  return (
    <div className="assortment-analysis">
      <nav
        className="assortment-retailer-tabs"
        aria-label="Competitor assortment"
      >
        {competitors.map((competitor) => (
          <button
            aria-current={
              competitor.id === activeCompetitor?.id ? "page" : undefined
            }
            key={competitor.id}
            onClick={() => setRequestedCompetitorId(competitor.id)}
            type="button"
          >
            {benchmark.name} vs. {competitor.name}
          </button>
        ))}
      </nav>
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

function PortfolioLeadershipSummary({
  benchmark,
  scorecards,
  reported,
  ready,
}: Readonly<{
  benchmark: RetailerOption;
  scorecards: RetailerScorecard[];
  reported: RetailerScorecard[];
  ready: RetailerScorecard[];
}>) {
  const matchedObservations = reported.reduce(
    (total, scorecard) => total + (scorecard.matches ?? 0),
    0,
  );
  const benchmarkLeads = ready.filter(
    (scorecard) => scorecard.dominant_outcome === "benchmark_lower",
  ).length;
  const competitorLeads = ready.filter(
    (scorecard) => scorecard.dominant_outcome === "competitor_lower",
  ).length;
  const limitedViews = scorecards.length - ready.length;
  const coverageRate = scorecards.length
    ? reported.length / scorecards.length
    : null;

  return (
    <section className="portfolio-leadership-summary">
      <header>
        <div>
          <p className="eyebrow">Current governed comparison</p>
          <h2>Portfolio price leadership at a glance</h2>
          <p>
            A retailer-level rollup for the selected comparison basis. Counts
            below summarize governed scorecards; open the retailer table for the
            products and evidence behind each result.
          </p>
        </div>
        <span className="portfolio-summary-context">
          {benchmark.name} versus {scorecards.length.toLocaleString()} retailer
          {scorecards.length === 1 ? "" : " views"}
        </span>
      </header>
      <div className="portfolio-summary-grid">
        <article>
          <small>Competitors with evidence</small>
          <strong>
            {reported.length.toLocaleString()} of{" "}
            {scorecards.length.toLocaleString()}
          </strong>
          <span>
            {coverageRate === null
              ? "No retailer views configured"
              : `${formatScorecardRate(coverageRate)} of selected views`}
          </span>
        </article>
        <article>
          <small>Decision-ready retailer views</small>
          <strong>
            {ready.length.toLocaleString()} of{" "}
            {scorecards.length.toLocaleString()}
          </strong>
          <span>
            {limitedViews.toLocaleString()} limited or unscored under current
            rules
          </span>
        </article>
        <article>
          <small>Matched price observations</small>
          <strong>{matchedObservations.toLocaleString()}</strong>
          <span>Summed across the selected retailer scorecards</span>
        </article>
        <article className="portfolio-summary-position">
          <small>Retailer-view leadership</small>
          <strong>
            {benchmarkLeads.toLocaleString()}–{competitorLeads.toLocaleString()}
          </strong>
          <span>
            {benchmark.name} leads – competitor leads; ready views only
          </span>
        </article>
      </div>
      <footer>
        <span>
          Snapshot measure: price position, not sales, margin, elasticity, or
          customer price perception.
        </span>
        <span>Parity and mixed outcomes remain visible in the scorecard.</span>
      </footer>
    </section>
  );
}

function RetailerScorecardPanel({
  benchmark,
  rows,
  candidates,
  decisions,
  relationships,
  assortment,
  onSelect,
  onReviewMatch,
}: Readonly<{
  benchmark: RetailerOption;
  rows: RetailerScorecard[];
  candidates: ProductMatchCandidate[];
  decisions: ProductDecision[];
  relationships: JsonObject[];
  assortment: AssortmentAnalysis | null;
  onSelect: (retailerId: string) => void;
  onReviewMatch: (product: ScorecardProductSummary) => void;
}>) {
  const [selectedScorecard, setSelectedScorecard] =
    useState<RetailerScorecard | null>(null);
  const ranked = useMemo(
    () =>
      [...rows].sort(
        (left, right) => (right.matches ?? 0) - (left.matches ?? 0),
      ),
    [rows],
  );
  const productsByScorecard = useMemo(
    () =>
      new Map(
        ranked.map((row) => [
          `${row.competitor_id}::${row.profile_id}`,
          scorecardProductSummaries(
            row,
            candidates,
            decisions,
            relationships,
            assortment,
          ),
        ]),
      ),
    [assortment, candidates, decisions, ranked, relationships],
  );
  const selectedProducts = selectedScorecard
    ? (productsByScorecard.get(
        `${selectedScorecard.competitor_id}::${selectedScorecard.profile_id}`,
      ) ?? [])
    : [];
  return (
    <>
      <Section
        title={
          rows.length === 1
            ? `${rows[0].competitor} scorecard`
            : "Retailer scorecard"
        }
        note={`Each row names its persisted Product Pack comparison basis. These publication scorecards retain their legacy exact-ZIP geography; use Product Leadership for current 1-, 3-, or 5-mile physical-store analysis and same-ZIP service-area analysis. Open a row's relationship-pair view to inspect its governed product identities.`}
      >
        <div className="retailer-scorecard-table">
          <div className="retailer-scorecard-head">
            <span>Competitor</span>
            <span>Matched evidence</span>
            <span>Lower-price share</span>
            <span>Paired median price position</span>
            <span>Status</span>
          </div>
          {ranked.map((row) => {
            const includedProducts =
              productsByScorecard.get(
                `${row.competitor_id}::${row.profile_id}`,
              ) ?? [];
            return (
              <div
                className="retailer-scorecard-row"
                key={`${row.competitor_id}::${row.profile_id}`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(row.competitor_id)}
                >
                  <strong>{row.competitor}</strong>
                  <span>{row.comparison_lens}</span>
                  <small>
                    {displayLabel(row.comparison_metric)} ·{" "}
                    {priceUnitLabel(row.price_unit)} ·{" "}
                    {displayLabel(row.geography)}
                  </small>
                </button>
                <div className="retailer-scorecard-evidence">
                  <strong>{(row.matches ?? 0).toLocaleString()}</strong>
                  <span>
                    {row.evidence_state === "no_governed_relationships"
                      ? "governed relationships"
                      : row.evidence_state === "no_admissible_observations"
                        ? "admissible observations"
                        : "matched observations"}
                  </span>
                  <small>
                    {row.matched_geographies === null
                      ? "Legacy exact-ZIP count unavailable"
                      : `${row.matched_geographies.toLocaleString()} legacy exact-ZIP markets`}
                  </small>
                  <button
                    type="button"
                    disabled={includedProducts.length === 0}
                    onClick={() => setSelectedScorecard(row)}
                  >
                    {includedProducts.length > 0
                      ? `View ${includedProducts.length.toLocaleString()} relationship pair${includedProducts.length === 1 ? "" : "s"}`
                      : "Product summary unavailable"}
                  </button>
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
            );
          })}
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
      {selectedScorecard ? (
        <IncludedProductsDrawer
          key={`${selectedScorecard.competitor_id}::${selectedScorecard.profile_id}`}
          benchmark={benchmark}
          scorecard={selectedScorecard}
          products={selectedProducts}
          onClose={() => setSelectedScorecard(null)}
          onReviewMatch={onReviewMatch}
        />
      ) : null}
    </>
  );
}

interface CohortDrawerContext {
  cohort: ComparableCohort;
  comparisonBasis: AnalysisReportView["comparison_bases"][number] | null;
}

function IncludedProductsDrawer({
  benchmark,
  scorecard,
  cohort,
  products,
  onClose,
  onReviewMatch,
}: Readonly<{
  benchmark: RetailerOption;
  scorecard?: RetailerScorecard;
  cohort?: CohortDrawerContext;
  products: ScorecardProductSummary[];
  onClose: () => void;
  onReviewMatch: (product: ScorecardProductSummary) => void;
}>) {
  const competitor =
    scorecard?.competitor ?? cohort?.cohort.competitor ?? "Competitor";
  const priceUnit =
    scorecard?.price_unit ??
    cohort?.comparisonBasis?.price_unit ??
    "USD/package";
  const matches = scorecard?.matches ?? cohort?.cohort.matches ?? 0;
  const geographies =
    scorecard?.matched_geographies ?? cohort?.cohort.matchedGeographies ?? null;
  const basisLabel =
    scorecard?.comparison_lens ??
    cohort?.comparisonBasis?.label ??
    "Configured Product Pack cohort";
  const basisDetail = scorecard
    ? `${displayLabel(scorecard.comparison_metric)} · ${priceUnitLabel(scorecard.price_unit)} · ${displayLabel(scorecard.geography)}`
    : cohort?.comparisonBasis
      ? `${displayLabel(cohort.comparisonBasis.comparison_metric)} · ${priceUnitLabel(cohort.comparisonBasis.price_unit)} · ${displayLabel(cohort.comparisonBasis.geography)}`
      : "Persisted comparison basis";
  const drawerId = scorecard
    ? "scorecard-products-title"
    : "cohort-products-title";
  const [query, setQuery] = useState("");
  const [visibleLimit, setVisibleLimit] = useState(25);
  const hasAggregateOnlyRelationships = products.some(
    (product) => !product.evidence_available,
  );
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);
  const filteredProducts = useMemo(() => {
    const token = query.trim().toLocaleLowerCase("en-US");
    if (!token) return products;
    return products.filter((product) =>
      [
        product.benchmark_product_name,
        product.benchmark_product_id,
        product.competitor_product_name,
        product.competitor_product_id,
        product.match_rationale ?? "",
        ...Object.entries(product.match_attributes).flatMap(([name, value]) => [
          name,
          displayValue(value),
        ]),
      ]
        .join(" ")
        .toLocaleLowerCase("en-US")
        .includes(token),
    );
  }, [products, query]);
  const visibleProducts = filteredProducts.slice(0, visibleLimit);
  return (
    <div
      className="evidence-drawer-backdrop scorecard-products-layer"
      role="presentation"
      onClick={onClose}
    >
      <aside
        className="evidence-drawer scorecard-products-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby={drawerId}
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span className="eyebrow">
              {scorecard
                ? "Retailer scorecard evidence"
                : "Product Pack cohort evidence"}
            </span>
            <h2 id={drawerId}>
              {scorecard
                ? hasAggregateOnlyRelationships
                  ? `Governed products behind ${competitor} scorecard`
                  : `Products included in ${competitor} scorecard`
                : `Products included in ${cohort?.cohort.segment ?? "this cohort"}`}
            </h2>
            <p>
              One summary per {benchmark.name}–{competitor} product pair
              represented by this result. Store-level rows are intentionally
              omitted.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close included products"
          >
            ×
          </button>
        </header>
        <div className="scorecard-products-summary">
          <div>
            <span>
              {hasAggregateOnlyRelationships
                ? "Governed relationships"
                : "Included relationships"}
            </span>
            <strong>{products.length.toLocaleString()}</strong>
          </div>
          <div>
            <span>Matched observations</span>
            <strong>{matches.toLocaleString()}</strong>
          </div>
          <div>
            <span>Legacy exact-ZIP markets</span>
            <strong>{geographies?.toLocaleString() ?? "—"}</strong>
          </div>
          <div>
            <span>Comparison basis</span>
            <strong>{basisLabel}</strong>
            <small>{basisDetail}</small>
          </div>
        </div>
        <div className="scorecard-products-authority">
          <strong>How to read this list</strong>
          <p>
            {scorecard
              ? hasAggregateOnlyRelationships
                ? "These relationships are admitted to the scorecard's governed comparison profile. Rows with persisted relationship-level outcomes show their own price evidence; aggregate-only rows show product identity without allocating or inferring a product-level price result."
                : "These are the admitted product relationships represented by the scorecard's governed comparison profile."
              : "These are the analysis-source product pairs whose Product Pack attributes place them in this immutable cohort result. Their current relationship status is shown on each row; the cohort does not create one-to-many product matches."}{" "}
            Search observations remain authoritative for price and location; PDP
            enrichment supplies identity and imagery where available.
          </p>
        </div>
        <div className="scorecard-products-toolbar">
          <label>
            <span>Find a product</span>
            <input
              type="search"
              value={query}
              placeholder="Search by product name, item ID, or attribute"
              onChange={(event) => {
                setQuery(event.target.value);
                setVisibleLimit(25);
              }}
            />
          </label>
          <span>
            Showing {Math.min(visibleLimit, filteredProducts.length)} of{" "}
            {filteredProducts.length.toLocaleString()} relationships
          </span>
        </div>
        <div className="scorecard-product-list">
          {visibleProducts.map((product) => (
            <ScorecardProductRow
              key={
                product.relationship_id ??
                `${product.benchmark_product_id}::${product.competitor_product_id}`
              }
              benchmark={benchmark}
              competitor={competitor}
              priceUnit={priceUnit}
              product={product}
              onReviewMatch={() => onReviewMatch(product)}
            />
          ))}
          {visibleProducts.length === 0 ? (
            <p className="scorecard-products-empty">
              {query
                ? "No included products match this search."
                : "No product identities are available for this summary in the current publication."}
            </p>
          ) : null}
        </div>
        {visibleLimit < filteredProducts.length ? (
          <button
            className="scorecard-products-more"
            type="button"
            onClick={() => setVisibleLimit((value) => value + 25)}
          >
            Show 25 more products
          </button>
        ) : null}
      </aside>
    </div>
  );
}

function ScorecardProductRow({
  benchmark,
  competitor,
  priceUnit,
  product,
  onReviewMatch,
}: Readonly<{
  benchmark: RetailerOption;
  competitor: string;
  priceUnit: string;
  product: ScorecardProductSummary;
  onReviewMatch: () => void;
}>) {
  const hasRelationshipEvidence = product.evidence_available;
  const parityShare = product.matches ? product.parity / product.matches : 0;
  const outcome =
    product.stance === "attention"
      ? `${competitor} is lower in ${formatScorecardRate(product.competitor_lower_share)} of matched observations`
      : product.stance === "protect"
        ? `${benchmark.name} is lower in ${formatScorecardRate(product.benchmark_lower_share)} of matched observations`
        : product.stance === "parity"
          ? `Prices are tied in ${formatScorecardRate(parityShare)} of matched observations`
          : `Mixed result: ${benchmark.name} is lower in ${formatScorecardRate(product.benchmark_lower_share)}, ${competitor} is lower in ${formatScorecardRate(product.competitor_lower_share)}, and ${formatScorecardRate(parityShare)} are tied`;
  const attributeRows = Object.entries(product.match_attributes)
    .filter(
      ([, value]) => value !== null && value !== undefined && value !== "",
    )
    .slice(0, 6);
  return (
    <article className={`scorecard-product-row ${product.stance}`}>
      <div className="scorecard-product-pair">
        <div>
          <ProductImage
            imageUrl={product.benchmark_image_url}
            name={product.benchmark_product_name}
            retailer={benchmark.name}
          />
          <span>
            <small>{benchmark.name}</small>
            <strong>{product.benchmark_product_name}</strong>
            <code>Item {product.benchmark_product_id}</code>
          </span>
        </div>
        <b>vs</b>
        <div>
          <ProductImage
            imageUrl={product.competitor_image_url}
            name={product.competitor_product_name}
            retailer={competitor}
          />
          <span>
            <small>{competitor}</small>
            <strong>{product.competitor_product_name}</strong>
            <code>Item {product.competitor_product_id}</code>
          </span>
        </div>
      </div>
      <div className="scorecard-product-outcome">
        <span className={`scorecard-product-stance ${product.stance}`}>
          {!hasRelationshipEvidence
            ? "Governed relationship"
            : product.stance === "attention"
              ? "Needs attention"
              : product.stance === "protect"
                ? "Position to protect"
                : product.stance === "parity"
                  ? "Price parity"
                  : "Mixed result"}
        </span>
        {hasRelationshipEvidence ? (
          <>
            <strong>{outcome}</strong>
            <small>
              {product.matches.toLocaleString()} matched observations across{" "}
              {product.geographies.toLocaleString()} ZIP markets
            </small>
            <div
              className="scorecard-product-share"
              aria-label={`${benchmark.name} lower ${formatScorecardRate(product.benchmark_lower_share)}, ${competitor} lower ${formatScorecardRate(product.competitor_lower_share)}, parity ${formatScorecardRate(parityShare)}`}
            >
              <i
                className="benchmark"
                style={{ width: `${product.benchmark_lower_share * 100}%` }}
              />
              <i
                className="competitor"
                style={{ width: `${product.competitor_lower_share * 100}%` }}
              />
              <i
                className="parity"
                style={{ width: `${parityShare * 100}%` }}
              />
            </div>
            <div className="scorecard-product-prices">
              <span>
                {benchmark.name} median price
                <b>
                  {formatPriceForBasis(
                    product.median_benchmark_price,
                    priceUnit,
                  )}
                </b>
              </span>
              <span>
                {competitor} median price
                <b>
                  {formatPriceForBasis(
                    product.median_competitor_price,
                    priceUnit,
                  )}
                </b>
              </span>
              <span>
                Paired median gap · competitor minus {benchmark.name}
                <b>{formatPriceForBasis(product.median_gap, priceUnit)}</b>
              </span>
            </div>
          </>
        ) : (
          <>
            <strong>
              This product pair is governed for the scorecard basis.
            </strong>
            <small>
              The immutable publication retains retailer-level scorecard totals,
              but does not persist a separate price allocation for this
              relationship. No per-product price result is inferred here.
            </small>
          </>
        )}
        {product.match_rationale || attributeRows.length ? (
          <div className="scorecard-product-basis">
            {product.match_rationale ? <p>{product.match_rationale}</p> : null}
            {attributeRows.length ? (
              <div>
                {attributeRows.map(([name, value]) => (
                  <span key={name}>
                    {displayLabel(name)}: {displayValue(value)}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        <footer>
          <span>
            {product.relationship_status === "confirmed"
              ? "User-confirmed relationship"
              : product.relationship_status === "suggested"
                ? "Engine-suggested governed relationship"
                : product.relationship_status === "ambiguous"
                  ? "Ambiguous relationship · review required"
                  : product.relationship_status === "rejected"
                    ? "Rejected relationship in current governance"
                    : "Analysis-source pair · not yet governed"}
          </span>
          <button type="button" onClick={onReviewMatch}>
            Open in Match Certification →
          </button>
        </footer>
      </div>
    </article>
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
  onSelectCohort,
}: Readonly<{
  section: ReportSectionView;
  recommendedCharts: string[];
  benchmarkRetailer: string;
  productDecisions: ProductDecision[];
  qualityObservations: QualityObservation[];
  showPortfolioNarrative: boolean;
  selectedRetailerName: string | null;
  onSelectCohort?: (record: JsonObject) => void;
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
          onSelect={onSelectCohort}
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
                    ? `${evidence.benchmark_store_observations.toLocaleString()} observed benchmark stores across ${evidence.matched_zip_markets?.toLocaleString() ?? row.geographies.toLocaleString()} legacy exact-ZIP markets.`
                    : `${row.geographies.toLocaleString()} legacy exact-ZIP markets in this publication comparison.`}
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
                        Open in Match Certification
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
              <b>{row.geographies.toLocaleString()} legacy exact-ZIP markets</b>
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
  onSelect,
}: Readonly<{
  benchmarkRetailer: string;
  rows: JsonObject[];
  onSelect?: (record: JsonObject) => void;
}>) {
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
            <button
              type="button"
              className="segment-matrix-row"
              key={String(row.id ?? index)}
              onClick={() => onSelect?.(row)}
              disabled={!onSelect}
              aria-label={`View products included in ${displayValue(row.segment ?? "Comparable items")}`}
            >
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
              <span className="segment-matrix-action">View products →</span>
            </button>
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
