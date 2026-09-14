import { CustomerAuthAdmin } from "./customer-auth-admin";

export const dynamic = "force-dynamic";

export default function CustomerAuthPage() {
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Controlled rollout</p>
          <h1>Customer Auth</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Verify CPGHero customer login readiness, canary guardrails,
            invitation status, and WorkOS webhook processing before any cutover.
          </p>
        </div>
      </header>
      <CustomerAuthAdmin />
    </main>
  );
}
