import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { assertOwnedContent, validateGovernance, validateOwnershipEvidence, validateOwnershipMatrix } from "../lib/governance-validation.mjs";

const release = new URL("../../releases/1.0.0/", import.meta.url), adrs = new URL("../../adrs/", import.meta.url);
const adrFiles = ["ADR-001-responses.md", "ADR-002-principal.md", "ADR-003-api-keys.md", "ADR-004-grants.md", "ADR-005-audit-redaction.md"];
const provisionalAdr001 = `# ADR-001: Responses gateway boundary

- **Status:** Accepted
- **Contract version:** 1.0.0

## Context
Portable governance is required before runtime implementation.
## Decision
The gateway exposes only the text-only non-streaming POST /v1/responses subset. Validation precedes authentication; authorization precedes alias and model resolution. OpenRouter is the initial router, with a concrete model and effective provider. X-Generation-Id permits one bounded lookup. Trace Context is safe and errors use a redacted 502, 503, and 504 taxonomy.
## Consequences
The contract remains portable and closed.
## Alternatives
Broader provider and OpenAI surfaces were rejected.
## Deferred
Runtime implementation, streaming, tools, conversations, provider SDK choice, credentials and secrets, persistence, and broader OpenAI and OpenRouter surfaces are deferred.
## Supersedes
None.
## Links
- Parent issue #9
`;
async function withAdrMutation(mutate) {
  const directory = await mkdtemp(join(tmpdir(), "sre-adrs-"));
  try {
    for (const file of adrFiles) {
      let text;
      try { text = await readFile(new URL(file, adrs), "utf8"); } catch (error) { if (file !== adrFiles[0] || error.code !== "ENOENT") throw error; text = provisionalAdr001; }
      await writeFile(join(directory, file), text);
    }
    await mutate(directory);
    return await validateGovernance(release, new URL(`file://${directory}/`));
  } finally { await rm(directory, { recursive: true, force: true }); }
}
const replaceIn = async (directory, file, before, after = "") => { const path = join(directory, file), text = await readFile(path, "utf8"); assert.notEqual(text.includes(before), false, `${file} mutation anchor missing: ${before}`); await writeFile(path, text.replace(before, after)); };

