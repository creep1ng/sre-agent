import type { Severity } from "./types";

/*
 * Same-origin reads of one incident through the governed API, with the credential of the
 * console's session. Answers are reduced to what the page needs; server codes and messages
 * never reach the screen.
 */

export type ApiResult<T> =
  | { kind: "ok"; body: T }
  | { kind: "auth" }
  | { kind: "forbidden"; code?: string }
  | { kind: "missing" }
  | { kind: "conflict"; code?: string }
  | { kind: "transient"; code?: string };

export type RunStatus = "running" | "awaiting_human" | "completed" | "terminated";

export interface RunSummary {
  run_id: string;
  version: number;
  status: RunStatus | null;
  current_state: string | null;
  updated_at: string;
}

export interface IncidentDetail {
  incident_id: string;
  workflow_version: string;
  state: string;
  severity: Severity | null;
  impact: string | null;
  alert: { alert_id: string; service: string; summary: string; observed_at: string; source: string } | null;
  version: number;
  updated_at: string;
  runs: RunSummary[];
}

export interface RunState {
  run_id: string;
  status: RunStatus;
  current_state: string;
  pending_command: string | null;
  terminated_reason: string | null;
  cursor: string;
  updated_at: string;
}

export interface RunEvent {
  event_id: string;
  kind: string;
  sequence: number;
  state: string | null;
  summary: string;
  actor: { type: "human" | "agent" | "system"; reference?: { principal_id?: string; display_name?: string | null } | null };
  reason_code: string | null;
  occurred_at: string;
}

export interface EventPage {
  events: RunEvent[];
  next_cursor: string;
  has_more: boolean;
}

export interface Hypothesis {
  hypothesis_id: string;
  statement: string;
  confidence: "low" | "medium" | "high";
  status?: string;
  supporting_evidence?: string[];
  contradicting_evidence?: string[];
  created_at?: string;
}

export interface Evidence {
  evidence_id: string;
  source: string;
  tool?: string | null;
  query?: string | null;
  time_window?: string | null;
  summary?: string;
  collected_at?: string;
  /** #707: fields present only once the investigator records them. */
  empty?: boolean;
  verdict?: "supports" | "contradicts" | "inconclusive" | null;
  finding?: string | null;
}

export interface Mitigation {
  mitigation_id?: string;
  description: string;
  steps?: string[];
  risk?: "low" | "medium" | "high";
  verification_check?: string;
  approval_status?: string;
  /** #722: the catalog operation the executor runs once a person approves. */
  operation?: { service: string; operation: string; parameters?: Record<string, string> } | null;
  /** #920: the deploy-executor's receipt once an approval ran the operation. */
  execution?: Execution | null;
  created_at?: string;
}

export interface Execution {
  execution_id: string;
  outcome: string;
  replayed: boolean;
  /** Image references for a rollback or restart; a flag.set (#724) touches no image. */
  before_image?: string;
  after_image?: string;
  executed_at: string;
  duration_ms?: number;
}

export interface Reasoning {
  hypotheses: Hypothesis[];
  evidence: Evidence[];
  mitigation_strategy: Mitigation | null;
}

export interface ChangeEvent {
  change_id: string;
  service: string;
  kind: "deploy" | "rollback" | "ci";
  status: "succeeded" | "failed";
  version: string | null;
  author: string | null;
  url: string | null;
  occurred_at: string;
}

/** A canonical alert as GET /v1/alerts lists it; intake (#765) lists resolved episodes apart. */
export interface Alert {
  alert_id: string;
  service: string;
  incident_id?: string | null;
  origin?: { observed_at?: string } | null;
}

