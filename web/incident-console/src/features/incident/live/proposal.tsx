import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import type { Mitigation } from "@/lib/incident-api";
import { cn } from "@/lib/utils";
import { Prose, useActorName, useWhen } from "./say";
import { code, type Key, type StoryEntry } from "./story";
import type { Choice, DecisionError } from "./use-decision";

/** The catalog operation in a developer's words, for the technical detail only. */
export function operationCall(mitigation: Mitigation): string | null {
  const operation = mitigation.operation;
  if (!operation) return null;
  const args = Object.entries({ service: operation.service, ...operation.parameters }).map(([name, value]) => `${name}="${value}"`);
  return `${operation.operation}(${args.join(", ")})`;
}

/**
 * The plan in plain words. A catalog operation (#722) is told as the executor runs it: the
 * rollback starts the target version next to the running one and keeps the running one if the
 * target does not come up healthy. Otherwise the agent's own description and steps.
 */
function usePlan(mitigation: Mitigation): { title: string; steps: string[] } {
  const t = useT("incident");
  const operation = mitigation.operation;
  const params = { service: code(operation?.service ?? ""), tag: code(operation?.parameters?.to_tag ?? "") };
  const told = (name: "rollback" | "restart", count: number) => ({
    title: t(`plan.${name}`, params),
    steps: Array.from({ length: count }, (_, index) => t(`plan.${name}.${index + 1}` as Key, params)),
  });
  if (operation?.operation === "deployment.rollback" && operation.parameters?.to_tag) return told("rollback", 3);
  if (operation?.operation === "deployment.restart") return told("restart", 2);
  return { title: mitigation.description, steps: mitigation.steps ?? [] };
}

interface ProposalProps {
  mitigation: Mitigation;
  /** Waiting for a decision now; otherwise the card tells who decided. */
  pending: boolean;
  decision: StoryEntry | undefined;
  sending: Choice | null;
  error: DecisionError | null;
  canDecide: boolean;
  onDecide: (choice: Choice) => void;
}

export function Proposal({ mitigation, pending, decision, sending, error, canDecide, onDecide }: ProposalProps) {
  const t = useT("incident");
  const name = useActorName();
  const when = useWhen();
  const now = useNow();
  const plan = usePlan(mitigation);
  const outcome = mitigation.approval_status;
  if (!pending && outcome !== "approved" && outcome !== "rejected" && outcome !== "changes_requested") return null;
  return (
    <section
      aria-label={t("plan.label")}
      data-decision={pending ? "" : undefined}
      title={operationCall(mitigation) ?? undefined}
      className={cn("overflow-hidden rounded-2xl border", pending && "border-star bg-[color-mix(in_oklab,var(--star)_8%,transparent)]")}
    >
      <div className="px-[30px] pt-7 pb-2">
        <h2 className="mb-[18px] [&_code]:text-[0.65em] [&_code]:font-normal font-display text-[30px] leading-[1.1] tracking-[-0.01em]">
          <Prose text={plan.title} />
        </h2>
        {plan.steps.length > 0 && (
          <ol className="mb-[18px] list-decimal pl-[22px] text-[var(--text-2)] marker:font-mono marker:text-[13px] marker:text-star-ink">
            {plan.steps.map((step, index) => (
              <li key={index} className="py-1">
                <Prose text={step} />
              </li>
            ))}
          </ol>
        )}
        {mitigation.risk && <p className="mb-5 font-mono text-[13px] text-[var(--mist)]">{t(`plan.risk.${mitigation.risk}`)}</p>}
      </div>
      {pending ? (
        <div className="flex flex-wrap items-center justify-end gap-2.5 border-t border-star px-[18px] py-4">
          {error && (
            <span role="alert" className="mr-auto text-sm text-[var(--danger)]">
              {t(`decision.${error}`)}
            </span>
          )}
          <Button variant="outline" size="lg" className="font-mono" disabled={!canDecide || sending !== null} onClick={() => onDecide("reject")}>
            {t("decision.reject")}
          </Button>
          <Button size="lg" className="bg-star font-mono text-on-star hover:bg-star/90" disabled={!canDecide || sending !== null} onClick={() => onDecide("approve")}>
            {t("decision.approve")}
          </Button>
        </div>
      ) : (
        <p className="border-t px-[30px] py-4 font-mono text-[13px] text-[var(--dim)]">
          {t(`decision.${outcome as "approved" | "rejected" | "changes_requested"}`)}
          {decision && ` · ${name(decision.actor)} · ${when(decision.at, now)}`}
        </p>
      )}
    </section>
  );
}
