import { expect, test } from "@playwright/test";

// S1 (issue #143): consumption client seam only. No audit UI (#25) is built in
// this slice, so the XOR selector shape is pinned at the fetch seam with a
// mocked transport. Runs offline under the default Playwright config;
// production registration arrives with this same file.
test("consumption client seam requires exactly one selector and passes responses through", async ({
  page,
}) => {
  await page.goto("/");
  const evidence = await page.evaluate(async () => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } =
      await import("/public/api/client.js");
    const calls = [];
    const responseBody = {
      filter: { month: "2026-09" },
      request_count: 1,
      incident_runs: 1,
      months: [{ month: "2026-09", request_count: 1 }],
      totals: {
        input_tokens: 11,
        output_tokens: 7,
        total_tokens: 18,
        cost: {
          amount: "0.0012300",
          currency: "USD",
          nature: "billed",
          precision: "exact",
          price_versions: ["openrouter:2026-09-10T14:00:00Z"],
        },
      },
      coverage: { status: "complete", known: 1, incomplete: 0, unknown: 0 },
    };
    const client = createAdministrativeApiClient({
      credentialStore: createMemoryCredentialStore(),
      fetchImplementation: async (url, init = {}) => {
        calls.push({ url: String(url), method: init.method ?? "GET" });
        return Response.json(responseBody);
      },
    });
    const failures = [];
    for (const args of [
      {},
      { requestId: "a", incidentId: "b" },
      { requestId: "a", month: "2026-09" },
      { incidentId: "b", month: "2026-09" },
      { requestId: "a", incidentId: "b", month: "2026-09" },
      { requestId: "" },
      { incidentId: "" },
      { month: "" },
      { requestId: "", incidentId: "", month: "" },
    ]) {
      try {
        await client.readUsageConsumption(args);
        failures.push(JSON.stringify(args));
      } catch (error) {
        if (!(error instanceof TypeError)) throw error;
      }
    }
    const requestId = "123e4567-e89b-12d3-a456-426614174000";
    const byRequest = await client.readUsageConsumption({ requestId });
    const byIncident = await client.readUsageConsumption({ incidentId: "incident-a" });
    const byMonth = await client.readUsageConsumption({ month: "2026-09" });
    return { calls, failures, byRequest, byIncident, byMonth, responseBody, requestId };
  });

  expect(evidence.failures).toEqual([]);
  expect(evidence.calls).toHaveLength(3);

  const [byRequest, byIncident, byMonth] = evidence.calls;
  for (const call of evidence.calls) {
    expect(call.method).toBe("GET");
    expect(call.url).toContain("/api/v1/usage/consumption?");
  }
  const names = (url) => [...new URL(url, "http://localhost").searchParams.keys()].sort();
  const valueOf = (url, name) => new URL(url, "http://localhost").searchParams.get(name);
  expect(names(byRequest.url)).toEqual(["request_id"]);
  expect(valueOf(byRequest.url, "request_id")).toBe(evidence.requestId);
  expect(names(byIncident.url)).toEqual(["incident_id"]);
  expect(valueOf(byIncident.url, "incident_id")).toBe("incident-a");
  expect(names(byMonth.url)).toEqual(["month"]);
  expect(valueOf(byMonth.url, "month")).toBe("2026-09");

  for (const call of evidence.calls) {
    for (const forbidden of [
      "from=",
      "to=",
      "cursor",
      "page=",
      "offset",
      "continuation_token",
      "prompt",
      "output",
      "api_key",
      "limit=",
    ]) {
      expect(call.url).not.toContain(forbidden);
    }
  }

  expect(evidence.byRequest).toEqual(evidence.responseBody);
  expect(evidence.byIncident).toEqual(evidence.responseBody);
  expect(evidence.byMonth).toEqual(evidence.responseBody);
});