export interface Alerts {
  alerts: Alert[];
  /** Episodes Grafana resolved in the last day; `origin.observed_at` is when the resolution came in. */
  resolved?: Alert[];
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

async function call<T>(
  token: string,
  path: string,
  signal: AbortSignal,
  accept: (body: unknown) => body is T,
  send?: { body: unknown; key: string },
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: send ? "POST" : "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(send ? { "Content-Type": "application/json", "Idempotency-Key": send.key } : {}),
      },
      body: send ? JSON.stringify(send.body) : undefined,
      credentials: "omit",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if ((error as { name?: string } | null)?.name === "AbortError") throw error;
    return { kind: "transient" };
  }
  if (response.status === 401) return { kind: "auth" };
  if (response.status === 404) return { kind: "missing" };
  if (![200, 201, 202].includes(response.status)) {
    // The error's code tells a refused approval (#923) from a credential or a stale version.
    const code = await response.json().then(
      (body: unknown) => (isObject(body) && isObject(body.error) && typeof body.error.code === "string" ? body.error.code : undefined),
      () => undefined,
    );
    if (response.status === 403) return { kind: "forbidden", code };
    if (response.status === 409) return { kind: "conflict", code };
    return { kind: "transient", code };
  }
  try {
    const body: unknown = await response.json();
    return accept(body) ? { kind: "ok", body } : { kind: "transient" };
  } catch {
    return { kind: "transient" };
  }
}

const isDetail = (body: unknown): body is IncidentDetail =>
  isObject(body) && typeof body.incident_id === "string" && typeof body.state === "string" && Array.isArray(body.runs);
const isRun = (body: unknown): body is RunState =>
  isObject(body) && typeof body.run_id === "string" && typeof body.status === "string";
const isPage = (body: unknown): body is EventPage =>
  isObject(body) && Array.isArray(body.events) && typeof body.next_cursor === "string";
const isContext = (body: unknown): body is { reasoning: Reasoning } =>
  isObject(body) && isObject(body.reasoning) && Array.isArray(body.reasoning.hypotheses) && Array.isArray(body.reasoning.evidence);
const isAlerts = (body: unknown): body is Alerts => isObject(body) && Array.isArray(body.alerts);
const isChanges = (body: unknown): body is { changes: ChangeEvent[] } => isObject(body) && Array.isArray(body.changes);

const at = (id: string) => `/incidents/${encodeURIComponent(id)}`;

export const incidentApi = {
  detail: (token: string, id: string, signal: AbortSignal) => call(token, at(id), signal, isDetail),
  run: (token: string, id: string, run: string, signal: AbortSignal) =>
    call(token, `${at(id)}/runs/${encodeURIComponent(run)}`, signal, isRun),
  events: (token: string, id: string, run: string, after: string | null, signal: AbortSignal) => {
    const page = `?limit=200${after ? `&after=${encodeURIComponent(after)}` : ""}`;
    return call(token, `${at(id)}/runs/${encodeURIComponent(run)}/events${page}`, signal, isPage);
  },
  /** The recorded reasoning (hypotheses, evidence, mitigation); it needs run.read_context. */
  reasoning: (token: string, id: string, run: string, signal: AbortSignal) =>
    call(token, `${at(id)}/runs/${encodeURIComponent(run)}/context`, signal, isContext),
  changes: (token: string, service: string, signal: AbortSignal) =>
    call(token, `/changes?service=${encodeURIComponent(service)}&limit=5`, signal, isChanges),
  alerts: (token: string, signal: AbortSignal) => call(token, "/alerts", signal, isAlerts),
  whoami: (token: string, signal: AbortSignal) =>
    call(token, "/whoami", signal, (body): body is { principal_id: string } => isObject(body) && typeof body.principal_id === "string"),
  /** A governed human command on a run (approve_mitigation, reject_mitigation); the key replays one submission. */
  command: (token: string, id: string, run: string, body: unknown, key: string, signal: AbortSignal) =>
    call(token, `${at(id)}/runs/${encodeURIComponent(run)}/commands`, signal, isRun, { body, key }),
  /** Starts an investigation run; the same key replays the same run instead of opening another. */
  investigate: (token: string, id: string, workflowVersion: string, key: string, signal: AbortSignal) =>
    call(token, `${at(id)}/runs`, signal, isRun, { body: { workflow_version: workflowVersion, objective: "investigate" }, key }),
};
