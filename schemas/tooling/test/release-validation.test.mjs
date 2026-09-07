import test from "node:test";
import assert from "node:assert/strict";
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { parse, stringify } from "yaml";
import { assertEveryPublishedRelease, assertImmutableManifest, assertReleaseMetadata, runConsumer, validateCompatibility, validateCoverage, validatePublishedReleases, writeImmutable, writeProjectionFixtures } from "../lib/release-validation.mjs";

test("consumer coverage pins every owner, fixture, command, and non-authority boundary", async () => { const result = await validateCoverage(); assert.equal(result.consumers.consumers.length, 6); assert.equal(result.suite.obligations.length, 6); });
test("coverage rejects YAML command substitution without executing it", async () => {
  const root = await mkdtemp(join(tmpdir(), "release-coverage-")), source = new URL("../../releases/1.0.0/", import.meta.url), suite = parse(await readFile(new URL("conformance/suite.yaml", source), "utf8"));
  await mkdir(join(root, "conformance"), { recursive: true }); await cp(new URL("conformance/consumers.yaml", source), join(root, "conformance/consumers.yaml"));
  for (const obligation of suite.obligations) { const target = join(root, obligation.fixture); await mkdir(dirname(target), { recursive: true }); await writeFile(target, "{}"); }
  suite.obligations[0].command = "node arbitrary-from-yaml.mjs"; await writeFile(join(root, "conformance/suite.yaml"), stringify(suite)); await assert.rejects(validateCoverage(root), /exact owner, fixture, command/);
});
test("coverage pins every obligation to its exact fixture", async () => { const root = await mkdtemp(join(tmpdir(), "release-mapping-")), source = new URL("../../releases/1.0.0/", import.meta.url); try { await cp(source, root, { recursive: true }); const suitePath = join(root, "conformance/suite.yaml"), suite = parse(await readFile(suitePath, "utf8")); suite.obligations[0].fixture = suite.obligations[1].fixture; await writeFile(suitePath, stringify(suite)); await assert.rejects(validateCoverage(root), /exact owner, fixture, command/); } finally { await rm(root, { recursive: true, force: true }); } });
test("consumer command validates the pinned fixture semantics", async () => { const root = await mkdtemp(join(tmpdir(), "release-fixture-")), source = new URL("../../releases/1.0.0/", import.meta.url), issue10 = "fixtures/positive/control.bootstrap.first.positive.v1.0.0.fixture.json", issue11 = "fixtures/positive/shared.principal.human.positive.v1.0.0.fixture.json"; try { await cp(source, root, { recursive: true }); await writeFile(join(root, issue10), "{}"); await assert.rejects(runConsumer("issue-10", root), /lacks target|fixture/i); await writeFile(join(root, issue11), await readFile(new URL(issue10, source))); await assert.rejects(runConsumer("issue-11", root), /immutable manifest hash/); } finally { await rm(root, { recursive: true, force: true }); } });
test("immutable release comparison rejects any hash drift", () => { assert.doesNotThrow(() => assertImmutableManifest({ hash: "a" }, { hash: "a" })); assert.throws(() => assertImmutableManifest({ hash: "a" }, { hash: "b" }), /immutable/); });
test("generation is byte-deterministic and fails closed on drift or corrupt state", async () => { const root = await mkdtemp(join(tmpdir(), "release-generate-")), path = join(root, "evidence.json"), value = { contract_version: "1.0.0", results: ["passed"] }; try { const first = await writeImmutable(path, value), bytes = await readFile(path, "utf8"), second = await writeImmutable(path, structuredClone(value)); assert.equal(first, second); assert.equal(await readFile(path, "utf8"), bytes); await assert.rejects(writeImmutable(path, { ...value, results: ["drift"] }), /immutable/); await writeFile(path, "{"); await assert.rejects(writeImmutable(path, value), /JSON/); } finally { await rm(root, { recursive: true, force: true }); } });
test("validation rejects corrupt baseline, dialect, and API major metadata", async () => { const manifest = parse(await readFile(new URL("../../releases/1.0.0/manifest.yaml", import.meta.url), "utf8")), cases = [["baseline", (value) => value.baseline.previous_release = "0.9.0"], ["dialects", (value) => value.dialects.json_schema = "draft-07"], ["API major", (value) => value.inventory.openapi[0].api_major = 9]]; for (const [label, mutate] of cases) { const value = structuredClone(manifest); mutate(value); assert.throws(() => assertReleaseMetadata(value), new RegExp(label, "i")); } });
test("published projection goldens cannot be regenerated", async () => { await assert.rejects(writeProjectionFixtures(), /immutable/); });
test("minor release preserves every positive 1.0.0 instance", async () => assert.deepEqual(await validateCompatibility(), { previous_release: "1.0.0", current_release: "1.1.0", positive_fixtures: 81, examples: 10, status: "passed" }));
test("release 1.2.0 preserves every positive 1.1.0 instance", async () => assert.deepEqual(await validateCompatibility("1.1.0", "1.2.0"), { previous_release: "1.1.0", current_release: "1.2.0", positive_fixtures: 81, examples: 10, status: "passed" }));
test("release 1.3.0 preserves compatible 1.2.0 instances while retaining nullable historical audit readback", async () => assert.deepEqual(await validateCompatibility("1.2.0", "1.3.0"), { previous_release: "1.2.0", current_release: "1.3.0", positive_fixtures: 80, examples: 9, status: "passed" }));
test("published release validation rejects an omitted release", () => {
  assert.throws(
    () => assertEveryPublishedRelease(["1.0.0", "1.1.0"], ["1.0.0"]),
    /omitted.*1\.1\.0/i,
  );
});
test("published release validation discovers deterministically and rejects invalid metadata", async () => {
  const root = await mkdtemp(join(tmpdir(), "published-releases-"));
  try {
    for (const version of ["1.0.0", "1.1.0"]) {
      const target = join(root, version);
      await cp(new URL(`../../releases/${version}/`, import.meta.url), target, { recursive: true });
    }
    const seen = [];
    const result = await validatePublishedReleases(root, async (version) => {
      seen.push(version);
      return { artifacts: 1, results: 1 };
    });
    assert.deepEqual(seen, ["1.0.0", "1.1.0"]);
    assert.deepEqual(result.releases, ["1.0.0", "1.1.0"]);

    const manifestPath = join(root, "1.1.0/manifest.yaml");
    const manifest = parse(await readFile(manifestPath, "utf8"));
    manifest.contract_version = "1.0.0";
    await writeFile(manifestPath, stringify(manifest));
    await assert.rejects(
      validatePublishedReleases(root, async () => ({ artifacts: 1, results: 1 })),
      /directory.*manifest/i,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
