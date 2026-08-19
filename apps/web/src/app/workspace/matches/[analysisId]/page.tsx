import { redirect } from "next/navigation";

interface MatchSearchParams {
  competitor?: string;
}

export default async function RetiredMatchWorkbenchDetailPage({
  searchParams,
}: Readonly<{ searchParams: Promise<MatchSearchParams> }>) {
  const query = await searchParams;
  const parameters = new URLSearchParams();
  if (query.competitor) parameters.set("competitor", query.competitor);
  redirect(
    `/admin/matching-v2${parameters.size ? `?${parameters.toString()}` : ""}`,
  );
}
