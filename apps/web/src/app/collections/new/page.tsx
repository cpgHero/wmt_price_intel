import Link from "next/link";

import { EmptyState } from "@/app/components/empty-state";
import { getApi, type CollectionBuilderOptions } from "@/lib/api";

import { CollectionBuilder } from "../collection-builder";

export const dynamic = "force-dynamic";

export default async function NewCollectionPage() {
  const response = await getApi<CollectionBuilderOptions>(
    "/api/v1/collection-builder/options",
  );
  return (
    <main>
      <header className="page-header compact builder-page-header">
        <div>
          <p className="eyebrow">Collection builder</p>
          <h1>New collection</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Construct, inspect, and approve an exact retailer footprint before
            any paid provider work begins.
          </p>
          <Link className="button secondary" href="/collections">
            Back to collections
          </Link>
        </div>
      </header>
      {response.data ? (
        <CollectionBuilder options={response.data} />
      ) : (
        <EmptyState
          eyebrow="Builder unavailable"
          title="Collection options could not be loaded"
          message={response.error ?? "Try again when the API is available."}
        />
      )}
    </main>
  );
}
