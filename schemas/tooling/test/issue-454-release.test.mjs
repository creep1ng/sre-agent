// Failure modes: historical attribution is reconstructed from today's alias;
// caller-provided credit is accepted; legacy absence is misreported; selectors
// are combined/unbounded; denied reads enumerate requests; and response payload,
// HMAC material, or incident destinations leak through a closed projection.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { validateRelease, runConsumer } from "../lib/release-validation.mjs";
import { loadReleaseDirectory, validateFixtures } from "../lib/schema-validation.mjs";

const version = "2.8.0";
const root = new URL(`../../releases/${version}/`, import.meta.url);
const text = async (path) => readFile(new URL(path, root), "utf8");
const json = async (path) => JSON.parse(await text(path));

test("2.8.0 publishes a self-contained historical request contract", async () => {
  const manifest = parse(await text("manifest.yaml"));
  const control = parse(await text("openapi/control-plane.yaml"));
  const usageRead = parse(await text("openapi/usage-read.yaml"));
  const schema = await json("json-schema/http/usage-requests.schema.json");
  const apiRoute = control.paths["/v1/usage/requests"]?.get;
  const standaloneRoute = usageRead.paths["/v1/usage/requests"]?.get;

  assert.deepEqual(manifest.baseline, {
    previous_release: "2.7.0",
    previous_major: "2.0.0",
    compatibility: "additive",
  });
  assert.equal(control.info.version, version);
  assert.equal(usageRead.info.version, version);
  assert.ok(apiRoute, "canonical control-plane API publishes the new endpoint");
  assert.ok(standaloneRoute, "standalone usage-read API publishes the same endpoint");
  assert.equal(apiRoute.responses["200"].content["application/json"].schema.$ref, `urn:sre-agent:schema:usage-requests:${version}`);
  assert.equal(standaloneRoute.responses["200"].content["application/json"].schema.$ref, `urn:sre-agent:schema:usage-requests:${version}`);
  assert.deepEqual(
    apiRoute.parameters.filter(({ in: location }) => location === "query").map(({ name }) => name).sort(),
    ["incident_id", "month", "request_id"],
  );
  assert.deepEqual(
    standaloneRoute.parameters.filter(({ in: location }) => location === "query").map(({ name }) => name).sort(),
    ["incident_id", "month", "request_id"],
  );
  assert.deepEqual(apiRoute["x-required-query-one-of"], ["request_id", "incident_id", "month"]);
  assert.equal(apiRoute["x-reject-unknown-query-parameters"], true);
  assert.deepEqual(apiRoute["x-governed-scope"], {
    action: "admin.read", resource_type: "administrative_control", resource_id: "usage",
  });
  for (const status of ["401", "403", "413", "422", "503"]) {
    assert.equal(apiRoute.responses[status].content["application/json"].schema.$ref, `urn:sre-agent:schema:error-envelope:${version}`);
  }
  assert.equal(schema.$id, `urn:sre-agent:schema:usage-requests:${version}`);
  assert.ok(manifest.inventory.openapi.some(({ path }) => path === `releases/${version}/openapi/control-plane.yaml`));
  assert.ok(manifest.inventory.schemas.some(({ id }) => id === schema.$id));
  assert.ok(manifest.inventory.fixtures.some(({ path }) => path.includes("usage.requests")));

  const releaseFiles = manifest.inventory.openapi.concat(manifest.inventory.schemas);
  for (const item of releaseFiles) {
    const artifact = item.path.replace(`releases/${version}/`, "");
    const body = await text(artifact);
    assert.doesNotMatch(body, /urn:sre-agent:schema:[A-Za-z0-9-]+:2\.7\.0/, `${artifact} must not depend on a published schema release`);
  }
  assert.ok(await validateRelease(version));
});

test("request conformance covers honest evidence states and rejects leakage", async () => {
  const release = await loadReleaseDirectory(root, "all");
  const conformance = await parse(await text("conformance/consumers.yaml"));
  const cases = release.fixtures.filter(({ group }) => group === "usage-requests-projection");
  const byName = new Map(cases.map((fixture) => [fixture.name, fixture]));
  const positive = [
    `positive/usage.requests.available.positive.v${version}.fixture.json`,
    `positive/usage.requests.partial.positive.v${version}.fixture.json`,
    `positive/usage.requests.unavailable.positive.v${version}.fixture.json`,
    `positive/usage.requests.legacy.positive.v${version}.fixture.json`,
  ];
  const negative = [
    `negative/usage.requests.credit-without-evidence.negative.v${version}.fixture.json`,
    `negative/usage.requests.conflicting-availability.negative.v${version}.fixture.json`,
    `negative/usage.requests.extra-content.negative.v${version}.fixture.json`,
    `negative/usage.requests.navigation-destination.negative.v${version}.fixture.json`,
    `negative/usage.requests.multiple-selectors.negative.v${version}.fixture.json`,
    `negative/usage.requests.no-selector.negative.v${version}.fixture.json`,
    `negative/usage.requests.oversized-items.negative.v${version}.fixture.json`,
  ];
  for (const name of [...positive, ...negative]) assert.ok(byName.has(name), `missing observable conformance case ${name}`);
  validateFixtures(release.schemas, [...positive, ...negative].map((name) => byName.get(name)));

  const consumer = conformance.consumers.find(({ id }) => id === "issue-454");
  assert.deepEqual(consumer?.obligations, ["issue-454.historical-request-contract"]);
  assert.equal(consumer?.owner, "release");
  assert.equal(consumer?.internal_models_are_authority, false);
  const obligation = (await parse(await text("conformance/suite.yaml"))).obligations.find(
    ({ id }) => id === "issue-454.historical-request-contract",
  );
  assert.equal(obligation?.fixture, `fixtures/${positive[0]}`);
  assert.equal(obligation?.action, "historical-request-contract");
  assert.equal(obligation?.command, `npm --prefix schemas/tooling run conformance -- --consumer issue-454 --release ${version}`);
  assert.ok(await runConsumer("issue-454", fileURLToPath(root)));
});
