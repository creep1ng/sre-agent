import { CheckIcon, HandIcon, InfoIcon, MessageSquareIcon, SendIcon, ShieldCheckIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { AgentAvatar } from "@/components/brand";
import { ToneBadge } from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useStore } from "@/lib/store";
import type { Confidence, Incident, Proposal } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CONFIDENCE, RISK } from "@/lib/vocabulary";
import { FindingList } from "./findings";
import { Panel, PanelSection } from "./panel";

export function ConfidenceMeter({ confidence }: { confidence: Confidence }) {
  const meta = CONFIDENCE[confidence];
  return (
    <span className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground">
      <span className="flex items-end gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((level) => (
          <span
            key={level}
            className={cn("w-1.5 rounded-sm", level <= meta.level ? "bg-primary dark:bg-brand-line" : "bg-border")}
            style={{ height: 4 + level * 4 }}
          />
        ))}
      </span>
      {meta.label}
    </span>
  );
}

export function HypothesisBlock({ proposal }: { proposal: Proposal }) {
  return (
    <div>
      <p className="text-[15px] leading-relaxed text-pretty">{proposal.hypothesis.statement}</p>
      <p className="mt-2 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Qué la descartaría:</span> {proposal.hypothesis.refutedIf}
      </p>
    </div>
  );
}

export function StepsList({ steps }: { steps: string[] }) {
  return (
    <ol className="flex flex-col gap-2.5">
      {steps.map((step, index) => (
        <li key={step} className="flex gap-3">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground tabular">
            {index + 1}
          </span>
          <span className="pt-0.5 text-[15px] leading-relaxed">{step}</span>
        </li>
      ))}
    </ol>
  );
}

type Mode = "idle" | "comment" | "changes" | "reject";

export function ProposalPanel({ incident }: { incident: Incident }) {
  const decide = useStore((s) => s.decide);
  const proposal = incident.proposals.at(-1)!;
  const [mode, setMode] = useState<Mode>("idle");
  const [text, setText] = useState("");
  const risk = RISK[proposal.risk];

  function submit(outcome: "approved" | "changes_requested" | "rejected") {
    if (outcome === "changes_requested" && !text.trim()) return;
    decide(incident.id, outcome, mode === "idle" ? undefined : text);
    if (outcome === "approved") {
      toast.success("Mitigación aprobada", { description: "Aplica los pasos; el agente vigilará la señal." });
    } else {
      toast.info("El agente preparará otra propuesta", {
        description: outcome === "rejected" ? "Rechazaste la propuesta." : "Le enviamos tu comentario.",
      });
    }
    setMode("idle");
    setText("");
  }

  const prompt =
    mode === "changes"
      ? "¿Qué debería cambiar?"
      : mode === "reject"
        ? "¿Por qué la rechazas? (opcional)"
        : "Comentario para el registro (opcional)";

  return (
    <Panel
      tone="attention"
      icon={<AgentAvatar className="size-10 rounded-xl" />}
      title="El agente propone una mitigación"
      meta={
        <span>
          {proposal.number > 1 ? `Propuesta ${proposal.number} · ` : ""}
          <RelativeTime at={proposal.createdAt} />
        </span>
      }
      description="Revísala y decide. El agente no aplica cambios en tu infraestructura: lo haces tú."
      footer={
        mode === "idle" ? (
          <>
            <Button size="lg" className="w-full sm:w-auto" onClick={() => submit("approved")}>
              <CheckIcon /> Aprobar mitigación
            </Button>
            <Button size="lg" variant="outline" className="flex-1 sm:flex-none" onClick={() => setMode("changes")}>
              <MessageSquareIcon /> Pedir cambios
            </Button>
            <Button
              size="lg"
              variant="ghost"
              className="flex-1 text-critical hover:text-critical sm:flex-none"
              onClick={() => setMode("reject")}
            >
              <XIcon /> Rechazar
            </Button>
            <button
              type="button"
              className="ml-auto hidden text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline sm:inline"
              onClick={() => setMode("comment")}
            >
              Aprobar con un comentario
            </button>
          </>
        ) : (
          <div className="flex w-full flex-col gap-2">
            <label htmlFor="decision-text" className="text-sm font-medium">
              {prompt}
            </label>
            <Textarea
              id="decision-text"
              autoFocus
              rows={2}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={
                mode === "changes"
                  ? "Por ejemplo: prefiero no tocar el flag a mano, usa el restablecimiento de la tienda."
                  : undefined
              }
              className="resize-none"
            />
            <div className="flex flex-wrap gap-2">
              {mode === "comment" && (
                <Button onClick={() => submit("approved")}>
                  <CheckIcon /> Aprobar mitigación
                </Button>
              )}
              {mode === "changes" && (
                <Button onClick={() => submit("changes_requested")} disabled={!text.trim()}>
                  <SendIcon /> Enviar al agente
                </Button>
              )}
              {mode === "reject" && (
                <Button variant="destructive" onClick={() => submit("rejected")}>
                  <XIcon /> Rechazar propuesta
                </Button>
              )}
              <Button variant="ghost" onClick={() => (setMode("idle"), setText(""))}>
                Cancelar
              </Button>
            </div>
          </div>
        )
      }
    >
      <div className="flex flex-col gap-5">
        {proposal.revisionNote && (
          <div className="flex items-start gap-2 rounded-lg bg-info-soft px-3 py-2 text-sm text-info">
            <InfoIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {proposal.revisionNote}
          </div>
        )}

        <PanelSection title="Qué está pasando" aside={<ConfidenceMeter confidence={proposal.hypothesis.confidence} />}>
          <HypothesisBlock proposal={proposal} />
        </PanelSection>

        <PanelSection title={`En qué se basa · ${proposal.findings.length} hallazgos`}>
          <FindingList findings={proposal.findings} />
        </PanelSection>

        <PanelSection title="Qué propone hacer">
          <p className="mb-3 text-base font-semibold">{proposal.summary}</p>
          <StepsList steps={proposal.steps} />
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <div className="flex items-start gap-2 rounded-lg border p-3 text-sm">
              <ShieldCheckIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span>
                <ToneBadge tone={risk.tone} className="mb-1">
                  {risk.label}
                </ToneBadge>
                <span className="block text-muted-foreground">{proposal.riskNote}</span>
              </span>
            </div>
            <div className="flex items-start gap-2 rounded-lg border p-3 text-sm">
              <HandIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span>
                <span className="block font-medium">Cómo sabremos que funcionó</span>
                <span className="block text-muted-foreground">{proposal.verification}</span>
              </span>
            </div>
          </div>
        </PanelSection>
      </div>
    </Panel>
  );
}
