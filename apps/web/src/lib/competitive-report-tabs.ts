export type ProductLeadershipViewName =
  | "overview"
  | "footprint"
  | "match_group"
  | "ladders"
  | "stores"
  | "markets"
  | "exceptions"
  | "history";

export interface ProductLeadershipTab {
  id: string;
  label: string;
  view: ProductLeadershipViewName;
}

export const leadershipTabs: readonly ProductLeadershipTab[] = [
  { id: "leadership-overview", label: "Leadership Overview", view: "overview" },
  {
    id: "competitive-footprint",
    label: "Competitive Footprint",
    view: "footprint",
  },
  {
    id: "match-group-analysis",
    label: "Match Group Analysis",
    view: "match_group",
  },
  { id: "price-ladders", label: "Price Ladders", view: "ladders" },
  { id: "store-comparisons", label: "Store Comparisons", view: "stores" },
  { id: "market-performance", label: "Market Performance", view: "markets" },
  {
    id: "competitive-exceptions",
    label: "Competitive Exceptions",
    view: "exceptions",
  },
  { id: "competitive-history", label: "Competitive History", view: "history" },
];

const defaultLeadershipTab = leadershipTabs[0]!;

export function leadershipTab(groupId: string) {
  return leadershipTabs.find((tab) => tab.id === groupId) ?? null;
}

export function legacyLeadershipTab(view: string | null) {
  return (
    leadershipTabs.find((tab) => tab.view === view) ?? defaultLeadershipTab
  );
}
