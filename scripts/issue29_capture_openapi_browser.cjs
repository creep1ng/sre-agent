const { chromium } = require('/e2e/node_modules/playwright');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1400 } });
  // Route any authenticated request only to this isolated API; deny external pages/assets.
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== 'api') return route.abort();
    return route.continue({
      headers: {
        ...route.request().headers(),
        Authorization: `Bearer ${process.env.DEMO_HUMAN_API_KEY}`,
      },
    });
  });
  const page = await context.newPage();
  const response = await page.goto('http://api:8000/openapi.json');
  const document = await response.json();
  const operation = document.paths?.['/v1/mcp/tools/{tool_id}']?.post;
  const body = operation?.requestBody;
  const media = body?.content?.['application/json'];
  const names = Object.keys(media?.examples ?? {}).sort();
  const variants = media?.schema?.oneOf ?? [];
  const propertySets = variants.map((variant) => new Set(Object.keys(variant.properties ?? {})));
  if (
    response.status() !== 200 ||
    body?.required !== true ||
    names.join(',') !== 'query_elasticsearch,query_prometheus' ||
    variants.length !== 2 ||
    variants.some((variant) => variant.type !== 'object' || !Array.isArray(variant.required)) ||
    !['datasource_uid', 'expr', 'query_type', 'end_time'].every((name) => propertySets[0].has(name)) ||
    !['datasource_uid', 'index', 'query', 'start_time', 'end_time', 'limit'].every((name) => propertySets[1].has(name))
  ) {
    throw new Error('Unexpected actual OpenAPI document');
  }
  // Use Chromium's native JSON-viewer Pretty-print control, then scroll the actual
  // OpenAPI document to the real invocation path. This alters only rendering; no
  // schema example is submitted and no endpoint operation is executed.
  await page.mouse.click(89, 8);
  await page.waitForTimeout(100);
  await page.evaluate(() => {
    window.find('"/v1/mcp/tools/{tool_id}"');
    window.scrollBy(0, 250);
  });
  await page.waitForTimeout(100);
  const visible = await page.locator('body').innerText();
  // OpenAPI legitimately documents bearer auth; only reject actual key disclosure.
  if (visible.includes(process.env.DEMO_HUMAN_API_KEY)) {
    throw new Error('Unsafe screenshot');
  }
  await page.screenshot({ path: '/capture/openapi-document.png' });
  fs.writeFileSync(
    '/capture/screenshot-provenance.json',
    `${JSON.stringify(
      {
        tested_sha: process.env.TESTED_SHA,
        captured_at_utc: new Date().toISOString(),
        request_id: response.headers()['x-request-id'] ?? null,
        response_date: response.headers().date,
        status: response.status(),
        request_url: 'GET /openapi.json',
        surface: 'real browser rendering of the actual FastAPI OpenAPI response; checks required MCP body, typed oneOf and request examples; no example invocation executed',
        file: 'openapi-document.png',
        sanitized: true,
      },
      null,
      2,
    )}\n`,
  );
  await browser.close();
  console.log('Real OpenAPI document captured; shape checked; no schema example was invoked.');
})().catch((error) => {
  const message = String(error.message ?? '').replace(process.env.DEMO_HUMAN_API_KEY, '[REDACTED]');
  console.error(error.name, message);
  process.exit(1);
});
