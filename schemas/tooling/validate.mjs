import { loadFixtureDirectory, loadReleaseDirectory, validateFixtures } from "./lib/schema-validation.mjs";
const args = process.argv.slice(2);
const scoped = args.length === 2 && args[0] === "--scope", directory = new URL("test/fixtures/schema/", import.meta.url);
if (!(args.length === 0 || (args.length === 1 && !args[0].startsWith("-")) || scoped)) {
  console.error("Usage: node validate.mjs [fixture-directory | --scope identity|model-resource|policy|shared]"); process.exitCode = 2;
} else try {
  const { schemas, fixtures } = scoped ? await loadReleaseDirectory(new URL("../releases/1.0.0/", import.meta.url), args[1]) : await loadFixtureDirectory(args[0] ?? directory);
  validateFixtures(schemas, fixtures); console.log(`Validated ${schemas.length} schemas and ${fixtures.length} fixtures.`);
} catch (error) {
  console.error(`Schema validation failed: ${error.message}`); process.exitCode = 1;
}
