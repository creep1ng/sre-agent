import { CheckCheckIcon, CopyIcon, PencilIcon } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { AgentAvatar } from "@/components/brand";
import { RelativeTime } from "@/components/relative-time";
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
import { Textarea } from "@/components/ui/textarea";
import { useNow } from "@/hooks/use-now";
import { formatDayTime, formatTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Certainty, Incident, PostmortemDoc } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CERTAINTY, SEVERITY } from "@/lib/vocabulary";
import { Panel } from "./panel";

/* ------------------------------------------------------------ editing */

function EditableField({
  value,
  readOnly,
  onSave,
  children,
  label,
}: {
  value: string;
  readOnly?: boolean;
  onSave: (value: string) => void;
  children: ReactNode;
  label: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    const element = ref.current;
    if (!editing || !element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight + 2}px`;
  }, [editing, draft]);

  if (readOnly) return <>{children}</>;

  if (editing) {
    return (
      <div>
        <Textarea
          ref={ref}
          autoFocus
          aria-label={label}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => {
            setEditing(false);
            if (draft.trim() !== value.trim()) onSave(draft);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setDraft(value);
              setEditing(false);
            }
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) event.currentTarget.blur();
          }}
          className="min-h-20 resize-none text-[15px] leading-relaxed"
        />
        <p className="mt-1 text-xs text-muted-foreground">Se guarda al salir del campo · Esc deshace</p>
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Editar ${label}`}
      onClick={() => setEditing(true)}
      onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && (event.preventDefault(), setEditing(true))}
      className="group relative -mx-2 cursor-text rounded-lg py-1 pr-8 pl-2 transition-colors outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50"
    >
      {children}
      <PencilIcon
        className="absolute top-2 right-2.5 size-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
        aria-hidden="true"
      />
    </div>
  );
}

function Bullets({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="text-[15px] text-muted-foreground">{empty}</p>;
  return (
    <ul className="flex list-disc flex-col gap-1 pl-5 text-[15px] leading-relaxed marker:text-brand-line">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2 border-t py-5 first:border-t-0 first:pt-0 md:grid-cols-[180px_minmax(0,1fr)] md:gap-6">
      <h3 className="text-sm font-semibold text-muted-foreground md:pt-1">{title}</h3>
      <div>{children}</div>
    </section>
  );
}

function CertaintyPicker({ value, onChange, readOnly }: { value: Certainty; onChange: (value: Certainty) => void; readOnly?: boolean }) {
  const options: Certainty[] = ["confirmed", "probable", "hypothesis", "unknown"];
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-xs text-muted-foreground">Certeza:</span>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          disabled={readOnly && option !== value}
          title={CERTAINTY[option].hint}
          onClick={() => !readOnly && onChange(option)}
          aria-pressed={value === option}
          className={cn(
            "rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
            value === option
              ? "border-primary bg-primary text-primary-foreground"
              : "border-border text-muted-foreground hover:text-foreground disabled:hidden",
          )}
        >
          {CERTAINTY[option].label}
        </button>
      ))}
    </div>
  );
}

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

