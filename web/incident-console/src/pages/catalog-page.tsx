import { ArrowUpRightIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { ConnectDialog } from "@/features/inbox/connect-dialog";
import { useWhen } from "@/features/incident/live/say";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import { incidentApi, type ActionCatalog, type CatalogOperation } from "@/lib/incident-api";
import { useLive } from "@/lib/live";
import { appMode } from "@/lib/mode";
import { cn } from "@/lib/utils";

const POLL_MS = 15_000;

type Phase = "unauthenticated" | "loading" | "ready" | "auth" | "forbidden" | "error";

/** Mock mode: the local demo's catalog, as the simulator's sre-checkout would enrol it. */
const MOCK: ActionCatalog = {
  executor_status: "available",
  services: [
    {
      service: "sre-checkout",
      operations: [
        { operation: "deployment.restart", parameters: [], runner: null, executions: [] },
        {
          operation: "deployment.rollback",
          parameters: [{ name: "to_tag", allowed: ["1.4.0"] }],
          runner: { principal_id: "incident-harness", display_name: "Incident harness" },
          executions: [],
        },
      ],
    },
  ],
};

/** The catalog from the real API, read again every 15 s; a failed read keeps what is on screen. */
function useCatalog() {
  const token = useLive((s) => s.token);
  const [state, setState] = useState<{ phase: Phase; stale: boolean; catalog: ActionCatalog | null }>({
    phase: appMode === "mock" ? "ready" : "loading",
    stale: false,
    catalog: appMode === "mock" ? MOCK : null,
  });
  useEffect(() => {
    if (appMode === "mock") return;
    if (!token) {
      setState({ phase: "unauthenticated", stale: false, catalog: null });
      return;
    }
    const abort = new AbortController();
    let timer: number | undefined;
    async function poll() {
      const result = await incidentApi.catalog(token!, abort.signal).catch(() => null);
      if (abort.signal.aborted || !result) return;
      if (result.kind === "ok") setState({ phase: "ready", stale: false, catalog: result.body });
      else if (result.kind === "auth" || result.kind === "forbidden") setState({ phase: result.kind, stale: false, catalog: null });
      else setState((s) => (s.catalog ? { ...s, stale: true } : { phase: "error", stale: false, catalog: null }));
      if (result.kind !== "auth") timer = window.setTimeout(() => void poll(), POLL_MS);
    }
    void poll();
    return () => {
      abort.abort();
      window.clearTimeout(timer);
    };
  }, [token]);
  return state;
}

/** `to_tag ∈ {1.4.0}`, `variant = off`: the only values a parameter may take. */
function Parameters({ operation }: { operation: CatalogOperation }) {
  const t = useT("catalog");
  if (operation.parameters === null) return <span className="text-[var(--dim)]">{` · ${t("parameters.unknown")}`}</span>;
  return operation.parameters.map(({ name, allowed }) => (
    <span key={name}>
      {" · "}
      {name}{" "}
      {allowed === null ? (
        <span className="text-[var(--dim)]">({t("parameters.unlisted")})</span>
      ) : allowed.length === 1 ? (
        `= ${allowed[0]}`
      ) : (
        `∈ {${allowed.join(", ")}}`
      )}
    </span>
  ));
}

const OUTCOME_TONE = { succeeded: "text-[var(--ok)]", refused: "text-[var(--danger)]", failed: "text-[var(--danger)]" };

function Operation({ service, operation }: { service: string; operation: CatalogOperation }) {
  const t = useT("catalog");
  const when = useWhen();
  const now = useNow();
  const known = ["deployment.rollback", "deployment.restart", "flag.set"].includes(operation.operation);
  return (
    <li className="border-t py-6" data-operation={`${service}:${operation.operation}`}>
      <h3 className="font-display text-2xl font-light">
        {known ? t(`operation.${operation.operation}` as "operation.flag.set") : operation.operation}
      </h3>
      <p className="mt-2 font-mono text-[13px] text-[var(--text-2)]">
        {service} · {operation.operation}
        <Parameters operation={operation} />
      </p>
      <p className={cn("mt-3", operation.runner ? "text-[var(--mist)]" : "text-[var(--dim)]")}>
        {t(operation.runner ? "runner.agent" : "runner.none")}
      </p>
      <h4 className="mt-4 text-sm font-medium text-[var(--dim)]">{t("executions")}</h4>
      {operation.executions.length === 0 ? (
        <p className="mt-1 text-sm text-[var(--dim)]">{t("executions.none")}</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1 text-sm">
          {operation.executions.map((execution, index) => (
            <li key={index} className="flex flex-wrap items-baseline gap-x-3">
              <time dateTime={execution.occurred_at} className="w-20 font-mono text-[13px] text-[var(--mist)] tabular">
                {when(Date.parse(execution.occurred_at), now)}
              </time>
              <span className={OUTCOME_TONE[execution.outcome]}>{t(`outcome.${execution.outcome}`)}</span>
              {execution.approved_by && (
                <span className="text-[var(--text-2)]">
                  {t("approved.by", { name: execution.approved_by.display_name ?? t("approved.someone") })}
                </span>
              )}
              {execution.incident_id && (
                <Link to={`/incidentes/${encodeURIComponent(execution.incident_id)}`} className="inline-flex items-center gap-0.5 underline underline-offset-4">
                  {t("incident.open")} <ArrowUpRightIcon className="size-3.5" aria-hidden="true" />
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** What Midnight may run, per service; nothing on this page is a decision, so nothing is amber. */
export function CatalogPage() {
  const t = useT("catalog");
  const { phase, stale, catalog } = useCatalog();
  const [connectOpen, setConnectOpen] = useState(false);
  if (phase !== "ready" || !catalog) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
        <h1 className="font-display text-3xl">{t(`blocked.${phase === "ready" ? "loading" : phase}`)}</h1>
        {(phase === "unauthenticated" || phase === "auth") && (
          <Button className="mt-6" onClick={() => setConnectOpen(true)}>
            {t("blocked.connect")}
          </Button>
        )}
        <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
      </div>
    );
  }
  return (
    <article className="mx-auto w-full max-w-4xl min-w-0 px-4 py-8 sm:px-8 lg:px-14 lg:py-12">
      {stale && <p className="mb-4 font-mono text-[13px] text-[var(--danger)]">{t("stale")}</p>}
      <h1 className="font-display text-4xl leading-none font-light tracking-[-0.03em] sm:text-[54px]">{t("title")}</h1>
      <p className="mt-6 max-w-[52ch] text-lg text-[var(--text-2)]">{t("promise")}</p>
      {catalog.executor_status !== "available" && (
        <p role="status" className="mt-6 text-[var(--danger)]">
          {t(`executor.${catalog.executor_status}`)}
        </p>
      )}
      {catalog.services.length === 0 && <p className="mt-10 text-[var(--dim)]">{t("empty")}</p>}
      {catalog.services.map(({ service, operations }) => (
        <section key={service} className="mt-12" aria-labelledby={`service-${service}`}>
          <h2 id={`service-${service}`} className="mb-2 font-mono text-sm font-medium text-[var(--mist)]">
            {service}
          </h2>
          <ul>
            {operations.map((operation) => (
              <Operation key={operation.operation} service={service} operation={operation} />
            ))}
          </ul>
        </section>
      ))}
    </article>
  );
}
