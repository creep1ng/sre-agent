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
function semanticFixtureValid(fixture) {
  if (fixture.target !== "urn:sre-agent:schema:bootstrap-seed:1.0.0" || fixture.data?.output?.result !== "success") return true;
  const { seed, output } = fixture.data, principal = output.principal, grants = new Map(output.grants.map((grant) => [grant.grant_id, grant]));
  return principal.principal_id === seed.principal.principal_id && principal.kind === seed.principal.kind && principal.display_name === seed.principal.display_name && output.credential.credential.principal_id === seed.principal.principal_id && output.grants.length === seed.grants.length && seed.grants.every((expected) => { const actual = grants.get(expected.grant_id); return actual?.principal_id === seed.principal.principal_id && actual.action === expected.action && JSON.stringify(actual.resource) === JSON.stringify(expected.resource); });
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
  for (const example of examples) { const validate = ajv.getSchema(example.target); if (!validate || !validate(example.data)) throw new Error(`Example ${example.name} failed: ${ajv.errorsText(validate?.errors)}`); }
}
function prohibitedFields(value, path = "$") {
  if (!value || typeof value !== "object") return [];
  if (Array.isArray(value)) return value.flatMap((item, index) => prohibitedFields(item, `${path}/${index}`));
  return Object.entries(value).flatMap(([key, child]) => [...(PROHIBITED_FIELDS.has(key) ? [`${path}/${key}`] : []), ...prohibitedFields(child, `${path}/${key}`)]);
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
export async function loadReleaseDirectory(directory, group = "shared") {
  const base = directory instanceof URL ? directory : pathToFileURL(`${resolve(directory)}/`);
  const schemas = (await readJsonTree(new URL("json-schema/", base), ".schema.json")).map(({ value }) => value);
  const loaded = (await readJsonTree(new URL("fixtures/", base), ".fixture.json")).map(({ name, value }) => ({ name, ...value }));
  const fixtures = group === "shared" ? loaded : loaded.filter((fixture) => fixture.group === group);
  const exampleTarget = group === "audit" ? () => "urn:sre-agent:schema:audit-event:1.0.0" : group === "control" ? (name) => name.startsWith("credential-") ? "urn:sre-agent:schema:credential-issuance:1.0.0" : "urn:sre-agent:schema:bootstrap-seed:1.0.0" : null;
  const examples = exampleTarget ? (await readJsonTree(new URL(`examples/${group}/`, base), ".example.json")).map(({ name, value: data }) => ({ name, data, target: exampleTarget(name) })) : [];
  if (!fixtures.length) throw new Error(`Unknown or empty fixture scope: ${group}`);
  return { schemas, fixtures, examples };
}
export async function loadFixtureDirectory(directory) {
  const base = directory instanceof URL ? directory : pathToFileURL(`${resolve(directory)}/`), names = (await readdir(base)).sort();
  const read = (name) => readFile(new URL(name, base), "utf8").then(JSON.parse);
  return { schemas: await Promise.all(names.filter((name) => name.endsWith(".schema.json")).map(read)), fixtures: await Promise.all(names.filter((name) => name.endsWith(".fixture.json")).map(async (name) => ({ name, ...await read(name) }))) };
}
