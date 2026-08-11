import { ProductPackDraftWorkspace } from "./product-pack-draft-workspace";

export const dynamic = "force-dynamic";

export default async function ProductPackDraftPage({
  params,
}: {
  params: Promise<{ draftId: string }>;
}) {
  const { draftId } = await params;
  return <ProductPackDraftWorkspace draftId={draftId} />;
}
