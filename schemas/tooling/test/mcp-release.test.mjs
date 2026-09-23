import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { createSchemaRegistry, loadReleaseDirectory } from "../lib/schema-validation.mjs";
import { runConsumer, validateCoverage, validateRelease } from "../lib/release-validation.mjs";

const releaseRoot = new URL("../../releases/2.4.0/", import.meta.url);
const releasePath = fileURLToPath(releaseRoot);

test("2.4.0 publishes governed MCP audit operations and resource subjects", async () => {
  const audit = JSON.parse(await readFile(new URL("json-schema/domain/audit-event.schema.json", releaseRoot), "utf8"));
  assert.deepEqual(audit.properties.operation.enum.slice(-2), ["mcp.discovery", "mcp.invoke"]);
  const resource = JSON.parse(await readFile(new URL("json-schema/domain/resource.schema.json", releaseRoot), "utf8"));
  assert.ok(resource.properties.resource_type.enum.includes("mcp_server"));
  assert.ok(resource.properties.resource_type.enum.includes("mcp_tool"));
});

test("2.4.0 validates metadata-only MCP discovery and invocation audit fixtures", async () => {
  const release = await loadReleaseDirectory(releaseRoot, "audit");
  const registry = createSchemaRegistry(release.schemas);
  const audit = registry.getSchema("urn:sre-agent:schema:audit-event:2.4.0");
  const metadata = registry.getSchema("urn:sre-agent:schema:audit-event-metadata:2.4.0");
  const cases = [
    ["positive/audit.mcp.discovery.positive.v2.4.0.fixture.json", "mcp.discovery", "read_metadata", "mcp_server", "mcp_tool"],
    ["positive/audit.mcp.invoke.positive.v2.4.0.fixture.json", "mcp.invoke", "invoke", "mcp_tool", "mcp_server"],
  ];
  for (const [name, operation, action, subject, wrongSubject] of cases) {
    const fixture = release.fixtures.find(({ name: path }) => path === name);
    assert.ok(fixture, `Missing MCP audit fixture ${name}`);
    const event = fixture.data;
    assert.equal(event.operation, operation);
    assert.equal(event.action, action);
    assert.equal(event.resource.resource_type, subject);
    assert.equal(event.content_state, "absent");
    assert.equal("redacted_content" in event, false);
    assert.equal("consumption" in event, false);
    assert.equal(audit(event), true, JSON.stringify(audit.errors));
    assert.equal(metadata(event), true, JSON.stringify(metadata.errors));

    const wrongMapping = structuredClone(event);
    wrongMapping.resource.resource_type = wrongSubject;
    assert.equal(audit(wrongMapping), false, `${operation} must be bound to ${subject}`);
    assert.equal(metadata(wrongMapping), false);

    const modelRoute = structuredClone(event);
    modelRoute.model_alias_ref = {
      algorithm: "hmac-sha-256",
      key_version: 1,
      digest: "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    };
    assert.equal(audit(modelRoute), false, "MCP audit evidence must not carry an LLM model alias");

    const contentLeak = structuredClone(event);
    contentLeak.redacted_content = { representation: "fully_redacted" };
    assert.equal(metadata(contentLeak), false, "MCP metadata schema must never expose response content");

    const rawArguments = structuredClone(event);
    rawArguments.tool_arguments = { query: "sensitive" };
    assert.equal(audit(rawArguments), false, "MCP event schema must reject raw tool arguments");
  }
});

test("2.4.0 validates as an immutable additive snapshot over 2.3.0", async () => {
  const manifest = parse(await readFile(new URL("manifest.yaml", releaseRoot), "utf8"));
  assert.deepEqual(manifest.baseline, {
    previous_release: "2.3.0",
    previous_major: "2.0.0",
    compatibility: "additive",
  });
  assert.equal(manifest.status, "immutable");
  assert.ok(manifest.inventory.fixtures.some(({ path }) => path.endsWith("audit.mcp.discovery.positive.v2.4.0.fixture.json")));
  assert.ok(manifest.inventory.fixtures.some(({ path }) => path.endsWith("audit.mcp.invoke.positive.v2.4.0.fixture.json")));
  const coverage = await validateCoverage(releasePath);
  assert.equal(coverage.consumers.consumers.length, 14);
  assert.ok(coverage.suite.obligations.some(({ id }) => id === "issue-187.mcp-audit-contract"));
  assert.deepEqual(await runConsumer("issue-187", releasePath), {
    consumer: "issue-187",
    action: "mcp-audit-contract",
    fixture: "fixtures/positive/audit.mcp.discovery.positive.v2.4.0.fixture.json",
    status: "passed",
  });
  const result = await validateRelease("2.4.0");
  assert.ok(result.artifacts > 0);
});
