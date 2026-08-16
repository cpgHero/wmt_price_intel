import { DocsAdmin } from "./docs-admin";

export const dynamic = "force-dynamic";

export default function PlatformDocsPage() {
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Owner and administrator reference</p>
          <h1>Platform Docs</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Current implementation, operating workflows, trust boundaries, and
            maintained change orders—from data collection through reporting.
          </p>
        </div>
      </header>
      <DocsAdmin />
    </main>
  );
}
