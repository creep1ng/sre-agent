import { useCallback, useEffect, useRef, useState } from "react";
import {
  incidentApi,
  type ApiResult,
  type ChangeEvent,
  type IncidentDetail,
  type Reasoning,
  type RunEvent,
  type RunState,
} from "./incident-api";
import { useLive } from "./live";

/** While the agent works the page asks every few seconds; otherwise it only keeps fresh. */
const WORKING_POLL_MS = 2_500;
const IDLE_POLL_MS = 15_000;

export type IncidentPhase = "unauthenticated" | "loading" | "ready" | "auth" | "forbidden" | "missing" | "error";

export interface LiveIncident {
  phase: IncidentPhase;
  /** The last poll failed while a previous answer stays on screen. */
  stale: boolean;
  detail: IncidentDetail | null;
  /** Runs in the order the incident lists them; the last one is the current one. */
  runs: RunState[];
  events: (RunEvent & { run_id: string })[];
  reasoning: Reasoning | "forbidden" | null;
  changes: ChangeEvent[] | "forbidden" | null;
  /** An investigation request is in flight. */
  starting: boolean;
  startError: string | null;
}

const EMPTY: LiveIncident = {
  phase: "loading",
  stale: false,
  detail: null,
  runs: [],
  events: [],
  reasoning: null,
  changes: null,
  starting: false,
  startError: null,
};

class Stop extends Error {
  constructor(readonly phase: IncidentPhase) {
    super(phase);
  }
}

/** The body of an answer, or a stop of the whole poll for a session or access problem. */
function body<T>(result: ApiResult<T>): T {
  if (result.kind === "ok") return result.body;
  if (result.kind === "auth") throw new Stop("auth");
  if (result.kind === "forbidden") throw new Stop("forbidden");
  if (result.kind === "missing") throw new Stop("missing");
  throw new Stop("error");
}

function investigating(runs: RunState[]): boolean {
  const run = runs.at(-1);
  return run?.status === "running" && run.current_state === "investigating";
}

