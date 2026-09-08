import { expect, test } from "@playwright/test";

test("production web proxy reaches the candidate API", async ({ request }) => {
  const response = await request.get("/api/v1/principals");

  // An unauthenticated request proves that Nginx reached FastAPI. A bad proxy
  // returns a gateway failure instead, which makes this scenario fail loudly.
  expect(response.status()).toBe(401);
});
