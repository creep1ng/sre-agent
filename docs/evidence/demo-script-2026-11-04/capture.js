const { chromium } = require("/e2e/node_modules/playwright");
const [sha, out] = process.argv.slice(2);
const base = `https://github.com/creep1ng/sre-agent/blob/${sha}/docs/`;
const pages = [
  ["product-direction-2026-10-28.md", "#sixth-round-of-decisions-2026-11-02-and-2026-11-03", "decisions.png"],
  ["demo-2026-11-04-script.md", "", "script.png"],
];
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  for (const [file, anchor, png] of pages) {
    await page.goto(base + file + anchor, { waitUntil: "load", timeout: 60000 });
    const article = page.locator("article.markdown-body").first();
    await article.waitFor();
    // GitHub's sticky file header would cover the article in an element screenshot.
    await page.evaluate(() => {
      for (const el of document.querySelectorAll("*")) {
        const pos = getComputedStyle(el).position;
        if (pos === "sticky" || pos === "fixed") el.style.display = "none";
      }
    });
    if (anchor) {
      // Only the new rounds: from the sixth round's heading to the end of the article.
      await page.evaluate(() => {
        const body = document.querySelector("article.markdown-body");
        const start = [...body.querySelectorAll("h2")].find((h) => h.textContent.startsWith("Sixth round"));
        let node = start.closest(".markdown-heading") || start;
        while (node.previousElementSibling) node.previousElementSibling.remove();
      });
    }
    await article.screenshot({ path: `${out}/${png}` });
    console.log(png, await article.evaluate((a) => a.querySelectorAll("table tr").length), "table rows");
  }
  await browser.close();
})().catch((err) => { console.error(String(err)); process.exit(1); });
