import type { TriageFailure } from "./api";
import { resumePolling, stopPolling, useLive } from "./live";
import type { TriageStatus } from "./types";

/** Shows a decision the API just accepted, then polls again so the server confirms it. */
export function markTriaged(alertId: string, status: TriageStatus, incidentId?: string) {
  useLive.setState((state) => ({
    alerts: state.alerts.map((alert) =>
      alert.alert_id === alertId ? { ...alert, triage_status: status, incident_id: incidentId ?? alert.incident_id } : alert,
    ),
  }));
  stopPolling();
  resumePolling();
}

/** What the operator reads when the API refuses a decision: never codes, versions or operations. */
export const TRIAGE_FAILURE = {
  declare: {
    auth: "La API rechazó la credencial. Conecta otra y vuelve a intentarlo.",
    conflict: "Alguien más decidió sobre esta alerta. Revisa la bandeja antes de volver a intentarlo.",
    forbidden: "Tu credencial no tiene permiso para declarar incidentes.",
    rejected: "La API no aceptó la declaración. Revisa la gravedad y el impacto.",
    transient: "No pudimos declarar el incidente. Vuelve a intentarlo.",
  },
} satisfies Record<string, Record<TriageFailure, string>>;
