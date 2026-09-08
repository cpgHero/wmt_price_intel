import type { AssortmentBrand, AssortmentProduct } from "./api";

function brandToken(value: unknown) {
  return String(value ?? "")
    .trim()
    .toLocaleLowerCase("en-US")
    .replace(/\s+/g, " ");
}

function nonNegativeInteger(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    Number.isFinite(value) &&
    value >= 0
  );
}

/**
 * Assortment presentation fails closed unless both explicit distribution
 * dimensions are present. Legacy Search, availability, and observed-location
 * counters are intentionally ignored.
 */
export function hasAssortmentDistribution(product: AssortmentProduct) {
  return (
    nonNegativeInteger(product.distribution_store_count) &&
    nonNegativeInteger(product.service_area_presence_count) &&
    (product.distribution_store_count > 0 ||
      product.service_area_presence_count > 0)
  );
}

export function assortmentProductsWithDistribution(
  products: AssortmentProduct[],
) {
  return products.filter(hasAssortmentDistribution);
}

export function hasAssortmentBrandDistribution(brand: AssortmentBrand) {
  return (
    nonNegativeInteger(brand.distribution_store_count) &&
    nonNegativeInteger(brand.service_area_presence_count) &&
    (brand.distribution_store_count > 0 ||
      brand.service_area_presence_count > 0)
  );
}

export function assortmentBrandsWithDistribution(brands: AssortmentBrand[]) {
  return brands.filter(hasAssortmentBrandDistribution);
}

export function productsForObservedBrand(
  products: AssortmentProduct[],
  brand: AssortmentBrand,
) {
  const target = brandToken(brand.brand);
  return assortmentProductsWithDistribution(products).filter(
    (product) =>
      brandToken(
        Object.prototype.hasOwnProperty.call(product, "observed_brand")
          ? product.observed_brand
          : product.brand,
      ) === target,
  );
}
