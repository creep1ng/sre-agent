// Connected browser proof; reads existing gateway-produced PostgreSQL events.
import { chromium, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const evidence = JSON.parse(readFileSync('/evidence/issue-25-audit-http.json', 'utf8'));
const browser = await chromium.launch();
const proofs = [];
const uiHash = createHash('sha256').update(readFileSync('/candidate/audit-events.js')).digest('hex');
try {
  for (const name of ['allow', 'deny']) {
    const entry = evidence.cases.find((item) => item.name === name);
    const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
    const page = await context.newPage();
    const apiRequests = [];
    const listStatuses = [];
    page.on('response', (response) => {
      if (new URL(response.url()).pathname === '/api/v1/audit-events') listStatuses.push(response.status());
    });
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname === '/api/v1/audit-events') apiRequests.push(url.searchParams.get('request_id'));
    });
    await page.goto('http://web/public/admin/audit-events.html');
    const servedUi = await page.request.get('http://web/public/admin/audit-events.js');
    expect(createHash('sha256').update(await servedUi.body()).digest('hex')).toBe(uiHash);
    await page.fill('#filter-request-id', entry.request_id);
    await page.fill('#api-key', process.env.ADMIN_HUMAN_API_KEY);
    await page.click('#connect-button');
    await expect(page.locator('[data-event-row]')).toHaveCount(1);
    await page.click('[data-expand-event]');
    const link = page.getByRole('link', { name: 'View correlated events' });
    const href = `/public/admin/audit-events.html?request_id=${entry.request_id}`;
    await expect(link).toHaveAttribute('href', href);
    await expect(page.locator('[data-event-detail]')).toContainText(String(entry.producer_status));
    await link.click();
    await expect(page).toHaveURL(`http://web${href}`);
    await expect(page.locator('#filter-request-id')).toHaveValue(entry.request_id);
    await expect(page.locator('#api-key')).toHaveValue('');
    await expect(page.locator('[data-event-row]')).toHaveCount(0);
    await expect(page.locator('#audit-events-page')).toHaveAttribute('data-state', 'idle');
    expect(apiRequests).toEqual([entry.request_id]);
    // The link does not carry administrative authority to a restricted identity.
    await page.fill('#api-key', process.env.RESTRICTED_HARNESS_API_KEY);
    await page.click('#connect-button');
    await expect(page.locator('#page-error')).toBeVisible();
    await expect(page.locator('#page-error-title')).toHaveText('Access unavailable');
    await expect(page.locator('[data-event-row]')).toHaveCount(0);
    await page.fill('#api-key', process.env.ADMIN_HUMAN_API_KEY);
    await page.click('#connect-button');
    await expect(page.locator('[data-event-row]')).toHaveCount(1);
    await page.click('[data-expand-event]');
    const detail = page.locator('[data-event-detail]');
    await expect(detail).toContainText(entry.sql.event_id);
    await expect(detail).toContainText(String(entry.producer_status));
    const body = await page.locator('body').innerText();
    for (const value of [process.env.ADMIN_HUMAN_API_KEY, process.env.RESTRICTED_HARNESS_API_KEY,
      'ISSUE25_PRIVATE_PROMPT_', 'ISSUE25_PRIVATE_OUTPUT_']) {
      if (!value || body.includes(value) || page.url().includes(value)) throw new Error('Unsafe proof');
    }
    expect(listStatuses).toEqual([200, 403, 200]);
    await page.screenshot({ path: `/evidence/issue-25-correlation-${name}.png`, fullPage: true });
    proofs.push({ name, request_id: entry.request_id, event_id: entry.sql.event_id,
      href, browser_url: page.url(), requires_reauthentication: true,
      nonadmin_rows: 0, nonadmin_error: 'Access unavailable', producer_status: entry.producer_status,
      list_request_ids: apiRequests, list_statuses: listStatuses, metadata_only: true });
    await context.close();
  }
  writeFileSync('/evidence/issue-25-correlation.json', JSON.stringify({
    captured_at: new Date().toISOString(), evidence_kind: 'controlled integration', proofs,
    ui_sha256: uiHash,
  }) + '\n');
  console.log('Real allow/deny correlation links, reauthentication and denied identity verified.');
} finally {
  await browser.close();
}
