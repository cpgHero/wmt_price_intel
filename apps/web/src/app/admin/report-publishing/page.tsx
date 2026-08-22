import { ReportPublishingAdmin } from "./report-publishing-admin";

export const dynamic = "force-dynamic";

export default function ReportPublishingPage() {
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Publication reliability</p>
          <h1>Report Publishing</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Follow background materialization, semantic trust checks, retries,
            and atomic report activation.
          </p>
        </div>
      </header>
      <ReportPublishingAdmin />
    </main>
  );
}
