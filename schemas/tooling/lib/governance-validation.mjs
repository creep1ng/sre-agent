import { readFile, readdir } from "node:fs/promises";
import { parse } from "yaml";

const OWNERS = ["git", "db", "secret_store"], LABELS = { git: "Git", db: "Database", secret_store: "Secret store or environment" }, HEADINGS = ["Context", "Decision", "Consequences", "Alternatives", "Deferred", "Supersedes", "Links"];
const CONTENT = { git: { required: ["openapi", "schemas", "adrs", "examples", "fixtures", "seeds", "conformance"], prohibited: ["raw_keys", "authorization", "runtime_records"] }, db: { required: ["principals", "credential_records", "model_aliases", "grants", "audit_events", "idempotency_records"], prohibited: ["raw_keys", "upstream_secrets", "contract_definitions"] }, secret_store: { required: ["provider_secrets", "deployment_secrets"], prohibited: ["policy", "grants", "schemas", "audit_content"] } };
const ADRS = {
  "ADR-001-responses.md": { id: "001", decision: ["text-only", "non-streaming", "post /v1/responses", "validation", "authentication", "authorization", "alias and model resolution", "openrouter", "concrete", "effective provider", "x-generation-id", "trace context", "502", "503", "504"], deferred: ["runtime implementation", "streaming", "tools", "conversations", "provider sdk choice", "credentials and secrets", "persistence", "broader openai and openrouter surfaces"] },
  "ADR-002-principal.md": { id: "002", decision: ["principal", "kind=human|agent", "organization", "role", "scope"], deferred: ["workspace tenancy", "memberships", "roles", "federation", "oauth", "jwt identity"] },
  "ADR-003-api-keys.md": { id: "003", decision: ["bearer api keys", "principalcontext", "one-way hash", "exactly once"], deferred: ["hash algorithm selection", "secret-store implementation", "rotation transactions", "authentication runtime"] },
  "ADR-004-grants.md": { id: "004", decision: ["direct `allow`", "no match returns `deny`", "authorization completes before model routing", "policy_id=null"], deferred: ["policy engine selection", "condition languages", "delegation", "hierarchical resources", "explicit deny rules"] },
  "ADR-005-audit-redaction.md": { id: "005", decision: ["stage-aware", "pre-sink", "fail-closed", "durable acceptance", "append-only", "downstream exporters"], deferred: ["retention", "content-read authorization", "product sink selection", "database design", "exporters", "operational retry policy", "runtime redactor implementation"] },
  "ADR-006-sanitized-audit-content.md": { id: "006", decision: ["sanitized_text", "llm_input", "llm_response", "fully_redacted", "65,536", "fail-closed"], deferred: ["retention", "content-read authorization", "runtime redactor implementation"] }
};
const ADR_FILES_BY_VERSION = { "1.0.0": Object.keys(ADRS).slice(0, 5), "1.1.0": Object.keys(ADRS) };
function assertKeys(value, expected, path) {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length !== expected.length || Object.keys(value).some((key) => !expected.includes(key))) throw new Error(`${path} contains unknown or missing fields`);
}

export function validateOwnershipMatrix(matrix) {
  assertKeys(matrix, ["contract_version", "authorities"], "Ownership matrix"); assertKeys(matrix.authorities, OWNERS, "Ownership authorities");
  if (!/^(?:1\.0\.0|1\.1\.0)$/.test(matrix.contract_version)) throw new Error("Ownership matrix must define a supported contract version");
  for (const owner of OWNERS) {
    const row = matrix.authorities[owner];
    assertKeys(row, ["label", "required", "prohibited"], `Ownership authority ${owner}`);
    if (row.label !== LABELS[owner] || !Array.isArray(row.required) || !row.required.length || !Array.isArray(row.prohibited) || !row.prohibited.length || ![...row.required, ...row.prohibited].every((item) => typeof item === "string")) throw new Error(`Ownership authority ${owner} has invalid closed metadata`);
    for (const kind of ["required", "prohibited"]) if (row[kind].length !== CONTENT[owner][kind].length || row[kind].some((item) => !CONTENT[owner][kind].includes(item))) throw new Error(`Ownership authority ${owner} must pin exact normative ${kind} content`);
    const all = [...row.required, ...row.prohibited];
    if (new Set(all).size !== all.length) throw new Error(`Ownership authority ${owner} has duplicate or conflicting content classifications`);
  }
  return matrix;
}

