import { CheckIcon } from "lucide-react";
import { formatTime } from "@/lib/format";
import { PHASES, currentPhase, incidentStatus, phaseEnds } from "@/lib/status";
import type { Incident } from "@/lib/types";
import { cn } from "@/lib/utils";

/** The whole lifecycle in one line: where the incident is and who has the next move. */
export function LifecycleStepper({ incident }: { incident: Incident }) {
  const current = currentPhase(incident);
  const ends = phaseEnds(incident);
  const status = incidentStatus(incident);
  const closed = incident.state === "closed";
  const step = Math.min(current, PHASES.length - 1);
  return (
    <nav aria-label="Progreso del incidente">
      <div className="sm:hidden">
        <div className="flex items-baseline justify-between gap-2 text-sm">
          <span className="font-semibold">
            {closed ? "Cerrado" : `Paso ${step + 1} de ${PHASES.length} · ${PHASES[step].label}`}
          </span>
          <span className={cn("text-xs", closed ? "text-success" : status.working ? "text-info" : "text-warning")}>
            {closed ? "Completado" : status.working ? "Agente · en curso" : "Te toca"}
          </span>
        </div>
        <div className="mt-2 flex gap-1" aria-hidden="true">
          {PHASES.map((phase, index) => (
            <span
              key={phase.key}
              className={cn(
                "h-1.5 flex-1 rounded-full",
                index < current || closed ? "bg-primary dark:bg-brand-line" : index === current ? "bg-warning" : "bg-border",
                index === current && status.working && "bg-info",
              )}
            />
          ))}
        </div>
      </div>
      <ol className="hidden items-start sm:flex">
        {PHASES.map((phase, index) => {
          const done = index < current || (index === 5 && incident.state === "closed");
          const active = index === current && incident.state !== "closed";
          const end = ends[index];
          return (
            <li key={phase.key} className="relative flex flex-1 flex-col items-center text-center">
              {index > 0 && (
                <span
                  className={cn(
                    "absolute top-3.5 right-1/2 left-[-50%] h-0.5 rounded-full",
                    index <= current ? "bg-primary dark:bg-brand-line" : "bg-border",
                  )}
                  aria-hidden="true"
                />
              )}
              <span
                className={cn(
                  "relative z-10 flex size-7 items-center justify-center rounded-full border-2 text-xs font-semibold transition-colors",
                  done && "border-primary bg-primary text-primary-foreground dark:border-brand-line dark:bg-brand-line dark:text-background",
                  active &&
                    (status.working
                      ? "border-info bg-card text-info animate-pulse-ring"
                      : "border-warning bg-warning-soft text-warning"),
                  !done && !active && "border-border bg-card text-muted-foreground",
                )}
                aria-current={active ? "step" : undefined}
              >
                {done ? <CheckIcon className="size-3.5" /> : index + 1}
              </span>
              <span className={cn("mt-2 text-sm font-medium", !done && !active && "text-muted-foreground")}>{phase.label}</span>
              <span className={cn("text-xs", active ? (status.working ? "text-info" : "text-warning") : "text-muted-foreground")}>
                {done && end ? formatTime(end) : active ? (status.working ? "Agente · en curso" : "Te toca") : phase.owner}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
