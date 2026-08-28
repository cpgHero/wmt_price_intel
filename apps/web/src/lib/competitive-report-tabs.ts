export type ProductLeadershipViewName =
  "overview" | "match_group" | "matrix" | "ladders" | "stores" | "history";

export interface ProductLeadershipTab {
  id: string;
  label: string;
  view: ProductLeadershipViewName;
}

export type CompetitivePortfolioProjection =
  "scorecards" | "cohorts" | "assortment";

export function competitivePortfolioProjection(
  groupId: string,
): CompetitivePortfolioProjection | null {
  if (groupId === "overview") return "scorecards";
  if (groupId === "price-segments") return "cohorts";
  if (groupId === "assortment") return "assortment";
  return null;
}

export const leadershipTabs: readonly ProductLeadershipTab[] = [
  {
    id: "competitive-footprint",
    label: "Competitive Footprint",
    view: "overview",
  },
  {
    id: "matched-price-matrix",
    label: "Matched Price Matrix",
    view: "matrix",
  },
  {
    id: "match-summary",
    label: "Match Summary",
    view: "match_group",
  },
  { id: "price-ladders", label: "Price Ladders", view: "ladders" },
  { id: "store-comparisons", label: "Store Comparisons", view: "stores" },
  { id: "competitive-history", label: "Competitive History", view: "history" },
];

const defaultLeadershipTab = leadershipTabs[0]!;

export function leadershipTab(groupId: string) {
  return leadershipTabs.find((tab) => tab.id === groupId) ?? null;
}

export function legacyLeadershipTab(view: string | null) {
  if (view === "footprint" || view === "markets") return defaultLeadershipTab;
  if (view === "exceptions")
    return (
      leadershipTabs.find((tab) => tab.view === "stores") ??
      defaultLeadershipTab
    );
  return (
    leadershipTabs.find((tab) => tab.view === view) ?? defaultLeadershipTab
  );
}
