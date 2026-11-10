// Reuse issue29's real browser capture boundary; this navigation submits one live POST.
const { chromium } = require('/e2e/node_modules/playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const started = new Date().toISOString();
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.hostname !== 'api' || url.pathname !== '/v1/mcp/tools/query_prometheus') {
      return route.abort();
    }
    return route.continue({
      method: 'POST',
      headers: { ...route.request().headers(), 'Content-Type': 'application/json',
        Authorization: `Bearer ${process.env.DEMO_HUMAN_API_KEY}` },
      postData: JSON.stringify({ datasource_uid: 'webstore-metrics', expr: 'vector(1)',
        query_type: 'instant', end_time: 'now' })
    });
  });
  const page = await context.newPage();
  const response = await page.goto('http://api:8000/v1/mcp/tools/query_prometheus');
  const body = await response.json();
  const requestId = response.headers()['x-request-id'];
  if (response.status() !== 200 || !requestId || body.result_type !== 'vector' ||
      body.result.length !== 1 || body.result[0].value[1] !== '1') {
    throw new Error('Unexpected public result');
  }
  const text = await page.locator('body').innerText();
  if (text.includes(process.env.DEMO_HUMAN_API_KEY) || text.includes('Bearer ')) {
    throw new Error('Unsafe screenshot');
  }
  await page.screenshot({ path: '/capture/issue30-invocation.png', fullPage: true });
  fs.writeFileSync('/capture/issue30-screenshot.json', JSON.stringify({
    tested_sha: process.env.TESTED_SHA, started_at: started,
    captured_at: new Date().toISOString(), request_id: requestId,
    status: response.status(), surface: 'actual browser-rendered FastAPI POST response',
    separate_from_replay: true, synthetic_result: 'vector(1)', sanitized: true
  }, null, 2) + '\n');
  await browser.close();
  console.log('Real invocation screenshot captured; no headers or credentials recorded.');
})().catch(error => { console.error(error.name); process.exit(1); });
