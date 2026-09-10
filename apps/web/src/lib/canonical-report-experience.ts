type QueryValue = string | string[] | undefined;

export type CanonicalReportExperienceSearchParams = Record<string, QueryValue>;

function firstValue(value: QueryValue) {
  return Array.isArray(value) ? value[0] : value;
}

function normalizedFlag(value: QueryValue) {
  return firstValue(value)?.trim().toLocaleLowerCase("en-US") ?? null;
}

function environmentDefaultDisabled(
  environment: Readonly<Record<string, string | undefined>>,
) {
  const flag =
    environment.RCI_CANONICAL_REPORT_DEFAULT?.trim().toLocaleLowerCase("en-US");
  return flag === "0" || flag === "false" || flag === "disabled";
}

export function canonicalReportExperienceEnabled(
  searchParams: CanonicalReportExperienceSearchParams | null | undefined,
  environment: Readonly<Record<string, string | undefined>> = process.env,
) {
  const experience = normalizedFlag(searchParams?.experience);
  const reportExperience = normalizedFlag(searchParams?.reportExperience);
  const canonical = normalizedFlag(searchParams?.canonical);
  if (
    experience === "legacy" ||
    experience === "current" ||
    reportExperience === "legacy" ||
    reportExperience === "current" ||
    canonical === "0" ||
    canonical === "false"
  ) {
    return false;
  }
  if (
    experience === "canonical" ||
    experience === "simplified" ||
    reportExperience === "canonical" ||
    reportExperience === "simplified" ||
    canonical === "1" ||
    canonical === "true"
  ) {
    return true;
  }
  return !environmentDefaultDisabled(environment);
}
