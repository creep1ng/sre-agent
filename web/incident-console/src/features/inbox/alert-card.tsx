import { ChevronDownIcon, SirenIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ServiceChip, SeverityBadge } from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";
import { SignalChart, Sparkline } from "@/components/signal-chart";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useNow } from "@/hooks/use-now";
import { formatDayTime, formatSignal, formatTime } from "@/lib/format";
import { currentValue } from "@/lib/signal";
import type { Alert, Incident } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SEVERITY, TONE_DOT } from "@/lib/vocabulary";
import { DismissPopover, LinkPopover } from "./alert-actions";
import { TriageBadge } from "./triage-badge";

export function AlertCard({
  alert,
  openIncidents,
  onDeclare,
}: {
  alert: Alert;
  openIncidents: Incident[];
  onDeclare: (alert: Alert) => void;
}) {
  const now = useNow();
  const [open, setOpen] = useState(false);

  if (alert.live) {
    const undecided = alert.triageStatus === "new" || alert.triageStatus === "triaging";
    return (
      <article data-alert-id={alert.id} className="group relative overflow-hidden rounded-xl border bg-card shadow-xs">
        <span className={cn("absolute inset-y-0 left-0 w-1", TONE_DOT[SEVERITY[alert.severity].tone])} aria-hidden="true" />
        <div className="p-4 pl-5">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <SeverityBadge severity={alert.severity} />
            <ServiceChip service={alert.service} />
            {alert.triageStatus && <TriageBadge status={alert.triageStatus} />}
            <span>{formatDayTime(alert.detectedAt, now)}</span>
          </div>
          <h3 className="mt-2 text-base font-semibold text-balance">{alert.title}</h3>
          {alert.summary && <p className="mt-0.5 text-sm text-muted-foreground">{alert.summary}</p>}
        </div>
        {(undecided || alert.incidentId) && (
          <div className="flex flex-wrap items-center gap-1.5 border-t bg-muted/40 px-3 py-2.5 pl-4">
            {undecided ? (
              <Button onClick={() => onDeclare(alert)}>
                <SirenIcon /> Declarar incidente
              </Button>
            ) : (
              <Button variant="ghost" asChild>
                <Link to={`/incidentes/${alert.incidentId}`}>Ver incidente</Link>
              </Button>
            )}
          </div>
        )}
      </article>
    );
  }

  const value = currentValue(alert, now);
  const above = value > alert.signal.threshold;

  return (
    <Collapsible open={open} onOpenChange={setOpen} asChild>
      <article className="group relative overflow-hidden rounded-xl border bg-card shadow-xs transition-shadow hover:shadow-sm">
        <span className={cn("absolute inset-y-0 left-0 w-1", TONE_DOT[SEVERITY[alert.severity].tone])} aria-hidden="true" />
        <div className="flex flex-col gap-4 p-4 pl-5 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <SeverityBadge severity={alert.severity} />
              <ServiceChip service={alert.service} />
              <span>
                Alerta nueva · <RelativeTime at={alert.detectedAt} />
              </span>
            </div>
            <h3 className="mt-2 text-base font-semibold text-balance">{alert.title}</h3>
            <p className="mt-0.5 text-sm text-muted-foreground">{alert.summary}</p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <Sparkline alert={alert} />
            <div className="w-20 text-right">
              <div className={cn("text-lg leading-tight font-semibold", above ? "text-critical" : "text-foreground")}>
                {formatSignal(value, alert.signal.unit)}
              </div>
              <div className="text-[11px] leading-tight text-muted-foreground">{alert.signal.label.toLowerCase()} ahora</div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 border-t bg-muted/40 px-3 py-2.5 pl-4">
          <Button onClick={() => onDeclare(alert)}>
            <SirenIcon /> Declarar incidente
          </Button>
          <DismissPopover alert={alert} />
          {openIncidents.length > 0 && <LinkPopover alert={alert} incidents={openIncidents} />}
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="ml-auto text-muted-foreground" aria-label="Ver qué detectamos">
              Qué detectamos
              <ChevronDownIcon className={cn("transition-transform", open && "rotate-180")} />
            </Button>
          </CollapsibleTrigger>
        </div>

        <CollapsibleContent className="data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down overflow-hidden">
          <div className="grid gap-5 border-t p-4 pl-5 md:grid-cols-[minmax(0,1fr)_220px]">
            <div>
              <p className="mb-1 text-sm font-medium">{alert.signal.label} · últimos 30 minutos</p>
              <SignalChart alert={alert} windowMs={30 * 60_000} stepMs={30_000} height={170} />
            </div>
            <dl className="grid content-start gap-3 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">Regla</dt>
                <dd>{alert.rule}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Empezó</dt>
                <dd>
                  {formatTime(alert.startedAt)} · detectada a las {formatTime(alert.detectedAt)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Fuente</dt>
                <dd>{alert.source}</dd>
              </div>
            </dl>
          </div>
        </CollapsibleContent>
      </article>
    </Collapsible>
  );
}
