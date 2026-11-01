// Real admin grants page after the #759 seed-reset E2E: revoked seed grants next to their restores.
import { chromium, expect } from '@playwright/test';

if (!process.env.ADMIN_HUMAN_API_KEY) throw new Error('Missing ADMIN_HUMAN_API_KEY');
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto('http://web/public/admin/grants.html');
  await page.fill('#api-key', process.env.ADMIN_HUMAN_API_KEY);
  await page.click('#connect-button');
  await expect(page.locator('#principal-filter')).toBeEnabled();
  await page.selectOption('#principal-filter', 'demo-human');
  await expect(page.locator('#grant-rows')).toContainText('grant-setup-human-change-read-restored-1');
  await expect(page.locator('#api-key')).toHaveValue('');
  if ((await page.locator('body').innerText()).includes(process.env.ADMIN_HUMAN_API_KEY))
    throw new Error('API key visible');
  await page.locator('#grant-list').screenshot({ path: '/evidence/grants-after-seed-reset.png' });
} finally {
  await browser.close();
}
