import { CheckIcon, LinkIcon, XIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { StatusPill } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandItem, CommandList } from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { dismissAlert, fetchEligibleIncidents, linkAlert, type EligibleIncident } from "@/lib/api";
import { useLive } from "@/lib/live";
import { incidentStatus } from "@/lib/status";
import { useStore } from "@/lib/store";
import { markTriaged, TRIAGE_FAILURE, useTriageSubmission } from "@/lib/triage";
import type { Alert, Incident } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DISMISS_REASONS } from "@/lib/vocabulary";

export function DismissPopover({ alert }: { alert: Alert }) {
  const dismiss = useStore((s) => s.dismiss);
  const restore = useStore((s) => s.restore);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string>(DISMISS_REASONS[0]);
  const [other, setOther] = useState("");
  const live = useTriageSubmission(alert.live ? alert.id : undefined, open);
  const isOther = reason === "otro";
  const finalReason = isOther ? other.trim() : reason;

  async function confirmLive() {
    const result = await live.send(finalReason, (token, attempt) => dismissAlert(token, alert.id, finalReason, attempt));
    if (result.kind !== "ok") return live.fail(TRIAGE_FAILURE.dismiss[result.kind]);
    markTriaged(alert.id, "dismissed");
    setOpen(false);
    toast("Alerta descartada", { description: `${alert.title} · ${finalReason}` });
  }

  function confirm() {
    if (!finalReason || live.pending) return;
    if (alert.live) return void confirmLive();
    dismiss(alert.id, finalReason);
    setOpen(false);
    toast("Alerta descartada", {
      description: `${alert.title} · ${finalReason}`,
      action: { label: "Deshacer", onClick: () => restore(alert.id) },
    });
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost">
          <XIcon /> Descartar
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-3">
        <p className="mb-2 text-sm font-semibold">¿Por qué la descartas?</p>
        <div role="radiogroup" className="flex flex-col gap-1">
          {[...DISMISS_REASONS, "otro"].map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={reason === option}
              onClick={() => setReason(option)}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent",
                reason === option && "bg-secondary font-medium",
              )}
            >
              <span
                className={cn(
                  "flex size-4 items-center justify-center rounded-full border",
                  reason === option ? "border-primary bg-primary text-primary-foreground" : "border-input",
                )}
              >
                {reason === option && <CheckIcon className="size-3" />}
              </span>
              {option === "otro" ? "Otro motivo" : option}
            </button>
          ))}
        </div>
        {isOther && (
          <Input
            autoFocus
            value={other}
            onChange={(event) => setOther(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && confirm()}
            placeholder="Cuéntanos el motivo"
            className="mt-2"
          />
        )}
        <LiveFailure message={live.failure} />
        <Button className="mt-3 w-full" onClick={confirm} disabled={!finalReason || live.pending}>
          {live.pending ? "Descartando…" : "Descartar alerta"}
        </Button>
      </PopoverContent>
    </Popover>
  );
}

export function LinkPopover({ alert, incidents }: { alert: Alert; incidents: Incident[] }) {
  const link = useStore((s) => s.link);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const live = useTriageSubmission(alert.live ? alert.id : undefined, open);
  const [eligible, setEligible] = useState<EligibleIncident[] | null>(null);
  const token = useLive((s) => s.token);

  useEffect(() => {
    if (!open || !alert.live || !token) return;
    setEligible(null);
    void fetchEligibleIncidents(token, alert.id).then((result) => {
      if (result.kind === "ok") return setEligible(result.items);
      setEligible([]);
      live.fail(TRIAGE_FAILURE.link[result.kind]);
    });
    // The list is read again each time the popover opens; `live.fail` only sets state.
  }, [open, alert.live, alert.id, token]);

  async function chooseLive(incidentId: string) {
    if (live.pending) return;
    const result = await live.send(incidentId, (key, attempt) => linkAlert(key, alert.id, incidentId, attempt));
    if (result.kind !== "ok") return live.fail(TRIAGE_FAILURE.link[result.kind]);
    markTriaged(alert.id, "linked", incidentId);
    setOpen(false);
    toast.success(`Alerta vinculada a ${incidentId}`, {
      action: { label: "Ver", onClick: () => navigate(`/incidentes/${incidentId}`) },
    });
  }

  function choose(incident: Incident) {
    link(alert.id, incident.id);
    setOpen(false);
    toast.success(`Alerta vinculada a ${incident.id}`, {
      description: incident.title,
      action: { label: "Ver", onClick: () => navigate(`/incidentes/${incident.id}`) },
    });
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost">
          <LinkIcon /> Vincular a un incidente
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 p-0">
        <Command>
          <div className="border-b px-3 py-2.5">
            <p className="text-sm font-semibold">¿Es parte de un incidente abierto?</p>
            <p className="text-xs text-muted-foreground">La alerta se suma a su historia y deja la bandeja.</p>
          </div>
          <CommandList>
            <CommandEmpty>{alert.live && eligible === null ? "Buscando incidentes abiertos…" : "No hay incidentes abiertos."}</CommandEmpty>
            {alert.live && (
              <CommandGroup>
                {(eligible ?? []).map((incident) => (
                  <CommandItem
                    key={incident.incident_id}
                    value={`${incident.incident_id} ${incident.service ?? ""} ${incident.summary ?? ""}`}
                    disabled={live.pending}
                    onSelect={() => void chooseLive(incident.incident_id)}
                    className="flex-col items-start gap-1"
                  >
                    <span className="flex w-full items-center gap-2">
                      <span className="flex-1 truncate font-medium">{incident.summary ?? incident.incident_id}</span>
                      <span className="text-xs text-muted-foreground">{INCIDENT_STATE[incident.state] ?? "Abierto"}</span>
                    </span>
                    <span className="flex w-full items-center gap-2 text-xs text-muted-foreground">
                      {incident.service && <span>{incident.service}</span>}
                      <span className="font-mono">{incident.incident_id}</span>
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {!alert.live && (
              <CommandGroup>
                {incidents.map((incident) => (
                  <CommandItem
                    key={incident.id}
                    value={`${incident.id} ${incident.title}`}
                    onSelect={() => choose(incident)}
                    className="flex-col items-start gap-1"
                  >
                    <span className="flex w-full items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{incident.id}</span>
                      <span className="flex-1 truncate font-medium">{incident.title}</span>
                    </span>
                    <StatusPill status={incidentStatus(incident)} className="py-0.5" />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
        <div className="px-3 empty:hidden">
          <LiveFailure message={live.failure} />
        </div>
      </PopoverContent>
    </Popover>
  );
}

const INCIDENT_STATE: Record<string, string> = {
  active: "Activo",
  investigating: "Investigando",
  mitigating: "Mitigando",
  verifying: "Verificando",
};

function LiveFailure({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-2 mb-2 rounded-lg border border-critical-line bg-critical-soft px-3 py-2 text-sm text-critical">
      {message}
    </p>
  );
}
