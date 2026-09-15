import { afterEach, describe, expect, it, vi } from "vitest";

import { GET as getCustomerReportDataset } from "./[accessId]/canonical-report-dataset/route";
import { GET as getCustomerReportEvidenceCsv } from "./[accessId]/price-monitoring/evidence.csv/route";
import { GET as getCustomerReportMap } from "./[accessId]/price-monitoring/map/route";
import { POST as postCustomerReportStateCoverage } from "./[accessId]/price-monitoring/state-coverage/route";
import { GET as getCustomerProductEvidence } from "./[accessId]/product-decisions/[decisionId]/evidence/route";
import { GET as getCustomerReportDetail } from "./[accessId]/route";
import { GET as getCustomerReportQuality } from "./[accessId]/quality/route";
import { GET as getCustomerReportView } from "./[accessId]/report/route";
import { GET as getCustomerReports } from "./route";

describe("customer report APIs in legacy restore mode", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a disabled response for every customer report endpoint", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("must not be called"));
    const request = new Request("https://app.cpghero.com/api/customer/reports");
    const responses = await Promise.all([
      getCustomerReports(),
      getCustomerReportDetail(),
      getCustomerReportView(),
      getCustomerReportQuality(),
      getCustomerReportDataset(),
      getCustomerReportMap(),
      getCustomerReportEvidenceCsv(),
      postCustomerReportStateCoverage(),
      getCustomerProductEvidence(),
    ]);

    for (const response of responses) {
      expect(response.status).toBe(404);
      expect(response.headers.get("cache-control")).toBe("private, no-store");
      await expect(response.json()).resolves.toEqual({
        error:
          "Customer report access is disabled while legacy reporting is restored.",
      });
    }
    expect(request.url).toContain("/api/customer/reports");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