export function PostmortemDocument({
  incident,
  doc,
  readOnly,
}: {
  incident: Incident;
  doc: PostmortemDoc;
  readOnly?: boolean;
}) {
  const edit = useStore((s) => s.editPostmortem);
  const now = useNow();
  const save = (patch: Partial<PostmortemDoc>) => edit(incident.id, patch);

  return (
    <article className="rounded-xl border bg-background/60 p-5 sm:p-6">
      <header className="mb-5">
        <p className="text-xs text-muted-foreground">
          Postmortem · {incident.id} · {SEVERITY[incident.severity].short}
        </p>
        <h2 className="mt-1 font-display text-2xl tracking-tight">{incident.title}</h2>
      </header>

      <Section title="Resumen">
        <EditableField label="el resumen" value={doc.summary} readOnly={readOnly} onSave={(summary) => save({ summary })}>
          <p className="text-[15px] leading-relaxed text-pretty">{doc.summary}</p>
        </EditableField>
      </Section>

      <Section title="Impacto">
        <EditableField label="el impacto" value={doc.impact} readOnly={readOnly} onSave={(impact) => save({ impact })}>
          <p className="text-[15px] leading-relaxed">{doc.impact}</p>
        </EditableField>
      </Section>

      <Section title="Causa">
        <EditableField
          label="la causa"
          value={doc.cause.statement}
          readOnly={readOnly}
          onSave={(statement) => save({ cause: { ...doc.cause, statement } })}
        >
          <p className="text-[15px] leading-relaxed">{doc.cause.statement}</p>
        </EditableField>
        <CertaintyPicker
          value={doc.cause.certainty}
          readOnly={readOnly}
          onChange={(certainty) => save({ cause: { ...doc.cause, certainty } })}
        />
      </Section>

      <Section title="Qué hicimos">
        <EditableField
          label="las acciones"
          value={doc.actions.join("\n")}
          readOnly={readOnly}
          onSave={(text) => save({ actions: lines(text) })}
        >
          <Bullets items={doc.actions} empty="Sin acciones registradas." />
        </EditableField>
      </Section>

      <Section title="Cómo lo verificamos">
        <EditableField
          label="la verificación"
          value={doc.verification}
          readOnly={readOnly}
          onSave={(verification) => save({ verification })}
        >
          <p className="text-[15px] leading-relaxed">{doc.verification}</p>
        </EditableField>
      </Section>

      <Section title="Cronología">
        <ol className="flex flex-col gap-1.5 text-[15px]">
          {doc.timeline.map((item) => (
            <li key={`${item.at}-${item.text}`} className="flex gap-3">
              <span className="w-24 shrink-0 text-sm text-muted-foreground tabular">{formatDayTime(item.at, now).replace("hoy ", "")}</span>
              <span>{item.text}</span>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Pendientes">
        <EditableField
          label="los pendientes"
          value={doc.pending.join("\n")}
          readOnly={readOnly}
          onSave={(text) => save({ pending: lines(text) })}
        >
          <Bullets items={doc.pending} empty="Ninguno." />
        </EditableField>
      </Section>

      <Section title="Lo que aún no sabemos">
        <EditableField
          label="lo que no se sabe"
          value={doc.unknowns.join("\n")}
          readOnly={readOnly}
          onSave={(text) => save({ unknowns: lines(text) })}
        >
          <Bullets items={doc.unknowns} empty="Nada pendiente de averiguar." />
        </EditableField>
      </Section>
    </article>
  );
}

/* ------------------------------------------------------------ export */

export function postmortemMarkdown(incident: Incident, doc: PostmortemDoc): string {
  const list = (items: string[]) => (items.length ? items.map((item) => `- ${item}`).join("\n") : "- Ninguno");
  return [
    `# Postmortem ${incident.id}: ${incident.title}`,
    "",
    `Gravedad: ${SEVERITY[incident.severity].short} · Servicio: ${incident.service}`,
    "",
    "## Resumen",
    doc.summary,
    "",
    "## Impacto",
    doc.impact,
    "",
    `## Causa (${CERTAINTY[doc.cause.certainty].label.toLowerCase()})`,
    doc.cause.statement,
    "",
    "## Qué hicimos",
    list(doc.actions),
    "",
    "## Cómo lo verificamos",
    doc.verification,
    "",
    "## Cronología",
    doc.timeline.map((item) => `- ${formatTime(item.at)} · ${item.text}`).join("\n"),
    "",
    "## Pendientes",
    list(doc.pending),
    "",
    "## Lo que aún no sabemos",
    list(doc.unknowns),
    "",
  ].join("\n");
}

export function CopyMarkdownButton({ incident, doc }: { incident: Incident; doc: PostmortemDoc }) {
  return (
    <Button
      variant="outline"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(postmortemMarkdown(incident, doc));
          toast.success("Postmortem copiado en Markdown");
        } catch {
          toast.error("No pudimos copiarlo. Revisa los permisos del portapapeles.");
        }
      }}
    >
      <CopyIcon /> Copiar en Markdown
    </Button>
  );
}

/* ------------------------------------------------------------ review */

export function PostmortemReviewPanel({ incident }: { incident: Incident }) {
  const approveAndClose = useStore((s) => s.approveAndClose);
  const [confirming, setConfirming] = useState(false);
  const postmortem = incident.postmortem!;
  const doc = postmortem.doc!;

  return (
    <Panel
      tone="attention"
      icon={<AgentAvatar className="size-10 rounded-xl" />}
      title="Revisa el postmortem y cierra el incidente"
      meta={
        <span>
          Borrador del agente · <RelativeTime at={postmortem.draftedAt!} />
          {postmortem.editedAt && (
            <>
              {" "}
              · editado por ti <RelativeTime at={postmortem.editedAt} />
            </>
          )}
        </span>
      }
      description="Haz clic en cualquier texto para editarlo; se guarda solo. Cuando esté bien, apruébalo y el incidente queda cerrado."
      footer={
        <>
          <Button size="lg" onClick={() => setConfirming(true)}>
            <CheckCheckIcon /> Aprobar y cerrar incidente
          </Button>
          <CopyMarkdownButton incident={incident} doc={doc} />
        </>
      }
    >
      <PostmortemDocument incident={incident} doc={doc} />

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Aprobar el postmortem y cerrar {incident.id}?</AlertDialogTitle>
            <AlertDialogDescription>
              El postmortem queda aprobado tal como está y el incidente se cierra. Podrás consultarlo siempre desde
              Incidentes.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Seguir revisando</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                approveAndClose(incident.id);
                toast.success(`${incident.id} cerrado`, { description: "Postmortem aprobado. Buen trabajo." });
              }}
            >
              Aprobar y cerrar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Panel>
  );
}
