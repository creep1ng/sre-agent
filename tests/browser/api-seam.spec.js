import { expect, test } from "@playwright/test";

const credentials = {
  admin: process.env.ADMIN_HUMAN_API_KEY,
  restricted: process.env.RESTRICTED_HARNESS_API_KEY,
  demo: process.env.DEMO_HUMAN_API_KEY,
};
const productionTopology = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";

async function openHarness(page) {
  const response = await page.goto("/health");
  expect(response?.status()).toBe(200);
  await expect(page.locator("body")).toHaveText("ok");
}

test("browser client consumes the real administrative API without fixture fallback", async ({
  page,
}) => {
  expect(Object.values(credentials).every(Boolean)).toBe(true);
  await openHarness(page);

  const evidence = await page.evaluate(async (keys) => {
    const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } =
      await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    const client = createAdministrativeApiClient({ credentialStore: store });

    async function captured(operation) {
      try {
        return { value: await operation() };
      } catch (error) {
        if (!(error instanceof ApiClientError)) throw error;
        return {
          error: {
            kind: error.kind,
            status: error.status,
            code: error.code,
            retryable: error.retryable,
          },
        };
      }
    }

    store.set(keys.admin);
    const valid = await captured(() => client.listPrincipals());
    store.clear();
    const absent = await captured(() => client.listPrincipals());
    store.set("sre_invalid_0123456789abcdefghijklmnop");
    const invalid = await captured(() => client.listPrincipals());
    store.set(keys.demo);
    const demo = await captured(() => client.listPrincipals());

    store.set(keys.restricted);
    const denied = await captured(() =>
      client.createPrincipal(
        { principal_id: "browser-denied", kind: "human", display_name: "Denied" },
        "browser-denied-key",
      ),
    );

    store.set(keys.admin);
    const deniedDidNotAdvance = await captured(() => client.getPrincipal("browser-denied"));
    const missing = await captured(() => client.getPrincipal("browser-missing"));
    const created = await captured(() =>
      client.createPrincipal(
        { principal_id: "browser-conflict-a", kind: "human", display_name: "First" },
        "browser-conflict-key",
      ),
    );
    const conflict = await captured(() =>
      client.createPrincipal(
        { principal_id: "browser-conflict-b", kind: "human", display_name: "Second" },
        "browser-conflict-key",
      ),
    );
    const conflictDidNotAdvance = await captured(() => client.getPrincipal("browser-conflict-b"));

    return {
      valid,
      absent,
      invalid,
      demo,
      denied,
      deniedDidNotAdvance,
      missing,
      created,
      conflict,
      conflictDidNotAdvance,
      storageValues: [
        ...Object.values(localStorage),
        ...Object.values(sessionStorage),
      ],
    };
  }, credentials);

  expect(evidence.valid.value.items).toEqual(
    expect.arrayContaining([expect.objectContaining({ principal_id: "admin-human" })]),
  );
  for (const result of [evidence.absent, evidence.invalid]) {
    expect(result.error).toMatchObject({
      kind: "authentication",
      status: 401,
      code: "authentication_failed",
    });
  }
  expect(evidence.demo.error).toMatchObject(
    productionTopology
      ? { kind: "not_found", status: 404, code: "resource_not_found" }
      : { kind: "authentication", status: 401, code: "authentication_failed" },
  );
  expect(evidence.denied.error).toMatchObject({ kind: "authorization", status: 403 });
  expect(evidence.deniedDidNotAdvance.error).toMatchObject({ kind: "not_found", status: 404 });
  expect(evidence.missing.error).toMatchObject({ kind: "not_found", status: 404 });
  expect(evidence.created.value.principal_id).toBe("browser-conflict-a");
  expect(evidence.conflict.error).toMatchObject({ kind: "conflict", status: 409 });
  expect(evidence.conflictDidNotAdvance.error).toMatchObject({ kind: "not_found", status: 404 });
  await page.context().setOffline(true);
  const network = await page.evaluate(async () => {
    const { ApiClientError, createAdministrativeApiClient } = await import(
      "/public/api/client.js"
    );
    try {
      await createAdministrativeApiClient().listPrincipals();
      return null;
    } catch (error) {
      if (!(error instanceof ApiClientError)) throw error;
      return {
        kind: error.kind,
        status: error.status,
        code: error.code,
        retryable: error.retryable,
      };
    }
  });
  expect(network).toEqual({
    kind: "network",
    status: null,
    code: null,
    retryable: true,
  });
  expect(evidence.storageValues).not.toEqual(expect.arrayContaining(Object.values(credentials)));
});

test("client rejects cross-origin-normalized bases and invalid success bodies", async ({ page }) => {
  await openHarness(page);

  const evidence = await page.evaluate(async () => {
    const { ApiClientError, apiBaseUrlFrom, createAdministrativeApiClient } = await import(
      "/public/api/client.js"
    );
    const rejectedBases = ["//evil.example/api", "/\\evil.example/api", "/api?redirect=evil"];
    const baseResults = rejectedBases.map((apiBaseUrl) => {
      try {
        apiBaseUrlFrom({
          __SRE_AGENT_CONFIG__: { apiBaseUrl },
          location: window.location,
        });
        return false;
      } catch (error) {
        return error instanceof TypeError;
      }
    });

    async function failureFor(fetchImplementation) {
      try {
        await createAdministrativeApiClient({ fetchImplementation }).listPrincipals();
        return null;
      } catch (error) {
        if (!(error instanceof ApiClientError)) throw error;
        return {
          kind: error.kind,
          status: error.status,
          retryable: error.retryable,
        };
      }
    }

    const malformed = await failureFor(async () => new Response("not-json", { status: 200 }));
    const truncated = await failureFor(
      async () =>
        new Response(
          new ReadableStream({
            start(controller) {
              controller.error(new TypeError("truncated body"));
            },
          }),
          { status: 200 },
        ),
    );
    return { baseResults, malformed, truncated };
  });

  expect(evidence.baseResults).toEqual([true, true, true]);
  for (const failure of [evidence.malformed, evidence.truncated]) {
    expect(failure).toEqual({ kind: "invalid_response", status: 200, retryable: true });
  }
});

test("same-origin proxy rejects cross-site browser requests and ambient cookies", async ({
  request,
}) => {
  if (!productionTopology) {
    const forwarded = await request.get("/api/__test/forwarded-headers", {
      headers: {
        Cookie: "ambient-session=must-not-cross-the-seam",
        Origin: "http://127.0.0.1:4173",
      },
    });
    expect(forwarded.status()).toBe(200);
    expect(await forwarded.json()).toEqual({ cookie: false, origin: false });
  }

  const response = await request.get("/api/v1/principals", {
    headers: {
      Authorization: `Bearer ${credentials.admin}`,
      Cookie: "ambient-session=must-not-cross-the-seam",
      "Sec-Fetch-Site": "cross-site",
    },
  });

  expect(response.status()).toBe(403);
  expect(response.headers()).not.toHaveProperty("access-control-allow-origin");
});
