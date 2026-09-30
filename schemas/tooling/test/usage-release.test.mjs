import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { parse } from "yaml";
import { validateRelease } from "../lib/release-validation.mjs";

const releases = new URL("../../releases/", import.meta.url);
const publication = new URL("2.5.0/", releases);

test("2.5.0 publishes usage read as a self-contained additive contract", async () => {
  const manifest = parse(await readFile(new URL("manifest.yaml", publication), "utf8"));
  const api = parse(await readFile(new URL("openapi/control-plane.yaml", publication), "utf8"));
  const audit = JSON.parse(
    await readFile(new URL("json-schema/domain/audit-event.schema.json", publication), "utf8"),
  );
  const usage = JSON.parse(
    await readFile(new URL("json-schema/http/usage-read.schema.json", publication), "utf8"),
  );

  assert.deepEqual(manifest.baseline, {
    previous_release: "2.4.0",
    previous_major: "2.0.0",
    compatibility: "additive",
  });
  assert.equal(api.info.version, "2.5.0");
  assert.ok(api.paths["/v1/usage/consumption"]?.get);
  assert.equal(
    api.paths["/v1/usage/consumption"].get.responses["200"].content["application/json"].schema.$ref,
    "urn:sre-agent:schema:usage-read:2.5.0",
  );
  assert.ok(audit.properties.operation.enum.includes("usage.read"));
  assert.equal(usage.$id, "urn:sre-agent:schema:usage-read:2.5.0");
  assert.ok(manifest.inventory.openapi.some(({ path }) => path === "releases/2.5.0/openapi/control-plane.yaml"));
  assert.ok(manifest.inventory.schemas.some(({ id }) => id === "urn:sre-agent:schema:usage-read:2.5.0"));
  assert.ok(manifest.inventory.fixtures.some(({ path }) => path.includes("usage.read")));
  assert.ok(manifest.inventory.conformance.some(({ path }) => path.endsWith("conformance/consumers.yaml")));
  assert.ok(await validateRelease("2.5.0"));
});
