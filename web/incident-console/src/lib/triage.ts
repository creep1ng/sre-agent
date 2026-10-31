import { useEffect, useRef, useState } from "react";
import { newAttempt, readTriageVersion, type TriageAttempt, type TriageFailure, type TriageResult, type TriageSent } from "./api";
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

/**
 * One live decision from a dialog or popover. The version is read when it opens; a failed read is
 * read again on submit instead of guessed. A manual retry of the same choice reuses the key and
 * version sent last, so a lost answer is replayed rather than refused as someone else's decision.
 */
export function useTriageSubmission(alertId: string | undefined, open: boolean) {
  const token = useLive((s) => s.token);
  const [version, setVersion] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const last = useRef<{ choice: string; attempt: TriageAttempt } | null>(null);

  useEffect(() => {
    if (!open || !alertId || !token) return;
    setFailure(null);
    setVersion(null);
    last.current = null;
    void readTriageVersion(token, alertId).then(setVersion);
  }, [open, alertId, token]);

  async function send(choice: string, command: (token: string, attempt: TriageAttempt) => Promise<TriageSent>): Promise<TriageResult> {
    if (!token || !alertId) return { kind: "auth" };
    setPending(true);
    setFailure(null);
    try {
      let attempt = last.current?.choice === choice ? last.current.attempt : null;
      if (!attempt) {
        const read = version ?? (await readTriageVersion(token, alertId));
        if (read === null) return { kind: "transient" };
        attempt = newAttempt(read);
      }
      const sent = await command(token, attempt);
      last.current = { choice, attempt: sent.attempt };
      return sent.result;
    } finally {
      setPending(false);
    }
  }

  return { pending, failure, fail: setFailure, send };
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
