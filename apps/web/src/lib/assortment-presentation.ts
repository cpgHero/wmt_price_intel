import type { AssortmentBrand, AssortmentProduct } from "./api";

function brandToken(value: unknown) {
  return String(value ?? "")
    .trim()
    .toLocaleLowerCase("en-US")
    .replace(/\s+/g, " ");
}

export function productsForObservedBrand(
  products: AssortmentProduct[],
  brand: AssortmentBrand,
) {
  const target = brandToken(brand.brand);
  return products.filter(
    (product) =>
      brandToken(
        Object.prototype.hasOwnProperty.call(product, "observed_brand")
          ? product.observed_brand
          : product.brand,
      ) === target,
  );
}
