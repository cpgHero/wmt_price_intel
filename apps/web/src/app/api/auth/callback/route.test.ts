import { describe, expect, it } from "vitest";

import { GET } from "./route";

describe("customer auth callback route", () => {
  it("redirects to the restored app home in legacy restore mode", () => {
    const response = GET(
      new Request("https://app.cpghero.com/api/auth/callback?code=abc"),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.cpghero.com/");
  });

  it("uses the forwarded public origin when Railway supplies an internal request URL", () => {
    const response = GET(
      new Request("http://0.0.0.0:3000/api/auth/callback?code=abc", {
        headers: {
          host: "0.0.0.0:3000",
          "x-forwarded-host": "web-production-ee2a4.up.railway.app",
          "x-forwarded-proto": "https",
        },
      }),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://web-production-ee2a4.up.railway.app/",
    );
  });
});
