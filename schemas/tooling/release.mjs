import { fileURLToPath } from "node:url";
import { generateRelease, runConsumer, validateCoverage, validatePublishedReleases, validateRelease, writeProjectionFixtures } from "./lib/release-validation.mjs";

const [operation, ...args] = process.argv.slice(2);
const versions = /^(?:1\.0\.0|1\.1\.0|1\.2\.0|1\.3\.0|1\.4\.0|2\.0\.0|2\.1\.0|2\.2\.0)$/;
const version = args[0] === "--release" && versions.test(args[1] ?? "") && args.length === 2 ? args[1] : null;
const consumerRelease = args[0] === "--consumer" && args[2] === "--release" && versions.test(args[3] ?? "") && args.length === 4 ? args[3] : null;
const consumer = args[0] === "--consumer" && args[1] && (args.length === 2 || consumerRelease);
const coverage = args[0] === "--check" && args[1] === "coverage" && args.length === 2;
try {
  if (operation === "projection" && version) { const files = await writeProjectionFixtures(version); console.log(`Generated ${files.length} future FastAPI projection fixtures.`); }
  else if (operation === "evidence" && version) { const result = await generateRelease(version); console.log(`Generated deterministic evidence and immutable manifest for ${result.artifacts} artifacts and ${result.results} checks.`); }
  else if (operation === "validate" && version) { const result = await validateRelease(version); console.log(`Validated immutable release ${version}: ${result.artifacts} artifacts and ${result.results} checks.`); }
  else if (operation === "validate-all" && args.length === 0) { const result = await validatePublishedReleases(); console.log(`Validated all immutable releases: ${result.releases.join(", ")}.`); }
  else if (operation === "conformance" && coverage) { const result = await validateCoverage(); console.log(`Validated coverage for ${result.consumers.consumers.length} consumers.`); }
  else if (operation === "conformance" && consumer) { const root = consumerRelease ? fileURLToPath(new URL(`../releases/${consumerRelease}/`, import.meta.url)) : undefined, result = await runConsumer(args[1], root); console.log(`Validated ${result.consumer} via ${result.action}.`); }
  else { console.error("Usage: node release.mjs projection|evidence|validate --release 1.0.0|1.1.0|1.2.0|1.3.0|1.4.0|2.0.0|2.1.0|2.2.0 | validate-all | conformance --check coverage | conformance --consumer <id> [--release <version>]"); process.exitCode = 2; }
} catch (error) { console.error(`Release validation failed: ${error.message}`); process.exitCode = 1; }
