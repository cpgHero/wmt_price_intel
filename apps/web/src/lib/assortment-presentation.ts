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
 * Assortment presentation fails closed. Search discovery or a legacy
 * `observed_locations` count cannot be relabeled as verified local carriage.
 */
export function isVerifiedAssortmentProduct(product: AssortmentProduct) {
  return (
    product.availability_status === "verified_in_stock" &&
    nonNegativeInteger(product.verified_available_locations) &&
    product.verified_available_locations > 0 &&
    nonNegativeInteger(product.verified_available_zipcodes) &&
    nonNegativeInteger(product.search_observed_locations) &&
    product.search_observed_locations >= product.verified_available_locations &&
    nonNegativeInteger(product.search_observed_zipcodes) &&
    product.search_observed_zipcodes >= product.verified_available_zipcodes
  );
}

export function verifiedAssortmentProducts(products: AssortmentProduct[]) {
  return products.filter(isVerifiedAssortmentProduct);
}

export function isVerifiedAssortmentBrand(brand: AssortmentBrand) {
  return (
    nonNegativeInteger(brand.verified_available_products) &&
    brand.verified_available_products > 0 &&
    nonNegativeInteger(brand.verified_available_locations) &&
    brand.verified_available_locations > 0 &&
    nonNegativeInteger(brand.verified_available_zipcodes)
  );
}

export function verifiedAssortmentBrands(brands: AssortmentBrand[]) {
  return brands.filter(isVerifiedAssortmentBrand);
}

export function productsForObservedBrand(
  products: AssortmentProduct[],
  brand: AssortmentBrand,
) {
  const target = brandToken(brand.brand);
  return verifiedAssortmentProducts(products).filter(
    (product) =>
      brandToken(
        Object.prototype.hasOwnProperty.call(product, "observed_brand")
          ? product.observed_brand
          : product.brand,
      ) === target,
  );
}
