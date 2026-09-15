const CUSTOMER_PRIMARY_ROLE_PRIORITY: Array<readonly [string, string]> = [
  ["system_owner", "System owner"],
  ["system_admin", "System admin"],
  ["account_owner", "Account owner"],
  ["account_admin", "Account admin"],
  ["analyst", "Analyst"],
  ["viewer", "Viewer"],
];

export function customerPrimaryRoleLabel(roles: readonly string[]): string {
  for (const [role, label] of CUSTOMER_PRIMARY_ROLE_PRIORITY) {
    if (roles.includes(role)) return label;
  }

  return roles.at(0)?.replaceAll("_", " ") ?? "Customer";
}
