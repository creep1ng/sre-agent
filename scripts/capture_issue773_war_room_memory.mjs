// Evidence for #773: the war room of inc-recall-second, whose hypothesis cites the recalled memory
// of the closed inc-recall-first. Needs the data the recall E2E leaves in python-checks-db, served
// by the real API and web proxy (see the PR's reproduction commands):
//   docker compose --profile e2e run --rm --no-deps -v ./scripts:/e2e/scripts:ro \
//     -v ./docs/evidence:/e2e/docs/evidence -e DEMO_HUMAN_API_KEY=<the E2E's demo key> \
//     e2e node scripts/capture_issue773_war_room_memory.mjs
import { chromium } from "@playwright/test";
import { connectConsole } from "../tests/browser/support/console-session.mjs";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const key = process.env.DEMO_HUMAN_API_KEY;
if (!key) throw new Error("DEMO_HUMAN_API_KEY is required.");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
try {
  await page.goto(`${baseURL}/?view=war-room&incident_id=inc-recall-second`);
  await connectConsole(page, key);
  const memory = page.getByRole("link", { name: "Recuerdo de incidente cerrado" }).first();
  await memory.waitFor({ state: "visible", timeout: 20000 });
  console.log("memory link:", await memory.getAttribute("href"));
  const reasoning = page.getByRole("heading", { name: "Razonamiento del agente" });
  await page.waitForTimeout(300);
  await reasoning
    .locator("xpath=ancestor::section[1]")
    .screenshot({ path: "docs/evidence/issue-773/war-room-memory.png" });
} finally {
  await browser.close();
}
