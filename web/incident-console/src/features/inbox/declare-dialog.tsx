import { SirenIcon } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { AgentAvatar } from "@/components/brand";
import { ServiceChip } from "@/components/badges";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useNow } from "@/hooks/use-now";
import { formatDayTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Alert, Severity } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SEVERITIES, SEVERITY, TONE_CLASSES } from "@/lib/vocabulary";

export function SeverityPicker({ value, onChange }: { value: Severity; onChange: (value: Severity) => void }) {
  return (
    <div role="radiogroup" aria-label="Gravedad" className="grid grid-cols-4 gap-2">
      {SEVERITIES.map((severity) => {
        const meta = SEVERITY[severity];
        const selected = value === severity;
        return (
          <button
            key={severity}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(severity)}
            className={cn(
              "flex flex-col items-center gap-0.5 rounded-lg border px-2 py-2 text-xs transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
              selected
                ? [TONE_CLASSES[meta.tone], "ring-2 ring-current/30"]
                : "border-border bg-card text-muted-foreground hover:border-brand-line hover:text-foreground",
            )}
          >
            <span className="text-sm font-semibold">{meta.short}</span>
            <span>{meta.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function DeclareDialog({ alert, onOpenChange }: { alert: Alert | null; onOpenChange: (open: boolean) => void }) {
  const declare = useStore((s) => s.declare);
  const navigate = useNavigate();
  const now = useNow();
  const [severity, setSeverity] = useState<Severity>("sev1");
  const [impact, setImpact] = useState("");

  useEffect(() => {
    if (!alert) return;
    setSeverity(alert.severity);
    setImpact(alert.suggestedImpact);
  }, [alert]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!alert) return;
    const id = declare(alert.id, { severity, impact });
    onOpenChange(false);
    if (id) {
      toast.success(`${id} declarado`, { description: "El agente ya está investigando." });
      navigate(`/incidentes/${id}`);
    }
  }

  return (
    <Dialog open={alert !== null} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 p-0 sm:max-w-lg">
        {alert && (
          <form onSubmit={submit}>
            <DialogHeader className="gap-1 border-b p-5 pb-4 text-left">
              <DialogTitle className="text-lg">Declarar incidente</DialogTitle>
              <DialogDescription className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="font-medium text-foreground">{alert.title}</span>
                <ServiceChip service={alert.service} />
                <span>detectada {formatDayTime(alert.detectedAt, now)}</span>
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-5 p-5">
              <div className="flex flex-col gap-2">
                <Label>¿Qué tan grave es?</Label>
                <SeverityPicker value={severity} onChange={setSeverity} />
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{SEVERITY[severity].label}:</span>{" "}
                  {SEVERITY[severity].description}
                  {severity === alert.severity && " Es la gravedad que sugiere la alerta."}
                </p>
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="impact">¿Qué notan tus clientes?</Label>
                <Textarea
                  id="impact"
                  value={impact}
                  onChange={(event) => setImpact(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
                  }}
                  rows={2}
                  className="resize-none"
                />
                <p className="text-xs text-muted-foreground">Lo sugerimos a partir de la alerta. Cámbialo si hace falta.</p>
              </div>

              <div className="flex items-center gap-3 rounded-lg bg-secondary px-3 py-2.5 text-sm">
                <AgentAvatar />
                <span>Al declararlo, el agente empieza a investigar de inmediato.</span>
              </div>
            </div>

            <DialogFooter className="border-t p-4">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button type="submit" autoFocus>
                <SirenIcon /> Declarar e investigar
                <Kbd className="ml-1 hidden bg-white/15 text-current sm:inline-flex">Ctrl ⏎</Kbd>
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
