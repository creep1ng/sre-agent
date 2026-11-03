import { ArrowUpRightIcon } from "lucide-react";
import { Link } from "react-router";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import type { Hypothesis } from "@/lib/incident-api";
import { cn } from "@/lib/utils";
import { Prose, useSay, useWhen } from "./say";
import { Statement } from "./statement";
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
          "rounded-sm break-words underline decoration-[var(--mist-line)] decoration-[1.5px] underline-offset-[5px] outline-none [text-decoration-skip-ink:none]",
          "hover:bg-[var(--mist-wash)] hover:decoration-[var(--mist)] focus-visible:bg-[var(--mist-wash)] focus-visible:decoration-[var(--mist)]",
          context && "decoration-dashed",
        )}
      >
        <Prose text={sentence(entry.quote ?? source)} />
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

/** The hypothesis in its parts, then each piece of evidence it cites: one line each, verdict first. */
export function HypothesisProse({ hypothesis, claims }: { hypothesis: Hypothesis; claims: StoryEntry[] }) {
  const t = useT("incident");
  const filled = { low: 1, medium: 2, high: 3 }[hypothesis.confidence] ?? 0;
  return (
    <section id="hypothesis" aria-label={t("hypothesis.label")} className="mb-12">
      <h2 className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[13px] font-medium text-[var(--mist)]">
        {t("hypothesis.label")}
        <span className="font-normal">
          {[1, 2, 3].map((bar) => (
            <i key={bar} className={cn("mr-[3px] inline-block h-1.5 w-[22px] rounded-[3px] align-[1px]", bar <= filled ? "bg-[var(--mist)]" : "bg-[var(--night-3)]")} />
          ))}{" "}
          {t(`confidence.${hypothesis.confidence}`)}
        </span>
      </h2>
      <Statement statement={hypothesis.statement} className="max-w-[68ch] text-[17px] leading-[1.55] sm:text-[18px]" />
      {claims.length > 0 && (
        <>
          <h3 className="mt-7 mb-2 font-mono text-[13px] font-medium text-[var(--mist)]">{t("hypothesis.evidence")}</h3>
          <ol className="max-w-[68ch] list-none p-0 text-[15px] leading-normal">
            {claims.map((claim) => (
              <li key={claim.id} className="grid grid-cols-[2rem_minmax(0,1fr)] border-t py-2.5 first:border-t-0">
                <span className="pt-0.5 font-mono text-[12px] font-medium text-[var(--mist)]">{claim.number}</span>
                <span className="min-w-0">
                  {claim.verdict && <em className={cn("mr-2 font-mono text-[12px] not-italic", VERDICT_TONE[claim.verdict])}>{t(`verdict.${claim.verdict}`)}</em>}
                  <Claim entry={claim} />
                </span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
