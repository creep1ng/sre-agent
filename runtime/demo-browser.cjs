// Evidence-only browser observation against a fresh local synthetic demo.
// No credentials, response bodies, query strings, or external destination URLs logged.
const {chromium} = require('/e2e/node_modules/playwright');
const fs = require('node:fs');
const origin = 'http://127.0.0.1:8090';
const output = '/out/reproduction-370';
fs.mkdirSync(output, {recursive: true});
const safePath = value => {
  try { const u = new URL(value); return u.origin === origin ? u.pathname : '[external omitted]'; }
  catch { return '[invalid URL omitted]'; }
};
(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    for (const [name, path] of [['store', '/'], ['grafana', '/grafana/'], ['jaeger', '/jaeger/ui/']]) {
      const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
      const assets = new Set();
      let errors = 0;
      page.on('pageerror', () => { errors++; console.log(JSON.stringify({service: name, event: 'pageerror'})); });
      page.on('requestfailed', request => console.log(JSON.stringify({service: name, event: 'requestfailed', path: safePath(request.url())})));
      page.on('response', response => {
        const route = safePath(response.url());
        if (route.startsWith('/grafana/public/build/') && route.endsWith('.js')) assets.add(response.url());
        if (response.status() >= 400) console.log(JSON.stringify({service: name, status: response.status(), path: route}));
      });
      let status = null;
      try { const response = await page.goto(origin + path, {waitUntil: 'domcontentloaded', timeout: 30000}); status = response?.status(); }
      catch { console.log(JSON.stringify({service: name, event: 'navigation_failed'})); }
      await page.waitForTimeout(12000);
      const body = await page.locator('body').innerText({timeout: 5000}).catch(() => '');
      const bootError = /Grafana has failed to load its application files/i.test(body);
      await page.screenshot({path: `${output}/${name}.png`, timeout: 15000});
      console.log(JSON.stringify({service: name, document_status: status, visible_text: body.trim().length > 0, grafana_boot_error: bootError, page_errors: errors}));
      // Compare up to three of the same JS assets sequentially, from this container.
      if (name === 'grafana') {
        for (const url of [...assets].slice(0, 3)) {
          try { const result = await page.request.get(url, {timeout: 10000}); console.log(JSON.stringify({service: name, sequential_status: result.status(), path: safePath(url)})); }
          catch { console.log(JSON.stringify({service: name, event: 'sequential_fetch_failed', path: safePath(url)})); }
        }
      }
      if (status !== 200 || !body.trim() || bootError || errors) process.exitCode = 1;
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(() => { console.error('Browser probe failed; inspect the bounded output and available screenshots.'); process.exitCode = 1; });
