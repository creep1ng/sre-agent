import { expect, test } from "@playwright/test";

const WEB = process.env.E2E_BASE_URL ?? "http://web";
const API = process.env.E2E_API_BASE_URL ?? "http://api:8000";

function requiredKey(name) {
  const value = process.env[name];
  if (!value) throw new Error(`requires ${name} from the isolated triage fixture`);
  return value;
}

function alertId(label) {
  return `al-t23-16-${label}-${Date.now().toString(36)}`;
}

async function connect(page, id, key) {
  await page.goto(`${WEB}/public/admin/triage.html?alert_id=${encodeURIComponent(id)}`);
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
}

async function context(request, id, key) {
  return request.get(`${API}/v1/alerts/${encodeURIComponent(id)}/triage/context`, {
    headers: { Authorization: `Bearer ${key}` },
  });
}

test("human and read-only projections control the operation options for an unrecorded alert", async ({ page, request }) => {
  const operator = requiredKey("E2E_TRIAGE_API_KEY");
  const reader = requiredKey("E2E_TRIAGE_READONLY_API_KEY");
  const id = alertId("projection");
  const full = await context(request, id, operator);
  expect(full.status()).toBe(200);
  expect(await full.json()).toEqual({
    alert_id: id,
    triage_state: null,
    allowed_actions: ["open_triage", "triage_dismiss", "triage_link", "triage_declare"],
  });
  await connect(page, id, operator);
  await expect(page.locator("#result-summary")).toHaveText("No recorded decision for this alert.");
  for (const operation of ["open_triage", "triage_dismiss", "triage_link", "triage_declare"])
    await expect(page.locator(`#command-operation option[value='${operation}']`)).toBeEnabled();
  await expect(page.locator("#submit-button")).toBeEnabled();

  const readOnly = await context(request, id, reader);
  expect(readOnly.status()).toBe(200);
  expect(await readOnly.json()).toEqual({ alert_id: id, triage_state: null, allowed_actions: [] });
  await connect(page, id, reader);
  await expect(page.locator("#result-summary")).toHaveText("No recorded decision for this alert.");
  for (const operation of ["open_triage", "triage_dismiss", "triage_link", "triage_declare"])
    await expect(page.locator(`#command-operation option[value='${operation}']`)).toBeDisabled();
  await expect(page.locator("#submit-button")).toBeDisabled();
  await expect(page.locator("#page-error")).toBeHidden();
});
