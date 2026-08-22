import { readFile, rm } from "node:fs/promises";
import { basename, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { assertOpenapiEquivalent, combineOpenapi } from "./lib/openapi-normalize.mjs";
import { preflightOpenapi, readContractFile, runOpenapi, runReleaseOpenapi } from "./lib/openapi-validation.mjs";
const tooling = fileURLToPath(new URL("./", import.meta.url)), temporary = (name) => join(tooling, ".tmp", name);
export async function assertFutureFastapi(root = new URL("../releases/1.0.0/", import.meta.url)) {
  const version = basename(fileURLToPath(root)), outputs = [temporary(`future-control-${version}.yaml`), temporary(`future-responses-${version}.yaml`)];
  try {
    await Promise.all([runReleaseOpenapi("control-plane", outputs[0], version), runReleaseOpenapi("responses", outputs[1], version)]);
    const canonical = combineOpenapi(...await Promise.all(outputs.map(readContractFile))), fixture = (kind, status) => new URL(`fixtures/${status}/future-fastapi.${kind}.projection.json`, root);
    assertOpenapiEquivalent(canonical, JSON.parse(await readFile(fixture("match", "positive"), "utf8")));
    for (const kind of ["missing", "extra"]) { const value = JSON.parse(await readFile(fixture(kind, "negative"), "utf8")); try { assertOpenapiEquivalent(canonical, value); throw new Error(`${kind} projection validated unexpectedly`); } catch (error) { if (!new RegExp(`OpenAPI semantic diff: ${kind}`).test(error.message)) throw error; } }
  } finally { await Promise.all(outputs.map((path) => rm(path, { force: true }))); }
}
if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) { const args = process.argv.slice(2); if (!args.length) args.push("test/fixtures/openapi/canonical.yaml", "test/fixtures/openapi/projection.json"); const fixtureMode = args.length === 2 && args[0] === "--projection-fixture"; if (fixtureMode) try { if (args[1] !== "future-fastapi") throw new Error(`Unknown projection fixture: ${args[1]}`); await assertFutureFastapi(); console.log("Future FastAPI match/missing/extra semantic diff passed."); } catch (error) { console.error(error.message); process.exitCode = 1; }
  else { const [canonical, projection, ...extra] = args, outputs = [resolve(".tmp/diff-canonical.yaml"), resolve(".tmp/diff-projection.yaml")]; if (!canonical || !projection || extra.length) { console.error("Usage: node diff-openapi.mjs <canonical> <projection> | --projection-fixture future-fastapi"); process.exitCode = 2; } else try { await Promise.all([canonical, projection].map((path) => preflightOpenapi(path))); await runOpenapi("bundle", canonical, outputs[0]); await runOpenapi("bundle", projection, outputs[1]); assertOpenapiEquivalent(await readContractFile(outputs[0]), await readContractFile(outputs[1])); console.log("OpenAPI semantic diff passed."); } catch (error) { console.error(error.message); process.exitCode = 1; } finally { await Promise.all(outputs.map((path) => rm(path, { force: true }))); } } }
