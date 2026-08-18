import { loadFixtureDirectory, validateFixtures } from "./lib/schema-validation.mjs";
const args = process.argv.slice(2);
if (args.length !== 1 || args[0].startsWith("-")) {
  console.error("Usage: node validate.mjs <fixture-directory>"); process.exitCode = 2;
} else try {
  const { schemas, fixtures } = await loadFixtureDirectory(args[0]);
  validateFixtures(schemas, fixtures); console.log(`Validated ${schemas.length} schemas and ${fixtures.length} fixtures.`);
} catch (error) {
  console.error(`Schema validation failed: ${error.message}`); process.exitCode = 1;
}
