import { EmptyState } from "@/app/components/empty-state";
import { getApi, type ProductPackCatalog } from "@/lib/api";

import { CollectionWizard } from "./collection-wizard";

export const dynamic = "force-dynamic";

export default async function CollectionsPage() {
  const response = await getApi<ProductPackCatalog>("/api/v1/product-packs");
  return (
    <main>
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Collection control</p>
          <h1>New collection</h1>
        </div>
        <p>
          Define a safe scope, calculate the exact maximum cost, explicitly
          approve the credit ceiling, and follow the durable run into analysis.
        </p>
      </header>
      {response.data ? (
        <CollectionWizard catalog={response.data} />
      ) : (
        <EmptyState
          eyebrow="Product Packs unavailable"
          title="The collection wizard could not be loaded"
          message={response.error ?? "Try again when the API is available."}
        />
      )}
    </main>
  );
}
