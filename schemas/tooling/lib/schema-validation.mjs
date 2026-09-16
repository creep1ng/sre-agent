import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
const CORE = "(?:0|[1-9]\\d*)", IDENTIFIER = "(?:0|[1-9]\\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)", SEMVER_SOURCE = `${CORE}\\.${CORE}\\.${CORE}(?:-${IDENTIFIER}(?:\\.${IDENTIFIER})*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?`, SEMVER = new RegExp(`^${SEMVER_SOURCE}$`);
const HOST_LABEL = "[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", HOST = `${HOST_LABEL}(?:\\.${HOST_LABEL})*`, URN_COMPONENT = HOST_LABEL, HTTP_ID = new RegExp(`^https?://(?=[A-Za-z0-9.-]{1,253}/)${HOST}/(?:(?!\\.{1,2}/)[A-Za-z0-9._~-]+/)*(${SEMVER_SOURCE})$`), URN_ID = new RegExp(`^urn:${URN_COMPONENT}(?::${URN_COMPONENT})*:(${SEMVER_SOURCE})$`), APPLICATORS = new Set(["allOf", "anyOf", "oneOf", "if", "then", "else"]), ANNOTATIONS = new Set(["const", "default", "enum", "examples", "not"]), MAPS = new Set(["$defs", "definitions", "dependentSchemas", "patternProperties", "properties"]);
const PROHIBITED_FIELDS = new Set(["organization", "organization_id", "tenant", "tenant_id", "user", "user_id", "role", "roles", "scope", "scopes"]);
function schemaVersion(id) {
  const invalid = () => { throw new Error("Every schema requires an absolute $id with an unambiguous SemVer 2.0.0 identity component"); }; if (typeof id !== "string") invalid();
  const match = HTTP_ID.exec(id) ?? URN_ID.exec(id); if (!match) invalid(); return match[1];
}
function objectSchema(schema) {
  const types = Array.isArray(schema.type) ? schema.type : [schema.type]; return types.includes("object") || "properties" in schema || [...APPLICATORS].some((key) => (Array.isArray(schema[key]) ? schema[key] : [schema[key]]).some((child) => child && typeof child === "object" && objectSchema(child)));
}
function assertClosedObjects(value, path = "$", compositionClosed = false) {
  if (!value || typeof value !== "object") return;
  if (Array.isArray(value)) return value.forEach((item, index) => assertClosedObjects(item, `${path}/${index}`, compositionClosed));
  const closed = compositionClosed || value.additionalProperties === false || value.unevaluatedProperties === false;
  if (objectSchema(value) && !closed) throw new Error(`Object schema ${path} must close object with additionalProperties:false or unevaluatedProperties:false`);
  for (const [key, child] of Object.entries(value)) if (!ANNOTATIONS.has(key)) {
    const inherited = APPLICATORS.has(key) && (compositionClosed || value.unevaluatedProperties === false); if (MAPS.has(key) && child && typeof child === "object") for (const [name, schema] of Object.entries(child)) assertClosedObjects(schema, `${path}/${key}/${name}`, key === "dependentSchemas" && (compositionClosed || value.unevaluatedProperties === false)); else assertClosedObjects(child, `${path}/${key}`, inherited);
  }
}
export function createSchemaRegistry(schemas) {
  if (!schemas.length) throw new Error("At least one schema is required"); const ajv = new Ajv2020({ strict: true, allErrors: true }), ids = new Set(); addFormats(ajv);
  for (const schema of schemas) {
    schemaVersion(schema.$id);
    if (ids.has(schema.$id)) throw new Error(`Duplicate schema $id: ${schema.$id}`);
    assertClosedObjects(schema); ids.add(schema.$id); ajv.addSchema(schema);
  }
  for (const id of ids) ajv.getSchema(id); return ajv;
}
function consumptionSemanticsValid(value) {
  if (!value || value.source !== "openrouter") return false;
  const tokens = [value.input_tokens, value.output_tokens, value.total_tokens], billing = [value.billed_usd, value.currency, value.precision, value.pricing_context];
  if (tokens.every((item) => item !== null) && value.total_tokens !== value.input_tokens + value.output_tokens) return false;
  if (value.billed_usd === null && billing.slice(1).some((item) => item !== null)) return false;
  const hasEvidence = [...tokens, ...billing].some((item) => item !== null), complete = [...tokens, ...billing].every((item) => item !== null);
  if (value.availability === "complete") return complete;
  if (value.availability === "partial") return hasEvidence && !complete;
  return (value.availability === "absent" || value.availability === "unavailable") && !hasEvidence;
}
const CATALOG_ENTRY_RULES = {
  llm_model: { source: "model_alias", states: new Set(["active", "inactive"]) },
  mcp_server: { source: "mcp", states: new Set(["registered", "active", "inactive", "revoked"]) },
  mcp_tool: { source: "mcp", states: new Set(["registered", "active", "inactive", "revoked"]) },
  skill: { source: "skill", states: new Set(["draft", "published", "active", "inactive", "revoked"]) },
  bok_collection: { source: "bok", states: new Set(["draft", "indexing", "active", "inactive", "revoked"]) },
};
function resourceCatalogEntrySemanticsValid(value) {
  const rule = CATALOG_ENTRY_RULES[value?.resource_type];
  return Boolean(rule && value.source === rule.source && rule.states.has(value.status) && typeof value.owner_id === "string" && typeof value.source_ref === "string");
}
function orderedIds(ids) {
  const sorted = [...ids].sort((left, right) => left.localeCompare(right));
  return ids.length === sorted.length && ids.every((id, index) => id === sorted[index]) && new Set(ids).size === ids.length;
}
function catalogHttpCaseSemanticsValid(value) {
  const request = value?.request, expected = value?.expected, phases = request?.phase_order;
  if (!request || !expected || !Array.isArray(phases) || expected.enumerates !== false || expected.continuation !== false || expected.limit !== request.limit || !orderedIds(expected.result_ids)) return false;
  const empty = expected.visible_items === 0 && expected.result_ids.length === 0;
  const noLookup = request.lookup_performed === false && empty && expected.deterministic === true;
  if (request.authentication !== "valid") {
    const status = ["missing", "invalid"].includes(request.authentication) ? 401 : 403;
    const code = status === 401 ? "authentication_failed" : "resource_unavailable";
    return phases.join("/") === "authenticate" && request.lookup_performed === false && request.filters_valid === true && expected.status === status && expected.error_code === code && noLookup;
  }
  if (!request.filters_valid) return phases.join("/") === "authenticate/validate_filters" && request.lookup_performed === false && expected.status === 422 && expected.error_code === "validation_error" && noLookup && request.forbidden_parameter !== null;
  if (phases.join("/") !== "authenticate/validate_filters/lookup/project" || request.lookup_performed !== true || expected.deterministic !== true) return false;
  if (value.operation === "catalog.list") return request.target_visibility === "none" && expected.status === 200 && expected.error_code === null && expected.visible_items === expected.result_ids.length;
  if (value.operation !== "catalog.read") return false;
  if (request.target_visibility === "visible") return expected.status === 200 && expected.error_code === null && expected.visible_items === 1 && expected.result_ids.length === 1;
  return ["hidden", "absent", "inactive", "filtered"].includes(request.target_visibility) && expected.status === 404 && expected.error_code === "resource_not_found" && empty;
}
function lifecyclePhase(value, expected) {
  const request = value.request;
  return expected.state_before === request.state_before && expected.authorization_before === request.authorization_before && expected.authorization_after === request.authorization_after && expected.state_unchanged === (expected.state_before === expected.state_after) && expected.transition_count === (expected.state_unchanged ? 0 : 1);
}
function catalogLifecycleCaseSemanticsValid(value) {
  const request = value?.request, expected = value?.expected;
  if (!request || !expected || !lifecyclePhase(value, expected)) return false;
  const phase = request.phase_order.join("/");
  if (value.operation === "idempotent_replay") return request.prior_state === "active" && request.reset_requested === false && request.state_before === "active" && request.payload_matches_binding && request.version_matches && request.authorization_before === "allowed" && request.authorization_after === "allowed" && !request.drift_detected && phase === "authenticate/authorize/idempotency_lookup/replay_response" && expected.status === 200 && expected.transition_count === 0 && !expected.upstream_called && !expected.snapshot_allowed && expected.state_after === "active" && expected.stable_replay && expected.later_request_status === null && !expected.later_upstream_called && expected.upstream_denied_reason === "none" && !expected.repair_performed;
  if (value.operation === "idempotency_conflict") return request.prior_state === "active" && request.reset_requested === false && request.state_before === "active" && (!request.payload_matches_binding || !request.version_matches) && request.authorization_before === "allowed" && request.authorization_after === "allowed" && !request.drift_detected && phase === "authenticate/authorize/idempotency_lookup/conflict_response" && expected.status === 409 && !expected.upstream_called && !expected.snapshot_allowed && expected.state_after === "active" && !expected.stable_replay && expected.later_request_status === 409 && !expected.later_upstream_called && expected.upstream_denied_reason === "idempotency_conflict" && !expected.repair_performed;
  if (value.operation === "in_flight_snapshot") return request.prior_state === "active" && request.reset_requested === false && request.state_before === "active" && request.payload_matches_binding && request.version_matches && request.authorization_before === "allowed" && request.authorization_after === "denied" && !request.drift_detected && phase === "authenticate/authorize/capture_snapshot/lifecycle_change/upstream/later_authorize" && expected.status === 204 && expected.transition_count === 1 && expected.upstream_called && expected.snapshot_allowed && expected.state_after === "inactive" && !expected.stable_replay && expected.later_request_status === 403 && !expected.later_upstream_called && expected.upstream_denied_reason === "none" && !expected.repair_performed;
  if (value.operation === "startup_drift") return request.prior_state === "conflict" && request.reset_requested === false && request.state_before === "active" && request.payload_matches_binding && request.version_matches && request.authorization_before === "not_applicable" && request.authorization_after === "not_applicable" && request.drift_detected && phase === "startup/drift_detected/conflict_response" && expected.status === 409 && !expected.upstream_called && !expected.snapshot_allowed && expected.state_after === "active" && !expected.stable_replay && expected.later_request_status === 409 && !expected.later_upstream_called && expected.upstream_denied_reason === "startup_drift" && !expected.repair_performed;
  if (value.operation === "reconciliation") return request.prior_state === "conflict" && request.reset_requested === true && request.state_before === "conflict" && request.payload_matches_binding && request.version_matches && request.authorization_before === "allowed" && request.authorization_after === "allowed" && request.drift_detected && phase === "authenticate/authorize/startup/drift_detected/reconcile_authorize/reset" && expected.status === 201 && expected.transition_count === 1 && !expected.upstream_called && !expected.snapshot_allowed && expected.state_after === "restored" && expected.stable_replay && expected.later_request_status === null && !expected.later_upstream_called && expected.upstream_denied_reason === "none" && expected.repair_performed;
  return false;
}
function semanticFixtureValid(fixture) {
  const name = /^urn:sre-agent:schema:([a-z-]+):/.exec(fixture.target)?.[1];
  if (name === "consumption") return consumptionSemanticsValid(fixture.data);
  if (name === "idempotency-record") return idempotencyRetentionValid(fixture.data);
  if (name === "responses-http-case") return responsesHttpCaseValid(fixture.data);
  if (name === "openrouter-metadata-case") return openRouterMetadataValid(fixture.data);
  if (name === "resource-catalog-entry") return resourceCatalogEntrySemanticsValid(fixture.data);
  if (name === "resource-catalog-http-case") return catalogHttpCaseSemanticsValid(fixture.data);
  if (name === "resource-catalog-lifecycle-case") return catalogLifecycleCaseSemanticsValid(fixture.data);
  if (name !== "bootstrap-seed" || fixture.data?.output?.result !== "success") return true;
  const { seed, output } = fixture.data, principal = output.principal, grants = new Map(output.grants.map((grant) => [grant.grant_id, grant]));
  return principal.principal_id === seed.principal.principal_id && principal.kind === seed.principal.kind && principal.display_name === seed.principal.display_name && output.credential.credential.principal_id === seed.principal.principal_id && output.grants.length === seed.grants.length && seed.grants.every((expected) => { const actual = grants.get(expected.grant_id); return actual?.principal_id === seed.principal.principal_id && actual.action === expected.action && JSON.stringify(actual.resource) === JSON.stringify(expected.resource); });
}
function idempotencyRetentionValid(value) {
  if (value?.binding === "principal_lifetime") return value.expires_at === null;
  if (value?.binding !== "at_least_24h" || typeof value.created_at !== "string" || typeof value.expires_at !== "string") return false;
  const createdAt = Date.parse(value.created_at), expiresAt = Date.parse(value.expires_at);
  return Number.isFinite(createdAt) && Number.isFinite(expiresAt) && expiresAt - createdAt >= 86_400_000;
}
function openRouterMetadataValid(value) {
  const success = ["metadata-success", "lookup-success"].includes(value.condition), selected = value.selected_endpoints ?? [], generation = value.generation;
  if (!success) return value.outcome === "error" && value.status === 502 && Object.keys(value).every((key) => ["condition", "outcome", "status", "public"].includes(key)) && value.public?.error?.code === "provider_evidence_invalid" && value.public?.error?.message === "Provider evidence was invalid." && value.public?.retryable === false;
  const consistent = value.outcome === "success" && value.status === 200 && !value.public && value.router === "openrouter" && value.effective_provider !== "openrouter" && selected.length === 1 && selected[0].provider === value.effective_provider;
  if (!consistent) return false;
  if (value.condition === "metadata-success") return generation === undefined;
  return generation?.attempts === 1 && generation.response_header === generation.lookup_key && generation.lookup_key !== value.public_response_id;
}
function responsesHttpCaseValid(value) {
  const credentials = value.condition?.startsWith("credential-"), alias = value.condition?.startsWith("alias-"), trace = value.condition?.startsWith("trace-"), upstream = value.condition?.startsWith("upstream-");
  const envelope = (status, code, message, retryable) => value.status === status && value.public?.error?.code === code && value.public?.error?.message === message && value.public?.retryable === retryable;
  const noLater = !value.routed && !value.upstream_attempted, headerNames = Object.keys(value.headers ?? {}), challenge = headerNames.length === 1 && value.headers["WWW-Authenticate"] === "Bearer";
  if (value.condition === "invalid-request-and-credential") return value.stage === "validation" && envelope(422, "validation_error", "The request is invalid.", false) && !headerNames.length && !value.alias_evaluated && noLater;
  if (credentials) return value.stage === "authentication" && envelope(401, "authentication_failed", "Authentication failed.", false) && challenge && !value.alias_evaluated && noLater;
  if (alias) return value.stage === "authorization" && envelope(403, "resource_unavailable", "The requested resource is unavailable.", false) && !headerNames.length && value.alias_evaluated && noLater;
  if (trace) { const expectedMode = ["trace-missing", "trace-invalid"].includes(value.condition) ? "new" : "bounded-child"; return value.stage === "tracing" && value.status === 200 && !value.public && !value.alias_evaluated && noLater && value.trace?.mode === expectedMode && value.trace.incoming_flags_trusted === false && value.trace.tracestate_propagated === false && headerNames.length === 1 && "traceparent" in value.headers; }
  if (upstream) { const taxonomy = { "upstream-malformed": [502, "upstream_invalid_response", "The upstream response was invalid.", false], "upstream-unavailable": [503, "upstream_unavailable", "The upstream service is unavailable.", true], "upstream-timeout": [504, "upstream_timeout", "The upstream request timed out.", true] }[value.condition], hasRetry = "Retry-After" in (value.headers ?? {}); return value.stage === "upstream" && value.alias_evaluated && value.routed && envelope(...taxonomy) && headerNames.every((name) => name === "Retry-After") && hasRetry === (value.retry_after_reliable === true) && (!hasRetry || value.public.retryable); }
  return false;
}
export function validateFixtures(schemas, fixtures) {
  const ajv = createSchemaRegistry(schemas);
  if (!fixtures.length) throw new Error("At least one fixture is required");
  assertCanonicalVocabulary(schemas, fixtures);
  for (const fixture of fixtures) {
    for (const field of ["target", "rule", "status", "version", "data"]) if (!(field in fixture)) throw new Error(`Fixture ${fixture.name ?? "<unknown>"} lacks ${field}`);
    if (!/^(?:positive|negative)$/.test(fixture.status) || !SEMVER.test(fixture.version)) throw new Error(`Fixture ${fixture.name} has invalid metadata`);
    const target = schemas.find(({ $id }) => $id === fixture.target), validate = target && ajv.getSchema(fixture.target); if (!validate) throw new Error(`Fixture ${fixture.name} targets unknown schema ${fixture.target}`);
    const targetVersion = schemaVersion(target.$id); if (fixture.version !== targetVersion) throw new Error(`Fixture ${fixture.name} version ${fixture.version} does not match target schema version ${targetVersion}`); const shapeValid = validate(fixture.data), semanticValid = semanticFixtureValid(fixture), valid = shapeValid && semanticValid;
    if (fixture.status === "positive" && !valid) throw new Error(`Positive fixture ${fixture.name} failed: ${ajv.errorsText(validate.errors)}`);
    if (fixture.status === "negative" && valid) throw new Error(`Negative fixture ${fixture.name} for rule ${fixture.rule} validated unexpectedly`);
    if (fixture.status === "negative" && !(fixture.rule === "semantic" ? !semanticValid : validate.errors?.some(({ keyword }) => keyword === fixture.rule))) throw new Error(`Negative fixture ${fixture.name} did not fail rule ${fixture.rule}`);
  }
}
export function validateExamples(schemas, examples) {
  const ajv = createSchemaRegistry(schemas);
  if (!examples.length) throw new Error("At least one example is required");
  for (const example of examples) { const validate = ajv.getSchema(example.target), input = example.data?.input, bytesValid = example.target !== "urn:sre-agent:schema:responses-request:1.0.0" || typeof input !== "string" || Buffer.byteLength(input, "utf8") <= 65536; if (!validate || !validate(example.data) || !bytesValid) throw new Error(`Example ${example.name} failed: ${bytesValid ? ajv.errorsText(validate?.errors) : "input exceeds 65,536 UTF-8 bytes"}`); }
}
function prohibitedFields(value, path = "$") {
  if (!value || typeof value !== "object") return [];
  if (Array.isArray(value)) return value.flatMap((item, index) => prohibitedFields(item, `${path}/${index}`));
  return Object.entries(value).flatMap(([key, child]) => [...(PROHIBITED_FIELDS.has(key) && !(key === "role" && (child === "assistant" || child?.const === "assistant")) ? [`${path}/${key}`] : []), ...prohibitedFields(child, `${path}/${key}`)]);
}
export function assertCanonicalVocabulary(schemas, fixtures) {
  for (const schema of schemas) { const found = prohibitedFields(schema); if (found.length) throw new Error(`Schema ${schema.$id} contains prohibited field ${found[0]}`); }
  for (const fixture of fixtures) {
    if (fixture.legacy === true && fixture.status !== "negative") throw new Error(`Legacy fixture ${fixture.name} must be negative evidence`);
    if (fixture.legacy === true) continue;
    const found = prohibitedFields(fixture.data); if (found.length) throw new Error(`Fixture ${fixture.name} contains prohibited field ${found[0]}`);
  }
}
async function readJsonTree(directory, suffix, prefix = "") {
  const values = [];
  for (const entry of (await readdir(directory, { withFileTypes: true })).sort((left, right) => left.name.localeCompare(right.name))) {
    if (entry.isDirectory()) values.push(...await readJsonTree(new URL(`${entry.name}/`, directory), suffix, `${prefix}${entry.name}/`));
    else if (entry.isFile() && entry.name.endsWith(suffix)) values.push({ name: `${prefix}${entry.name}`, value: JSON.parse(await readFile(new URL(entry.name, directory), "utf8")) });
  }
  return values;
}
async function readJsonTreeOptional(directory, suffix) {
  try { return await readJsonTree(directory, suffix); } catch (error) { if (error.code === "ENOENT") return []; throw error; }
}
export async function loadReleaseDirectory(directory, group = "shared") {
  const base = directory instanceof URL ? directory : pathToFileURL(`${resolve(directory)}/`);
  const schemas = (await readJsonTree(new URL("json-schema/", base), ".schema.json")).map(({ value }) => value);
  const loaded = (await readJsonTree(new URL("fixtures/", base), ".fixture.json")).flatMap(({ name, value }) => value.cases ? value.cases.map((data, index) => ({ name: `${name}#${index + 1}`, target: value.target, rule: value.rule, status: value.status, version: value.version, group: value.group, data })) : [{ name, ...value }]);
  const fixtures = group === "all" || group === "shared" ? loaded : loaded.filter((fixture) => fixture.group === group);
  const version = schemaVersion(schemas[0]?.$id), schemaId = (name) => `urn:sre-agent:schema:${name}:${version}`, exampleTarget = (scope, name) => scope === "audit" ? schemaId("audit-event") : scope === "control" ? name.startsWith("credential-") ? schemaId("credential-issuance") : schemaId("bootstrap-seed") : scope === "catalog" ? name.includes("list") ? schemaId("resource-catalog-list") : schemaId("resource-catalog-entry") : name.startsWith("minimal-request") ? schemaId("responses-request") : schemaId("responses-response");
  const scopes = group === "all" ? ["audit", "control", "responses", "catalog"] : [group], examples = (await Promise.all(scopes.filter((scope) => ["audit", "control", "responses", "catalog"].includes(scope)).map(async (scope) => {
    const readExamples = scope === "catalog" ? readJsonTreeOptional : readJsonTree;
    return (await readExamples(new URL(`examples/${scope}/`, base), ".example.json")).map(({ name, value: data }) => ({ name: group === "all" ? `${scope}/${name}` : name, data, target: exampleTarget(scope, name) }));
  }))).flat();
  if (!fixtures.length && !examples.length) throw new Error(`Unknown or empty fixture scope: ${group}`);
  return { schemas, fixtures, examples };
}
export async function loadFixtureDirectory(directory) {
  const base = directory instanceof URL ? directory : pathToFileURL(`${resolve(directory)}/`), names = (await readdir(base)).sort();
  const read = (name) => readFile(new URL(name, base), "utf8").then(JSON.parse);
  return { schemas: await Promise.all(names.filter((name) => name.endsWith(".schema.json")).map(read)), fixtures: await Promise.all(names.filter((name) => name.endsWith(".fixture.json")).map(async (name) => ({ name, ...await read(name) }))) };
}
