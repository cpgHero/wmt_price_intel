import Link from "next/link";

import { StudyDiscoveryAdmin } from "./study-discovery-admin";

export const dynamic = "force-dynamic";

export default function StudyDiscoveryPage() {
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Governed category onboarding</p>
          <h1>Study Discovery</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Learn the Search population first, enrich only reviewed products,
            and hand evidence to Product Pack certification.
          </p>
          <Link className="button secondary" href="/admin/product-packs">
            Product Packs
          </Link>
        </div>
      </header>
      <StudyDiscoveryAdmin />
    </main>
  );
}
