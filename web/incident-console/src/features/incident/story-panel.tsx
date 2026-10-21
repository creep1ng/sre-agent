import { ChevronDownIcon, SendIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ActorAvatar, ActorName } from "@/components/actor";
import { ToneBadge } from "@/components/badges";
import { Sparkline } from "@/components/signal-chart";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { useNow } from "@/hooks/use-now";
import { formatDayLabel, formatTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Alert, Finding, Incident, Proposal, TimelineEvent } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RISK, VERDICT } from "@/lib/vocabulary";
import { QueryDisclosure } from "./findings";
import { ConfidenceMeter } from "./proposal-panel";

interface StoryProps {
  incident: Incident;
  alerts: Alert[];
}

function groupByDay(events: TimelineEvent[], now: number) {
  const groups: { label: string; events: TimelineEvent[] }[] = [];
  for (const event of events) {
    const label = formatDayLabel(event.at, now);
    const last = groups.at(-1);
    if (last && last.label === label) last.events.push(event);
    else groups.push({ label, events: [event] });
  }
  return groups;
}

function useStoryEvents(incident: Incident, onlyMilestones: boolean) {
  return useMemo(
    () =>
      [...incident.events]
        .sort((a, b) => a.at - b.at)
        .filter((event) => !onlyMilestones || event.kind === "milestone" || event.kind === "note"),
    [incident.events, onlyMilestones],
  );
}

/* ------------------------------------------------------------ rich entries */

interface RichDetail {
  /** Shown under the entry even when it is folded. */
  meta?: ReactNode;
  body: ReactNode;
}

function findingOf(incident: Incident, event: TimelineEvent): Finding | undefined {
  if (event.kind !== "finding") return undefined;
  const pool = [...incident.proposals.flatMap((p) => p.findings), ...(incident.job?.findings ?? [])];
  return (
    pool.find((finding) => finding.title === event.text && finding.at === event.at) ??
    pool.find((finding) => finding.title === event.text)
  );
}

function proposalAt(incident: Incident, at: number): Proposal | undefined {
  return incident.proposals.find((proposal) => proposal.createdAt === at);
}

