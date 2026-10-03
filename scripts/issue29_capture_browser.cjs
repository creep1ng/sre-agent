const { chromium } = require('/e2e/node_modules/playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  const context = await browser.newContext({viewport:{width:1280,height:1200}});
  // Restrict authenticated requests to this isolated API; no external pages/assets.
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if(url.hostname !== 'api') return route.abort();
    return route.continue({headers:{...route.request().headers(),Authorization:`Bearer ${process.env.DEMO_HUMAN_API_KEY}`}});
  });
  const page = await context.newPage();
  const response = await page.goto('http://api:8000/v1/mcp/discovery');
  const body = await response.json();
  if(response.status()!==200 || body.tools.length!==2) throw new Error('Unexpected public result');
  const text = await page.locator('body').innerText();
  if(text.includes(process.env.DEMO_HUMAN_API_KEY) || text.includes('Bearer ')) throw new Error('Unsafe screenshot');
  await page.screenshot({path:'/capture/final-stack-discovery.png',fullPage:true});
  fs.writeFileSync('/capture/screenshot-provenance.json',JSON.stringify({tested_sha:process.env.TESTED_SHA,captured_at_utc:new Date().toISOString(),request_id:body.request_id,response_date:response.headers().date,status:response.status(),surface:'real browser rendering of actual FastAPI JSON response; not Swagger examples',file:'final-stack-discovery.png',sanitized:true},null,2)+'\n');
  await browser.close();
  console.log('Real HTTP screenshot captured; no credentials or request headers recorded.');
})().catch(err=>{console.error(err.name);process.exit(1)});