test("governance validates ADR-001 through ADR-005 and normative ownership evidence", async () => assert.deepEqual(await validateGovernance(release, adrs), { authorities: 3, placements: 66, adrs: 5 }));
test("release 1.1.0 adds accepted ADR-006 without changing historical ADR membership", async () => assert.deepEqual(await validateGovernance(new URL("../../releases/1.1.0/", import.meta.url), adrs, "1.1.0"), { authorities: 3, placements: 66, adrs: 6 }));
test("release 1.2.0 preserves accepted governance and ADR membership", async () => assert.deepEqual(await validateGovernance(new URL("../../releases/1.2.0/", import.meta.url), adrs, "1.2.0"), { authorities: 3, placements: 66, adrs: 6 }));
test("release 1.3.0 preserves accepted governance and ADR membership", async () => assert.deepEqual(await validateGovernance(new URL("../../releases/1.3.0/", import.meta.url), adrs, "1.3.0"), { authorities: 3, placements: 66, adrs: 6 }));
test("governance pins exact ADR-001 through ADR-005 membership", async () => {
  await Promise.all(adrFiles.map((file) => assert.rejects(withAdrMutation((directory) => rm(join(directory, file))), /ADR|governance/i)));
  await assert.rejects(withAdrMutation((directory) => writeFile(join(directory, "ADR-006-unapproved.md"), provisionalAdr001.replace("ADR-001", "ADR-006"))), /ADR|governance/i);
});
test("governance requires Accepted status and every standard heading", async () => {
  await Promise.all(adrFiles.map((file) => assert.rejects(withAdrMutation((directory) => replaceIn(directory, file, "**Status:** Accepted", "**Status:** Proposed")), /accepted/i)));
  for (const heading of ["Context", "Decision", "Consequences", "Alternatives", "Deferred", "Supersedes", "Links"]) await Promise.all(adrFiles.map((file) => assert.rejects(withAdrMutation((directory) => replaceIn(directory, file, `## ${heading}`, `## Removed ${heading}`)), new RegExp(heading, "i"))));
});
test("governance pins every approved ADR decision", async () => {
  const decisions = [[adrFiles[0], "authorization precedes alias and model resolution"], [adrFiles[1], "kind=human|agent"], [adrFiles[2], "one-way hash"], [adrFiles[3], "Authorization completes before model routing"], [adrFiles[4], "durable acceptance"]];
  await Promise.all(decisions.map(([file, term]) => assert.rejects(withAdrMutation((directory) => replaceIn(directory, file, term)), /decision/i)));
});
test("governance pins every approved ADR deferral", async () => {
  const deferrals = [[adrFiles[0], "provider SDK choice"], [adrFiles[1], "Workspace tenancy"], [adrFiles[2], "Hash algorithm selection"], [adrFiles[3], "Policy engine selection"], [adrFiles[4], "Retention"]];
  await Promise.all(deferrals.map(([file, term]) => assert.rejects(withAdrMutation((directory) => replaceIn(directory, file, term)), /defer/i)));
});
test("ownership allowlist rejects content outside an authority", async () => { const { parse } = await import("yaml"), { readFile } = await import("node:fs/promises"), matrix = parse(await readFile(new URL("conformance/ownership-matrix.yaml", release), "utf8")); assert.doesNotThrow(() => assertOwnedContent(matrix, "git", "schemas")); assert.throws(() => assertOwnedContent(matrix, "git", "provider_secrets"), /out-of-authority/i); });
test("governance CLI validates ownership and ADR together", () => { const result = spawnSync(process.execPath, [fileURLToPath(new URL("../validate.mjs", import.meta.url)), "--scope", "governance"], { encoding: "utf8" }); assert.equal(result.status, 0, result.stderr); assert.match(result.stdout, /3 authorities, 66 ownership placements, and 5 accepted ADRs/); });
test("ownership governance fails closed for every reviewer mutation", async () => { const { parse } = await import("yaml"), { readFile } = await import("node:fs/promises"), matrix = parse(await readFile(new URL("conformance/ownership-matrix.yaml", release), "utf8")), evidence = JSON.parse(await readFile(new URL("conformance/ownership-evidence.json", release), "utf8")), mutate = (value, change) => { const copy = structuredClone(value); change(copy); return copy; }; for (const invalid of [mutate(matrix, (v) => { v.raw_key = "SK-example"; }), mutate(matrix, (v) => { v.authorities.git.Authorization = "BEARER example"; }), mutate(matrix, (v) => { v.authorities.git.label = "Git ApiKey=example"; })]) assert.throws(() => validateOwnershipMatrix(invalid), /unknown|invalid/i); for (const invalid of [mutate(evidence, (v) => { v.raw_key = "SK-example"; }), mutate(evidence, (v) => { v.placements[0].Authorization = "BEARER example"; })]) assert.throws(() => validateOwnershipEvidence(matrix, invalid), /unknown/i); });
test("ownership pins exclusive normative sets and exhaustive evidence", async () => { const { parse } = await import("yaml"), { readFile } = await import("node:fs/promises"), matrix = parse(await readFile(new URL("conformance/ownership-matrix.yaml", release), "utf8")), evidence = JSON.parse(await readFile(new URL("conformance/ownership-evidence.json", release), "utf8")), mutate = (value, change) => { const copy = structuredClone(value); change(copy); return copy; }, duplicate = mutate(matrix, (v) => v.authorities.db.required.push("deployment_secrets")), transfer = mutate(matrix, (v) => { v.authorities.secret_store.required.pop(); v.authorities.db.required.push("deployment_secrets"); }); for (const invalid of [duplicate, transfer]) assert.throws(() => validateOwnershipMatrix(invalid), /normative|exclusive/i); assert.throws(() => assertOwnedContent(matrix, "db", "deployment_secrets"), /out-of-authority/i); assert.throws(() => validateOwnershipEvidence(matrix, mutate(evidence, (v) => v.placements.pop())), /exhaustive/i); });
