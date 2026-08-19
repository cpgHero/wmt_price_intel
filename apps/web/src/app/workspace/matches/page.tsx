import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function MatchWorkbenchPage() {
  redirect("/admin/matching-v2");
}
