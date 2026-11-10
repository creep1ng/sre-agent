import { useMemo } from "react";
import { buildInbox, type InboxModel } from "@/lib/selectors";
import type { Incident } from "@/lib/types";
import { useStore } from "./store";

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
