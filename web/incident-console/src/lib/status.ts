import type { Incident } from "./types";
import type { Tone } from "./vocabulary";

export interface IncidentStatus {
  label: string;
  tone: Tone;
  /** The agent is doing something right now. */
  working: boolean;
  /** The next move is the human's. */
  needsYou: boolean;
  /** Label of the button that takes the human to that move. */
  action?: string;
  /** What the agent is doing, for the presence widget. */
  agentLabel?: string;
}

export function incidentStatus(incident: Incident): IncidentStatus {
  switch (incident.state) {
    case "investigating": {
      if (incident.job?.failure) {
        return { label: "El agente se detuvo", tone: "critical", working: false, needsYou: true, action: "Ver qué pasó" };
      }
      const kind = incident.job?.kind;
      const label =
        kind === "revision"
          ? "El agente prepara otra propuesta"
          : kind === "reinvestigation"
            ? "El agente vuelve a investigar"
            : "El agente está investigando";
      const agentLabel =
        kind === "revision" ? "Preparando otra propuesta" : kind === "reinvestigation" ? "Investigando de nuevo" : "Investigando";
      return { label, tone: "info", working: true, needsYou: false, agentLabel };
    }
    case "mitigating":
      return { label: "Esperando tu decisión", tone: "warning", working: false, needsYou: true, action: "Revisar propuesta" };
    case "verifying": {
      const verification = incident.verification;
      if (!verification?.appliedAt) {
        return { label: "Aplica la mitigación", tone: "warning", working: false, needsYou: true, action: "Ver los pasos" };
      }
      if (!verification.stableSuggestedAt) {
        return {
          label: "Vigilando la recuperación",
          tone: "info",
          working: true,
          needsYou: false,
          agentLabel: "Vigilando la recuperación",
        };
      }
      return { label: "Listo para confirmar", tone: "success", working: false, needsYou: true, action: "Confirmar recuperación" };
    }
    case "resolved":
    case "postmortem":
      if (incident.postmortem?.status === "review") {
        return { label: "Revisa el postmortem", tone: "warning", working: false, needsYou: true, action: "Revisar postmortem" };
      }
      return {
        label: "El agente redacta el postmortem",
        tone: "info",
        working: true,
        needsYou: false,
        agentLabel: "Redactando el postmortem",
      };
    case "closed":
      return { label: "Cerrado", tone: "success", working: false, needsYou: false };
  }
}

export const PHASES = [
  { key: "declared", label: "Declarado", owner: "Tú" },
  { key: "investigation", label: "Investigación", owner: "Agente" },
  { key: "decision", label: "Decisión", owner: "Tú" },
  { key: "recovery", label: "Recuperación", owner: "Tú y el agente" },
  { key: "postmortem", label: "Postmortem", owner: "Agente y tú" },
  { key: "closed", label: "Cierre", owner: "Tú" },
] as const;

export function currentPhase(incident: Incident): number {
  switch (incident.state) {
    case "investigating":
      return 1;
    case "mitigating":
      return 2;
    case "verifying":
      return 3;
    case "resolved":
    case "postmortem":
      return 4;
    case "closed":
      return 6;
  }
}

/** When each phase ended, if it did (the last time, after loops). */
export function phaseEnds(incident: Incident): (number | undefined)[] {
  const lastProposal = incident.proposals.at(-1);
  const approved = [...incident.proposals].reverse().find((p) => p.decision?.outcome === "approved");
  const phase = currentPhase(incident);
  return [
    incident.declaredAt,
    phase > 1 ? lastProposal?.createdAt : undefined,
    phase > 2 ? approved?.decision?.at : undefined,
    phase > 3 ? incident.verification?.confirmedAt : undefined,
    phase > 4 ? incident.postmortem?.approvedAt : undefined,
    incident.closedAt,
  ];
}
