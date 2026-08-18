import { rm } from "node:fs/promises";
import { resolve } from "node:path";
import { assertOpenapiEquivalent } from "./lib/openapi-normalize.mjs";
import { preflightOpenapi, readContractFile, runOpenapi } from "./lib/openapi-validation.mjs";
const [canonical, projection, ...extra] = process.argv.slice(2), outputs = [resolve(".tmp/diff-canonical.yaml"), resolve(".tmp/diff-projection.yaml")];
if (!canonical || !projection || extra.length) { console.error("Usage: node diff-openapi.mjs <canonical> <projection>"); process.exitCode = 2; }
else try { await Promise.all([canonical, projection].map((path) => preflightOpenapi(path))); await runOpenapi("bundle", canonical, outputs[0]); await runOpenapi("bundle", projection, outputs[1]); assertOpenapiEquivalent(await readContractFile(outputs[0]), await readContractFile(outputs[1])); console.log("OpenAPI semantic diff passed."); } catch (error) { console.error(error.message); process.exitCode = 1; } finally { await Promise.all(outputs.map((path) => rm(path, { force: true }))); }
