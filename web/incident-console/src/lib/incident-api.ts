import type { Severity } from "./types";

/*
 * Same-origin reads of one incident through the governed API, with the credential of the
 * console's session. Answers are reduced to what the page needs; server codes and messages
 * never reach the screen.
 */

export type ApiResult<T> =
  | { kind: "ok"; body: T }
  | { kind: "auth" }
  | { kind: "forbidden" }
  | { kind: "missing" }
  | { kind: "conflict" }
  | { kind: "transient" };

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
  actor: { type: "human" | "agent" | "system"; reference?: { display_name?: string | null } | null };
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
  description: string;
  steps?: string[];
  risk?: "low" | "medium" | "high";
  approval_status?: string;
  created_at?: string;
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
  if (response.status === 403) return { kind: "forbidden" };
  if (response.status === 404) return { kind: "missing" };
  if (response.status === 409) return { kind: "conflict" };
  if (response.status !== 200 && response.status !== 201) return { kind: "transient" };
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
  isObject(body) &&
  isObject(body.reasoning) &&
  Array.isArray(body.reasoning.hypotheses) &&
  Array.isArray(body.reasoning.evidence);
const isChanges = (body: unknown): body is { changes: ChangeEvent[] } => isObject(body) && Array.isArray(body.changes);

const at = (id: string) => `/incidents/${encodeURIComponent(id)}`;

export const incidentApi = {
  detail: (token: string, id: string, signal: AbortSignal) => call(token, at(id), signal, isDetail),
  run: (token: string, id: string, run: string, signal: AbortSignal) =>
    call(token, `${at(id)}/runs/${encodeURIComponent(run)}`, signal, isRun),
  events: (token: string, id: string, run: string, after: string | null, signal: AbortSignal) =>
    call(
      token,
      `${at(id)}/runs/${encodeURIComponent(run)}/events?limit=200${after ? `&after=${encodeURIComponent(after)}` : ""}`,
      signal,
      isPage,
    ),
  /** The recorded reasoning (hypotheses, evidence, mitigation); it needs run.read_context. */
  reasoning: (token: string, id: string, run: string, signal: AbortSignal) =>
    call(token, `${at(id)}/runs/${encodeURIComponent(run)}/context`, signal, isContext),
  changes: (token: string, service: string, signal: AbortSignal) =>
    call(token, `/changes?service=${encodeURIComponent(service)}&limit=5`, signal, isChanges),
  /** Starts an investigation run; the same key replays the same run instead of opening another. */
  investigate: (token: string, id: string, workflowVersion: string, key: string, signal: AbortSignal) =>
    call(token, `${at(id)}/runs`, signal, isRun, {
      body: { workflow_version: workflowVersion, objective: "investigate" },
      key,
    }),
};
