import { create } from "zustand";
import { POLL_MS, useLive } from "@/lib/live";

/** One row of GET /v1/incidents (incident-list:1.0.0). */
export interface InboxIncident {
  incident_id: string;
  state: string;
  severity: string | null;
  service: string | null;
  summary: string | null;
  impact: string | null;
  opened_at: string;
  updated_at: string;
  version: number;
  latest_run: {
    run_id: string;
    status: string | null;
    current_state: string | null;
    pending_command: string | null;
    terminated_reason: string | null;
    updated_at: string;
  } | null;
  pending_decision: {
    command: "approve_mitigation" | "escalate";
    run_id: string;
    incident_version: number;
    waiting_since: string;
    mitigation_id: string | null;
  } | null;
}

/** One row of GET /v1/changes. */
export interface ChangeEvent {
  change_id: string;
  service: string;
  kind: "deploy" | "rollback" | "ci";
  status: "succeeded" | "failed";
  version: string | null;
  occurred_at: string;
}

export type InboxPhase = "idle" | "loading" | "ready" | "auth" | "forbidden" | "error";

interface InboxData {
  phase: InboxPhase;
  incidents: InboxIncident[];
  changes: ChangeEvent[];
  /** The pending mitigation's own words by incident, read under run.read_context; null without that grant. */
  proposals: Record<string, string | null>;
}

export const useInboxData = create<InboxData>(() => ({ phase: "idle", incidents: [], changes: [], proposals: {} }));

type Reply = { kind: "ok"; body: unknown } | { kind: "auth" } | { kind: "forbidden" } | { kind: "transient" };

/** Same-origin read through the web proxy; server codes and details never reach the screen. */
async function read(path: string, token: string, signal: AbortSignal): Promise<Reply> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
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
  if (response.status !== 200) return { kind: "transient" };
  try {
    return { kind: "ok", body: await response.json() };
  } catch {
    return { kind: "transient" };
  }
}

/** The mitigation text of a pending decision, or null when the reader may not see it. */
async function proposal(incident: InboxIncident, token: string, signal: AbortSignal): Promise<string | null> {
  const decision = incident.pending_decision;
  if (decision?.command !== "approve_mitigation") return null;
  const reply = await read(`/v1/incidents/${incident.incident_id}/runs/${decision.run_id}/context`, token, signal);
  if (reply.kind !== "ok") return null;
  const strategy = (reply.body as { reasoning?: { mitigation_strategy?: { description?: unknown } | null } }).reasoning
    ?.mitigation_strategy;
  return typeof strategy?.description === "string" && strategy.description ? strategy.description : null;
}

let controller: AbortController | null = null;
let timer: number | undefined;

async function poll(token: string) {
  controller?.abort();
  const current = (controller = new AbortController());
  try {
    const [incidents, changes] = await Promise.all([
      read("/v1/incidents?status=recent&limit=100", token, current.signal),
      read("/v1/changes?limit=100", token, current.signal),
    ]);
    if (incidents.kind === "auth" || incidents.kind === "forbidden") {
      useInboxData.setState({ phase: incidents.kind, incidents: [], changes: [], proposals: {} });
    } else if (incidents.kind === "transient") {
      // Keep what is on screen; only an empty inbox says the read failed.
      if (useInboxData.getState().phase !== "ready") useInboxData.setState({ phase: "error" });
    } else {
      const rows = (incidents.body as { incidents?: InboxIncident[] }).incidents ?? [];
      const pending = rows.filter((row) => row.pending_decision);
      const words = await Promise.all(pending.map((row) => proposal(row, token, current.signal)));
      useInboxData.setState({
        phase: "ready",
        incidents: rows,
        // A reader without change.read still sees the rest of the inbox.
        changes: changes.kind === "ok" ? ((changes.body as { changes?: ChangeEvent[] }).changes ?? []) : [],
        proposals: Object.fromEntries(pending.map((row, index) => [row.incident_id, words[index]])),
      });
    }
  } catch {
    return;
  }
  if (controller === current) timer = window.setTimeout(() => void poll(token), POLL_MS);
}

/** Polls the inbox reads for the connected credential until stopped; returns the stop function. */
export function watchInbox(): () => void {
  const restart = (token: string | null) => {
    stop();
    if (!token) return useInboxData.setState({ phase: "idle", incidents: [], changes: [], proposals: {} });
    useInboxData.setState({ phase: "loading" });
    void poll(token);
  };
  const stop = () => {
    window.clearTimeout(timer);
    controller?.abort();
    controller = null;
  };
  restart(useLive.getState().token);
  const unsubscribe = useLive.subscribe((state, previous) => {
    if (state.token !== previous.token) restart(state.token);
  });
  return () => {
    unsubscribe();
    stop();
  };
}
