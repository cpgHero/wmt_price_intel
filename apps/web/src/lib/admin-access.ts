import "server-only";

import {
  adminAuthenticationConfigured,
  verifyAdminSession,
} from "./admin-session";
import { loadServerConfig } from "./config";

export type AdminSessionSource = "customer_system" | "legacy_admin" | "none";

export interface AdminSessionStatus {
  authenticated: boolean;
  configured: boolean;
  customer?: {
    email: string;
    permissions: string[];
    roles: string[];
  };
  source: AdminSessionSource;
}

interface CustomerPrincipalResponse {
  principal?: {
    email?: unknown;
    permissions?: unknown;
    roles?: unknown;
  };
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

async function customerPrincipalStatus(
  request: Request,
): Promise<AdminSessionStatus | null> {
  const cookie = request.headers.get("cookie");
  if (!cookie) return null;

  const upstreamUrl = new URL("/api/v1/me", loadServerConfig().apiInternalUrl);
  try {
    const upstream = await fetch(upstreamUrl, {
      cache: "no-store",
      headers: {
        accept: "application/json",
        cookie,
      },
      signal: AbortSignal.timeout(15_000),
    });
    if (!upstream.ok) return null;

    const payload = (await upstream.json()) as CustomerPrincipalResponse;
    const permissions = arrayOfStrings(payload.principal?.permissions);
    const roles = arrayOfStrings(payload.principal?.roles);
    const email =
      typeof payload.principal?.email === "string"
        ? payload.principal.email
        : "system-admin@cpghero";
    if (!permissions.includes("system.admin")) {
      return {
        authenticated: false,
        configured: true,
        customer: { email, permissions, roles },
        source: "none",
      };
    }

    return {
      authenticated: true,
      configured: true,
      customer: { email, permissions, roles },
      source: "customer_system",
    };
  } catch {
    return null;
  }
}

export async function adminSessionStatus(
  request: Request,
): Promise<AdminSessionStatus> {
  const legacyConfigured = adminAuthenticationConfigured();
  if (verifyAdminSession(request)) {
    return {
      authenticated: true,
      configured: legacyConfigured,
      source: "legacy_admin",
    };
  }

  const customerStatus = await customerPrincipalStatus(request);
  if (customerStatus) return customerStatus;

  return {
    authenticated: false,
    configured: legacyConfigured,
    source: "none",
  };
}

export async function verifyAdminAccess(request: Request): Promise<boolean> {
  return (await adminSessionStatus(request)).authenticated;
}
