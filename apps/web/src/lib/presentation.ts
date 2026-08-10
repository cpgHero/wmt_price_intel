import type { JsonObject } from "./api";

export function asObject(value: unknown): JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

export function asRows(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.map(asObject).filter(hasFields) : [];
}

function hasFields(value: JsonObject): boolean {
  return Object.keys(value).length > 0;
}

export function displayLabel(value: string): string {
  const knownLabels: Record<string, string> = {
    aldi_us: "ALDI",
    amazon_us_same_day: "Amazon Same Day",
    walmart_us: "Walmart",
  };
  if (knownLabels[value]) return knownLabels[value];
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 }).format(
      value,
    );
  }
  if (Array.isArray(value)) return value.map(displayValue).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function displayDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "America/Chicago",
      }).format(date);
}

export function displayDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3_600);
  const minutes = Math.floor((total % 3_600) / 60);
  const remainingSeconds = total % 60;
  return [
    hours && `${hours}h`,
    minutes && `${minutes}m`,
    `${remainingSeconds}s`,
  ]
    .filter(Boolean)
    .join(" ");
}
