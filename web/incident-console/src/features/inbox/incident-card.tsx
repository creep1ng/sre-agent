import { ArrowRightIcon } from "lucide-react";
import { Link } from "react-router";
import { ServiceChip, SeverityBadge, StatusPill } from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";
import { Button } from "@/components/ui/button";
import { IncidentContext } from "@/features/incident/summary";
import { useNow } from "@/hooks/use-now";
import { incidentStatus } from "@/lib/status";
import type { Incident } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SEVERITY, TONE_DOT } from "@/lib/vocabulary";

export function IncidentCard({ incident }: { incident: Incident }) {
  const now = useNow();
  const status = incidentStatus(incident);
  const href = `/incidentes/${incident.id}`;
  return (
    <article
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-card shadow-xs transition-all hover:border-brand-line hover:shadow-sm",
        status.needsYou && "ring-1 ring-brand-soft",
      )}
    >
      <span className={cn("absolute inset-y-0 left-0 w-1", TONE_DOT[SEVERITY[incident.severity].tone])} aria-hidden="true" />
      <div className="flex flex-col gap-3 p-4 pl-5 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono font-medium text-foreground">{incident.id}</span>
            <SeverityBadge severity={incident.severity} compact />
            <ServiceChip service={incident.service} />
            <span>
              Declarado <RelativeTime at={incident.declaredAt} />
            </span>
          </div>
          <h3 className="mt-2 text-base font-semibold">
            <Link to={href} className="outline-none after:absolute after:inset-0 focus-visible:underline">
              {incident.title}
            </Link>
          </h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            <IncidentContext incident={incident} now={now} />
          </p>
        </div>
        <div className="relative z-10 flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <StatusPill status={status} />
          {status.needsYou && status.action && (
            <Button asChild size="sm">
              <Link to={href}>
                {status.action}
                <ArrowRightIcon />
              </Link>
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}
