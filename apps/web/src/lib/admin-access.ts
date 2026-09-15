import "server-only";

import {
  adminAuthenticationConfigured,
  verifyAdminSession,
} from "./admin-session";

export type AdminSessionSource = "legacy_admin" | "none";

export interface AdminSessionStatus {
  authenticated: boolean;
  configured: boolean;
  source: AdminSessionSource;
}

export function adminSessionStatus(
  request: Request,
): AdminSessionStatus {
  const legacyConfigured = adminAuthenticationConfigured();
  if (verifyAdminSession(request)) {
    return {
      authenticated: true,
      configured: legacyConfigured,
      source: "legacy_admin",
    };
  }

  return {
    authenticated: false,
    configured: legacyConfigured,
    source: "none",
  };
}

export function verifyAdminAccess(request: Request): boolean {
  return adminSessionStatus(request).authenticated;
}
