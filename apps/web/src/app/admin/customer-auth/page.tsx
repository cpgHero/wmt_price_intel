import { CustomerAuthAdmin } from "./customer-auth-admin";

export const dynamic = "force-dynamic";

export default function CustomerAuthPage() {
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Accounts &amp; Access</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Manage customer account readiness, workspace scopes, identity
            webhook health, entitlements, and report access before broader
            self-service administration is enabled.
          </p>
        </div>
      </header>
      <CustomerAuthAdmin />
    </main>
  );
}
