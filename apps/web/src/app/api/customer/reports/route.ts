import { customerReportApiDisabledResponse } from "@/lib/customer-report-api-disabled";

export const dynamic = "force-dynamic";

export async function GET() {
  return customerReportApiDisabledResponse();
}
