import { describe, expect, it } from "vitest";

import {
  activeNavigationItem,
  applicationNavigation,
  homeNavigationItem,
  navigationItemIsActive,
} from "./app-navigation";

describe("application navigation", () => {
  it("exposes only routes that currently have usable application pages", () => {
    const hrefs = [
      homeNavigationItem.href,
      ...applicationNavigation.flatMap((group) =>
        group.items.map((item) => item.href),
      ),
    ];

    expect(hrefs).toEqual([
      "/",
      "/workspace/matches",
      "/workspace/brands",
      "/price-monitoring",
      "/analyses",
      "/collections",
      "/automation",
      "/data-quality",
      "/admin/studies",
      "/admin/product-packs",
    ]);
    expect(hrefs).not.toContain("/intelligence/price");
  });

  it("keeps the dashboard exact and activates nested workspaces by prefix", () => {
    const dashboard = homeNavigationItem;
    const competitive = applicationNavigation[1].items[1];

    expect(navigationItemIsActive("/", dashboard)).toBe(true);
    expect(navigationItemIsActive("/collections", dashboard)).toBe(false);
    expect(navigationItemIsActive("/analyses", competitive)).toBe(true);
    expect(navigationItemIsActive("/analyses/analysis-123", competitive)).toBe(
      true,
    );
    expect(activeNavigationItem("/workspace/matches")?.label).toBe(
      "Match Workbench",
    );
    expect(activeNavigationItem("/price-monitoring/analysis-123")?.label).toBe(
      "Price Monitoring",
    );
  });

  it("returns the page context for detail routes", () => {
    expect(activeNavigationItem("/collections/runs/run-123")?.label).toBe(
      "Collections",
    );
    expect(
      activeNavigationItem("/admin/product-packs/drafts/draft-1")?.label,
    ).toBe("Product Packs");
    expect(activeNavigationItem("/health")).toBeNull();
  });
});
