import { useMemo } from "react";
import { useStore } from "./store";
import { incidentStatus } from "./status";
import type { Alert, Incident } from "./types";
import { SEVERITY } from "./vocabulary";

const RECENT_MS = 36 * 60 * 60 * 1000;

export type RecentItem =
  | { kind: "closed"; at: number; incident: Incident }
  | { kind: "dismissed"; at: number; alert: Alert }
  | { kind: "linked"; at: number; alert: Alert };

export interface InboxModel {
  newAlerts: Alert[];
  needsYou: Incident[];
  working: Incident[];
  recent: RecentItem[];
  active: Incident[];
  attention: number;
}

function bySeverity<T extends { severity: Alert["severity"] }>(time: (item: T) => number) {
  return (a: T, b: T) => SEVERITY[a.severity].rank - SEVERITY[b.severity].rank || time(b) - time(a);
}

export function buildInbox(alerts: Alert[], incidents: Incident[], now: number): InboxModel {
  const newAlerts = alerts.filter((a) => a.status === "new").sort(bySeverity((a) => a.detectedAt));
  const active = incidents.filter((i) => i.state !== "closed").sort(bySeverity((i) => i.declaredAt));
  const needsYou = active.filter((i) => incidentStatus(i).needsYou);
  const working = active.filter((i) => !incidentStatus(i).needsYou);
  const recent: RecentItem[] = [
    ...incidents
      .filter((i) => i.closedAt && now - i.closedAt < RECENT_MS)
      .map((incident) => ({ kind: "closed" as const, at: incident.closedAt!, incident })),
    ...alerts
      .filter((a) => a.status === "dismissed" && a.dismissedAt)
      .map((alert) => ({ kind: "dismissed" as const, at: alert.dismissedAt!, alert })),
    ...alerts
      .filter((a) => a.status === "linked")
      .map((alert) => ({ kind: "linked" as const, at: alert.detectedAt, alert })),
  ].sort((a, b) => b.at - a.at);
  return { newAlerts, needsYou, working, recent, active, attention: newAlerts.length + needsYou.length };
}

export function useInbox(now: number): InboxModel {
  const alerts = useStore((s) => s.alerts);
  const incidents = useStore((s) => s.incidents);
  // The model only changes with the data; `now` matters for the recent window only.
  const minute = Math.floor(now / 60_000);
  return useMemo(() => buildInbox(alerts, incidents, minute * 60_000), [alerts, incidents, minute]);
}

export function useIncident(id: string | undefined): Incident | undefined {
  return useStore((s) => s.incidents.find((incident) => incident.id === id));
}
