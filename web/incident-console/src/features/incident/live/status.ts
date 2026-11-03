import type { LiveIncident } from "@/lib/live-incident";

export type AgentStatus =
  | { kind: "idle" }
  | { kind: "working"; since: number }
  | { kind: "waiting"; run: string; since: number }
  | { kind: "stopped" }
  | { kind: "resolved" }
  | { kind: "closed" }
  | { kind: "other" };

/** The triage run stays open in `active`; an investigation run moves past it. */
const investigation = (run: { current_state: string }) => run.current_state !== "triage" && run.current_state !== "active";

/** What the agent is doing now (#708), from the latest investigation run. */
export function agentStatus(live: LiveIncident): AgentStatus {
  const run = live.runs.filter(investigation).at(-1);
  const state = live.detail?.state ?? "";
  if (live.starting || (run?.status === "running" && run.current_state === "investigating")) {
    // Until the requested run shows up, the clock counts from the click.
    if (live.requested && live.runs.at(-1)?.run_id === live.requested.after) return { kind: "working", since: live.requested.at };
    const first = live.events.find((event) => event.run_id === run?.run_id);
    return { kind: "working", since: first ? Date.parse(first.occurred_at) : Date.now() };
  }
  if (!run) return state === "active" ? { kind: "idle" } : settled(state);
  // A denied run stored before #788 waits for `escalate`, which nothing accepts: it stopped.
  if (run.status === "awaiting_human" && run.pending_command !== "escalate") return { kind: "waiting", run: run.run_id, since: Date.parse(run.updated_at) };
  return state === "investigating" ? { kind: "stopped" } : settled(state);
}

/** A recovered incident says so; nothing waits for anyone, so it is never amber. */
function settled(state: string): AgentStatus {
  if (state === "closed") return { kind: "closed" };
  return state === "resolved" || state === "postmortem" ? { kind: "resolved" } : { kind: "other" };
}

/** The lifecycle phase each workflow state belongs to. */
export const PHASES = ["declared", "investigation", "decision", "recovery", "postmortem", "closed"] as const;
const PHASE_OF: Record<string, number> = { active: 0, triage: 0, investigating: 1, mitigating: 2, verifying: 3, resolved: 4, postmortem: 4, closed: 5 };
export const phaseOf = (state: string) => PHASE_OF[state] ?? 0;

/** When each phase up to `current` was first reached, from the incident's events; null otherwise. */
export function phaseTimes(events: { state: string | null; occurred_at: string }[], current: number): (number | null)[] {
  const times: (number | null)[] = PHASES.map(() => null);
  const sorted = events
    .map((event) => ({ at: Date.parse(event.occurred_at), phase: event.state ? phaseOf(event.state) : 0 }))
    .filter((event) => Number.isFinite(event.at))
    .sort((a, b) => a.at - b.at);
  // The first event declares the incident; a later phase is reached by the first event in it or past it.
  times[0] = sorted[0]?.at ?? null;
  for (const event of sorted) for (let phase = 1; phase <= Math.min(event.phase, current); phase++) times[phase] ??= event.at;
  return times;
}
