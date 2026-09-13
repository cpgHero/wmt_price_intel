import { describe, expect, it } from "vitest";

import {
  loadCustomerAuthConfig,
  workosRequiredEnvironment,
} from "./customer-auth-config";

describe("customer auth config", () => {
  it("defaults to disabled without requiring WorkOS secrets", () => {
    expect(loadCustomerAuthConfig({})).toEqual({
      configured: false,
      missingRequiredEnvironment: [],
      provider: "disabled",
      workosClientId: null,
      workosRedirectUri: null,
    });
  });

  it("reports missing WorkOS configuration without exposing secret values", () => {
    const config = loadCustomerAuthConfig({
      CPGHERO_CUSTOMER_AUTH_PROVIDER: "workos",
      WORKOS_CLIENT_ID: "client_123",
      WORKOS_REDIRECT_URI: "https://app.cpghero.com/api/auth/callback",
    });

    expect(config.configured).toBe(false);
    expect(config.missingRequiredEnvironment).toEqual([
      "WORKOS_API_KEY",
      "WORKOS_COOKIE_PASSWORD",
    ]);
    expect(JSON.stringify(config)).not.toContain("sk_");
  });

  it("marks WorkOS configured when all required variables are present", () => {
    const environment = Object.fromEntries(
      workosRequiredEnvironment.map((name) => [name, `${name}-value`]),
    );

    expect(
      loadCustomerAuthConfig({
        ...environment,
        CPGHERO_CUSTOMER_AUTH_PROVIDER: "workos",
      }),
    ).toMatchObject({
      configured: true,
      missingRequiredEnvironment: [],
      provider: "workos",
    });
  });

  it("fails closed for unsupported providers", () => {
    expect(() =>
      loadCustomerAuthConfig({
        CPGHERO_CUSTOMER_AUTH_PROVIDER: "custom-passwords",
      }),
    ).toThrow("CPGHERO_CUSTOMER_AUTH_PROVIDER must be disabled or workos.");
  });
});
