import { TableIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDuration, formatTime } from "@/lib/format";
import type { Alert, Incident } from "@/lib/types";
import { cn } from "@/lib/utils";

/*
 * The closed incident summed up: one hero figure (time to resolve), where the time went,
 * no stat cards or lists; the chart has its table twin ("Ver los datos").
 */

const PHASE_FILL = ["bg-chart-step-1", "bg-chart-step-2", "bg-chart-step-3"];

function closureFacts(incident: Incident, alert: Alert) {
  return {
    start: alert.startedAt,
    detected: alert.detectedAt,
    applied: incident.verification?.appliedAt,
    resolved: incident.resolvedAt ?? incident.closedAt!,
  };
}

/** The one number the summary leads with: same sans as the rest, proportional figures. */
function Hero({ value, caption }: { value: string; caption: ReactNode }) {
  return (
    <div>
      <div className="text-5xl leading-none font-semibold tracking-tight">{value}</div>
      <p className="mt-2 text-sm text-muted-foreground">{caption}</p>
    </div>
  );
}

function DataTwin({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline dark:text-brand-line"
      >
        <TableIcon className="size-3.5" aria-hidden="true" />
        {open ? "Ocultar los datos" : "Ver los datos"}
      </button>
      {open && <div className="mt-2 overflow-x-auto">{children}</div>}
    </div>
  );
}

function DataTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <table className="w-full max-w-xl text-left text-sm">
      <thead className="text-xs text-muted-foreground">
        <tr>
          {head.map((cell) => (
            <th key={cell} scope="col" className="border-b py-1.5 pr-4 font-medium">
              {cell}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="tabular">
        {rows.map((row, index) => (
          <tr key={index} className="border-b border-border/60 last:border-b-0">
            {row.map((cell, cellIndex) => (
              <td key={cellIndex} className="py-1.5 pr-4">
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Where the time went, in one bar of phases in order. */
export function ClosureTimeline({ incident, alert }: { incident: Incident; alert: Alert }) {
  const facts = closureFacts(incident, alert);
  const phases = [
    { label: "Detectar", detail: "Hasta que saltó la alerta", from: facts.start, to: facts.detected },
    { label: "Mitigar", detail: "Declarar, investigar, decidir y aplicar", from: facts.detected, to: facts.applied ?? facts.resolved },
    ...(facts.applied
      ? [{ label: "Confirmar", detail: "Hasta que la señal quedó estable", from: facts.applied, to: facts.resolved }]
      : []),
  ].filter((phase) => phase.to > phase.from);

  return (
    <div>
      <Hero
        value={formatDuration(facts.resolved - facts.start)}
        caption="de impacto: desde que empezó la falla hasta que confirmaste la recuperación"
      />
      <TooltipProvider delayDuration={80}>
        <div className="mt-6 flex gap-0.5" role="group" aria-label="En qué se fue el tiempo">
          {phases.map((phase, index) => (
            <Tooltip key={phase.label}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="group -my-2 min-w-1 py-2 outline-none"
                  style={{ flex: `${phase.to - phase.from} 1 0` }}
                  aria-label={`${phase.label}: ${formatDuration(phase.to - phase.from)}, de ${formatTime(phase.from)} a ${formatTime(phase.to)}`}
                >
                  <span
                    className={cn(
                      "block h-3 transition-opacity group-hover:opacity-80 group-focus-visible:ring-2 group-focus-visible:ring-ring group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-card",
                      PHASE_FILL[index],
                      index === phases.length - 1 && "rounded-r-[4px]",
                    )}
                  />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">
                <span className="font-semibold">{formatDuration(phase.to - phase.from)}</span> · {phase.detail} (
                {formatTime(phase.from)}–{formatTime(phase.to)})
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
      </TooltipProvider>
      <div className="mt-1.5 flex justify-between gap-4 text-xs text-muted-foreground tabular">
        <span>{formatTime(facts.start)} · empezó la falla</span>
        <span>{formatTime(facts.resolved)} · resuelto</span>
      </div>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2" aria-hidden="true">
        {phases.map((phase, index) => (
          <span key={phase.label} className="flex items-center gap-2 text-sm">
            <span className={cn("size-2.5 rounded-[3px]", PHASE_FILL[index])} />
            <span className="text-muted-foreground">{phase.label}</span>
            <span className="font-semibold">{formatDuration(phase.to - phase.from)}</span>
          </span>
        ))}
      </div>
      <DataTwin>
        <DataTable
          head={["Fase", "Desde", "Hasta", "Duración"]}
          rows={phases.map((phase) => [
            phase.label,
            formatTime(phase.from),
            formatTime(phase.to),
            formatDuration(phase.to - phase.from),
          ])}
        />
      </DataTwin>
    </div>
  );
}
