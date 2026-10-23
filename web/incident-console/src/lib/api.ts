import type { LiveAlert, Severity, TriageStatus } from "./types";
import { SEVERITIES } from "./vocabulary";

export type AlertsResult =
  | { kind: "ok"; alerts: LiveAlert[] }
  | { kind: "auth" }
  | { kind: "forbidden" }
  | { kind: "transient"; retryAfterMs?: number };

const TRIAGE: TriageStatus[] = ["new", "triaging", "declared", "linked", "dismissed"];

function retryAfterMs(response: Response): number | undefined {
  const seconds = Number(response.headers.get("retry-after"));
  return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : undefined;
}

function isLiveAlert(raw: unknown): raw is LiveAlert {
  if (!raw || typeof raw !== "object") return false;
  const value = raw as Record<string, unknown>;
  return (
    typeof value.alert_id === "string" &&
    typeof value.service === "string" &&
    typeof value.summary === "string" &&
    typeof value.source === "string" &&
    typeof value.observed_at === "string" &&
    Number.isFinite(Date.parse(value.observed_at)) &&
    SEVERITIES.includes(value.severity as Severity) &&
    TRIAGE.includes(value.triage_status as TriageStatus)
  );
}

/** Same-origin read of the real alert list. It never surfaces server codes or details. */
export async function fetchAlerts(token: string, signal: AbortSignal): Promise<AlertsResult> {
  let response: Response;
  try {
    response = await fetch("/api/v1/alerts", {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      credentials: "omit",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if ((error as { name?: string } | null)?.name === "AbortError") throw error;
    return { kind: "transient" };
  }
  if (response.status === 401) return { kind: "auth" };
  if (response.status === 403) return { kind: "forbidden" };
  if (response.status !== 200) return { kind: "transient", retryAfterMs: retryAfterMs(response) };
  try {
    const body = (await response.json()) as { alerts?: unknown };
    if (!Array.isArray(body.alerts) || !body.alerts.every(isLiveAlert)) {
      return { kind: "transient", retryAfterMs: retryAfterMs(response) };
    }
    return { kind: "ok", alerts: body.alerts };
  } catch {
    return { kind: "transient", retryAfterMs: retryAfterMs(response) };
  }
}
