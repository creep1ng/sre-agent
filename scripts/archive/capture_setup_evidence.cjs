// Capture the actual sanitized text report rendered by Chromium, not invented UI.
const { chromium } = require('/e2e/node_modules/playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1700, height: 900 } });
  await page.goto('file://' + process.argv[2]);
  await page.screenshot({ path: process.argv[3], fullPage: true });
  await browser.close();
})().catch(() => { console.error('evidence capture failed'); process.exitCode = 1; });
