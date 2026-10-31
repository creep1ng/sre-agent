import { ExternalLinkIcon } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router";
import { ActorAvatar, ActorName } from "@/components/actor";
import { ToneBadge } from "@/components/badges";
import { useNow } from "@/hooks/use-now";
import { formatDayLabel, formatTime } from "@/lib/format";
import type { LiveIncident } from "@/lib/live-incident";
import { cn } from "@/lib/utils";
import { QueryDisclosure, SourceIcon } from "../findings";
import { buildStory, type StoryEntry } from "./story";

function EntryText({ entry }: { entry: StoryEntry }) {
  const className = cn(
    "text-sm leading-snug",
    entry.tone === "success" && "font-medium text-success",
    entry.tone === "warning" && "text-warning",
    entry.tone === "critical" && "font-medium text-critical",
  );
  if (!entry.link) return <span className={className}>{entry.text}</span>;
  if (entry.link.external) {
    return (
      <a href={entry.link.to} target="_blank" rel="noreferrer" className={cn(className, "inline-flex items-center gap-1 hover:underline")}>
        {entry.text} <ExternalLinkIcon className="size-3" aria-hidden="true" />
      </a>
    );
  }
  return (
    <Link to={entry.link.to} className={cn(className, "font-medium text-primary hover:underline dark:text-brand-line")}>
      {entry.text}
    </Link>
  );
}

function Entry({ entry }: { entry: StoryEntry }) {
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      <span className="absolute top-7 bottom-0 left-3 w-px bg-border" aria-hidden="true" />
      {entry.source ? <SourceIcon source={entry.source} className="size-6 rounded-md" /> : <ActorAvatar actor={entry.actor} />}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2 text-xs">
          <ActorName actor={entry.actor} />
          <time className="text-muted-foreground tabular">{formatTime(entry.at)}</time>
        </div>
        <p className="mt-0.5">
          <EntryText entry={entry} />
        </p>
        {(entry.detail || entry.badge) && (
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
            {entry.badge && (
              <ToneBadge tone={entry.badge.tone} className="py-0 text-[11px]">
                {entry.badge.label}
              </ToneBadge>
            )}
            {entry.detail && <span>{entry.detail}</span>}
          </div>
        )}
        {entry.query && <QueryDisclosure query={entry.query} />}
      </div>
    </li>
  );
}

/** The incident's story, oldest first: a column beside the incident, one hairline apart. */
export function StoryColumn({ live }: { live: LiveIncident }) {
  const now = useNow();
  const entries = useMemo(() => buildStory(live), [live]);
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [entries.length]);

  const groups: { label: string; entries: StoryEntry[] }[] = [];
  for (const entry of entries) {
    const label = formatDayLabel(entry.at, now);
    if (groups.at(-1)?.label === label) groups.at(-1)!.entries.push(entry);
    else groups.push({ label, entries: [entry] });
  }

  return (
    <aside aria-label="Historia del incidente" className="border-t lg:border-t-0 lg:border-l">
      <div className="flex min-h-0 flex-col lg:sticky lg:top-0 lg:h-dvh lg:pt-3">
        <header className="flex items-center justify-between gap-2 px-5 pt-5 pb-3">
          <h2 className="text-sm font-semibold">Historia</h2>
          {live.stale && <span className="text-xs text-warning">Sin conexión; mostrando lo último que vimos</span>}
        </header>
        <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-2" aria-live="polite">
          {groups.map((group) => (
            <div key={group.label} className="mb-4 last:mb-0">
              <div className="mb-3 text-xs font-medium text-muted-foreground">{group.label}</div>
              <ol>
                {group.entries.map((entry) => (
                  <Entry key={entry.id} entry={entry} />
                ))}
              </ol>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
