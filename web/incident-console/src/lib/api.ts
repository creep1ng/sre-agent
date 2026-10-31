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

export type TriageResult =
  | { kind: "ok"; incidentId?: string }
  | { kind: "auth" }
  | { kind: "forbidden" }
  | { kind: "conflict" }
  | { kind: "ineligible" }
  | { kind: "rejected" }
  | { kind: "transient" };

export type TriageFailure = Exclude<TriageResult["kind"], "ok">;

export interface DeclareInput {
  severity: Severity;
  impact: string;
}

export interface EligibleIncident {
  incident_id: string;
  state: string;
  service?: string;
  summary?: string;
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

/** Incidents an alert can join: the server lists the open ones. */
export async function fetchEligibleIncidents(
  token: string,
  alertId: string,
): Promise<{ kind: "ok"; items: EligibleIncident[] } | { kind: "forbidden" } | { kind: "transient" }> {
  try {
    const response = await fetch(triagePath(alertId, "/eligible-incidents"), {
      headers: headers(token),
      credentials: "omit",
      cache: "no-store",
    });
    if (response.status === 403) return { kind: "forbidden" };
    if (response.status !== 200) return { kind: "transient" };
    const body = (await response.json()) as { items?: unknown };
    if (!Array.isArray(body.items)) return { kind: "transient" };
    const items = body.items.filter(
      (item): item is EligibleIncident =>
        typeof item?.incident_id === "string" && typeof item?.state === "string",
    );
    return { kind: "ok", items };
  } catch {
    return { kind: "transient" };
  }
}

type Command = { operation: "triage_declare" | "triage_dismiss" | "triage_link"; reason: string } & Record<string, unknown>;

/** What one submission sends: a manual retry of it reuses both, so a lost answer is replayed. */
export interface TriageAttempt {
  key: string;
  version: number;
}

export type TriageSent = { result: TriageResult; attempt: TriageAttempt };

export function newAttempt(version: number): TriageAttempt {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return { key: `triage-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`, version };
}

async function postCommand(token: string, alertId: string, command: Command, attempt: TriageAttempt) {
  const response = await fetch(triagePath(alertId, "/commands"), {
    method: "POST",
    headers: { ...headers(token), "Content-Type": "application/json", "Idempotency-Key": attempt.key },
    credentials: "omit",
    cache: "no-store",
    body: JSON.stringify({ ...command, expected_version: attempt.version }),
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
 * Sends one decision through POST /v1/alerts/{id}/triage/commands; the server decides. A version
 * that went stale while the operator was choosing is read again and retried once with a new key;
 * the attempt that was sent last comes back, for a manual retry to replay.
 */
async function sendCommand(token: string, alertId: string, command: Command, attempt: TriageAttempt): Promise<TriageSent> {
  const done = (result: TriageResult): TriageSent => ({ result, attempt });
  try {
    let sent = await postCommand(token, alertId, command, attempt);
    if (sent.status === 409 && sent.code === "stale_version") {
      const fresh = await readTriageVersion(token, alertId);
      if (fresh === null) return done({ kind: "transient" });
      attempt = newAttempt(fresh);
      sent = await postCommand(token, alertId, command, attempt);
    }
    if (sent.status === 200 || sent.status === 201) return done({ kind: "ok", incidentId: sent.incidentId });
    if (sent.status === 401) return done({ kind: "auth" });
    if (sent.status === 403) return done({ kind: "forbidden" });
    if (sent.code === "destination_ineligible" || sent.code === "incident_not_found") return done({ kind: "ineligible" });
    if (sent.status === 409) return done({ kind: "conflict" });
    if (sent.status === 400 || sent.status === 404 || sent.status === 422) return done({ kind: "rejected" });
    return done({ kind: "transient" });
  } catch {
    return done({ kind: "transient" });
  }
}

export async function declareAlert(
  token: string,
  alert: LiveAlert,
  input: DeclareInput,
  attempt: TriageAttempt,
): Promise<TriageSent> {
  const sent = await sendCommand(
    token,
    alert.alert_id,
    {
      operation: "triage_declare",
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
    },
    attempt,
  );
  return sent.result.kind === "ok" && !sent.result.incidentId ? { ...sent, result: { kind: "transient" } } : sent;
}

export function dismissAlert(token: string, alertId: string, reason: string, attempt: TriageAttempt) {
  return sendCommand(token, alertId, { operation: "triage_dismiss", reason }, attempt);
}

export function linkAlert(token: string, alertId: string, incidentId: string, attempt: TriageAttempt) {
  return sendCommand(
    token,
    alertId,
    { operation: "triage_link", reason: "Vinculada desde la bandeja de la consola de incidentes.", target_incident_id: incidentId },
    attempt,
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