export function useLiveIncident(incidentId: string | undefined) {
  const token = useLive((s) => s.token);
  const [state, setState] = useState<LiveIncident>(EMPTY);
  const stateRef = useRef(state);
  stateRef.current = state;
  const pollRef = useRef<() => Promise<RunState[] | null>>(async () => null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!token || !incidentId) {
      setState({ ...EMPTY, phase: "unauthenticated" });
      return;
    }
    setState(EMPTY);
    let alive = true;
    let timer: number | undefined;
    let paused = false; // A hidden tab stops asking until it shows again.
    // What each run's events were read up to, so a poll only asks for what is new.
    const known = new Map<string, { version: number; cursor: string | null; events: RunEvent[]; state: RunState }>();
    let reasoned = ""; // The events the reasoning on screen was read with.

    async function poll(): Promise<RunState[] | null> {
      let busy = false;
      let runs: RunState[] | null = null;
      window.clearTimeout(timer);
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      const signal = abort.signal;
      try {
        const detail = body(await incidentApi.detail(token!, incidentId!, signal));
        for (const summary of detail.runs) {
          const seen = known.get(summary.run_id);
          // A running run appends receipts without changing its summary, so it is read every time.
          const ended = seen && seen.state.status !== "running" && seen.state.status !== "awaiting_human";
          if (ended && seen.version === summary.version && seen.state.updated_at === summary.updated_at) continue;
          const read = await incidentApi.run(token!, incidentId!, summary.run_id, signal);
          // A transition landing between the reads answers 503; the run keeps its last state.
          if (read.kind === "transient") continue;
          const run = body(read);
          const events = [...(seen?.events ?? [])];
          let cursor = seen?.cursor ?? null;
          for (;;) {
            const page = body(await incidentApi.events(token!, incidentId!, summary.run_id, cursor, signal));
            events.push(...page.events);
            cursor = page.next_cursor;
            if (!page.has_more) break;
          }
          known.set(summary.run_id, { version: summary.version, cursor, events, state: run });
        }
        const current = detail.runs.flatMap((summary) => known.get(summary.run_id)?.state ?? []);
        runs = current;
        const latest = current.at(-1);
        const seen = `${latest?.run_id}:${[...known.values()].reduce((total, run) => total + run.events.length, 0)}`;
        let reasoning: LiveIncident["reasoning"] = latest && seen === reasoned ? stateRef.current.reasoning : null;
        if (latest && seen !== reasoned) {
          const read = await incidentApi.reasoning(token!, incidentId!, latest.run_id, signal);
          reasoning = read.kind === "forbidden" ? "forbidden" : read.kind === "ok" ? read.body.reasoning : stateRef.current.reasoning;
          if (read.kind === "ok" || read.kind === "forbidden") reasoned = seen;
        }
        let changes: LiveIncident["changes"] = null;
        if (detail.alert?.service) {
          const read = await incidentApi.changes(token!, detail.alert.service, signal);
          changes = read.kind === "forbidden" ? "forbidden" : read.kind === "ok" ? read.body.changes : stateRef.current.changes;
        }
        if (!alive || signal.aborted) return null;
        const events = detail.runs.flatMap(
          (summary) => known.get(summary.run_id)?.events.map((event) => ({ ...event, run_id: summary.run_id })) ?? [],
        );
        busy = investigating(current);
        setState((s) => ({ ...s, phase: "ready", stale: false, detail, runs: current, events, reasoning, changes }));
      } catch (error) {
        // An aborted poll was replaced by another one, which keeps the only loop.
        if (!alive || signal.aborted || (error as { name?: string }).name === "AbortError") return null;
        const phase = error instanceof Stop ? error.phase : "error";
        // A failed read keeps what is on screen; a rejected credential or a lost grant does not.
        setState((current) =>
          phase === "error" && current.phase === "ready"
            ? { ...current, stale: true }
            : { ...EMPTY, phase, starting: current.starting },
        );
        if (phase === "auth") return null;
      }
      if (!alive || signal.aborted) return null;
      paused = document.visibilityState === "hidden";
      const fast = busy || stateRef.current.starting;
      if (!paused) timer = window.setTimeout(() => void poll(), fast ? WORKING_POLL_MS : IDLE_POLL_MS);
      return runs;
    }

    const resume = () => {
      if (paused && document.visibilityState === "visible") void poll();
    };
    document.addEventListener("visibilitychange", resume);
    // Connecting again, even with the same key, asks again after a rejected one.
    const reconnected = useLive.subscribe((now, before) => {
      if (now.phase === "connecting" && before.phase !== "connecting") void poll();
    });
    pollRef.current = poll;
    void poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
      controller.current?.abort();
      document.removeEventListener("visibilitychange", resume);
      reconnected();
      pollRef.current = async () => null;
    };
  }, [token, incidentId]);

  /**
   * Asks for an investigation, or a retry after one that ended. The key names the run it
   * follows, so a double click or a reload replays the same request instead of opening two runs.
   */
  const investigate = useCallback(async () => {
    const current = stateRef.current;
    if (!token || !incidentId || current.starting) return;
    const key = `investigate-${incidentId}-after-${current.runs.at(-1)?.run_id ?? "none"}`;
    setState((s) => ({ ...s, starting: true, startError: null }));
    window.setTimeout(() => void pollRef.current(), 1_000);
    let result: ApiResult<RunState>;
    try {
      // The API answers when the dispatch ends; the poll shows the run meanwhile.
      const version = current.detail?.workflow_version ?? "1.0.0";
      result = await incidentApi.investigate(token, incidentId, version, key, new AbortController().signal);
    } catch {
      result = { kind: "transient" };
    }
    const startError =
      result.kind === "ok" || result.kind === "conflict"
        ? null
        : result.kind === "forbidden"
          ? "Tu credencial no puede iniciar investigaciones."
          : "No pudimos pedir la investigación. Inténtalo de nuevo.";
    setState((s) => ({ ...s, starting: false, startError }));
    void pollRef.current();
  }, [token, incidentId]);

  return { ...state, investigate };
}
