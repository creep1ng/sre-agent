import { generateRelease, runConsumer, validateCoverage, validateRelease, writeProjectionFixtures } from "./lib/release-validation.mjs";
const [operation, ...args] = process.argv.slice(2), version = args[0] === "--release" && /^(?:1\.0\.0|1\.1\.0)$/.test(args[1] ?? "") && args.length === 2 ? args[1] : null, consumer = args[0] === "--consumer" && args[1] && args.length === 2, coverage = args[0] === "--check" && args[1] === "coverage" && args.length === 2;
try {
  if (operation === "projection" && version) { const files = await writeProjectionFixtures(version); console.log(`Generated ${files.length} future FastAPI projection fixtures.`); }
  else if (operation === "evidence" && version) { const result = await generateRelease(version); console.log(`Generated deterministic evidence and immutable manifest for ${result.artifacts} artifacts and ${result.results} checks.`); }
  else if (operation === "validate" && version) { const result = await validateRelease(version); console.log(`Validated immutable release ${version}: ${result.artifacts} artifacts and ${result.results} checks.`); }
  else if (operation === "conformance" && coverage) { const result = await validateCoverage(); console.log(`Validated coverage for ${result.consumers.consumers.length} consumers.`); }
  else if (operation === "conformance" && consumer) { const result = await runConsumer(args[1]); console.log(`Validated ${result.consumer} via ${result.action}.`); }
  else { console.error("Usage: node release.mjs projection|evidence|validate --release 1.0.0|1.1.0 | conformance --check coverage | conformance --consumer <id>"); process.exitCode = 2; }
} catch (error) { console.error(`Release validation failed: ${error.message}`); process.exitCode = 1; }
