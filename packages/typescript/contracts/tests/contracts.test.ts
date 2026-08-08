import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import type { AnySchema } from "ajv";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";

const repositoryRoot = resolve(import.meta.dirname, "../../../..");

async function loadJson<T = unknown>(...parts: string[]): Promise<T> {
  return JSON.parse(
    await readFile(resolve(repositoryRoot, ...parts), "utf8"),
  ) as T;
}

describe("shared JSON contracts", () => {
  it("validates a normalized provider failure", async () => {
    const schema = await loadJson<AnySchema>(
      "schemas",
      "provider-error.schema.json",
    );
    const ajv = new Ajv2020({
      allErrors: true,
      allowUnionTypes: true,
      strict: true,
    });
    addFormats(ajv);
    const validate = ajv.compile(schema);

    expect(
      validate({
        success: false,
        provider: "metricscart",
        failure_class: "rate_limit",
        should_retry: true,
      }),
    ).toBe(true);
  });
});
