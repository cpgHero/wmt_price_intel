import { ReportPublishingAdmin } from "./report-publishing-admin";

export const dynamic = "force-dynamic";

export default function ReportPublishingPage() {
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Pipeline reliability</p>
          <h1>Pipeline Status</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Follow report readiness, background materialization, semantic trust
            checks, retries, and atomic activation.
          </p>
        </div>
      </header>
      <ReportPublishingAdmin />
    </main>
  );
}
