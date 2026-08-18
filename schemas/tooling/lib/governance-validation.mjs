import { readFile } from "node:fs/promises";
import { parse } from "yaml";

const OWNERS = ["git", "db", "secret_store"], LABELS = { git: "Git", db: "Database", secret_store: "Secret store or environment" }, HEADINGS = ["Context", "Decision", "Consequences", "Alternatives", "Deferred", "Supersedes", "Links"];
const CONTENT = { git: { required: ["openapi", "schemas", "adrs", "examples", "fixtures", "seeds", "conformance"], prohibited: ["raw_keys", "authorization", "runtime_records"] }, db: { required: ["principals", "credential_records", "model_aliases", "grants", "audit_events", "idempotency_records"], prohibited: ["raw_keys", "upstream_secrets", "contract_definitions"] }, secret_store: { required: ["provider_secrets", "deployment_secrets"], prohibited: ["policy", "grants", "schemas", "audit_content"] } };
function assertKeys(value, expected, path) {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length !== expected.length || Object.keys(value).some((key) => !expected.includes(key))) throw new Error(`${path} contains unknown or missing fields`);
}

export function validateOwnershipMatrix(matrix) {
  assertKeys(matrix, ["contract_version", "authorities"], "Ownership matrix"); assertKeys(matrix.authorities, OWNERS, "Ownership authorities");
  if (matrix.contract_version !== "1.0.0") throw new Error("Ownership matrix must define contract version 1.0.0");
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

export function validateAuditAdr(text) {
  if (!/^# ADR-005:/m.test(text) || !/\*\*Status:\*\* Accepted/.test(text)) throw new Error("ADR-005 must be accepted");
  for (const heading of HEADINGS) if (!new RegExp(`^## ${heading}$`, "m").test(text)) throw new Error(`ADR-005 lacks ${heading}`);
  for (const term of ["stage-aware", "pre-sink", "fail-closed", "durable acceptance", "append-only", "downstream exporters", "retention", "content-read authorization"]) if (!text.toLowerCase().includes(term)) throw new Error(`ADR-005 lacks required decision: ${term}`);
}

export async function validateGovernance(release, adrs) {
  const matrix = validateOwnershipMatrix(parse(await readFile(new URL("conformance/ownership-matrix.yaml", release), "utf8")));
  const evidence = JSON.parse(await readFile(new URL("conformance/ownership-evidence.json", release), "utf8"));
  const placements = validateOwnershipEvidence(matrix, evidence);
  validateAuditAdr(await readFile(new URL("ADR-005-audit-redaction.md", adrs), "utf8"));
  return { authorities: OWNERS.length, placements };
}
