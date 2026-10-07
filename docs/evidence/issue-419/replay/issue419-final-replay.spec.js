import fs from "node:fs";
import { expect, test } from "@playwright/test";

const SOURCE_SHA = process.env.SOURCE_SHA;
const VALID_INCIDENT = "inc-issue419-final-browser";
const VALID_RUN = "run_incissue419finalbrowser";
const MISMATCH_INCIDENT = "inc-issue419-final-mismatch";
const MISMATCH_RUN = "run_incissue419finalmismatch";

test("captures real packaged identity and command attribution proof", async ({ page, request }) => {
  expect(SOURCE_SHA).toMatch(/^[0-9a-f]{40}$/);
  const identities = {};
  for (const [label, variable, expected] of [
    ["demo_human", "DEMO_HUMAN_API_KEY", "demo-human"],
    ["admin_human", "ADMIN_HUMAN_API_KEY", "admin-human"],
  ]) {
    const key = process.env[variable];
    expect(key).toBeTruthy();
    const response = await request.get("/api/v1/whoami", {
      headers: { authorization: `Bearer ${key}` },
    });
    const body = await response.json();
    expect(response.status()).toBe(200);
    expect(body).toEqual({ principal_id: expected });
    expect(response.headers()["cache-control"]?.split(",").map((directive) =>
      directive.trim().toLowerCase())).toContain("no-store");
    identities[label] = {
      status: response.status(),
      body,
      cache_control: response.headers()["cache-control"],
    };
  }

  const invalidResponse = await request.get("/api/v1/whoami", {
    headers: { authorization: "Bearer invalid-synthetic-credential" },
  });
  const invalidBody = await invalidResponse.json();
  expect(invalidResponse.status()).toBe(401);
  expect(invalidBody.error).toEqual({
    code: "authentication_failed",
    message: "Authentication failed.",
  });
  expect(invalidBody).not.toHaveProperty("principal_id");

  const openapiResponse = await request.get("/api/openapi.json");
  const openapi = await openapiResponse.json();
  expect(openapi.info["x-sre-agent-build-revision"]).toBe(SOURCE_SHA);
  const whoamiOperation = openapi.paths["/v1/whoami"].get;
  const responseSchema = whoamiOperation.responses["200"].content["application/json"].schema;
  const responseModel = openapi.components.schemas[responseSchema.$ref.split("/").at(-1)];
  expect(whoamiOperation.security).toEqual([{ HTTPBearer: [] }]);
  expect(responseModel.properties).toHaveProperty("principal_id");
  expect(Object.keys(responseModel.properties)).toEqual(["principal_id"]);
  expect(whoamiOperation.responses).toHaveProperty("401");

  const commandPath = `/api/v1/incidents/${VALID_INCIDENT}/runs/${VALID_RUN}/commands`;
  const commandRequestPromise = page.waitForRequest((candidate) =>
    candidate.method() === "POST" && candidate.url().includes(commandPath));
  const commandResponsePromise = page.waitForResponse((candidate) =>
    candidate.request().method() === "POST" && candidate.url().includes(commandPath));

  await page.goto(`/public/incident-ui/review.html?incident_id=${VALID_INCIDENT}&run_id=${VALID_RUN}`);
  await expect(page.locator("#credential-section")).toBeVisible();
  await page.locator("#credential-input").fill(process.env.DEMO_HUMAN_API_KEY);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator('#actions-list button[data-command="approve_mitigation"]')).toBeVisible();
  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await page.locator("#decision-comment").fill("Verified by the authenticated operator.");
  await page.locator("#decision-submit").click();

  const commandRequest = await commandRequestPromise;
  const commandResponse = await commandResponsePromise;
  const requestBody = commandRequest.postDataJSON();
  const responseBody = await commandResponse.json();
  expect(commandResponse.status()).toBe(202);
  expect(requestBody).toMatchObject({
    command: "approve_mitigation",
    actor: "human",
    actor_reference: { reference_version: "1.0.0", principal_id: "demo-human" },
    comment: "Verified by the authenticated operator.",
  });
  await expect(page.locator("#receipt-section")).toBeVisible();
  await expect(page.locator("#receipt-line")).toContainText("approve_mitigation");
  expect(await page.locator("#credential-input").inputValue()).toBe("");
  await page.screenshot({ path: "/evidence/final-review-receipt.png", fullPage: true });

  const mismatchResponse = await request.post(
    `/api/v1/incidents/${MISMATCH_INCIDENT}/runs/${MISMATCH_RUN}/commands`,
    {
      headers: {
        authorization: `Bearer ${process.env.DEMO_HUMAN_API_KEY}`,
        "idempotency-key": "key-issue419-final-mismatch-01",
      },
      data: {
        command: "approve_mitigation",
        actor: "human",
        actor_reference: { reference_version: "1.0.0", principal_id: "admin-human" },
      },
    },
  );
  const mismatchBody = await mismatchResponse.json();
  expect(mismatchResponse.status()).toBe(403);
  expect(mismatchBody.error.code).toBe("actor_attribution_mismatch");

  const evidence = {
    source_sha: SOURCE_SHA,
    evidence_kind: "controlled integration",
    identities,
    invalid_credential: { status: invalidResponse.status(), body: invalidBody },
    whoami_openapi: {
      status: openapiResponse.status(),
      bearer_security: whoamiOperation.security,
      response_properties: Object.keys(responseModel.properties),
      declares_401: Boolean(whoamiOperation.responses["401"]),
    },
    valid_command: {
      status: commandResponse.status(),
      request: {
        command: requestBody.command,
        actor: requestBody.actor,
        actor_reference: requestBody.actor_reference,
        comment: requestBody.comment,
      },
      response: responseBody,
    },
    mismatched_identity: { status: mismatchResponse.status(), body: mismatchBody },
    screenshot: "final-review-receipt.png",
  };
  fs.writeFileSync("/evidence/final-replay.json", `${JSON.stringify(evidence, null, 2)}\n`);
});
