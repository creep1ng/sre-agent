import { create } from "zustand";
import { fetchAlerts } from "./api";
import type { LiveAlert } from "./types";

export const POLL_MS = 15_000;

export type LivePhase =
  | "unauthenticated"
  | "connecting"
  | "live"
  | "empty"
  | "auth"
  | "forbidden"
  | "error";

interface LiveState {
  token: string | null;
  alerts: LiveAlert[];
  phase: LivePhase;
  /** The last poll failed but a previous list is still on screen. */
  stale: boolean;
  lastSuccessAt: number | null;
  connect: (token: string) => void;
  disconnect: () => void;
  retry: () => void;
}

export const useLive = create<LiveState>((set) => ({
  token: null,
  alerts: [],
  phase: "unauthenticated",
  stale: false,
  lastSuccessAt: null,
  connect: (token) => {
    stop();
    set({ token, alerts: [], phase: "connecting", stale: false, lastSuccessAt: null });
    start();
  },
  disconnect: () => {
    stop();
    set({ token: null, alerts: [], phase: "unauthenticated", stale: false, lastSuccessAt: null });
  },
  retry: () => {
    if (!useLive.getState().token) return;
    stop();
    start();
  },
}));

let active = false;
let generation = 0;
let controller: AbortController | null = null;
let timer: number | undefined;

function schedule(delay: number) {
  window.clearTimeout(timer);
  timer = window.setTimeout(() => void poll(), delay);
}

async function poll() {
  const token = useLive.getState().token;
  if (!active || !token) return;
  const run = ++generation;
  controller?.abort();
  controller = new AbortController();
  let result;
  try {
    result = await fetchAlerts(token, controller.signal);
  } catch {
    return;
  }
  if (!active || run !== generation) return;
  const state = useLive.getState();
  if (result.kind === "ok") {
    useLive.setState({
      alerts: result.alerts,
      phase: result.alerts.length > 0 ? "live" : "empty",
      stale: false,
      lastSuccessAt: Date.now(),
    });
    schedule(POLL_MS);
  } else if (result.kind === "auth") {
    // A rejected credential stops the loop until the operator connects another one.
    useLive.setState({ alerts: [], phase: "auth", stale: false, lastSuccessAt: null });
  } else if (result.kind === "forbidden") {
    // Grants can change while the page is open: keep asking.
    useLive.setState({ alerts: [], phase: "forbidden", stale: false, lastSuccessAt: null });
    schedule(POLL_MS);
  } else {
    useLive.setState({
      stale: state.lastSuccessAt !== null,
      phase: state.lastSuccessAt !== null ? state.phase : "error",
    });
    schedule(result.retryAfterMs ?? POLL_MS);
  }
}

/** Starts or resumes the loop for a credential already in memory. */
export function resumePolling() {
  if (active || !useLive.getState().token) return;
  active = true;
  void poll();
}

export function stopPolling() {
  active = false;
  generation += 1;
  window.clearTimeout(timer);
  controller?.abort();
  controller = null;
}

function start() {
  stopPolling();
  resumePolling();
}
