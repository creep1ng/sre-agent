// Real connected audit detail plus explicitly route-mocked P2 demonstrations.
import { chromium, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const evidence = JSON.parse(readFileSync('/evidence/issue-25-audit-http.json', 'utf8'));
const allowed = evidence.cases.find((entry) => entry.name === 'allow');
if (!allowed?.request_id || !process.env.ADMIN_HUMAN_API_KEY) throw new Error('Missing evidence/session');
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('http://web/public/admin/audit-events.html');
  const servedUi = await page.request.get('http://web/public/admin/audit-events.js');
  if (!servedUi.ok()) throw new Error('Could not identify the served UI source');
  const uiSha256 = createHash('sha256').update(await servedUi.body()).digest('hex');
  await page.fill('#filter-request-id', allowed.request_id);
  await page.fill('#api-key', process.env.ADMIN_HUMAN_API_KEY);
  await page.click('#connect-button');
  await expect(page.locator('[data-event-row]')).toHaveCount(1);
  await page.click('[data-expand-event]');
  await expect(page.locator('[data-event-detail]')).toContainText('Response status');
  await expect(page.locator('[data-event-detail]')).toContainText('200');
  await expect(page.locator('[data-event-detail]')).toContainText('Latency (ms)');
  await expect(page.locator('#api-key')).toHaveValue('');
  const body = await page.locator('body').innerText();
  for (const forbidden of ['ISSUE25_PRIVATE_PROMPT_', 'ISSUE25_PRIVATE_OUTPUT_', process.env.ADMIN_HUMAN_API_KEY])
    if (body.includes(forbidden)) throw new Error('Sensitive marker visible');
  await page.screenshot({ path: '/evidence/issue-25-audit-connected.png', fullPage: true });
  const observations = { connected: { request_id: allowed.request_id, rows: 1, detail_status: 200 } };
  // Inject a detail miss without altering the persisted demonstration event.
  await page.click('[data-expand-event]');
  await page.route(/\/api\/v1\/audit-events\/[^?]+$/, (route) => route.fulfill({
    status: 404, contentType: 'application/json', body: '{}',
  }));
  await page.click('[data-expand-event]');
  await expect(page.locator('#page-error-title')).toHaveText('Audit event not found');
  await expect(page.locator('#audit-events-page')).toHaveAttribute('data-state', 'ready');
  await expect(page.locator('#page-error')).toBeVisible();
  await expect(page.locator('[data-event-row]')).toHaveCount(1);
  await page.screenshot({ path: '/evidence/issue-25-detail-404.png', fullPage: true });
  observations.detail_404 = {
    evidence_kind: 'mock', injected_status: 404, alert_visible_after_automatic_list_refresh: true,
  };

  // Verify a service error survives its automatic list refresh as well.
  await page.reload();
  await page.fill('#filter-request-id', allowed.request_id);
  await page.fill('#api-key', process.env.ADMIN_HUMAN_API_KEY);
  await page.click('#connect-button');
  await expect(page.locator('[data-event-row]')).toHaveCount(1);
  await page.route(/\/api\/v1\/audit-events\/[^?]+$/, (route) => route.fulfill({
    status: 503, contentType: 'application/json',
    body: JSON.stringify({ error: { code: 'audit_unavailable', message: 'Audit unavailable.' } }),
  }));
  await page.click('[data-expand-event]');
  await expect(page.locator('#page-error-title')).toHaveText('Service unavailable');
  await expect(page.locator('#page-error')).toBeVisible();
  await expect(page.locator('#audit-events-page')).toHaveAttribute('data-state', 'ready');
  await expect(page.locator('[data-event-row]')).toHaveCount(1);
  await page.screenshot({ path: '/evidence/issue-25-detail-503.png', fullPage: true });
  observations.detail_503 = {
    evidence_kind: 'mock', injected_status: 503, alert_visible_after_automatic_list_refresh: true,
  };
  const response = await page.request.get(`http://web/api/v1/audit-events?request_id=${allowed.request_id}`, {
    headers: { Authorization: `Bearer ${process.env.ADMIN_HUMAN_API_KEY}` },
  });
  if (!response.ok()) throw new Error('Connected metadata read failed');
  const payload = await response.json();
  await page.route((url) => url.pathname === '/api/v1/audit-events', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ ...payload, limit: 1, truncated: true }),
  }));
  await page.click('#apply-button');
  await expect(page.locator('#event-count')).toContainText(
    '1 audit event. Results are truncated; additional matching events were omitted.',
  );
  observations.truncation = {
    evidence_kind: 'mock', truncated: true,
    displayed_count: await page.locator('#event-count').innerText(),
    not_presented_as_complete: true,
  };
  await page.screenshot({ path: '/evidence/issue-25-audit-truncated.png', fullPage: true });
  if (errors.length) throw new Error('Browser script errors');
  writeFileSync('/evidence/issue-25-audit-browser.json', `${JSON.stringify({
    ...observations,
    ui_sha256: uiSha256,
    source_build_revision: process.env.SRE_AGENT_BUILD_REVISION || null,
  })}\n`);
  console.log('Connected detail and two mock P2 demonstrations verified; screenshot sanitized.');
} finally {
  await browser.close();
}
