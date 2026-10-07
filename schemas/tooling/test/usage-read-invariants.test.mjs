// Failure modes: unusable billed metadata, misleading coverage, evidence-row
// counts replacing request counts, and closed-schema registry incompatibility.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { parse } from "yaml";
import { createSchemaRegistry, validateFixtures } from "../lib/schema-validation.mjs";

const matrix = parse(await readFile(new URL("fixtures/usage-read-invariants.yaml", import.meta.url), "utf8"));
const document = parse(await readFile(new URL("../../proposals/issue-333/usage-read.openapi.yaml", import.meta.url), "utf8"));
const schema = document.components.schemas.UsageRead;
const ajv = new Ajv2020({ strict: true, allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

test("usage proposal registers without relaxing object closure", () => {
  assert.doesNotThrow(() => createSchemaRegistry([schema]));
});

for (const kind of ["cost_cases", "coverage_cases"]) {
  for (const scenario of matrix[kind]) {
    test(`usage invariant: ${scenario.name}`, () => {
      const data = structuredClone(matrix.base);
      if (kind === "cost_cases") {
        for (const key of ["amount", "currency", "precision"]) data.totals.cost[key] = scenario[key];
        if (scenario.name === "incompatible-prices") data.totals.cost.price_versions.push("controlled-v2");
      } else {
        for (const key of ["status", "known", "incomplete", "unknown"]) data.coverage[key] = scenario[key];
        data.request_count = scenario.request_count;
        data.months = scenario.request_count ? [{ month: "2026-09", request_count: scenario.request_count }] : [];
        if (!scenario.request_count || scenario.status !== "complete") {
          Object.assign(data.totals, { input_tokens: null, output_tokens: null, total_tokens: null });
          Object.assign(data.totals.cost, { amount: null, currency: null, precision: null });
        }
      }
      assert.equal(validate(data), scenario.valid || scenario.rule === "semantic", ajv.errorsText(validate.errors));
      validateFixtures([schema], [{
        name: scenario.name, target: schema.$id, version: document.info.version,
        status: scenario.valid ? "positive" : "negative",
        rule: scenario.rule ?? (kind === "cost_cases" ? "const" : "oneOf"), data,
      }]);
    });
  }
}
