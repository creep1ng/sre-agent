import { CheckIcon, CircleCheckIcon, HammerIcon, RotateCcwIcon, TableIcon, TriangleAlertIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { AgentAvatar } from "@/components/brand";
import { ToneBadge } from "@/components/badges";
import { SignalChart, SignalTable } from "@/components/signal-chart";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useNow } from "@/hooks/use-now";
import { formatSignal, formatTime } from "@/lib/format";
import { currentValue } from "@/lib/signal";
import { useStore } from "@/lib/store";
import type { Alert, Incident } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Panel, PanelSection } from "./panel";

function AgentWatch({ incident, alert, value }: { incident: Incident; alert: Alert; value: number }) {
  const verification = incident.verification!;
  const above = value > alert.signal.threshold;
  let message: ReactNode;
  if (!verification.appliedAt) {
    message = "Cuando apliques el cambio, pulsa «Ya la apliqué» y vigilaré la señal por ti.";
  } else if (verification.stableSuggestedAt) {
    message = (
      <>
        <span className="font-medium text-success">La señal se mantiene bajo el umbral</span> desde las{" "}
        {formatTime(verification.stableSuggestedAt)}. Puedes confirmar la recuperación.
      </>
    );
  } else if (above) {
    message = (
      <span className="text-shimmer">
        Vigilando la señal: sigue en {formatSignal(value, alert.signal.unit)}, esperando a que baje…
      </span>
    );
  } else {
    message = (
      <span className="text-shimmer">
        Bajó a {formatSignal(value, alert.signal.unit)}. Espero unos segundos para confirmar que se mantiene…
      </span>
    );
  }
  return (
    <div className="flex items-start gap-3 rounded-xl bg-secondary px-3 py-2.5 text-sm" aria-live="polite">
      <AgentAvatar className="mt-0.5" />
      <p className="pt-1">{message}</p>
    </div>
  );
}

export function RecoveryPanel({ incident, alert }: { incident: Incident; alert: Alert }) {
  const now = useNow();
  const toggleStep = useStore((s) => s.toggleStep);
  const markApplied = useStore((s) => s.markApplied);
  const confirmStable = useStore((s) => s.confirmStable);
  const reportNotStable = useStore((s) => s.reportNotStable);
  const [confirmAnyway, setConfirmAnyway] = useState(false);
  const [tableOpen, setTableOpen] = useState(false);

  const verification = incident.verification!;
  const approved = [...incident.proposals].reverse().find((p) => p.decision?.outcome === "approved")!;
  const value = currentValue(alert, now);
  const above = value > alert.signal.threshold;
  const doneSteps = verification.checklist.filter(Boolean).length;
  const applied = Boolean(verification.appliedAt);

  function onStable() {
    if (above) setConfirmAnyway(true);
    else confirmStable(incident.id);
  }

  return (
    <Panel
      tone={verification.stableSuggestedAt ? "success" : "attention"}
      icon={
        <span className="flex size-10 items-center justify-center rounded-xl bg-secondary text-primary">
          {applied ? <CircleCheckIcon className="size-5" /> : <HammerIcon className="size-5" />}
        </span>
      }
      title={applied ? "Confirma que el servicio se recuperó" : "Aplica la mitigación"}
      meta={`Aprobada a las ${formatTime(approved.decision!.at)}: ${approved.summary}`}
      description={
        applied
          ? "El agente vigila la señal. Confirma cuando veas el servicio estable."
          : "Sigue los pasos en tu infraestructura. Marcarlos es opcional; te ayuda a no perderte."
      }
      footer={
        applied ? (
          <>
            <Button size="lg" onClick={onStable} className={cn(verification.stableSuggestedAt && "shadow-md")}>
              <CheckIcon /> El servicio está estable
            </Button>
            <Button size="lg" variant="outline" onClick={() => reportNotStable(incident.id)}>
              <RotateCcwIcon /> Sigue fallando
            </Button>
            <span className="ml-auto hidden text-sm text-muted-foreground md:inline">
              «Sigue fallando» devuelve el incidente al agente para investigar otra vez.
            </span>
          </>
        ) : (
          <>
            <Button size="lg" onClick={() => markApplied(incident.id)}>
              <CheckIcon /> Ya la apliqué
            </Button>
            <span className="text-sm text-muted-foreground">
              {doneSteps === 0 ? "Avísale al agente cuando termines." : `${doneSteps} de ${verification.checklist.length} pasos hechos.`}
            </span>
          </>
        )
      }
    >
      <div className="flex flex-col gap-5">
        <PanelSection title="Pasos">
          <ul className="flex flex-col gap-1">
            {approved.steps.map((step, index) => {
              const checked = verification.checklist[index] ?? false;
              const id = `step-${incident.id}-${index}`;
              return (
                <li key={step}>
                  <label
                    htmlFor={id}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-accent",
                      checked && "text-muted-foreground",
                    )}
                  >
                    <Checkbox
                      id={id}
                      checked={checked}
                      onCheckedChange={() => toggleStep(incident.id, index)}
                      className="mt-0.5 size-5"
                    />
                    <span className={cn("text-[15px] leading-relaxed", checked && "line-through decoration-muted-foreground/60")}>
                      {step}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </PanelSection>

        <PanelSection
          title={`${alert.signal.label} · últimos 10 minutos`}
          aside={
            <span className="flex items-center gap-2">
              <span className="text-lg font-semibold">{formatSignal(value, alert.signal.unit)}</span>
              {above ? (
                <ToneBadge tone="critical" icon={<TriangleAlertIcon className="size-3" />}>
                  Sobre el umbral
                </ToneBadge>
              ) : (
                <ToneBadge tone="success" icon={<CircleCheckIcon className="size-3" />}>
                  Bajo el umbral
                </ToneBadge>
              )}
            </span>
          }
        >
          <SignalChart alert={alert} />
          <Collapsible open={tableOpen} onOpenChange={setTableOpen}>
            <CollapsibleTrigger className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
              <TableIcon className="size-3.5" aria-hidden="true" />
              {tableOpen ? "Ocultar los datos" : "Ver los datos"}
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 max-w-xs">
              <SignalTable alert={alert} />
            </CollapsibleContent>
          </Collapsible>
          <div className="mt-3">
            <AgentWatch incident={incident} alert={alert} value={value} />
          </div>
        </PanelSection>
      </div>

      <AlertDialog open={confirmAnyway} onOpenChange={setConfirmAnyway}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>La señal sigue sobre el umbral</AlertDialogTitle>
            <AlertDialogDescription>
              {alert.signal.label} está en {formatSignal(value, alert.signal.unit)} (umbral{" "}
              {formatSignal(alert.signal.threshold, alert.signal.unit)}). ¿Seguro que el servicio está estable?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Esperar</AlertDialogCancel>
            <AlertDialogAction onClick={() => confirmStable(incident.id)}>Confirmar de todos modos</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Panel>
  );
}
