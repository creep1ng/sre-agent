import { formatClock } from "@/lib/format";
import type { Incident } from "@/lib/types";
import { RISK } from "@/lib/vocabulary";

/** One line that says where the incident stands, in the words of its next step. */
export function IncidentContext({ incident, now }: { incident: Incident; now: number }) {
  const job = incident.job;
  switch (incident.state) {
    case "investigating": {
      if (job?.failure) return <span className="text-critical">{job.failure.reason}</span>;
      const current = job?.steps[job.done];
      return (
        <span className="flex flex-wrap items-center gap-x-2">
          {current ? <span className="text-shimmer">{current.label}…</span> : <span>Preparando la propuesta…</span>}
          {job && (
            <span className="text-muted-foreground tabular">
              · {job.findings.length} hallazgos · {formatClock(now - job.startedAt)}
            </span>
          )}
        </span>
      );
    }
    case "mitigating": {
      const proposal = incident.proposals.at(-1);
      if (!proposal) return null;
      return (
        <span>
          Propone: <span className="font-medium text-foreground">{proposal.summary}</span> · {RISK[proposal.risk].label}
        </span>
      );
    }
    case "verifying": {
      const verification = incident.verification;
      if (!verification?.appliedAt) return <span>Aprobaste la mitigación. Aplica los pasos y avísale al agente.</span>;
      if (!verification.stableSuggestedAt) return <span className="text-shimmer">El agente vigila la señal después de tu cambio…</span>;
      return <span>La señal se mantiene bajo el umbral. Confirma la recuperación.</span>;
    }
    case "resolved":
    case "postmortem":
      return incident.postmortem?.status === "review" ? (
        <span>El borrador está listo: revísalo y cierra el incidente.</span>
      ) : (
        <span className="text-shimmer">El agente está redactando el postmortem…</span>
      );
    case "closed":
      return <span>Cerrado con postmortem aprobado.</span>;
  }
}
