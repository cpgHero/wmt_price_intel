import { describe, expect, it } from "vitest";

import {
  activeNavigationItem,
  applicationNavigationForExperience,
  applicationNavigation,
  homeNavigationItem,
  navigationItemIsActive,
  simplifiedApplicationNavigation,
  simplifiedNavigationEnabled,
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
      "/price-intelligence",
      "/analyses",
      "/proximity",
      "/collections",
      "/automation",
      "/data-quality",
      "/admin/operations",
      "/admin/docs",
      "/admin/matching-v2",
      "/workspace/brands",
      "/admin/studies",
      "/admin/report-publishing",
      "/admin/product-packs",
    ]);
    expect(hrefs).not.toContain("/intelligence/price");
  });

  it("keeps the dashboard exact and activates nested workspaces by prefix", () => {
    const dashboard = homeNavigationItem;
    const competitive = applicationNavigation[0].items[1];

    expect(navigationItemIsActive("/", dashboard)).toBe(true);
    expect(navigationItemIsActive("/collections", dashboard)).toBe(false);
    expect(navigationItemIsActive("/analyses", competitive)).toBe(true);
    expect(navigationItemIsActive("/analyses/analysis-123", competitive)).toBe(
      true,
    );
    expect(activeNavigationItem("/workspace/matches")).toBeNull();
    expect(activeNavigationItem("/price-intelligence/analysis-123")).toBeNull();
    expect(activeNavigationItem("/proximity")?.label).toBe("Proximity");
    expect(
      activeNavigationItem(
        "/price-intelligence/analysis-123",
        applicationNavigation,
      )?.label,
    ).toBe("Price Intelligence");
    expect(activeNavigationItem("/admin/matching-v2")?.label).toBe(
      "Match Certification",
    );
    expect(activeNavigationItem("/admin/docs")?.label).toBe("Platform Docs");
    expect(activeNavigationItem("/admin/operations")?.label).toBe(
      "System Operations",
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

  it("uses simplified navigation by default and keeps legacy navigation behind an explicit disable flag", () => {
    expect(simplifiedNavigationEnabled({})).toBe(true);
    expect(
      simplifiedNavigationEnabled({
        NEXT_PUBLIC_RCI_SIMPLIFIED_NAV: "0",
      }),
    ).toBe(false);
    expect(
      simplifiedNavigationEnabled({
        NEXT_PUBLIC_RCI_SIMPLIFIED_NAV: "false",
      }),
    ).toBe(false);
    expect(
      simplifiedNavigationEnabled({
        NEXT_PUBLIC_RCI_SIMPLIFIED_NAV: "disabled",
      }),
    ).toBe(false);
    expect(
      simplifiedNavigationEnabled({
        NEXT_PUBLIC_RCI_SIMPLIFIED_NAV: "enabled",
      }),
    ).toBe(true);
    expect(applicationNavigationForExperience(false)).toBe(
      applicationNavigation,
    );
    expect(applicationNavigationForExperience(true)).toBe(
      simplifiedApplicationNavigation,
    );

    const hrefs = [
      homeNavigationItem.href,
      ...simplifiedApplicationNavigation.flatMap((group) =>
        group.items.map((item) => item.href),
      ),
    ];

    expect(hrefs).toEqual([
      "/",
      "/analyses",
      "/proximity",
      "/collections",
      "/automation",
      "/admin/report-publishing",
      "/admin/matching-v2",
      "/admin/product-packs",
      "/workspace/brands",
      "/admin/studies",
      "/admin/operations",
      "/admin/docs",
    ]);
    expect(hrefs).not.toContain("/price-intelligence");
    expect(hrefs).not.toContain("/data-quality");
    expect(
      activeNavigationItem(
        "/analyses/analysis-123",
        simplifiedApplicationNavigation,
      )?.label,
    ).toBe("Reports");
    expect(
      activeNavigationItem(
        "/admin/report-publishing",
        simplifiedApplicationNavigation,
      )?.label,
    ).toBe("Pipeline Status");
  });
});
