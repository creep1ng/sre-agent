import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { parse } from "yaml";
import { validateRelease } from "../lib/release-validation.mjs";
import { createSchemaRegistry, loadReleaseDirectory, validateFixtures } from "../lib/schema-validation.mjs";

const releases = new URL("../../releases/", import.meta.url);
const publication = new URL("2.5.0/", releases);

test("2.5.0 publishes usage read as a self-contained additive contract", async () => {
  const manifest = parse(await readFile(new URL("manifest.yaml", publication), "utf8"));
  const api = parse(await readFile(new URL("openapi/control-plane.yaml", publication), "utf8"));
  const audit = JSON.parse(
    await readFile(new URL("json-schema/domain/audit-event.schema.json", publication), "utf8"),
  );
  const usage = JSON.parse(
    await readFile(new URL("json-schema/http/usage-read.schema.json", publication), "utf8"),
  );

  assert.deepEqual(manifest.baseline, {
    previous_release: "2.4.0",
    previous_major: "2.0.0",
    compatibility: "additive",
  });
  assert.equal(api.info.version, "2.5.0");
  assert.ok(api.paths["/v1/usage/consumption"]?.get);
  assert.equal(
    api.paths["/v1/usage/consumption"].get.responses["200"].content["application/json"].schema.$ref,
    "urn:sre-agent:schema:usage-read:2.5.0",
  );
  assert.ok(audit.properties.operation.enum.includes("usage.read"));
  assert.equal(usage.$id, "urn:sre-agent:schema:usage-read:2.5.0");
  assert.ok(manifest.inventory.openapi.some(({ path }) => path === "releases/2.5.0/openapi/control-plane.yaml"));
  assert.ok(manifest.inventory.schemas.some(({ id }) => id === "urn:sre-agent:schema:usage-read:2.5.0"));
  assert.ok(manifest.inventory.fixtures.some(({ path }) => path.includes("usage.read")));
  assert.ok(manifest.inventory.conformance.some(({ path }) => path.endsWith("conformance/consumers.yaml")));
  assert.ok(await validateRelease("2.5.0"));
});

test("usage.read audit conformance captures each persisted runtime outcome and context", async () => {
  const release = await loadReleaseDirectory(publication, "all");
  const outcomes = release.fixtures.filter(
    ({ group }) => group === "usage-read-audit-outcomes",
  );
  const schema = release.schemas.find(
    ({ $id }) => $id === "urn:sre-agent:schema:audit-event:2.5.0",
  );
  const validate = createSchemaRegistry(release.schemas).getSchema(schema.$id);
  const byStatus = Object.fromEntries(
    outcomes.map(({ data }) => [data.response_status, structuredClone(data)]),
  );
  assert.deepEqual(Object.keys(byStatus).map(Number).sort((a, b) => a - b), [200, 401, 403, 413, 422, 503]);
  const deniedOutcomes = outcomes
    .filter(({ data }) => data.response_status === 403)
    .map(({ data }) => data);
  assert.deepEqual(
    deniedOutcomes.map(({ authorization_denial_cause }) => authorization_denial_cause).sort(),
    ["grant_not_applicable", "principal_inactive", "resource_inactive", "resource_missing"],
  );
  assert.deepEqual(
    Object.fromEntries(deniedOutcomes.map(({ authorization_denial_cause, identity }) => [
      authorization_denial_cause,
      identity.principal_status,
    ])),
    {
      grant_not_applicable: "active",
      principal_inactive: "inactive",
      resource_inactive: "active",
      resource_missing: "active",
    },
  );
  const runtimeOutcomesRejected = outcomes
    .filter(({ data }) => !validate(data))
    .map(({ data }) => data.response_status);

  const expectedAction = structuredClone(byStatus[401]);
  expectedAction.action = "invoke";
  const unauthenticatedWithPrincipal = structuredClone(byStatus[401]);
  const authenticated = structuredClone(byStatus[200]);
  unauthenticatedWithPrincipal.identity = {
    principal_ref: authenticated.identity.principal_ref,
    principal_kind: authenticated.identity.principal_kind,
    principal_status: authenticated.identity.principal_status,
    credential_ref: authenticated.identity.credential_ref,
  };
  const deniedWithoutContext = structuredClone(byStatus[403]);
  for (const field of ["identity", "resource", "policy_decision", "authorization_denial_cause"]) {
    delete deniedWithoutContext[field];
  }
  const inactivePrincipalWithActiveContext = structuredClone(
    deniedOutcomes.find(({ authorization_denial_cause }) => authorization_denial_cause === "principal_inactive"),
  );
  inactivePrincipalWithActiveContext.identity.principal_status = "active";
  const resourceCauseWithInactiveContext = structuredClone(
    deniedOutcomes.find(({ authorization_denial_cause }) => authorization_denial_cause === "resource_inactive"),
  );
  resourceCauseWithInactiveContext.identity.principal_status = "inactive";
  const preAuthValidationWithContext = structuredClone(byStatus[422]);
  preAuthValidationWithContext.identity = authenticated.identity;
  preAuthValidationWithContext.resource = authenticated.resource;
  preAuthValidationWithContext.policy_decision = authenticated.policy_decision;
  const overflowWithoutContext = structuredClone(byStatus[413]);
  const storageFailureWithoutContext = structuredClone(byStatus[503]);
  for (const event of [overflowWithoutContext, storageFailureWithoutContext]) {
    for (const field of ["identity", "resource", "policy_decision"]) delete event[field];
  }
  const unrecordedAuditUnavailable = structuredClone(storageFailureWithoutContext);
  unrecordedAuditUnavailable.reason_code = "audit_unavailable";
  unrecordedAuditUnavailable.authoritative_acceptance = "rejected";
  unrecordedAuditUnavailable.ordinary_result = "suppressed";

  const invalidCases = [
    ["usage.read uses admin.read even before authentication", expectedAction],
    ["unauthenticated 401 has no principal context", unauthenticatedWithPrincipal],
    ["403 denial has authenticated deny context", deniedWithoutContext],
    ["principal_inactive requires an inactive principal", inactivePrincipalWithActiveContext],
    ["resource_inactive requires an active principal", resourceCauseWithInactiveContext],
    ["422 validation does not leak auth context", preAuthValidationWithContext],
    ["413 overflow retains auth context", overflowWithoutContext],
    ["audited storage 503 retains auth context", storageFailureWithoutContext],
    ["audit_unavailable response is not a persisted usage event", unrecordedAuditUnavailable],
  ];
  const invalidVariantsAccepted = invalidCases
    .filter(([, data]) => validate(data))
    .map(([name]) => name);
  assert.deepEqual(
    { runtimeOutcomesRejected, invalidVariantsAccepted },
    { runtimeOutcomesRejected: [], invalidVariantsAccepted: [] },
    "usage.read positive and negative outcomes must have exact action/context constraints",
  );
  assert.doesNotThrow(() => validateFixtures(release.schemas, outcomes));
  for (const [name, invalid] of invalidCases) {
    assert.equal(validate(invalid), false, name);
  }

  const unrelated = release.fixtures.find(
    ({ status, data }) => status === "positive" && data.operation === "responses.create",
  );
  assert.ok(unrelated);
  assert.equal(validate(unrelated.data), true, "generic response audit contract remains valid");
});
