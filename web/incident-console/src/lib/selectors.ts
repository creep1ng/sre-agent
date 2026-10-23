import { useMemo } from "react";
import { useLive } from "./live";
import { useStore } from "./store";
import { incidentStatus } from "./status";
import type { Alert, Incident, LiveAlert } from "./types";
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

/** Declared, linked and dismissed alerts stay listed without asking for attention. */
function needsAttention(alert: Alert): boolean {
  if (!alert.live) return true;
  return alert.triageStatus === "new" || alert.triageStatus === "triaging";
}

/** Maps a real API alert onto the inbox card shape. */
export function liveAlertToAlert(alert: LiveAlert): Alert {
  const detectedAt = Date.parse(alert.observed_at);
  const [title, ...rest] = alert.summary.split(": ");
  const summary = rest.join(": ").split(" Evidence:")[0];
  return {
    id: alert.alert_id,
    scenario: "payments",
    title,
    summary,
    service: alert.service,
    severity: alert.severity,
    startedAt: detectedAt,
    detectedAt,
    signal: { label: "Tasa de error", unit: "%", threshold: 0, baseline: 0, peak: 0, max: 1 },
    rule: alert.source,
    source: alert.source,
    suggestedImpact: summary,
    status: "new",
    incidentId: alert.incident_id ?? undefined,
    live: true,
    triageStatus: alert.triage_status,
  };
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
  return {
    newAlerts,
    needsYou,
    working,
    recent,
    active,
    attention: newAlerts.filter(needsAttention).length + needsYou.length,
  };
}

export function useInbox(now: number): InboxModel {
  const alerts = useStore((s) => s.alerts);
  const incidents = useStore((s) => s.incidents);
  // The model only changes with the data; `now` matters for the recent window only.
  const minute = Math.floor(now / 60_000);
  return useMemo(() => buildInbox(alerts, incidents, minute * 60_000), [alerts, incidents, minute]);
}

export function useLiveInbox(now: number): InboxModel {
  const alerts = useLive((s) => s.alerts);
  const minute = Math.floor(now / 60_000);
  return useMemo(
    () => buildInbox(alerts.map(liveAlertToAlert), [], minute * 60_000),
    [alerts, minute],
  );
}

export function useIncident(id: string | undefined): Incident | undefined {
  return useStore((s) => s.incidents.find((incident) => incident.id === id));
}
