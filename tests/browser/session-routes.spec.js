import { expect, route, test } from "./support/session-routes.mjs";

// The shared session's worker sends the API requests (ADR-009). page.route never sees them; the
// routes of support/session-routes.mjs do, so specs that cut or fake API responses keep working.
test("routes reach the session worker, which page.route never sees", async ({ page }) => {
  const seen = [];
  await page.route("**/api/v1/whoami", (request) => (seen.push("page.route"), request.abort()));
  route(page, "**/api/v1/whoami", (request) => {
    seen.push(`session route ${request.request().method()}`);
    return request.fulfill({ status: 200, contentType: "application/json", body: '{"principal_id":"routed"}' });
  });
  await page.goto("/index.html");
  const principal = await page.evaluate(async () => {
    const { connectSharedSession } = await import("/public/api/client.js");
    const session = connectSharedSession();
    const active = new Promise((resolve) => session.subscribe((s) => s.phase === "active" && resolve(s.principalId)));
    session.setCredential("not-a-key");
    return active;
  });
  expect(principal).toBe("routed");
  expect(seen).toEqual(["session route GET"]);
});
