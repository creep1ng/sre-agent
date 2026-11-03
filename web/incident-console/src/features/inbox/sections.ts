import { useTitle } from "@/lib/title";
import type { LiveAlert } from "@/lib/types";
import type { ChangeEvent, InboxIncident } from "./live-data";

/** States in which the service is back: recovered, in its postmortem, or closed. */
const RECOVERED = new Set(["resolved", "postmortem", "closed"]);
/** Last night runs from 20:00 the day before until 08:00, in the browser's time zone. */
const NIGHT_START_HOUR = 20;
const NIGHT_END_HOUR = 8;

export type NightEvent =
  | { kind: "alert"; at: number; alert: LiveAlert }
  | { kind: "incident"; at: number; incident: InboxIncident }
  | { kind: "change"; at: number; change: ChangeEvent };

export interface InboxSections {
  /** Incidents whose latest run waits for a human, the longest wait first. */
  decisions: InboxIncident[];
  /** Incidents that recovered or whose run ended since the operator last looked. */
  coffee: InboxIncident[];
  /** What happened last night, in order. */
  night: NightEvent[];
}

/** The night before `now`: [yesterday 20:00, today 08:00), or up to `now` while it lasts. */
export function lastNight(now: number): { start: number; end: number } {
  const morning = new Date(now);
  morning.setHours(NIGHT_END_HOUR, 0, 0, 0);
  const start = new Date(morning);
  start.setDate(start.getDate() - 1);
  start.setHours(NIGHT_START_HOUR);
  // Before 08:00 the night is still going.
  return { start: start.getTime(), end: Math.min(morning.getTime(), now) };
}

const time = (iso: string) => Date.parse(iso);

export function inboxSections(
  incidents: InboxIncident[],
  alerts: LiveAlert[],
  changes: ChangeEvent[],
  now: number,
  lastSeen: number,
): InboxSections {
  const decisions = incidents
    .filter((incident) => incident.pending_decision)
    .sort((a, b) => time(a.pending_decision!.waiting_since) - time(b.pending_decision!.waiting_since));
  const coffee = incidents.filter(
    (incident) =>
      !incident.pending_decision &&
      time(incident.updated_at) >= lastSeen &&
      (RECOVERED.has(incident.state) || incident.latest_run?.status === "terminated"),
  );
  const { start, end } = lastNight(now);
  const within = (at: number) => at >= start && at < end;
  const night: NightEvent[] = [
    ...alerts.map((alert) => ({ kind: "alert" as const, at: time(alert.observed_at), alert })),
    ...incidents.map((incident) => ({ kind: "incident" as const, at: time(incident.opened_at), incident })),
    ...changes.map((change) => ({ kind: "change" as const, at: time(change.occurred_at), change })),
  ]
    .filter((event) => within(event.at))
    .sort((a, b) => a.at - b.at);
  return { decisions, coffee, night };
}

/** An incident's headline as the incident page words it: the investigator's title, else the alert's. */
export function useHeadline() {
  const title = useTitle();
  return (incident: InboxIncident) => incident.title || title(incident.summary) || incident.impact || incident.incident_id;
}
