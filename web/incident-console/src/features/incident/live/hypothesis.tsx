import { ArrowUpRightIcon } from "lucide-react";
import { Link } from "react-router";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import type { Hypothesis } from "@/lib/incident-api";
import { cn } from "@/lib/utils";
import { Prose, useSay, useWhen } from "./say";
import type { StoryEntry } from "./story";
import { VERDICT_TONE } from "./timeline";

const sentence = (text: string) => text.trim().replace(/[.\s]+$/, "");

/** One claim: underlined, its evidence card on hover or focus, a click goes to its step. */
function Claim({ entry }: { entry: StoryEntry }) {
  const t = useT("incident");
  const say = useSay();
  const when = useWhen();
  const now = useNow();
  const context = entry.verdict === "memory" || entry.verdict === "knowledge";
  const card = `card-${entry.id}`;
  const source = say(entry.line);
  return (
    <span className="group relative">
      <a
        href={`#${entry.id}`}
        aria-describedby={card}
        className={cn(
          "rounded-sm underline decoration-[var(--mist-line)] decoration-[1.5px] underline-offset-[6px] outline-none [text-decoration-skip-ink:none]",
          "hover:bg-[var(--mist-wash)] hover:decoration-[var(--mist)] focus-visible:bg-[var(--mist-wash)] focus-visible:decoration-[var(--mist)]",
          context && "decoration-dashed",
        )}
      >
        <Prose text={sentence(entry.quote ?? source)} />
        <sup className="ml-0.5 font-mono text-[11px] font-medium text-[var(--mist)]">{entry.number}</sup>
      </a>
      <span
        id={card}
        role="tooltip"
        className={cn(
          "invisible absolute top-full left-0 z-10 mt-2.5 w-[min(400px,80vw)] rounded-2xl border border-[var(--mist-line)] bg-card px-[18px] py-4 tracking-normal opacity-0 shadow-[0_24px_60px_-24px_var(--shadow)]",
          "group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100",
          "before:absolute before:inset-x-0 before:-top-3 before:h-3",
        )}
      >
        <span className="mb-2.5 flex justify-between font-mono text-xs font-medium text-[var(--dim)]">
          {entry.verdict ? <em className={cn("not-italic", VERDICT_TONE[entry.verdict])}>{t(`verdict.${entry.verdict}`)}</em> : <span />}
          <time>{when(entry.at, now)}</time>
        </span>
        <span className="block font-sans text-[17px] [&_code]:whitespace-nowrap leading-normal font-normal text-foreground">
          <Prose text={entry.quote ?? source} />
        </span>
        <span className="mt-3.5 flex justify-between gap-3 border-t pt-3 font-mono text-xs leading-snug font-normal text-[var(--dim)]">
          <span>
            <Prose text={source} />
          </span>
          {entry.link?.external ? (
            <a href={entry.link.to} target="_blank" rel="noreferrer" className="whitespace-nowrap text-[var(--mist)] hover:text-foreground">
              {t("card.open")} <ArrowUpRightIcon className="inline size-3" aria-hidden="true" />
            </a>
          ) : entry.link ? (
            <Link to={entry.link.to} className="whitespace-nowrap text-[var(--mist)] hover:text-foreground">
              {t("card.open")} <ArrowUpRightIcon className="inline size-3" aria-hidden="true" />
            </Link>
          ) : (
            <a href={`#${entry.id}`} className="whitespace-nowrap text-[var(--mist)] hover:text-foreground">
              {t("card.step")}
            </a>
          )}
        </span>
      </span>
    </span>
  );
}

/** The hypothesis as prose: the agent's statement, then each claim it cites with its evidence. */
export function HypothesisProse({ hypothesis, claims }: { hypothesis: Hypothesis; claims: StoryEntry[] }) {
  const t = useT("incident");
  const filled = { low: 1, medium: 2, high: 3 }[hypothesis.confidence] ?? 0;
  return (
    <div>
      <p id="hypothesis" className="mb-3.5 max-w-[36ch] [&_code]:text-[0.65em] [&_code]:font-normal [&_code]:whitespace-nowrap font-display text-[30px] leading-[1.4] font-light tracking-[-0.01em]">
        <Prose text={`${sentence(hypothesis.statement)}.`} />
        {claims.map((claim) => (
          <span key={claim.id}>
            {" "}
            <Claim entry={claim} />.
          </span>
        ))}
      </p>
      <p className="mb-11 font-mono text-[13px] text-[var(--mist)]">
        {[1, 2, 3].map((bar) => (
          <i key={bar} className={cn("mr-[3px] inline-block h-1.5 w-[22px] rounded-[3px] align-[1px]", bar <= filled ? "bg-[var(--mist)]" : "bg-[var(--night-3)]")} />
        ))}{" "}
        {t(`confidence.${hypothesis.confidence}`)}
      </p>
    </div>
  );
}
