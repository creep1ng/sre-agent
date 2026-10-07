import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { parse } from "yaml";
import { validateCompatibility, validateRelease } from "../lib/release-validation.mjs";

const release = new URL("../../releases/2.6.0/", import.meta.url);
const openapi = parse(await readFile(new URL("openapi/control-plane.yaml", release), "utf8"));

function resolveParameter(parameter) {
  if (!parameter.$ref) return parameter;
  const name = parameter.$ref.split("/").at(-1);
  return openapi.components.parameters[name];
}

test("2.6.0 audit detail accepts only schema event IDs without widening shared Id", () => {
  const audit = openapi.paths["/v1/audit-events/{id}"].get.parameters.map(resolveParameter);
  const auditId = audit.find(({ name }) => name === "id");
  assert.ok(auditId, "audit detail path ID is declared");
  assert.notEqual(auditId.schema, openapi.components.parameters.Id.schema);

  const principalId = resolveParameter(
    openapi.paths["/v1/principals/{id}"].get.parameters[0],
  );
  assert.equal(principalId.schema, openapi.components.parameters.Id.schema);
  assert.equal(principalId.schema.pattern, "^[a-z][a-z0-9_-]{2,63}$");

  const validate = new Ajv2020({ allErrors: true, strict: false });
  addFormats(validate);
  const accepts = validate.compile(auditId.schema);
  for (const eventId of [
    "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    "c0000000-0000-4000-8000-000000000005",
    "00000000-0000-0000-0000-000000000000",
    "C0000000-0000-4000-8000-000000000005",
    "cor_12345678-1234-1234-8234-123456789012",
  ]) {
    assert.equal(accepts(eventId), true, eventId);
  }
  for (const eventId of [
    "not-an-event-id",
    "0-not-a-uuid",
    "cor_not-a-uuid",
    "cor_12345678-1234-0234-8234-123456789012",
    "c0000000000040008000000000000005",
  ]) {
    assert.equal(accepts(eventId), false, eventId);
  }
});

test("2.5.0 remains immutable and retains its original generic audit Id", async () => {
  const previous = parse(
    await readFile(new URL("../../releases/2.5.0/openapi/control-plane.yaml", import.meta.url), "utf8"),
  );
  const audit = previous.paths["/v1/audit-events/{id}"].get.parameters[0];
  assert.equal(audit.$ref, "#/components/parameters/Id");
  assert.equal(previous.components.parameters.Id.schema.pattern, "^[a-z][a-z0-9_-]{2,63}$");
});

test("2.6.0 is a complete additive immutable release over 2.5.0", async () => {
  const manifest = parse(await readFile(new URL("manifest.yaml", release), "utf8"));
  assert.deepEqual(manifest.baseline, {
    previous_release: "2.5.0",
    previous_major: "2.0.0",
    compatibility: "additive",
  });
  assert.equal(manifest.status, "immutable");
  assert.equal((await validateCompatibility("2.5.0", "2.6.0")).status, "passed");
  assert.ok(await validateRelease("2.6.0"));
});
