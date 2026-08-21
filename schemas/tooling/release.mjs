import { generateRelease, runConsumer, validateCoverage, validateRelease, writeProjectionFixtures } from "./lib/release-validation.mjs";
const [operation, ...args] = process.argv.slice(2), release = args[0] === "--release" && args[1] === "1.0.0" && args.length === 2, consumer = args[0] === "--consumer" && args[1] && args.length === 2, coverage = args[0] === "--check" && args[1] === "coverage" && args.length === 2;
try {
  if (operation === "projection" && release) { const files = await writeProjectionFixtures(); console.log(`Generated ${files.length} future FastAPI projection fixtures.`); }
  else if (operation === "evidence" && release) { const result = await generateRelease(); console.log(`Generated deterministic evidence and immutable manifest for ${result.artifacts} artifacts and ${result.results} checks.`); }
  else if (operation === "validate" && release) { const result = await validateRelease(); console.log(`Validated immutable release 1.0.0: ${result.artifacts} artifacts and ${result.results} checks.`); }
  else if (operation === "conformance" && coverage) { const result = await validateCoverage(); console.log(`Validated coverage for ${result.consumers.consumers.length} consumers.`); }
  else if (operation === "conformance" && consumer) { const result = await runConsumer(args[1]); console.log(`Validated ${result.consumer} via ${result.action}.`); }
  else { console.error("Usage: node release.mjs projection|evidence|validate --release 1.0.0 | conformance --check coverage | conformance --consumer <id>"); process.exitCode = 2; }
} catch (error) { console.error(`Release validation failed: ${error.message}`); process.exitCode = 1; }
