// Native browser capture of actual SQL output; no generated UI or summary.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const directory = process.argv[2] || '/proof';
const sqlOutput = path.join(directory, 'runtime-sql.json');
const records = JSON.parse(fs.readFileSync(sqlOutput, 'utf8'));
if (records.length !== 11 || !/^[0-9a-f]{40}$/.test(records[0].tested_sha) ||
    records.some(record => record.tested_sha !== records[0].tested_sha)) {
  throw new Error('Complete candidate-bound SQL inspection is required before capture.');
}
(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
    await page.goto(pathToFileURL(sqlOutput).href);
    await page.screenshot({ path: path.join(directory, 'evidence.png'), fullPage: true });
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
