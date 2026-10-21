import { ArrowLeftIcon, CheckIcon, CopyIcon, EllipsisIcon, FileCode2Icon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { ServiceChip, SeverityBadge, StatusPill } from "@/components/badges";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useNow } from "@/hooks/use-now";
import { formatDayTime, formatDuration } from "@/lib/format";
import { incidentStatus } from "@/lib/status";
import { useStore } from "@/lib/store";
import type { Alert, Incident } from "@/lib/types";
import { SEVERITIES, SEVERITY } from "@/lib/vocabulary";
import { TechnicalDetails } from "./technical-details";

function SeverityMenu({ incident }: { incident: Incident }) {
  const changeSeverity = useStore((s) => s.changeSeverity);
  if (incident.state === "closed") return <SeverityBadge severity={incident.severity} />;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50" aria-label="Cambiar gravedad">
        <SeverityBadge severity={incident.severity} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-72">
        <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">Cambiar gravedad</DropdownMenuLabel>
        {SEVERITIES.map((severity) => (
          <DropdownMenuItem key={severity} onSelect={() => changeSeverity(incident.id, severity)} className="items-start">
            <span className="mt-0.5 w-4">{severity === incident.severity && <CheckIcon className="size-4" />}</span>
            <span>
              <span className="block font-medium">
                {SEVERITY[severity].short} · {SEVERITY[severity].label}
              </span>
              <span className="block text-xs text-muted-foreground">{SEVERITY[severity].description}</span>
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function IncidentHeader({ incident, alert }: { incident: Incident; alert: Alert }) {
  const now = useNow();
  const status = incidentStatus(incident);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const timing =
    incident.state === "closed"
      ? `Declarado ${formatDayTime(incident.declaredAt, now)} · resuelto en ${formatDuration((incident.resolvedAt ?? incident.closedAt!) - alert.startedAt)}`
      : incident.resolvedAt
        ? `Declarado ${formatDayTime(incident.declaredAt, now)} por ti · resuelto en ${formatDuration(incident.resolvedAt - alert.startedAt)}`
        : `Declarado ${formatDayTime(incident.declaredAt, now)} por ti · el problema lleva ${formatDuration(now - alert.startedAt)}`;

  return (
    <header>
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" aria-hidden="true" /> Bandeja
      </Link>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-medium">{incident.id}</span>
        <SeverityMenu incident={incident} />
        <ServiceChip service={incident.service} />
        <div className="ml-auto flex items-center gap-2">
          <StatusPill status={status} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Más acciones">
                <EllipsisIcon />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={async () => {
                  try {
                    await navigator.clipboard.writeText(window.location.href);
                    toast.success("Enlace copiado");
                  } catch {
                    toast.error("No pudimos copiar el enlace.");
                  }
                }}
              >
                <CopyIcon /> Copiar enlace
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setDetailsOpen(true)}>
                <FileCode2Icon /> Detalles técnicos
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <h1 className="mt-3 font-display text-3xl tracking-tight text-balance sm:text-[2.6rem] sm:leading-[1.1]">
        {incident.title}
      </h1>
      <p className="mt-3 max-w-3xl text-[15px] text-foreground/85">{incident.impact}</p>
      <p className="mt-1 text-sm text-muted-foreground">{timing}</p>
      <TechnicalDetails incident={incident} open={detailsOpen} onOpenChange={setDetailsOpen} />
    </header>
  );
}
