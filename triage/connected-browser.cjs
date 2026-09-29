const fs=require('fs');
const {chromium}=require('/e2e/node_modules/playwright');
(async()=>{
 const mode=process.argv[2], pr=process.argv[3], base=process.env.AUDIT_BASE_URL||'http://audit-triage-web-20260928:8100';
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1200}});
 const credential=JSON.parse(fs.readFileSync('/out/local-credential.json','utf8')).credential;
 const observed=[];
 page.on('response',async r=>{if(r.url().includes('/api/v1/')){let body;try{body=await r.json()}catch{}observed.push({path:new URL(r.url()).pathname,status:r.status(),request:r.request().postDataJSON(),body})}});
 await page.goto(base+'/public/admin/'+(mode==='triage'?'triage':'audit-events')+'.html');
 if(mode==='audit')await page.fill('#filter-decision','allow');
 await page.fill('#api-key',credential);await page.click('#connect-button');
 if(mode==='triage'){
  await page.fill('#alert-id','al-browser-review-'+Date.now());await page.fill('#command-reason','Controlled browser review');await page.selectOption('#command-operation','triage_link');await page.fill('#command-target','inc-http-target');await page.click('#submit-button');await page.waitForFunction(()=>document.querySelector('#result-status').textContent==='linked');
  await page.selectOption('#command-operation','triage_declare');await page.selectOption('#command-severity','sev2');await page.click('#submit-button');await page.waitForFunction(()=>document.querySelector('#triage-page').dataset.state==='error');
 }else{
  await page.waitForSelector('[data-event-row]');await page.locator('[data-expand-event]').first().click();await page.waitForSelector('[data-event-detail]');
 }
 await page.screenshot({path:`/out/pr-${pr}-connected.png`,fullPage:true});
 const dom=mode==='triage'?await page.locator('#page-error').innerText():await page.locator('[data-event-detail]').innerText();
 const result={candidate:process.env.CANDIDATE_SHA,evidence:'Real browser against candidate API and isolated PostgreSQL; synthetic persisted data; no route mocks',observed,visible:dom};
 fs.writeFileSync(`/out/pr-${pr}-connected.json`,JSON.stringify(result,null,2));console.log(JSON.stringify({candidate:result.candidate,statuses:observed.map(x=>x.status),visible:dom},null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
