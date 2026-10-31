import { ArrowLeftIcon, FileCode2Icon } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { ServiceChip, SeverityBadge, StatusPill } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ConnectDialog } from "@/features/inbox/connect-dialog";
import { AgentStatusPanel, STATUS_LABEL, agentStatus } from "@/features/incident/live/agent-status";
import { Row } from "@/features/incident/technical-details";
import { useNow } from "@/hooks/use-now";
import { formatDayTime } from "@/lib/format";
import { useLiveIncident, type IncidentPhase } from "@/lib/live-incident";

const BLOCKED: Record<Exclude<IncidentPhase, "ready">, { title: string; text: string }> = {
  unauthenticated: { title: "Conecta una credencial", text: "Para ver el incidente, conecta una clave de API." },
  loading: { title: "Cargando el incidente…", text: "" },
  auth: { title: "La API rechazó la credencial", text: "Conecta otra clave para seguir." },
  forbidden: { title: "Sin permiso para ver este incidente", text: "Pide a un administrador acceso de lectura." },
  missing: { title: "No encontramos ese incidente", text: "Revisa el enlace o vuelve a la bandeja." },
  error: { title: "No pudimos leer el incidente", text: "Lo intentaremos de nuevo en unos segundos." },
};

function Blocked({ phase }: { phase: Exclude<IncidentPhase, "ready"> }) {
  const [connectOpen, setConnectOpen] = useState(false);
  const { title, text } = BLOCKED[phase];
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
      <h1 className="font-display text-3xl">{title}</h1>
      {text && <p className="mt-2 text-muted-foreground">{text}</p>}
      {phase === "unauthenticated" || phase === "auth" ? (
        <Button className="mt-6" onClick={() => setConnectOpen(true)}>
          Conectar API
        </Button>
      ) : (
        phase !== "loading" && (
          <Button asChild className="mt-6" variant="secondary">
            <Link to="/">Ir a la bandeja</Link>
          </Button>
        )
      )}
      <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
    </div>
  );
}

/** The incident as the API records it: what the agent is doing now and the story so far. */
export function LiveIncidentPage() {
  const { incidentId } = useParams();
  const live = useLiveIncident(incidentId);
  const now = useNow();
  const [detailsOpen, setDetailsOpen] = useState(false);
  if (live.phase !== "ready" || !live.detail) return <Blocked phase={live.phase === "ready" ? "loading" : live.phase} />;

  const { detail } = live;
  const status = agentStatus(live);
  const label = STATUS_LABEL[status.kind];
  const declared = live.events[0] ? Date.parse(live.events[0].occurred_at) : Date.parse(detail.updated_at);
  return (
    <div className="lg:grid lg:min-h-dvh lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_400px]">
      <div className="mx-auto w-full max-w-5xl min-w-0 px-4 py-6 sm:px-8 lg:py-8">
        <header>
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
            <ArrowLeftIcon className="size-4" aria-hidden="true" /> Bandeja
          </Link>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {detail.severity && <SeverityBadge severity={detail.severity} />}
            {detail.alert && <ServiceChip service={detail.alert.service} />}
            <div className="ml-auto flex items-center gap-2">
              <StatusPill status={{ ...label, working: status.kind === "working", needsYou: status.kind !== "working" }} />
              <Button variant="ghost" size="sm" onClick={() => setDetailsOpen(true)}>
                <FileCode2Icon /> Detalles técnicos
              </Button>
            </div>
          </div>
          <h1 className="mt-3 font-display text-3xl tracking-tight text-balance sm:text-[2.6rem] sm:leading-[1.1]">
            {detail.alert?.summary ?? "Incidente declarado"}
          </h1>
          {detail.impact && <p className="mt-3 max-w-3xl text-[15px] text-foreground/85">{detail.impact}</p>}
          <p className="mt-1 text-sm text-muted-foreground">Declarado {formatDayTime(declared, now)}</p>
        </header>
        <div className="mt-6 min-w-0">
          <AgentStatusPanel live={live} status={status} onStart={() => void live.investigate()} />
        </div>
      </div>
      <Sheet open={detailsOpen} onOpenChange={setDetailsOpen}>
        <SheetContent className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Detalles técnicos</SheetTitle>
            <SheetDescription>Para auditoría y soporte. No hacen falta para atender el incidente.</SheetDescription>
          </SheetHeader>
          <dl className="overflow-y-auto px-4">
            <Row label="Incidente" values={[detail.incident_id]} />
            <Row label="Workflow" values={[`incident-response 1.0.0 · ${detail.state}`]} />
            <Row label="Ejecuciones del agente" values={live.runs.map((run) => `${run.run_id} · ${run.status}`)} />
            {detail.alert && <Row label="Alerta de origen" values={[detail.alert.alert_id]} />}
          </dl>
        </SheetContent>
      </Sheet>
    </div>
  );
}