export function assertOwnedContent(matrix, owner, content) {
  const row = validateOwnershipMatrix(matrix).authorities[owner];
  if (!row || !row.required.includes(content)) throw new Error(`Out-of-authority content rejected: ${owner}/${content}`);
}

export function validateOwnershipEvidence(matrix, evidence) {
  validateOwnershipMatrix(matrix);
  assertKeys(evidence, ["contract_version", "placements"], "Ownership evidence");
  if (evidence.contract_version !== matrix.contract_version || !Array.isArray(evidence.placements) || !evidence.placements.length) throw new Error("Ownership evidence must be non-empty and version-aligned");
  const contents = [...new Set(OWNERS.flatMap((owner) => [...matrix.authorities[owner].required, ...matrix.authorities[owner].prohibited]))], expected = new Set(OWNERS.flatMap((owner) => contents.map((content) => `${owner}/${content}/${matrix.authorities[owner].required.includes(content) ? "positive" : "negative"}`)));
  for (const placement of evidence.placements) {
    assertKeys(placement, ["owner", "content", "status"], "Ownership placement");
    if (!OWNERS.includes(placement.owner) || !["positive", "negative"].includes(placement.status) || typeof placement.content !== "string") throw new Error("Ownership evidence has invalid metadata");
    let allowed = true;
    try { assertOwnedContent(matrix, placement.owner, placement.content); } catch { allowed = false; }
    if ((placement.status === "positive") !== allowed) throw new Error(`Ownership evidence ${placement.owner}/${placement.content} produced an unexpected decision`);
    if (!expected.delete(`${placement.owner}/${placement.content}/${placement.status}`)) throw new Error(`Ownership evidence must be exhaustive and unique: ${placement.owner}/${placement.content}`);
  }
  if (expected.size) throw new Error(`Ownership evidence must be exhaustive; ${expected.size} placements are missing`);
  return evidence.placements.length;
}

function section(text, heading) {
  return text.match(new RegExp(`^## ${heading}\\s*$([\\s\\S]*?)(?=^## |(?![\\s\\S]))`, "m"))?.[1].toLowerCase() ?? "";
}

export function validateAdr(text, policy) {
  const name = `ADR-${policy.id}`;
  if (!new RegExp(`^# ${name}:`, "m").test(text) || !/^\s*- \*\*Status:\*\* Accepted\s*$/m.test(text)) throw new Error(`${name} must be accepted`);
  for (const heading of HEADINGS) if (!new RegExp(`^## ${heading}$`, "m").test(text)) throw new Error(`${name} lacks ${heading}`);
  for (const term of policy.decision) if (!section(text, "Decision").includes(term)) throw new Error(`${name} lacks approved decision: ${term}`);
  for (const term of policy.deferred) if (!section(text, "Deferred").includes(term)) throw new Error(`${name} lacks approved deferral: ${term}`);
}

export function validateAuditAdr(text) {
  validateAdr(text, ADRS["ADR-005-audit-redaction.md"]);
}

export async function validateAdrs(adrs, version = "1.0.0") {
  const expected = ADR_FILES_BY_VERSION[version]; if (!expected) throw new Error(`Unsupported governance version ${version}`);
  const actual = (await readdir(adrs)).filter((file) => /^ADR-\d{3}-.*\.md$/.test(file)).sort(), unknown = actual.filter((file) => !(file in ADRS));
  if (unknown.length || expected.some((file) => !actual.includes(file))) throw new Error(`ADR governance for ${version} must contain ${expected.join(", ")} and no unknown ADRs`);
  for (const file of expected) validateAdr(await readFile(new URL(file, adrs), "utf8"), ADRS[file]);
  return expected.length;
}

export async function validateGovernance(release, adrs, version = "1.0.0") {
  const matrix = validateOwnershipMatrix(parse(await readFile(new URL("conformance/ownership-matrix.yaml", release), "utf8")));
  if (matrix.contract_version !== version) throw new Error(`Ownership matrix must define contract version ${version}`);
  const evidence = JSON.parse(await readFile(new URL("conformance/ownership-evidence.json", release), "utf8"));
  const placements = validateOwnershipEvidence(matrix, evidence);
  const adrCount = await validateAdrs(adrs, version);
  return { authorities: OWNERS.length, placements, adrs: adrCount };
}
