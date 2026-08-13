export type NavigationIcon =
  | "dashboard"
  | "prices"
  | "intelligence"
  | "collections"
  | "automation"
  | "brands"
  | "quality"
  | "matches"
  | "studies"
  | "product-packs";

export interface NavigationItem {
  description: string;
  href: string;
  icon: NavigationIcon;
  label: string;
  match: "exact" | "prefix";
}

export interface NavigationGroup {
  id: "workspace" | "intelligence" | "operations" | "administration";
  items: readonly NavigationItem[];
  label: string;
}

export const homeNavigationItem: NavigationItem = {
  label: "Home",
  description: "Decisions, activity, and operational health",
  href: "/",
  icon: "dashboard",
  match: "exact",
};

export const applicationNavigation: readonly NavigationGroup[] = [
  {
    id: "workspace",
    label: "Workspace",
    items: [
      {
        label: "Match Workbench",
        description: "Review and govern product relationships across reports",
        href: "/workspace/matches",
        icon: "matches",
        match: "prefix",
      },
      {
        label: "Brand Workbench",
        description: "Classify and govern observed brands across reports",
        href: "/workspace/brands",
        icon: "brands",
        match: "prefix",
      },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      {
        label: "Price Intelligence",
        description: "Store-level price distribution within each retailer",
        href: "/price-intelligence",
        icon: "prices",
        match: "prefix",
      },
      {
        label: "Competitive Intelligence",
        description: "Comparable products, price position, and assortment",
        href: "/analyses",
        icon: "intelligence",
        match: "prefix",
      },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    items: [
      {
        label: "Collections",
        description: "Definitions, runs, and paid collection controls",
        href: "/collections",
        icon: "collections",
        match: "prefix",
      },
      {
        label: "Schedules & Alerts",
        description: "Recurring work, conditions, and delivery",
        href: "/automation",
        icon: "automation",
        match: "prefix",
      },
      {
        label: "Data Quality",
        description: "Decision readiness and evidence exceptions",
        href: "/data-quality",
        icon: "quality",
        match: "prefix",
      },
    ],
  },
  {
    id: "administration",
    label: "Administration",
    items: [
      {
        label: "Study Discovery",
        description: "Evidence-led category onboarding",
        href: "/admin/studies",
        icon: "studies",
        match: "prefix",
      },
      {
        label: "Product Packs",
        description: "Governed category rules and certification",
        href: "/admin/product-packs",
        icon: "product-packs",
        match: "prefix",
      },
    ],
  },
] as const;

export function navigationItemIsActive(
  pathname: string,
  item: NavigationItem,
): boolean {
  if (item.match === "exact") return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

export function activeNavigationItem(pathname: string): NavigationItem | null {
  if (navigationItemIsActive(pathname, homeNavigationItem)) {
    return homeNavigationItem;
  }
  for (const group of applicationNavigation) {
    const item = group.items.find((candidate) =>
      navigationItemIsActive(pathname, candidate),
    );
    if (item) return item;
  }
  return null;
}
