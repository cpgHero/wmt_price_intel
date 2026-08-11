import Link from "next/link";

import { EmptyState } from "@/app/components/empty-state";
import {
  getApi,
  type CollectionBuilderOptions,
  type CollectionDefinitionRecord,
  type CollectionGeographyResolution,
} from "@/lib/api";

import { CollectionBuilder } from "../../../collection-builder";

export const dynamic = "force-dynamic";

export default async function EditCollectionDefinitionPage({
  params,
}: {
  params: Promise<{ stableKey: string }>;
}) {
  const { stableKey } = await params;
  const [optionsResponse, definitionResponse] = await Promise.all([
    getApi<CollectionBuilderOptions>("/api/v1/collection-builder/options"),
    getApi<CollectionDefinitionRecord>(
      `/api/v1/collection-definitions/${encodeURIComponent(stableKey)}`,
    ),
  ]);
  const geography = definitionResponse.data?.config.geography;
  const resolutionId =
    geography && typeof geography === "object" && !Array.isArray(geography)
      ? String((geography as Record<string, unknown>).resolution_id ?? "")
      : "";
  const resolutionResponse = resolutionId
    ? await getApi<CollectionGeographyResolution>(
        `/api/v1/collection-geography-resolutions/${encodeURIComponent(resolutionId)}`,
      )
    : null;
  const error =
    optionsResponse.error ??
    definitionResponse.error ??
    resolutionResponse?.error;
  return (
    <main>
      <header className="page-header compact builder-page-header">
        <div>
          <p className="eyebrow">New immutable version</p>
          <h1>Edit collection definition</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Existing runs remain linked to their original definition and
            geography snapshot. A launch from this editor publishes a new
            version.
          </p>
          <Link className="button secondary" href="/collections">
            Back to collections
          </Link>
        </div>
      </header>
      {optionsResponse.data && definitionResponse.data ? (
        <CollectionBuilder
          options={optionsResponse.data}
          initialDefinition={definitionResponse.data.config}
          initialResolution={resolutionResponse?.data ?? null}
        />
      ) : (
        <EmptyState
          eyebrow="Definition unavailable"
          title="This collection could not be opened for editing"
          message={error ?? "Try again when the API is available."}
        />
      )}
    </main>
  );
}
