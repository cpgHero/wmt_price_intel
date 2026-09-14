import { CustomerReportDetail } from "./report-detail";

export const dynamic = "force-dynamic";

export default async function CustomerReportPage({
  params,
}: {
  params: Promise<{ accessId: string }>;
}) {
  const { accessId } = await params;
  return <CustomerReportDetail accessId={accessId} />;
}
