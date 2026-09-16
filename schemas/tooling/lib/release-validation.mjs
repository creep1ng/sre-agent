import { createHash } from "node:crypto";
import { access, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parse, stringify } from "yaml";
import { assertFutureFastapi } from "../diff-openapi.mjs";
import { validateGovernance } from "./governance-validation.mjs";
import { combineOpenapi, normalizeOpenapi } from "./openapi-normalize.mjs";
import { readContractFile, runReleaseOpenapi } from "./openapi-validation.mjs";
import { loadReleaseDirectory, validateExamples, validateFixtures } from "./schema-validation.mjs";

const tooling = fileURLToPath(new URL("../", import.meta.url)), schemas = resolve(tooling, ".."), DEFAULT_VERSION = "1.0.0", releaseRoot = (version) => join(schemas, `releases/${version}`), release = releaseRoot(DEFAULT_VERSION), adrs = join(schemas, "adrs");
const SEMVER = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
const CONSUMERS = ["issue-10", "issue-11", "issue-13", "issue-14", "harness", "ui"], consumersForVersion = (version) => version === "2.1.0" ? [...CONSUMERS, "issue-130"] : version === "2.2.0" ? [...CONSUMERS, "issue-130", "issue-129"] : CONSUMERS;
const POLICY = {
  "issue-10": ["infrastructure", "issue-10.fixture-transport", "fixtures-transport", "fixtures/positive/control.bootstrap.first.positive.v1.0.0.fixture.json"],
  "issue-11": ["persistence", "issue-11.schema-persistence", "schema-persistence", "fixtures/positive/shared.principal.human.positive.v1.0.0.fixture.json"],
  "issue-13": ["authentication", "issue-13.bearer-context-401", "bearer-context", "fixtures/positive/responses.boundary.credentials.positive.v1.0.0.fixture.json"],
  "issue-14": ["gateway", "issue-14.ordered-response-flow", "ordered-responses", "fixtures/positive/audit.responses.allowed.positive.v1.0.0.fixture.json"],
  harness: ["harness", "harness.execution-contract", "execution-openapi", "fixtures/positive/future-fastapi.match.projection.json"],
  ui: ["ui", "ui.control-contract", "control-openapi", "examples/control/credential-issuance-first.example.json"],
  "issue-130": ["release", "issue-130.consumption-contract", "consumption-contract", "fixtures/positive/consumption.states.positive.v{version}.fixture.json"],
  "issue-129": ["release", "issue-129.resource-catalog-contract", "resource-catalog-contract", "fixtures/positive/catalog.entries.positive.v{version}.fixture.json"]
};
const command = (consumer, version) => ["issue-130", "issue-129"].includes(consumer) ? `npm --prefix schemas/tooling run conformance -- --consumer ${consumer} --release ${version}` : `npm --prefix schemas/tooling run conformance -- --consumer ${consumer}`;
const versionedPolicy = (version) => Object.fromEntries(Object.entries(POLICY).map(([consumer, values]) => [consumer, values.map((value) => value.replaceAll("1.0.0", version).replaceAll("{version}", version))]));
const sorted = (value) => Array.isArray(value) ? value.map(sorted) : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, sorted(value[key])])) : value;
const digest = (value) => `sha256:${createHash("sha256").update(value).digest("hex")}`, canonical = (value) => JSON.stringify(sorted(value));
async function walk(root, prefix = "") { const files = []; for (const entry of (await readdir(join(root, prefix), { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) { const path = join(prefix, entry.name); if (entry.isDirectory()) files.push(...await walk(root, path)); else if (entry.isFile()) files.push(path.split(sep).join("/")); } return files; }
const fileHash = async (path) => digest(await readFile(path));
const exact = (value, keys, label) => { if (!value || typeof value !== "object" || Array.isArray(value) || canonical(Object.keys(value).sort()) !== canonical([...keys].sort())) throw new Error(`${label} contains unknown or missing fields`); };
async function parsed(path) { return parse(await readFile(path, "utf8")); }
async function optional(path, decode) { try { return decode(await readFile(path, "utf8")); } catch (error) { if (error.code === "ENOENT") return null; throw error; } }
async function validateGroup(group, root = release) { const loaded = await loadReleaseDirectory(root, group); if (loaded.fixtures.length) validateFixtures(loaded.schemas, loaded.fixtures); if (loaded.examples.length) validateExamples(loaded.schemas, loaded.examples); return { fixtures: loaded.fixtures.length, examples: loaded.examples.length }; }
async function assertPinnedArtifact(root, fixture) { const manifest = await optional(join(root, "manifest.yaml"), parse); if (!manifest) return; const path = `releases/${manifest.contract_version}/${fixture}`, record = [...(manifest.inventory?.fixtures ?? []), ...(manifest.inventory?.examples ?? [])].find((item) => item.path === path); if (!record || record.sha256 !== await fileHash(join(root, fixture))) throw new Error(`Obligation fixture ${fixture} does not match its immutable manifest hash`); }
async function validateObligationFixture(root, item) { if (item.fixture.endsWith(".projection.json")) await assertFutureFastapi(pathToFileURL(`${resolve(root)}/`)); else { const loaded = await loadReleaseDirectory(root, "all"), local = item.fixture.replace(/^(?:fixtures|examples)\//, ""); if (item.fixture.startsWith("fixtures/")) { const fixtures = loaded.fixtures.filter(({ name }) => name.replace(/#\d+$/, "") === local); if (!fixtures.length) throw new Error(`Obligation fixture ${item.fixture} was not loaded`); validateFixtures(loaded.schemas, fixtures); } else { const examples = loaded.examples.filter(({ name }) => name === local); if (!examples.length) throw new Error(`Obligation fixture ${item.fixture} was not loaded`); validateExamples(loaded.schemas, examples); } } await assertPinnedArtifact(root, item.fixture); }

const RESOURCE_TYPES = [
  { type: "llm_model", owner: "ModelAlias", identity: "alias_id", states: ["active", "inactive"], operations: [{ name: "assignment", action: "admin.write" }, { name: "status", action: "admin.write" }, { name: "read", action: "admin.read" }, { name: "invoke", action: "invoke" }] },
  { type: "mcp_server", owner: "MCP #187", identity: "server_id", states: ["registered", "active", "inactive", "revoked"], operations: [{ name: "register", action: "admin.write" }, { name: "update", action: "admin.write" }, { name: "deactivate", action: "admin.write" }, { name: "revoke", action: "admin.write" }, { name: "discovery", action: "mcp.discovery" }, { name: "invoke", action: "mcp.invoke" }] },
  { type: "mcp_tool", owner: "MCP #187", identity: "tool_id", states: ["registered", "active", "inactive", "revoked"], operations: [{ name: "register", action: "admin.write" }, { name: "update", action: "admin.write" }, { name: "deactivate", action: "admin.write" }, { name: "revoke", action: "admin.write" }, { name: "discovery", action: "mcp.discovery" }, { name: "invoke", action: "mcp.invoke" }] },
  { type: "skill", owner: "Skills #31", identity: "skill_id@version", states: ["draft", "published", "active", "inactive", "revoked"], operations: [{ name: "publish", action: "admin.write" }, { name: "version", action: "admin.write" }, { name: "deactivate", action: "admin.write" }, { name: "revoke", action: "admin.write" }, { name: "discovery", action: "skill.discovery" }, { name: "read", action: "skill.read" }, { name: "invoke", action: "skill.invoke" }] },
  { type: "bok_collection", owner: "BoK #33", identity: "collection_id@version", states: ["draft", "indexing", "active", "inactive", "revoked"], operations: [{ name: "publish", action: "admin.write" }, { name: "index", action: "admin.write" }, { name: "deactivate", action: "admin.write" }, { name: "revoke", action: "admin.write" }, { name: "discovery", action: "bok.discovery" }, { name: "search", action: "bok.search" }, { name: "read", action: "bok.read" }] },
];
const RESOURCE_EXCLUDED_FIELDS = ["credentials", "secrets", "concrete_model", "router", "inference_provider", "prompts", "raw_io", "configuration"];
const RESOURCE_SCENARIOS = [
  { id: "authority-preserved", status: "passed", fixture: "conformance/resource-catalog-matrix.yaml", assertions: ["owner-action-matrix", "resource-tuple-preserved"] },
  { id: "bounded-discovery", status: "passed", fixture: "fixtures/positive/catalog.http.positive.v2.2.0.fixture.json", assertions: ["catalog.list:200", "limit:1-100", "ordered-result-ids", "continuation:false"] },
  { id: "non-enumerating-read", status: "passed", fixture: "fixtures/positive/catalog.http.positive.v2.2.0.fixture.json", assertions: ["catalog.read:404:hidden", "catalog.read:404:absent", "catalog.read:404:inactive", "catalog.read:404:filtered", "enumerates:false"] },
  { id: "authentication-and-filter-errors", status: "passed", fixture: "fixtures/positive/catalog.http.positive.v2.2.0.fixture.json", assertions: ["401:authentication_failed", "403:resource_unavailable", "422:validation_error", "lookup:false"] },
  { id: "idempotent-replay-and-in-flight", status: "passed", fixture: "fixtures/positive/catalog.lifecycle.positive.v2.2.0.fixture.json", assertions: ["idempotent_replay:stable", "in_flight_snapshot:captured", "authorization-before-deactivation", "later-request:403"] },
  { id: "idempotency-conflict-no-mutation", status: "passed", fixture: "fixtures/positive/catalog.lifecycle.positive.v2.2.0.fixture.json", assertions: ["idempotency_conflict:409", "transition_count:0", "state_unchanged:true", "upstream:false"] },
  { id: "explicit-reconciliation-no-implicit-repair", status: "passed", fixture: "fixtures/positive/catalog.lifecycle.positive.v2.2.0.fixture.json", assertions: ["startup_drift:409", "repair_performed:false", "reconciliation:201", "repair_performed:true"] },
  { id: "historical-release-preserved", status: "passed", fixture: "conformance/migration.md", assertions: ["previous_release:2.1.0", "historical-byte-identity"] },
];
function validateResourceCatalogMatrix(resourceTypes) {
  if (!Array.isArray(resourceTypes) || resourceTypes.length !== RESOURCE_TYPES.length) throw new Error("Resource catalog owner/state/action matrix is incomplete");
  const baseKeys = new Set(["type", "owner", "identity", "states", "operations"]);
  for (const expected of RESOURCE_TYPES) {
    const actual = resourceTypes.find((item) => item?.type === expected.type);
    if (!actual) throw new Error(`Resource catalog matrix omits ${expected.type}`);
    const base = Object.fromEntries(Object.entries(actual).filter(([key]) => baseKeys.has(key)));
    if (canonical(base) !== canonical(expected)) throw new Error(`Resource catalog matrix drifted for ${expected.type}`);
    const extras = Object.keys(actual).filter((key) => !baseKeys.has(key));
    if (expected.type !== "mcp_tool" && extras.length) throw new Error(`Unexpected relation fields for ${expected.type}`);
    if (expected.type === "mcp_tool") {
      const relation = actual.relation ?? actual.server_relation ?? actual.server_identity ?? actual.server_ref ?? actual.server_id;
      const identity = typeof relation === "string" ? relation : relation?.identity ?? relation?.server_identity ?? relation?.target_identity;
      if (identity !== "server_id") throw new Error("MCP tool owner matrix must declare its MCP server relation");
    }
  }
}
function requireCatalogCase(cases, predicate, label) {
  if (!cases.some(predicate)) throw new Error(`Resource catalog evidence lacks ${label}`);
}
async function validateResourceCatalogContract(root, version) {
  const matrix = await parsed(join(root, "conformance/resource-catalog-matrix.yaml"));
  exact(matrix, ["contract_version", "resource_types"], "Resource catalog matrix");
  if (version !== "2.2.0" || matrix.contract_version !== version) throw new Error("Resource catalog owner/state/action matrix is not version-aligned");
  validateResourceCatalogMatrix(matrix.resource_types);
  const evidence = JSON.parse(await readFile(join(root, "conformance/resource-catalog-evidence.json"), "utf8"));
  exact(evidence, ["contract_version", "closed_projection", "excluded_fields", "scenarios"], "Resource catalog evidence");
  if (evidence.contract_version !== version || evidence.closed_projection !== true || canonical(evidence.excluded_fields) !== canonical(RESOURCE_EXCLUDED_FIELDS) || canonical(evidence.scenarios) !== canonical(RESOURCE_SCENARIOS)) throw new Error("Resource catalog evidence is incomplete or not version-aligned");
  for (const scenario of evidence.scenarios) { await access(join(root, scenario.fixture)); if (scenario.status !== "passed" || !scenario.assertions.length) throw new Error(`Resource catalog scenario ${scenario.id} lacks traceable assertions`); }
  const groups = await validateGroup("catalog", root), catalog = await loadReleaseDirectory(root, "catalog");
  const entries = catalog.fixtures.filter(({ target, status }) => status === "positive" && target.endsWith("resource-catalog-entry:2.2.0"));
  const entryTypes = new Set(entries.map(({ data }) => data.resource_type));
  if (RESOURCE_TYPES.some(({ type }) => !entryTypes.has(type))) throw new Error("Resource catalog positive projections omit an owner type");
  const http = catalog.fixtures.filter(({ target, status }) => status === "positive" && target.endsWith("resource-catalog-http-case:2.2.0")).map(({ data }) => data);
  requireCatalogCase(http, (item) => item.operation === "catalog.list" && item.expected.status === 200 && item.expected.deterministic && item.expected.continuation === false, "bounded deterministic list");
  for (const visibility of ["hidden", "absent", "inactive", "filtered"]) requireCatalogCase(http, (item) => item.operation === "catalog.read" && item.request.target_visibility === visibility && item.expected.status === 404 && item.expected.error_code === "resource_not_found" && item.expected.enumerates === false, `${visibility} non-enumerating read`);
  for (const [status, code] of [[401, "authentication_failed"], [403, "resource_unavailable"], [422, "validation_error"]]) requireCatalogCase(http, (item) => item.expected.status === status && item.expected.error_code === code && item.request.lookup_performed === false, `${status} authentication/filter error`);
  const lifecycle = catalog.fixtures.filter(({ target, status }) => status === "positive" && target.endsWith("resource-catalog-lifecycle-case:2.2.0")).map(({ data }) => data);
  requireCatalogCase(lifecycle, (item) => item.operation === "idempotent_replay" && item.expected.stable_replay, "stable idempotent replay");
  requireCatalogCase(lifecycle, (item) => item.operation === "in_flight_snapshot" && item.request.authorization_before === "allowed" && item.request.authorization_after === "denied" && item.expected.later_request_status === 403 && !item.expected.later_upstream_called, "authorization-before-deactivation");
  requireCatalogCase(lifecycle, (item) => item.operation === "idempotency_conflict" && item.expected.status === 409 && item.expected.transition_count === 0 && item.expected.state_unchanged && !item.expected.upstream_called, "idempotency conflict without mutation");
  requireCatalogCase(lifecycle, (item) => item.operation === "startup_drift" && item.expected.status === 409 && !item.expected.repair_performed && item.expected.state_unchanged, "startup drift without repair");
  requireCatalogCase(lifecycle, (item) => item.operation === "reconciliation" && item.request.reset_requested && item.expected.status === 201 && item.expected.repair_performed, "explicit reconciliation");
  const api = await readContractFile(join(root, "openapi/control-plane.yaml")), list = api.paths?.["/v1/catalog/resources"]?.get, read = api.paths?.["/v1/catalog/resources/{resource_type}/{id}"]?.get;
  if (api.info?.version !== version || !list || !read || list.responses?.["200"]?.content?.["application/json"]?.schema?.$ref !== "urn:sre-agent:schema:resource-catalog-list:2.2.0" || read.responses?.["200"]?.content?.["application/json"]?.schema?.$ref !== "urn:sre-agent:schema:resource-catalog-entry:2.2.0" || ["401", "403", "404", "422"].some((status) => !list.responses?.[status] || !read.responses?.[status])) throw new Error("Catalog OpenAPI reads are incomplete or version-misaligned");
  return { ...groups, resource_types: matrix.resource_types.length, scenarios: evidence.scenarios.length };
}

const ACTIONS = {
  "fixtures-transport": (root) => validateGroup("all", root),
  "schema-persistence": (root) => Promise.all(["identity", "model-resource", "policy"].map((group) => validateGroup(group, root))),
  "bearer-context": (root) => Promise.all(["identity", "responses-boundary"].map((group) => validateGroup(group, root))),
  "ordered-responses": (root) => Promise.all(["responses-boundary", "responses-errors", "openrouter-metadata", "audit", "redaction-success", "redaction-failure"].map((group) => validateGroup(group, root))),
  "execution-openapi": async (root, version) => { await runReleaseOpenapi("responses", join(tooling, `.tmp/responses-${version}.yaml`), version); await assertFutureFastapi(pathToFileURL(`${resolve(root)}/`)); },
  "control-openapi": (root, version) => runReleaseOpenapi("control-plane", join(tooling, `.tmp/control-plane-${version}.yaml`), version),
  "consumption-contract": (root) => validateGroup("consumption-contract", root),
  "resource-catalog-contract": (root, version) => validateResourceCatalogContract(root, version)
};

export async function validateCoverage(root = release) {
  const suite = await parsed(join(root, "conformance/suite.yaml")), consumers = await parsed(join(root, "conformance/consumers.yaml")), version = suite.contract_version, policyByConsumer = versionedPolicy(version);
  exact(suite, ["contract_version", "obligations"], "Conformance suite"); exact(consumers, ["contract_version", "consumers", "prohibited_authorities"], "Consumer registry");
  if (suite.contract_version !== version || consumers.contract_version !== version || canonical(consumers.prohibited_authorities) !== canonical(["framework_dto", "orm_model", "database_model", "provider_sdk_type"])) throw new Error("Conformance metadata is not version-aligned and authority-closed");
  const expectedConsumers = consumersForVersion(version);
  if (!Array.isArray(suite.obligations) || !Array.isArray(consumers.consumers) || consumers.consumers.length !== expectedConsumers.length) throw new Error("Consumer coverage must be exhaustive");
  const obligations = new Map(); for (const item of suite.obligations) { exact(item, ["id", "owner", "fixture", "action", "command"], `Obligation ${item?.id}`); if (obligations.has(item.id) || typeof item.fixture !== "string" || item.fixture.startsWith("/") || item.fixture.split("/").includes("..")) throw new Error(`Unsafe or duplicate obligation ${item.id}`); obligations.set(item.id, item); await access(join(root, item.fixture)); }
  for (const consumer of consumers.consumers) { exact(consumer, ["id", "owner", "obligations", "internal_models_are_authority"], `Consumer ${consumer?.id}`); const policy = policyByConsumer[consumer.id], item = policy && obligations.get(policy[1]); if (!policy || consumer.owner !== policy[0] || canonical(consumer.obligations) !== canonical([policy[1]]) || consumer.internal_models_are_authority !== false || !item || item.owner !== policy[0] || item.action !== policy[2] || item.fixture !== policy[3] || item.command !== command(consumer.id, version)) throw new Error(`Consumer ${consumer.id} lacks its exact owner, fixture, command, or authority boundary`); obligations.delete(policy[1]); }
  if (canonical(consumers.consumers.map(({ id }) => id).sort()) !== canonical([...expectedConsumers].sort()) || obligations.size) throw new Error("Consumer obligations are missing or unclaimed"); return { suite, consumers };
}

export async function runConsumer(consumer, root = release) { const { suite } = await validateCoverage(root), version = suite.contract_version, policy = versionedPolicy(version)[consumer]; if (!policy) throw new Error(`Unknown consumer: ${consumer}`); const item = suite.obligations.find(({ id }) => id === policy[1]); await validateObligationFixture(root, item); await ACTIONS[policy[2]](root, version); return { consumer, action: policy[2], fixture: item.fixture, status: "passed" }; }
export async function runConformance(root = release) { const suite = await parsed(join(root, "conformance/suite.yaml")), results = []; for (const consumer of consumersForVersion(suite.contract_version)) results.push(await runConsumer(consumer, root)); return results; }

async function inventory(root, version, includeEvidence = true) {
  const releaseFiles = await walk(root), records = { openapi: [], schemas: [], examples: [], fixtures: [], adrs: [], conformance: [] };
  for (const local of releaseFiles) { if (local === "manifest.yaml" || (!includeEvidence && ["conformance/evidence.json", "conformance/compatibility.json"].includes(local))) continue; const path = join(root, local), record = { path: `releases/${version}/${local}`, sha256: await fileHash(path) };
    if (local.startsWith("json-schema/")) { const value = JSON.parse(await readFile(path)); records.schemas.push({ ...record, dialect: value.$schema, id: value.$id }); }
    else if (local.startsWith("openapi/")) { const value = await readContractFile(path), major = Number(value.info.version.split(".")[0]); records.openapi.push({ ...record, dialect: value.openapi, version: value.info.version, api_major: 1 }); }
    else if (local.startsWith("examples/")) records.examples.push(record); else if (local.startsWith("fixtures/")) records.fixtures.push(record); else if (local.startsWith("conformance/")) records.conformance.push(record);
  }
  const adrFiles = (await walk(adrs)).filter((name) => /^ADR-\d{3}-.*\.md$/.test(name)).sort(), included = version === "1.0.0" ? adrFiles.filter((name) => !name.startsWith("ADR-006-")) : adrFiles;
  for (const local of included) records.adrs.push({ path: `adrs/${local}`, sha256: await fileHash(join(adrs, local)) }); return records;
}
async function semanticHashes(root, version) { const outputs = [join(tooling, `.tmp/evidence-control-${version}.yaml`), join(tooling, `.tmp/evidence-responses-${version}.yaml`)]; try { await Promise.all([runReleaseOpenapi("control-plane", outputs[0], version), runReleaseOpenapi("responses", outputs[1], version)]); const documents = await Promise.all(outputs.map(readContractFile)); return { control_plane: digest(canonical(normalizeOpenapi(documents[0]))), responses: digest(canonical(normalizeOpenapi(documents[1]))), combined_projection: digest(canonical(combineOpenapi(...documents))) }; } finally { await Promise.all(outputs.map((path) => rm(path, { force: true }))); } }
async function evidenceObject(root, version, results) { const packageJson = JSON.parse(await readFile(join(tooling, "package.json"))), inputs = await inventory(root, version, false), semantics = await semanticHashes(root, version); semantics.adrs = digest(canonical(inputs.adrs)); semantics.fixtures = digest(canonical(inputs.fixtures)); return { contract_version: version, inputs_sha256: digest(canonical(inputs)), semantics, results: [...results, { consumer: "governance", action: "ownership-and-adrs", status: "passed" }], toolchain: { node: packageJson.engines.node, ajv: packageJson.devDependencies.ajv, redocly: packageJson.devDependencies["@redocly/cli"], yaml: packageJson.devDependencies.yaml } }; }
const PREVIOUS_RELEASE = { "1.1.0": "1.0.0", "1.2.0": "1.1.0", "1.3.0": "1.2.0", "1.4.0": "1.3.0", "2.0.0": "1.4.0", "2.1.0": "2.0.0", "2.2.0": "2.1.0" };
const baseline = (version) => version === "1.0.0" ? { previous_release: null, previous_major: null, compatibility: "initial-publication" } : version === "2.0.0" ? { previous_release: "1.4.0", previous_major: "1.0.0", compatibility: "breaking" } : PREVIOUS_RELEASE[version] ? { previous_release: PREVIOUS_RELEASE[version], previous_major: version.startsWith("2.") ? "2.0.0" : "1.0.0", compatibility: "additive" } : null;
async function manifestObject(root, version) { return { contract_version: version, status: "immutable", baseline: baseline(version), dialects: { json_schema: "https://json-schema.org/draft/2020-12/schema", openapi: "3.1.0" }, inventory: await inventory(root, version, true) }; }
export function assertImmutableManifest(existing, candidate) { if (canonical(existing) !== canonical(candidate)) throw new Error(`Release ${existing?.contract_version ?? "artifact"} is immutable; publish a new version instead of rewriting it`); }
export function assertReleaseMetadata(manifest) { exact(manifest, ["contract_version", "status", "baseline", "dialects", "inventory"], "Release manifest"); exact(manifest.baseline, ["previous_release", "previous_major", "compatibility"], "Release baseline"); exact(manifest.dialects, ["json_schema", "openapi"], "Release dialects"); exact(manifest.inventory, ["openapi", "schemas", "examples", "fixtures", "adrs", "conformance"], "Release inventory"); if (Object.values(manifest.inventory).some((items) => !Array.isArray(items))) throw new Error("Manifest inventory categories must be arrays"); const version = manifest.contract_version; if (!SEMVER.test(version) || !baseline(version) || manifest.status !== "immutable" || canonical(manifest.baseline) !== canonical(baseline(version))) throw new Error("Manifest release baseline is invalid"); if (canonical(manifest.dialects) !== canonical({ json_schema: "https://json-schema.org/draft/2020-12/schema", openapi: "3.1.0" })) throw new Error("Manifest release dialects are invalid"); if (manifest.inventory.schemas.some((item) => item.dialect !== manifest.dialects.json_schema || !item.id.endsWith(`:${version}`)) || manifest.inventory.openapi.some((item) => item.dialect !== manifest.dialects.openapi || item.api_major !== 1 || item.version !== version)) throw new Error("Manifest $id or API major is invalid"); }
export async function writeImmutable(path, value, options = {}) { const decode = options.decode ?? JSON.parse, encode = options.encode ?? ((item) => `${canonical(item)}\n`), existing = await optional(path, decode); if (existing) assertImmutableManifest(existing, value); const bytes = encode(value); await writeFile(path, bytes); return digest(bytes); }

export async function validateCompatibility(previousVersion = "1.0.0", version = "1.1.0") {
  const previous = await loadReleaseDirectory(releaseRoot(previousVersion), "all"), current = await loadReleaseDirectory(releaseRoot(version), "all"), previousMajor = Number(previousVersion.split(".")[0]), currentMajor = Number(version.split(".")[0]);
  if (previousMajor !== currentMajor) {
    const openapi = await parsed(join(releaseRoot(version), "openapi/control-plane.yaml")), migration = await readFile(join(releaseRoot(version), "conformance/migration.md"), "utf8"), statusSchema = current.schemas.find(({ $id }) => $id === `urn:sre-agent:schema:principal-status-replace:${version}`), statusRoute = openapi.paths?.["/v1/principals/{id}/status"]?.put, principalList = openapi.paths?.["/v1/principals"]?.get, principalGet = openapi.paths?.["/v1/principals/{id}"]?.get, rotationRoute = openapi.paths?.["/v1/credentials/{id}/rotation"]?.post;
    const rotationSchema = rotationRoute?.responses?.["201"]?.content?.["application/json"]?.schema?.$ref, rotationConflict = openapi.components?.responses?.RotationConflict?.content?.["application/json"]?.schema?.oneOf ?? [];
    if (openapi.info?.version !== version || !statusRoute || statusRoute.requestBody?.content?.["application/json"]?.schema?.$ref !== "#/components/schemas/PrincipalStatusReplace" || !statusRoute.responses?.["409"] || !Array.isArray(statusSchema?.required) || !statusSchema.required.includes("status") || !statusSchema.required.includes("expected_updated_at") || principalList?.responses?.["403"] || !principalList?.responses?.["404"] || principalGet?.responses?.["403"] || !principalGet?.responses?.["404"] || rotationSchema !== `urn:sre-agent:schema:credential-rotation:${version}` || rotationRoute?.responses?.["409"]?.$ref !== "#/components/responses/RotationConflict" || !rotationConflict.some((item) => item.$ref === `urn:sre-agent:schema:credential-rotation:${version}`) || !rotationConflict.some((item) => item.$ref === `urn:sre-agent:schema:error-envelope:${version}`) || !migration.includes("1.4.0") || !migration.includes("2.0.0") || !migration.includes("/v1") || !migration.includes("expected_updated_at")) throw new Error("Breaking-release migration proof is incomplete");
    return { previous_release: previousVersion, current_release: version, compatibility: "breaking", preserved_api_major: 1, migration_note: "conformance/migration.md", status: "passed" };
  }
  const positives = previous.fixtures.filter(({ status }) => status === "positive"), historicalNullableAuthorizationDeny = ({ target, data }) => previousVersion === "1.2.0" && version === "1.3.0" && target === "urn:sre-agent:schema:audit-event:1.2.0" && data.stage === "authorization" && data.outcome === "denied" && data.response_status === 403 && data.authorization_denial_cause === undefined, compatible = positives.filter((fixture) => !historicalNullableAuthorizationDeny(fixture)), compatibleExamples = previous.examples.filter((example) => !historicalNullableAuthorizationDeny(example)), advance = (target) => target.replace(new RegExp(`:${previousVersion.replaceAll(".", "\\.")}$`), `:${version}`);
  const absentConsumption = { availability: "absent", source: "openrouter", input_tokens: null, output_tokens: null, total_tokens: null, billed_usd: null, currency: null, precision: null, pricing_context: null };
  const legacyConsumption = (example) => previousVersion === "2.0.0" && version === "2.1.0" && example.target === "urn:sre-agent:schema:responses-response:" + version && example.data?.metadata && !("consumption" in example.data.metadata) ? { ...example, data: { ...example.data, metadata: { ...example.data.metadata, consumption: absentConsumption } } } : example;
  const legacyAudit = (fixture) => previousVersion === "2.0.0" && version === "2.1.0" && fixture.target === "urn:sre-agent:schema:audit-event:" + version && fixture.data?.stage === "response" && fixture.data?.outcome === "success" && !("consumption" in fixture.data) ? { ...fixture, data: { ...fixture.data, consumption: absentConsumption } } : fixture;
  try { validateFixtures(current.schemas, compatible.map((fixture) => legacyAudit({ ...fixture, target: advance(fixture.target), version }))); validateExamples(current.schemas, compatibleExamples.map((example) => legacyAudit(legacyConsumption({ ...example, target: advance(example.target) })))); } catch (error) { throw new Error("Additive compatibility failed: " + error.message); }
  const result = { previous_release: previousVersion, current_release: version, positive_fixtures: compatible.length, examples: compatibleExamples.length, status: "passed" };
  if (previousVersion === "2.0.0" && version === "2.1.0") result.normalization = { mode: "validation-only", legacy_success_consumption: "absent", raw_schema_acceptance: false, strict_consumer_note: "2.1.0 successful response metadata requires consumption; strict 2.0.0 consumers must tolerate the additive field" };
  return result;
}

export async function generateRelease(version = DEFAULT_VERSION) {
  const root = releaseRoot(version), results = await runConformance(root); await validateGovernance(pathToFileURL(`${root}/`), pathToFileURL(`${adrs}/`), version);
  if (version !== DEFAULT_VERSION) { const compatibility = await validateCompatibility(PREVIOUS_RELEASE[version], version); await writeImmutable(join(root, "conformance/compatibility.json"), compatibility); results.push({ consumer: "cross-version", action: baseline(version).compatibility === "breaking" ? "breaking-migration" : "additive-compatibility", fixture: "conformance/compatibility.json", status: "passed" }); }
  const evidence = await evidenceObject(root, version, results), evidencePath = join(root, "conformance/evidence.json"); await writeImmutable(evidencePath, evidence);
  const manifest = await manifestObject(root, version), manifestPath = join(root, "manifest.yaml"); assertReleaseMetadata(manifest); await writeImmutable(manifestPath, manifest, { decode: parse, encode: (value) => stringify(value, { sortMapEntries: true, lineWidth: 0 }) }); return { artifacts: Object.values(manifest.inventory).flat().length, results: results.length + 1 };
}

export async function validateRelease(version = DEFAULT_VERSION) {
  const root = releaseRoot(version), results = await runConformance(root); await validateGovernance(pathToFileURL(`${root}/`), pathToFileURL(`${adrs}/`), version);
  if (version !== DEFAULT_VERSION) { const expected = await validateCompatibility(PREVIOUS_RELEASE[version], version), actual = JSON.parse(await readFile(join(root, "conformance/compatibility.json"))); assertImmutableManifest(actual, expected); results.push({ consumer: "cross-version", action: baseline(version).compatibility === "breaking" ? "breaking-migration" : "additive-compatibility", fixture: "conformance/compatibility.json", status: "passed" }); }
  const manifest = parse(await readFile(join(root, "manifest.yaml"), "utf8")), expectedManifest = await manifestObject(root, version); assertReleaseMetadata(manifest); assertImmutableManifest(manifest, expectedManifest);
  const evidence = JSON.parse(await readFile(join(root, "conformance/evidence.json"))), expectedEvidence = await evidenceObject(root, version, results); assertImmutableManifest(evidence, expectedEvidence); return { artifacts: Object.values(manifest.inventory).flat().length, results: evidence.results.length };
}

export function assertEveryPublishedRelease(published, validated) {
  const omitted = published.filter((version) => !validated.includes(version));
  const unknown = validated.filter((version) => !published.includes(version));
  if (omitted.length || unknown.length) {
    throw new Error(
      `Release validation omitted [${omitted.join(", ")}] and added unknown [${unknown.join(", ")}]`,
    );
  }
}

export async function validatePublishedReleases(
  root = join(schemas, "releases"),
  validator = validateRelease,
) {
  const entries = await readdir(root, { withFileTypes: true });
  const versions = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
  if (!versions.length || versions.some((version) => !SEMVER.test(version))) {
    throw new Error("Published release directories must use semantic versions");
  }
  const validated = [];
  const results = [];
  for (const version of versions) {
    const manifest = await parsed(join(root, version, "manifest.yaml"));
    if (manifest?.contract_version !== version) {
      throw new Error(`Release directory ${version} does not match its manifest`);
    }
    results.push({ version, ...await validator(version) });
    validated.push(version);
  }
  assertEveryPublishedRelease(versions, validated);
  return { releases: validated, results };
}

export async function writeProjectionFixtures(version = DEFAULT_VERSION) {
  const root = releaseRoot(version); if (await optional(join(root, "manifest.yaml"), parse)) throw new Error(`Release ${version} is immutable; projection fixtures cannot be regenerated`); const outputs = [join(tooling, `.tmp/projection-control-${version}.yaml`), join(tooling, `.tmp/projection-responses-${version}.yaml`)]; await mkdir(dirname(outputs[0]), { recursive: true }); try { await Promise.all([runReleaseOpenapi("control-plane", outputs[0], version), runReleaseOpenapi("responses", outputs[1], version)]); const match = { contract_version: version, ...combineOpenapi(...await Promise.all(outputs.map(readContractFile))) }, missing = structuredClone(match), extra = structuredClone(match), first = Object.keys(missing.paths).sort()[0]; delete missing.paths[first]; extra.paths["/__future_drift__"] = { get: { parameters: [], security: { requirements: [], schemes: {} }, request: null, responses: { 200: { content: {} } } } };
    const files = [["positive/future-fastapi.match.projection.json", match], ["negative/future-fastapi.missing.projection.json", missing], ["negative/future-fastapi.extra.projection.json", extra]]; for (const [name, value] of files) await writeFile(join(root, "fixtures", name), `${canonical(value)}\n`); return files.map(([name]) => name);
  } finally { await Promise.all(outputs.map((path) => rm(path, { force: true }))); }
}
