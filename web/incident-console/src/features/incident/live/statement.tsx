import { Fragment, type ReactNode } from "react";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

/*
 * What the agent writes, as a small and safe markdown: **bold** and `code` inline, one line per
 * line. React escapes every character, so raw HTML stays text; there are no images, and links
 * are not markup here, so a model cannot plant one.
 */

/** One line: **bold** and `code`; everything else is text. */
export function Inline({ text }: { text: string }) {
  return text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/).map((part, index): ReactNode => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={index} className="font-medium">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={index}>{part.slice(1, -1)}</code>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}

export interface Part {
  label: string | null;
  text: string;
}

const LABELLED = /^\s*\*\*([^*\n]{1,40}?):\*\*\s*(.*)$/;
// Statements written before the labelled lines (#870) run their parts together in one paragraph.
const PLAIN = /(Causa|Mecanismo|Observación que la refutaría|La refutaría|Cause|Mechanism|Observation that would refute it|Would refute it):\s+/g;

/** A hypothesis statement in its parts: cause, mechanism and what would refute it. */
export function partsOf(statement: string): Part[] {
  const lines = statement.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  if (lines.length > 0 && LABELLED.test(lines[0])) {
    return lines.map((line) => {
      const labelled = LABELLED.exec(line);
      return labelled ? { label: labelled[1], text: labelled[2] } : { label: null, text: line };
    });
  }
  const plain = statement.trim();
  const found = [...plain.matchAll(PLAIN)];
  if (found[0]?.index !== 0) return [{ label: null, text: plain }];
  return found.map((match, index) => ({
    label: match[1],
    text: plain.slice(match.index + match[0].length, found[index + 1]?.index ?? plain.length).trim(),
  }));
}

function Row({ part }: { part: Part }) {
  return (
    <>
      {part.label && <dt className="pt-[0.3em] font-mono text-[12px] leading-snug font-medium text-[var(--mist)]">{part.label}</dt>}
      <dd className={cn("m-0 min-w-0 break-words", !part.label && "col-span-full")}>
        <Inline text={part.text} />
      </dd>
    </>
  );
}

const GRID = "grid grid-cols-1 gap-x-5 gap-y-1 sm:grid-cols-[minmax(7rem,max-content)_minmax(0,1fr)] sm:gap-y-2.5";

/** The statement as labelled lines; `compact` shows the cause and folds the rest away. */
export function Statement({ statement, compact, className }: { statement: string; compact?: boolean; className?: string }) {
  const t = useT("incident");
  const parts = partsOf(statement);
  if (!compact || parts.length < 2) {
    return (
      <dl className={cn(GRID, className)}>
        {parts.map((part, index) => (
          <Row key={index} part={part} />
        ))}
      </dl>
    );
  }
  return (
    <div className={className}>
      <dl className={GRID}>
        <Row part={parts[0]} />
      </dl>
      <details className="group/more mt-1">
        <summary className="cursor-pointer font-mono text-[12px] text-[var(--mist)]">{t("hypothesis.more")}</summary>
        <dl className={cn(GRID, "mt-1.5")}>
          {parts.slice(1).map((part, index) => (
            <Row key={index} part={part} />
          ))}
        </dl>
      </details>
    </div>
  );
}
