import { describe, expect, it } from "vitest";

import { loadServerConfig } from "./config";

describe("loadServerConfig", () => {
  it("uses the local API by default", () => {
    expect(loadServerConfig({}).apiInternalUrl).toBe("http://localhost:8000");
  });

  it("accepts Railway's private API URL", () => {
    expect(
      loadServerConfig({ RCI_API_INTERNAL_URL: "http://api.railway.internal" }),
    ).toEqual({
      apiInternalUrl: "http://api.railway.internal",
    });
  });
});