function richDetail(event: TimelineEvent, incident: Incident, alerts: Alert[]): RichDetail | null {
  const finding = findingOf(incident, event);
  if (finding) {
    const verdict = VERDICT[finding.verdict];
    return {
      meta: (
        <ToneBadge tone={verdict.tone} className="py-0 text-[11px]">
          {verdict.label}
        </ToneBadge>
      ),
      body: (
        <>
          <p>{finding.detail}</p>
          {finding.query && <QueryDisclosure query={finding.query} />}
        </>
      ),
    };
  }
  if (event.actor === "agent" && event.text.startsWith("Propuso una hipótesis")) {
    const proposal = proposalAt(incident, event.at) ?? incident.proposals[0];
    if (!proposal) return null;
    return {
      body: (
        <>
          <ConfidenceMeter confidence={proposal.hypothesis.confidence} />
          <p className="mt-1.5">
            <span className="font-medium text-foreground">Qué la descartaría:</span> {proposal.hypothesis.refutedIf}
          </p>
        </>
      ),
    };
  }
  if (event.actor === "agent" && event.text.startsWith("Propuso: ")) {
    const proposal = proposalAt(incident, event.at);
    if (!proposal) return null;
    const risk = RISK[proposal.risk];
    return {
      body: (
        <>
          <ol className="flex flex-col gap-1.5">
            {proposal.steps.map((step, index) => (
              <li key={step} className="flex gap-2">
                <span className="font-semibold text-foreground tabular">{index + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
          <p className="mt-2 flex flex-wrap items-center gap-1.5">
            <ToneBadge tone={risk.tone} className="py-0 text-[11px]">
              {risk.label}
            </ToneBadge>
            {proposal.riskNote}
          </p>
        </>
      ),
    };
  }
  if (event.actor === "system" && event.text.startsWith("Detectamos") && alerts[0]) {
    const alert = alerts[0];
    return {
      body: (
        <>
          {incident.state !== "closed" && <Sparkline alert={alert} className="mb-1.5" />}
          <p>
            <span className="font-medium text-foreground">Regla:</span> {alert.rule}
          </p>
          <p className="mt-1">
            <span className="font-medium text-foreground">Fuente:</span> {alert.source}
          </p>
        </>
      ),
    };
  }
  return null;
}

/* ------------------------------------------------------------------- entry */

function EventItem({ event, rich }: { event: TimelineEvent; rich: RichDetail | null }) {
  const [open, setOpen] = useState(false);
  const textClass = cn(
    "text-sm leading-snug",
    event.kind === "finding" && "text-muted-foreground",
    event.tone === "success" && "font-medium text-success",
    event.tone === "warning" && "text-warning",
    event.tone === "critical" && "font-medium text-critical",
  );
  const detail = event.detail && event.kind !== "note" && (
    <span className={cn(event.kind !== "finding" && !open && "line-clamp-3")}>{event.detail}</span>
  );

  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      <span className="absolute top-7 bottom-0 left-3 w-px bg-border" aria-hidden="true" />
      <ActorAvatar actor={event.actor} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2 text-xs">
          <ActorName actor={event.actor} />
          <time className="text-muted-foreground tabular">{formatTime(event.at)}</time>
        </div>
        {event.kind === "note" ? (
          <p className="mt-1 rounded-lg rounded-tl-sm bg-secondary px-3 py-2 text-sm">{event.text}</p>
        ) : rich ? (
          <Collapsible open={open} onOpenChange={setOpen}>
            <CollapsibleTrigger className="group mt-0.5 flex w-full items-start gap-1.5 text-left">
              <span className={cn(textClass, "flex-1 underline-offset-4 group-hover:text-foreground group-hover:underline")}>
                {event.text}
              </span>
              <ChevronDownIcon
                className="mt-0.5 size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
                aria-hidden="true"
              />
            </CollapsibleTrigger>
            {(detail || rich.meta) && (
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                {detail}
                {rich.meta}
              </div>
            )}
            <CollapsibleContent>
              <div className="mt-2 border-l-2 border-brand-soft pl-3 text-sm text-muted-foreground">{rich.body}</div>
            </CollapsibleContent>
          </Collapsible>
        ) : (
          <>
            <p className={cn("mt-0.5", textClass)}>{event.text}</p>
            {detail && <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>}
          </>
        )}
      </div>
    </li>
  );
}

function EventGroups({ incident, alerts, events }: StoryProps & { events: TimelineEvent[] }) {
  const now = useNow();
  return groupByDay(events, now).map((group) => (
    <div key={group.label} className="mb-4 last:mb-0">
      <div className="mb-3 text-xs font-medium text-muted-foreground">{group.label}</div>
      <ol>
        {group.events.map((event) => (
          <EventItem key={event.id} event={event} rich={richDetail(event, incident, alerts)} />
        ))}
      </ol>
    </div>
  ));
}

function MilestoneToggle({ value, onChange }: { value: boolean; onChange: (value: boolean) => void }) {
  return (
    <div className="flex rounded-lg bg-muted p-0.5 text-xs" role="group" aria-label="Qué mostrar">
      {[
        { value: false, label: "Todo" },
        { value: true, label: "Hitos" },
      ].map((option) => (
        <button
          key={option.label}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-md px-2.5 py-1 font-medium text-muted-foreground transition-colors",
            value === option.value && "bg-card text-foreground shadow-xs",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function NoteComposer({ incident, className }: { incident: Incident; className?: string }) {
  const addNote = useStore((s) => s.addNote);
  const [note, setNote] = useState("");
  if (incident.state === "closed") return null;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) return;
    addNote(incident.id, note);
    setNote("");
  }
  return (
    <form onSubmit={submit} className={cn("flex gap-2", className)}>
      <Input
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Añade una nota para la historia…"
        aria-label="Nota"
      />
      <Button type="submit" size="icon" variant="secondary" disabled={!note.trim()} aria-label="Añadir nota">
        <SendIcon />
      </Button>
    </form>
  );
}

/** Oldest first in its own scroll area, the composer at the end. */
function ScrollingStory({
  incident,
  alerts,
  className,
}: StoryProps & { className?: string }) {
  const [onlyMilestones, setOnlyMilestones] = useState(false);
  const events = useStoryEvents(incident, onlyMilestones);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = listRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
  }, [events.length]);

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <header className="flex items-center justify-between gap-2 px-5 pt-5 pb-3">
        <h2 className="text-sm font-semibold">Historia</h2>
        <MilestoneToggle value={onlyMilestones} onChange={setOnlyMilestones} />
      </header>
      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-2">
        <EventGroups incident={incident} alerts={alerts} events={events} />
      </div>
      <NoteComposer incident={incident} className="border-t px-5 py-3" />
    </div>
  );
}

/** A column beside the incident, one hairline apart, no card. */
export function StoryRail(props: StoryProps) {
  return (
    <aside aria-label="Historia del incidente" className="border-t lg:border-t-0 lg:border-l">
      <ScrollingStory {...props} className="lg:sticky lg:top-0 lg:h-dvh lg:pt-3" />
    </aside>
  );
}
