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

export type DeclareResult =
  | { kind: "ok"; incidentId: string }
  | { kind: "auth" }
  | { kind: "forbidden" }
  | { kind: "conflict" }
  | { kind: "rejected" }
  | { kind: "transient" };

export interface DeclareInput {
  severity: Severity;
  impact: string;
}

function headers(token: string): Record<string, string> {
  return { Accept: "application/json", Authorization: `Bearer ${token}` };
}

function triagePath(alertId: string, suffix: string): string {
  return `/api/v1/alerts/${encodeURIComponent(alertId)}/triage${suffix}`;
}

/** The triage version a command must name: 1 while the alert has no decision yet. */
export async function readTriageVersion(token: string, alertId: string): Promise<number | null> {
  try {
    const response = await fetch(triagePath(alertId, "/context"), {
      headers: headers(token),
      credentials: "omit",
      cache: "no-store",
    });
    if (response.status !== 200) return null;
    const body = (await response.json()) as { triage_state?: { expected_version?: unknown } | null };
    if (body.triage_state == null) return 1;
    const version = body.triage_state.expected_version;
    return typeof version === "number" ? version : null;
  } catch {
    return null;
  }
}

function idempotencyKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return `declare-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

async function postDeclare(token: string, alert: LiveAlert, input: DeclareInput, version: number) {
  const response = await fetch(triagePath(alert.alert_id, "/commands"), {
    method: "POST",
    headers: { ...headers(token), "Content-Type": "application/json", "Idempotency-Key": idempotencyKey() },
    credentials: "omit",
    cache: "no-store",
    body: JSON.stringify({
      operation: "triage_declare",
      expected_version: version,
      reason: "Declarado desde la bandeja de la consola de incidentes.",
      severity: input.severity,
      impact: input.impact,
      alert_context: {
        service: alert.service,
        summary: alert.summary,
        observed_at: alert.observed_at,
        source: alert.source,
        severity: alert.severity,
      },
    }),
  });
  try {
    const body = (await response.json()) as { incident_id?: unknown; error?: { code?: unknown } };
    return {
      status: response.status,
      code: typeof body.error?.code === "string" ? body.error.code : undefined,
      incidentId: typeof body.incident_id === "string" ? body.incident_id : undefined,
    };
  } catch {
    return { status: response.status };
  }
}

/**
 * Declares through POST /v1/alerts/{id}/triage/commands; the server decides. A version that went
 * stale while the dialog was open is read again and retried once, with a new key.
 */
export async function declareAlert(
  token: string,
  alert: LiveAlert,
  input: DeclareInput,
  version: number,
): Promise<DeclareResult> {
  try {
    let sent = await postDeclare(token, alert, input, version);
    if (sent.status === 409 && sent.code === "stale_version") {
      const fresh = await readTriageVersion(token, alert.alert_id);
      if (fresh === null) return { kind: "transient" };
      sent = await postDeclare(token, alert, input, fresh);
    }
    if (sent.status === 201 && sent.incidentId) return { kind: "ok", incidentId: sent.incidentId };
    if (sent.status === 401) return { kind: "auth" };
    if (sent.status === 403) return { kind: "forbidden" };
    if (sent.status === 409) return { kind: "conflict" };
    if (sent.status === 400 || sent.status === 404 || sent.status === 422) return { kind: "rejected" };
    return { kind: "transient" };
  } catch {
    return { kind: "transient" };
  }
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
