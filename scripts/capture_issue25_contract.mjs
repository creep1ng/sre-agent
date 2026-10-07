// Render the actual sanitized harness output; no invented service or test results.
import { chromium } from '@playwright/test';
import { readFileSync } from 'node:fs';

const output = readFileSync('/evidence/issue-25-contract-validation.log', 'utf8');
const escaped = output.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  await page.setContent(`<html lang="en"><title>Actual contract harness output</title><body><h1>Actual contract harness output</h1><pre>${escaped}</pre></body></html>`);
  await page.screenshot({ path: '/evidence/issue-25-contract-validation.png', fullPage: true });
} finally {
  await browser.close();
}
