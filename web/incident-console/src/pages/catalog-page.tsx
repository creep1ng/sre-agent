import { ArrowUpRightIcon, BanIcon, ChevronRightIcon, ServerIcon } from "lucide-react";
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

/** Each parameter on its own row, its allowed values as chips: what the executor will accept. */
function Parameters({ operation }: { operation: CatalogOperation }) {
  const t = useT("catalog");
  if (operation.parameters === null) return <p className="mt-3 font-mono text-[13px] text-[var(--dim)]">{t("parameters.unknown")}</p>;
  if (operation.parameters.length === 0) return null;
  return (
    <dl className="mt-3 grid grid-cols-[max-content_minmax(0,1fr)] items-baseline gap-x-4 gap-y-2 font-mono text-[13px]">
      {operation.parameters.map(({ name, allowed }) => (
        <div key={name} className="contents" data-parameter={name}>
          <dt className="text-[var(--dim)]">{name}</dt>
          <dd className="flex flex-wrap gap-1.5">
            {allowed === null ? (
              <span className="text-[var(--dim)]">{t("parameters.unlisted")}</span>
            ) : (
              allowed.map((value) => (
                <code key={value} className="rounded-md border border-[var(--mist-line)] bg-[var(--mist-wash)] px-1.5 py-0.5 text-foreground">
                  {value}
                </code>
              ))
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const OUTCOME_TONE = { succeeded: "text-[var(--ok)]", refused: "text-[var(--danger)]", failed: "text-[var(--danger)]" };

/** The runs, folded until asked for; with none, the summary line says so and there is nothing to open. */
function Executions({ operation }: { operation: CatalogOperation }) {
  const t = useT("catalog");
  const when = useWhen();
  const now = useNow();
  if (operation.executions.length === 0) return <p className="mt-4 text-sm text-[var(--dim)]">{t("executions.none")}</p>;
  return (
    <details className="group mt-4 text-sm">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-[var(--text-2)] hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRightIcon className="size-4 transition-transform group-open:rotate-90" aria-hidden="true" />
        {t("executions", { count: operation.executions.length })}
      </summary>
      <ul className="mt-2 flex flex-col gap-1 pl-5">
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
    </details>
  );
}

function Operation({ service, operation }: { service: string; operation: CatalogOperation }) {
  const t = useT("catalog");
  const known = ["deployment.rollback", "deployment.restart", "flag.set"].includes(operation.operation);
  return (
    <li className="border-t px-6 py-5" data-operation={`${service}:${operation.operation}`}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="font-display text-xl">{known ? t(`operation.${operation.operation}` as "operation.flag.set") : operation.operation}</h3>
        {known && <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[12px] text-[var(--mist)]">{operation.operation}</code>}
      </div>
      <Parameters operation={operation} />
      {/* The lead says who runs every operation; only the exception is told here. */}
      {!operation.runner && (
        <p className="mt-3 inline-flex items-center gap-1.5 text-sm text-[var(--dim)]">
          <BanIcon className="size-3.5" aria-hidden="true" />
          {t("runner.none")}
        </p>
      )}
      <Executions operation={operation} />
    </li>
  );
}

/** A service as a card: its name, how many operations it has and when one last ran. */
function Service({ service, operations }: ActionCatalog["services"][number]) {
  const t = useT("catalog");
  const when = useWhen();
  const now = useNow();
  const last = Math.max(...operations.flatMap((operation) => operation.executions.map((execution) => Date.parse(execution.occurred_at))));
  return (
    <section className="mt-8 overflow-hidden rounded-2xl border bg-panel" aria-labelledby={`service-${service}`} data-service={service}>
      <header className="flex items-center gap-3 px-6 py-5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-[var(--mist-wash)] text-[var(--mist)]">
          <ServerIcon className="size-[18px]" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 id={`service-${service}`} className="truncate font-mono text-base font-medium">
            {service}
          </h2>
          <p className="text-sm text-[var(--dim)]">
            {t(operations.length === 1 ? "service.one" : "service.many", { count: operations.length })}
            {" · "}
            {Number.isFinite(last) ? t("service.last", { when: when(last, now) }) : t("service.never")}
          </p>
        </div>
      </header>
      <ul>
        {operations.map((operation) => (
          <Operation key={operation.operation} service={service} operation={operation} />
        ))}
      </ul>
    </section>
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
      <p className="mt-6 max-w-[56ch] text-lg text-[var(--text-2)]">{t("lead")}</p>
      {catalog.executor_status !== "available" && (
        <p role="status" className="mt-6 text-[var(--danger)]">
          {t(`executor.${catalog.executor_status}`)}
        </p>
      )}
      {catalog.services.length === 0 && <p className="mt-10 text-[var(--dim)]">{t("empty")}</p>}
      {catalog.services.map((entry) => (
        <Service key={entry.service} {...entry} />
      ))}
    </article>
  );
}
