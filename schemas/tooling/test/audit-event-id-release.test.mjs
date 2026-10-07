import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
import { parse } from "yaml";
import { validateCompatibility, validatePublishedReleases, validateRelease } from "../lib/release-validation.mjs";

async function openApi(version) {
  return parse(await readFile(new URL(`../../releases/${version}/openapi/control-plane.yaml`, import.meta.url), "utf8"));
}

function auditEventIdSchema(api) {
  const ref = api.paths["/v1/audit-events/{id}"].get.parameters[0].$ref;
  assert.equal(ref, "#/components/parameters/AuditEventId");
  return api.components.parameters.AuditEventId.schema;
}

function validator(schema, enforceFormats) {
  const ajv = new Ajv2020({ strict: false, allErrors: true, validateFormats: enforceFormats });
  addFormats(ajv);
  return ajv.compile(schema);
}

test("2.7 audit event IDs preserve 2.6 values and add canonical UUIDs with formats on and off", async () => {
  const api26 = await openApi("2.6.0");
  const api = await openApi("2.7.0");
  const schema = auditEventIdSchema(api);
  const accepted = [
    "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
    "c0000000-0000-4000-8000-000000000005",
    "00000000-0000-0000-0000-000000000000",
    "C0000000-0000-4000-8000-000000000005",
    "cor_12345678-1234-1234-8234-123456789012",
    "abc",
    "usr_existing",
    "cor_not-a-uuid",
    "cor_12345678-1234-7234-8234-123456789012",
    "not-an-event-id",
  ];
  const rejected = [
    "ab",
    "Aaa",
    "a".repeat(65),
    "not an event id",
    "cor_bad/character",
    "3f2504e0-4f89-11d3-9a0c-0305e82c330x",
  ];

  for (const enforceFormats of [true, false]) {
    const valid = validator(schema, enforceFormats);
    const legacy = validator(api26.components.parameters.Id.schema, enforceFormats);
    for (const value of accepted) {
      if (["abc", "cor_not-a-uuid", "not-an-event-id"].includes(value)) assert.equal(legacy(value), true, `${value} must remain valid under 2.6 Id`);
      assert.equal(valid(value), true, `${value} should validate with formats ${enforceFormats ? "on" : "off"}`);
    }
    for (const value of rejected) {
      assert.equal(legacy(value), false, `${value} was not valid under 2.6 Id`);
      assert.equal(valid(value), false, `${value} should fail with formats ${enforceFormats ? "on" : "off"}`);
    }
  }
});

test("2.7 broadens only the audit detail parameter and preserves the 2.6 grant 404", async () => {
  const api26 = await openApi("2.6.0");
  const api27 = await openApi("2.7.0");
  const previousGenericId = api26.components.parameters.Id;
  assert.deepEqual(api27.components.parameters.Id, previousGenericId);
  assert.equal(api27.paths["/v1/audit-events/{id}"].get.parameters[0].$ref, "#/components/parameters/AuditEventId");
  assert.deepEqual(api27.paths["/v1/grants"].post.responses["404"], api26.paths["/v1/grants"].post.responses["404"]);

  const genericId = validator(api27.components.parameters.Id.schema, true);
  assert.equal(genericId("3f2504e0-4f89-11d3-9a0c-0305e82c3301"), false, "generic Id must retain its pre-existing UUID rejection");
  assert.equal(genericId("usr_existing"), true);
  assert.equal(genericId("cor_12345678-1234-1234-8234-123456789012"), true, "generic Id must retain its pre-existing lowercase/underscore acceptance");
});

test("2.7 is additive and immutable over the published 2.6 contract", async () => {
  const cli = spawnSync(process.execPath, [fileURLToPath(new URL("../release.mjs", import.meta.url)), "validate", "--release", "2.7.0"], { encoding: "utf8" });
  assert.doesNotMatch(cli.stderr, /Usage:/);
  const published = await validatePublishedReleases(undefined, async (version) => ({ version }));
  assert.equal(published.releases.at(-1), "2.7.0");

  const api = await openApi("2.7.0");
  const manifest = parse(await readFile(new URL("../../releases/2.7.0/manifest.yaml", import.meta.url), "utf8"));
  assert.equal(api.info.version, "2.7.0");
  assert.deepEqual(manifest.baseline, { previous_release: "2.6.0", previous_major: "2.0.0", compatibility: "additive" });
  assert.equal(manifest.status, "immutable");
  const compatibility = await validateCompatibility("2.6.0", "2.7.0");
  assert.equal(compatibility.previous_release, "2.6.0");
  assert.equal(compatibility.current_release, "2.7.0");
  assert.equal(compatibility.status, "passed");
  const result = await validateRelease("2.7.0");
  assert.ok(result.artifacts > 0);
  assert.ok(result.results > 0);
});
