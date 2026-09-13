export type CustomerAuthProvider = "disabled" | "workos";

export const workosRequiredEnvironment = [
  "WORKOS_CLIENT_ID",
  "WORKOS_API_KEY",
  "WORKOS_COOKIE_PASSWORD",
  "WORKOS_REDIRECT_URI",
] as const;

export const workosWebhookEnvironment = ["WORKOS_WEBHOOK_SECRET"] as const;

export interface CustomerAuthConfig {
  configured: boolean;
  missingRequiredEnvironment: string[];
  provider: CustomerAuthProvider;
  workosClientId: string | null;
  workosRedirectUri: string | null;
}

function normalizedProvider(
  environment: Readonly<Record<string, string | undefined>>,
): CustomerAuthProvider {
  const provider =
    environment.CPGHERO_CUSTOMER_AUTH_PROVIDER?.trim().toLocaleLowerCase(
      "en-US",
    ) ?? "disabled";
  if (provider === "disabled" || provider === "workos") return provider;
  throw new Error("CPGHERO_CUSTOMER_AUTH_PROVIDER must be disabled or workos.");
}

function present(value: string | undefined): boolean {
  return Boolean(value?.trim());
}

export function loadCustomerAuthConfig(
  environment: Readonly<Record<string, string | undefined>> = process.env,
): CustomerAuthConfig {
  const provider = normalizedProvider(environment);
  const missingRequiredEnvironment =
    provider === "workos"
      ? workosRequiredEnvironment.filter((name) => !present(environment[name]))
      : [];

  return {
    configured:
      provider === "workos" && missingRequiredEnvironment.length === 0,
    missingRequiredEnvironment,
    provider,
    workosClientId: environment.WORKOS_CLIENT_ID?.trim() || null,
    workosRedirectUri: environment.WORKOS_REDIRECT_URI?.trim() || null,
  };
}
