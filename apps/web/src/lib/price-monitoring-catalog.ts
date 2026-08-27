import type { PriceMonitoringView } from "./api";

/**
 * Keep catalog responses focused on fields rendered by the product index.
 * Product workspaces always request one product and retain the complete PDP,
 * location, histogram, and distribution-gap evidence.
 */
export function compactPriceMonitoringCatalog(
  view: PriceMonitoringView,
): PriceMonitoringView {
  if (view.filters.product_id) return view;

  const gapTotal = view.distribution_gaps.location_display.total;
  return {
    ...view,
    distribution_gaps: {
      ...view.distribution_gaps,
      geographies: [],
      locations: [],
      location_display: {
        ...view.distribution_gaps.location_display,
        returned: 0,
        sampled: gapTotal > 0,
      },
    },
    products: view.products.map((product) => ({
      ...product,
      pdp: {
        enriched: product.pdp.enriched,
        authority: product.pdp.authority,
      },
      price_histogram: [],
      sample_locations: [],
    })),
  };
}
