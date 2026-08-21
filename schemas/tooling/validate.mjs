import { loadFixtureDirectory, loadReleaseDirectory, validateExamples, validateFixtures } from "./lib/schema-validation.mjs";
import { validateGovernance } from "./lib/governance-validation.mjs";
const args = process.argv.slice(2);
const scoped = args.length === 2 && args[0] === "--scope", directory = new URL("test/fixtures/schema/", import.meta.url);
if (!(args.length === 0 || (args.length === 1 && !args[0].startsWith("-")) || scoped)) {
  console.error("Usage: node validate.mjs [fixture-directory | --scope identity|model-resource|policy|shared|audit|redaction-success|redaction-failure|governance|idempotency|credentials|bootstrap|control|responses|responses-boundary|responses-errors]"); process.exitCode = 2;
} else try {
  if (scoped && args[1] === "governance") { const result = await validateGovernance(new URL("../releases/1.0.0/", import.meta.url), new URL("../adrs/", import.meta.url)); console.log(`Validated ${result.authorities} authorities and ${result.placements} ownership placements.`); }
  else { const { schemas, fixtures, examples = [] } = scoped ? await loadReleaseDirectory(new URL("../releases/1.0.0/", import.meta.url), args[1]) : await loadFixtureDirectory(args[0] ?? directory); if (!fixtures.length && !examples.length) throw new Error("At least one fixture or example is required"); if (fixtures.length) validateFixtures(schemas, fixtures); if (examples.length) validateExamples(schemas, examples); console.log(examples.length ? `Validated ${schemas.length} schemas, ${fixtures.length} fixtures, and ${examples.length} examples.` : `Validated ${schemas.length} schemas and ${fixtures.length} fixtures.`); }
} catch (error) {
  console.error(`Schema validation failed: ${error.message}`); process.exitCode = 1;
}
