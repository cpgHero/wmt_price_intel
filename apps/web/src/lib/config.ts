export interface ServerConfig {
  apiInternalUrl: string;
}

export function loadServerConfig(
  environment: Readonly<Record<string, string | undefined>> = process.env,
): ServerConfig {
  return {
    apiInternalUrl: environment.RCI_API_INTERNAL_URL ?? "http://localhost:8000",
  };
}
