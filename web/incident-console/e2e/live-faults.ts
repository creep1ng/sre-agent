import { writeFileSync, rmSync } from "node:fs";
import { expect, type APIRequestContext } from "@playwright/test";

/*
 * The Grafana stand-in of compose.live-triage-e2e.yaml delivers each rule to intake (#765),
 * firing unless `$FAULT_DIR/{rule id}` reads `ok`. freshEpisodes ends every open episode and
 * opens one per rule in `firing`, so each live spec starts from untriaged alerts whatever ran
 * before it.
 */
export const RULES = ["checkout-payment-error-rate", "checkout-orders-error-rate"] as const;

interface LiveAlerts {
  alerts: { alert_id: string; triage_status: string }[];
}

export async function freshEpisodes(
  api: APIRequestContext,
  base: string,
  firing: readonly string[] = RULES,
): Promise<string[]> {
  const dir = process.env.FAULT_DIR;
  if (!dir) return [];
  const read = async () => {
    const response = await api.get(`${base}/api/v1/alerts`);
    expect(response.status()).toBe(200);
    return (await response.json()) as LiveAlerts;
  };
  for (const rule of RULES) writeFileSync(`${dir}/${rule}`, "ok");
  await expect.poll(async () => (await read()).alerts.length).toBe(0);
  for (const rule of firing) rmSync(`${dir}/${rule}`, { force: true });
  let fresh: string[] = [];
  await expect
    .poll(async () => {
      fresh = (await read()).alerts.filter((alert) => alert.triage_status === "new").map((alert) => alert.alert_id);
      return fresh.length;
    })
    .toBe(firing.length);
  return fresh;
}
