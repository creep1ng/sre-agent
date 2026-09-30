import { expect, test } from "@playwright/test";

// S1A (issue #21): client seam only. No grants UI exists in this slice, so the
// seven request-shape behaviors are pinned at the fetch seam with a mocked
// transport. Runs offline under the default Playwright config; production
// registration arrives with the S1B read-only surface.
test("grants client seam issues XOR-validated and mutation requests", async ({ page }) => {
  await page.goto("/");
  const evidence = await page.evaluate(async () => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } =
      await import("/public/api/client.js");
    const calls = [];
    const client = createAdministrativeApiClient({
      credentialStore: createMemoryCredentialStore(),
      fetchImplementation: async (url, init = {}) => {
        const headers = new Headers(init.headers ?? {});
        calls.push({
          url: String(url),
          method: init.method ?? "GET",
          idempotencyKey: headers.get("Idempotency-Key"),
          body: init.body === undefined ? null : JSON.parse(init.body),
        });
        return Response.json({ items: [], limit: 100, truncated: false });
      },
    });
    const failures = [];
    for (const args of [{}, { principalId: "a", resourceId: "b" }, { principalId: "" }, { limit: 5 }]) {
      try {
        await client.listGrants(args);
        failures.push(JSON.stringify(args));
      } catch (error) {
        if (!(error instanceof TypeError)) throw error;
      }
    }
    await client.listGrants({ principalId: "admin-human" });
    await client.listGrants({ resourceId: "triage-agent" });
    const grantBody = {
      principal_id: "incident-harness",
      action: "invoke",
      resource: { resource_type: "llm_model", resource_id: "triage-agent" },
    };
    await client.createGrant(grantBody, "test-key-1");
    await client.revokeGrant("grant-1");
    await client.listCatalogResources({ resourceType: "llm_model", ownerId: "triage-agent", status: "active" });
    return { calls, failures, grantBody };
  });

  expect(evidence.failures).toEqual([]);
  expect(evidence.calls).toHaveLength(5);

  const [byPrincipal, byResource, created, revoked, catalog] = evidence.calls;
  expect(byPrincipal.method).toBe("GET");
  expect(byPrincipal.url).toContain("principal_id=admin-human");
  expect(byPrincipal.url).not.toContain("resource_id=");
  expect(byPrincipal.url).toContain("limit=100");
  expect(byResource.method).toBe("GET");
  expect(byResource.url).toContain("resource_id=triage-agent");
  expect(byResource.url).not.toContain("principal_id=");
  expect(byResource.url).toContain("limit=100");
  expect(created.method).toBe("POST");
  expect(created.url).toContain("/api/v1/grants");
  expect(created.idempotencyKey).toBe("test-key-1");
  expect(created.body).toEqual(evidence.grantBody);
  expect(revoked.method).toBe("DELETE");
  expect(revoked.url).toContain("/api/v1/grants/grant-1");
  expect(catalog.method).toBe("GET");
  expect(catalog.url).toContain("resource_type=llm_model");
  expect(catalog.url).toContain("owner_id=triage-agent");
  expect(catalog.url).toContain("status=active");
  expect(catalog.url).not.toContain("visibility=");
  expect(catalog.url).toContain("limit=100");
});
