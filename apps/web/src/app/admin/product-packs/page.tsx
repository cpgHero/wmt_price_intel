import Link from "next/link";

import { ProductPackAdmin } from "./product-pack-admin";

export const dynamic = "force-dynamic";

export default function ProductPacksPage() {
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Governed administration</p>
          <h1>Product Packs</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Build category intelligence through evidence, deterministic rules,
            comparison lenses, and immutable certification.
          </p>
          <Link className="button secondary" href="/admin/studies">
            Start with Study Discovery
          </Link>
        </div>
      </header>
      <ProductPackAdmin />
    </main>
  );
}
