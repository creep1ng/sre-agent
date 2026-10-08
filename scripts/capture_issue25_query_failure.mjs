// Connected browser proof that a post-authentication list-query failure clears stale data.
import { chromium, expect } from '@playwright/test';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const evidence = JSON.parse(readFileSync('/evidence/issue-25-audit-http.json', 'utf8'));
const entry = evidence.cases.find((item) => item.name === 'allow');
const adminKey = process.env.ADMIN_HUMAN_API_KEY;
if (!entry?.request_id || !adminKey) throw new Error('Missing controlled evidence or session');

const markerPrefixes = ['ISSUE25_PRIVATE_PROMPT_', 'ISSUE25_PRIVATE_OUTPUT_'];
const safeCheck = async (page) => {
  const body = await page.locator('body').innerText();
  const storage = await page.evaluate(() => JSON.stringify({
    local: Object.keys(localStorage).map((key) => [key, localStorage.getItem(key)]),
    session: Object.keys(sessionStorage).map((key) => [key, sessionStorage.getItem(key)]),
  }));
  for (const marker of [...markerPrefixes, adminKey, process.env.RESTRICTED_HARNESS_API_KEY]) {
    if (marker && (body.includes(marker) || storage.includes(marker) || page.url().includes(marker))) {
      throw new Error('Sensitive marker visible or stored');
    }
  }
};

const browser = await chromium.launch();
const startedAt = new Date().toISOString();
let stage = 'initial';
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const listStatuses = [];
  page.on('response', (response) => {
    if (new URL(response.url()).pathname === '/api/v1/audit-events') listStatuses.push(response.status());
  });
  await page.goto('http://web/public/admin/audit-events.html');
  await page.fill('#filter-request-id', entry.request_id);
  await page.fill('#api-key', adminKey);
  await page.click('#connect-button');
  await expect(page.locator('[data-event-row]')).toHaveCount(1);
  await page.click('[data-expand-event]');
  await expect(page.locator('[data-event-detail]')).toBeVisible();
  await safeCheck(page);

  const uiSource = await page.request.get('http://web/public/admin/audit-events.js');
  if (!uiSource.ok()) throw new Error('Could not identify the served UI source');
  const uiSha256 = createHash('sha256').update(await uiSource.body()).digest('hex');
  writeFileSync('/evidence/query-fault-ready.json', JSON.stringify({
    evidence_kind: 'controlled integration',
    started_at: startedAt,
    ui_sha256: uiSha256,
    precondition: { connected: true, rows: 1, expanded_details: 1, sensitive_absent: true },
  }) + '\n');

  stage = 'waiting_for_controlled_query_failure';
  const deadline = Date.now() + 90_000;
  while (!existsSync('/evidence/query-fault-active') && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  if (!existsSync('/evidence/query-fault-active')) throw new Error('Controlled fault activation timed out');

  stage = 'checking_failed_apply';
  const failedList = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/v1/audit-events' && response.status() === 503;
  }, { timeout: 20_000 });
  await page.click('#apply-button');
  const response = await failedList;
  await expect(page.locator('#page-error-title')).toHaveText('Service unavailable');
  await expect(page.locator('#page-error')).toBeVisible();
  await expect(page.locator('[data-event-row]')).toHaveCount(0);
  await expect(page.locator('[data-event-detail]')).toHaveCount(0);
  await expect(page.locator('#audit-events-page')).toHaveAttribute('data-state', 'error');
  await safeCheck(page);

  await page.screenshot({ path: '/evidence/issue-25-query-failure.png', fullPage: true });
  writeFileSync('/evidence/issue-25-query-failure.json', JSON.stringify({
    evidence_kind: 'controlled integration',
    started_at: startedAt,
    completed_at: new Date().toISOString(),
    ui_sha256: uiSha256,
    list_statuses: listStatuses,
    failed_apply_status: response.status(),
    error_title: await page.locator('#page-error-title').innerText(),
    visible_error: true,
    stale_rows: await page.locator('[data-event-row]').count(),
    stale_details: await page.locator('[data-event-detail]').count(),
    sensitive_absent_before_and_after_apply: true,
  }) + '\n');
  console.log('Authenticated query failure cleared rows/details and retained a visible error.');
} catch {
  writeFileSync('/evidence/issue-25-query-failure-failed.json', JSON.stringify({
    evidence_kind: 'controlled integration', stage, failed: true,
    note: 'Capture assertion failed; inspect the controlled run without publishing raw output.',
  }) + '\n');
  throw new Error('Issue 25 query-failure browser evidence did not verify');
} finally {
  if (existsSync('/evidence/query-fault-active')) writeFileSync('/evidence/query-fault-done', 'done\n');
  await browser.close();
}
