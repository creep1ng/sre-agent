import { CheckIcon, LinkIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { StatusPill } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandItem, CommandList } from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { incidentStatus } from "@/lib/status";
import { useStore } from "@/lib/store";
import type { Alert, Incident } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DISMISS_REASONS } from "@/lib/vocabulary";

export function DismissPopover({ alert }: { alert: Alert }) {
  const dismiss = useStore((s) => s.dismiss);
  const restore = useStore((s) => s.restore);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string>(DISMISS_REASONS[0]);
  const [other, setOther] = useState("");
  const isOther = reason === "otro";
  const finalReason = isOther ? other.trim() : reason;

  function confirm() {
    if (!finalReason) return;
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
        <Button className="mt-3 w-full" onClick={confirm} disabled={!finalReason}>
          Descartar alerta
        </Button>
      </PopoverContent>
    </Popover>
  );
}

export function LinkPopover({ alert, incidents }: { alert: Alert; incidents: Incident[] }) {
  const link = useStore((s) => s.link);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

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
            <CommandEmpty>No hay incidentes abiertos.</CommandEmpty>
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
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
