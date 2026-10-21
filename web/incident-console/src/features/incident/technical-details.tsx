import { CopyIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { Incident } from "@/lib/types";

const WORKFLOW_STATE: Record<Incident["state"], string> = {
  investigating: "investigating · running",
  mitigating: "mitigating · awaiting_human",
  verifying: "verifying · awaiting_human",
  resolved: "resolved",
  postmortem: "postmortem · awaiting_human",
  closed: "closed · completed",
};

function Row({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="border-b py-3 last:border-b-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      {values.map((value) => (
        <dd key={value} className="mt-1 flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate font-mono text-xs">{value}</code>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={`Copiar ${value}`}
            onClick={async () => {
              await navigator.clipboard.writeText(value).catch(() => undefined);
              toast.success("Copiado");
            }}
          >
            <CopyIcon />
          </Button>
        </dd>
      ))}
    </div>
  );
}

/** Ids and protocol data stay available for audit and support, out of the operator's way. */
export function TechnicalDetails({
  incident,
  open,
  onOpenChange,
}: {
  incident: Incident;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const tools = [
    ...new Set(incident.proposals.flatMap((p) => p.findings.map((f) => f.query?.tool)).filter(Boolean) as string[]),
  ];
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Detalles técnicos</SheetTitle>
          <SheetDescription>Para auditoría y soporte. No hacen falta para atender el incidente.</SheetDescription>
        </SheetHeader>
        <dl className="overflow-y-auto px-4">
          <Row label="Incidente" values={[incident.backendId]} />
          <Row label="Workflow" values={["incident-response 1.0.0", WORKFLOW_STATE[incident.state]]} />
          <Row label="Ejecuciones del agente" values={incident.runIds} />
          <Row label="Alertas de origen" values={incident.alertIds} />
          {tools.length > 0 && <Row label="Herramientas consultadas" values={tools} />}
        </dl>
      </SheetContent>
    </Sheet>
  );
}
