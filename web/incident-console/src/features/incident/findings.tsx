import {
  ActivityIcon,
  BookOpenIcon,
  ChevronDownIcon,
  CodeIcon,
  ScrollTextIcon,
  SparklesIcon,
  ToggleRightIcon,
  WaypointsIcon,
} from "lucide-react";
import { useState } from "react";
import { ToneBadge } from "@/components/badges";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { EvidenceSource, Finding } from "@/lib/types";
import { cn } from "@/lib/utils";
import { LIVE_VERDICT, SOURCE_LABEL, VERDICT } from "@/lib/vocabulary";

export const SOURCE_ICON: Record<EvidenceSource, typeof ActivityIcon> = {
  metrics: ActivityIcon,
  logs: ScrollTextIcon,
  traces: WaypointsIcon,
  changes: ToggleRightIcon,
  knowledge: BookOpenIcon,
  reasoning: SparklesIcon,
};

export function SourceIcon({ source, className }: { source: EvidenceSource; className?: string }) {
  const Icon = SOURCE_ICON[source];
  return (
    <span
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary",
        className,
      )}
      title={SOURCE_LABEL[source]}
    >
      <Icon className="size-3.5" aria-hidden="true" />
    </span>
  );
}

export function QueryBlock({ query }: { query: NonNullable<Finding["query"]> }) {
  return (
    <div className="mt-2 rounded-lg border bg-muted/50 p-3">
      <div className="mb-1.5 flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
        <span>{query.tool}</span>
        <span>{query.window}</span>
      </div>
      <pre className="overflow-x-auto font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap text-foreground">
        {query.text}
      </pre>
    </div>
  );
}

/** A piece of evidence as a sentence, with what it means for the hypothesis. */
export function FindingRow({ finding, live = false }: { finding: Finding; live?: boolean }) {
  const [open, setOpen] = useState(false);
  const verdict = (live ? LIVE_VERDICT : VERDICT)[finding.verdict];
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="flex gap-3 py-2.5">
        <SourceIcon source={finding.source} />
        <div className="min-w-0 flex-1">
          <CollapsibleTrigger className="group flex w-full items-start gap-2 text-left">
            <span className="flex-1">
              <span className="text-sm font-medium">{finding.title}</span>
              <span className="mt-1 flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-muted-foreground">{SOURCE_LABEL[finding.source]}</span>
                <ToneBadge tone={verdict.tone} className="py-0 text-[11px]">
                  {verdict.label}
                </ToneBadge>
              </span>
            </span>
            <ChevronDownIcon
              className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
              aria-label={open ? "Ocultar detalle" : "Ver detalle"}
            />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <p className="mt-2 text-sm text-muted-foreground">{finding.detail}</p>
            {finding.query && <QueryDisclosure query={finding.query} />}
          </CollapsibleContent>
        </div>
      </div>
    </Collapsible>
  );
}

export function QueryDisclosure({ query }: { query: NonNullable<Finding["query"]> }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline dark:text-brand-line">
        <CodeIcon className="size-3.5" aria-hidden="true" />
        {open ? "Ocultar la consulta" : "Ver la consulta"}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <QueryBlock query={query} />
      </CollapsibleContent>
    </Collapsible>
  );
}

export function FindingList({ findings, className }: { findings: Finding[]; className?: string }) {
  return (
    <div className={cn("divide-y divide-border/70", className)}>
      {findings.map((finding) => (
        <FindingRow key={finding.id} finding={finding} />
      ))}
    </div>
  );
}
