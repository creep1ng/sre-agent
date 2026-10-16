import { expect } from "@playwright/test";

// The console holds one session per tab (#487): views read through it and no longer render a
// credential form of their own. Mocked specs answer whoami; production specs use the real one.
export async function answerWhoAmI(page, principalId = "demo-human") {
  await page.route("**/api/v1/whoami", (route) =>
    route.fulfill({ json: { principal_id: principalId }, headers: { "Cache-Control": "no-store" } }),
  );
}

export async function connectConsole(page, key = "sre_demo_token_demo_0001") {
  if (await page.locator("#console-session").isHidden()) await page.locator("#session-chip").click();
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
  await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "active");
}

export async function logoutConsole(page) {
  await page.locator("#session-chip").click();
  await page.locator("#disconnect-button").click();
  await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "anonymous");
}

// Changing identity while a session is active goes through the session menu, never a second form.
export async function switchConsoleCredential(page, key) {
  await page.locator("#session-chip").click();
  await page.locator("#change-credential").click();
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
  await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "active");
}
