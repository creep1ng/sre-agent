import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2Icon, ChevronDownIcon, CircleCheckIcon, LinkIcon, Undo2Icon, XCircleIcon } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { BrandMark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { AlertCard } from "@/features/inbox/alert-card";
import { ConnectDialog } from "@/features/inbox/connect-dialog";
import { DeclareDialog } from "@/features/inbox/declare-dialog";
import { IncidentCard } from "@/features/inbox/incident-card";
import { MenuServiceFilter, type ServiceStatus } from "@/features/inbox/service-filter";
import { useNow } from "@/hooks/use-now";
import { formatDayTime, formatDuration, formatTime, plural } from "@/lib/format";
import { useLive, type LivePhase } from "@/lib/live";
import { appMode } from "@/lib/mode";
import { useInbox, useLiveInbox, type RecentItem } from "@/lib/selectors";
import { useStore } from "@/lib/store";
import type { Alert } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SEVERITY } from "@/lib/vocabulary";

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
        {title}
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs tabular">{count}</span>
      </h2>
      <div className="flex flex-col gap-3">
        <AnimatePresence initial={false}>{children}</AnimatePresence>
      </div>
    </section>
  );
}

function Appear({ id, children }: { id: string; children: ReactNode }) {
  return (
    <motion.div
      key={id}
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginTop: -12 }}
      transition={{ duration: 0.22, ease: [0.2, 0, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}

function RecentRow({ item, now }: { item: RecentItem; now: number }) {
  const restore = useStore((s) => s.restore);
  if (item.kind === "closed") {
    const incident = item.incident;
    return (
      <Link
        to={`/incidentes/${incident.id}`}
        className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors hover:bg-accent"
      >
        <CircleCheckIcon className="size-4 shrink-0 text-success" aria-hidden="true" />
        <span className="font-mono text-xs text-muted-foreground">{incident.id}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{incident.title}</span>
        <span className="hidden text-muted-foreground sm:inline">
          Cerrado {formatDayTime(item.at, now)} · duró{" "}
          {formatDuration((incident.resolvedAt ?? item.at) - incident.declaredAt)}
        </span>
      </Link>
    );
  }
  const alert = item.alert;
  return (
    <div className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm">
      {item.kind === "dismissed" ? (
        <XCircleIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      ) : (
        <LinkIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      )}
      <span className="min-w-0 flex-1 truncate">{alert.title}</span>
      <span className="hidden text-muted-foreground sm:inline">
        {item.kind === "dismissed" ? `Descartada: ${alert.dismissReason} · ${formatTime(item.at)}` : `Vinculada a ${alert.incidentId}`}
      </span>
      {item.kind === "dismissed" && (
        <Button variant="ghost" size="sm" onClick={() => restore(alert.id)}>
          <Undo2Icon /> Deshacer
        </Button>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed bg-card/60 px-6 py-14 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-secondary text-primary">
        <BrandMark className="size-9" />
      </span>
      <h2 className="mt-4 text-lg font-semibold">Todo en orden</h2>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">
        No hay alertas ni decisiones pendientes. Si algo falla en tus servicios, aparecerá aquí.
      </p>
    </div>
  );
}

const LIVE_STATE: Partial<Record<LivePhase, { title: string; body: string; action?: string }>> = {
  connecting: { title: "Conectando con la API", body: "Estamos pidiendo las alertas de tus servicios." },
  unauthenticated: {
    title: "Conecta una credencial",
    body: "La bandeja muestra las alertas reales de tu API. Conecta una clave con permiso para verlas.",
    action: "Conectar API",
  },
  auth: {
    title: "La API rechazó la credencial",
    body: "La clave no es válida o venció. Conecta otra para seguir viendo las alertas.",
    action: "Conectar API",
  },
  forbidden: {
    title: "Sin acceso a las alertas",
    body: "Tu credencial no tiene permiso para ver alertas. Pide acceso a quien administra la API.",
    action: "Conectar otra",
  },
  error: {
    title: "No pudimos cargar las alertas",
    body: "Revisa que la API esté disponible. Se reintenta automáticamente.",
    action: "Reintentar ahora",
  },
};

export function InboxPage() {
  const now = useNow();
  const live = appMode === "live";
  const mockInbox = useInbox(now);
  const liveInbox = useLiveInbox(now);
  const inbox = live ? liveInbox : mockInbox;
  const phase = useLive((s) => s.phase);
  const stale = useLive((s) => s.stale);
  const lastSuccessAt = useLive((s) => s.lastSuccessAt);
  const retry = useLive((s) => s.retry);
  const alerts = useStore((s) => s.alerts);
  const [params, setParams] = useSearchParams();
  const [service, setService] = useState<string>("all");
  const [recentOpen, setRecentOpen] = useState(false);
  const [declaring, setDeclaring] = useState<Alert | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);

  const declareParam = params.get("declarar");
  const linkedAlert = declareParam ? alerts.find((a) => a.id === declareParam && a.status === "new") ?? null : null;
  const dialogAlert = declaring ?? linkedAlert;

  // The services with something waiting in the inbox, the worst severity first.
  const services = useMemo(() => {
    const byService = new Map<string, ServiceStatus>();
    for (const item of [...inbox.newAlerts, ...inbox.active]) {
      const entry = byService.get(item.service) ?? { service: item.service, count: 0 };
      byService.set(item.service, entry);
      entry.count += 1;
      if (!entry.severity || SEVERITY[item.severity].rank < SEVERITY[entry.severity].rank) entry.severity = item.severity;
    }
    const rank = (entry: ServiceStatus) => (entry.severity ? SEVERITY[entry.severity].rank : 9);
    return [...byService.values()].sort((a, b) => rank(a) - rank(b) || a.service.localeCompare(b.service));
  }, [inbox.newAlerts, inbox.active]);
  const selected = services.some((entry) => entry.service === service) ? service : "all";
  const visible = <T extends { service: string }>(items: T[]) =>
    selected === "all" ? items : items.filter((item) => item.service === selected);

  const newAlerts = visible(inbox.newAlerts);
  const needsYou = visible(inbox.needsYou);
  const working = visible(inbox.working);
  const attentionAlerts = live
    ? newAlerts.filter((alert) => alert.triageStatus === "new" || alert.triageStatus === "triaging")
    : newAlerts;
  const attention = attentionAlerts.length + needsYou.length;
  // A live alert intake already declared or linked (#765) is the agent's work, not calm.
  const handled = live
    ? newAlerts.filter((alert) => alert.triageStatus === "declared" || alert.triageStatus === "linked").length
    : 0;
  const state = live ? LIVE_STATE[phase] : undefined;

  const headline =
    state?.title ??
    (attention > 0
      ? `${plural(attention, "cosa necesita", "cosas necesitan")} tu atención`
      : working.length > 0 || handled > 0
        ? "El agente se está encargando"
        : "Todo en orden");
  const subline = live
    ? newAlerts.length > 0
      ? plural(newAlerts.length, "alerta en vivo", "alertas en vivo")
      : "No hay alertas activas"
    : [
        newAlerts.length > 0 && plural(newAlerts.length, "alerta nueva", "alertas nuevas"),
        needsYou.length > 0 && `${plural(needsYou.length, "incidente espera", "incidentes esperan")} una decisión tuya`,
        working.length > 0 && `el agente trabaja en ${plural(working.length, "incidente", "incidentes")}`,
      ]
        .filter(Boolean)
        .join(" · ");

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-8 lg:py-10">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-3xl tracking-tight sm:text-4xl">{headline}</h1>
          {!state && (
            <p className="mt-2 text-muted-foreground">
              {subline ? `${subline.charAt(0).toUpperCase()}${subline.slice(1)}.` : "No hay nada pendiente."}{" "}
              {live ? (
                lastSuccessAt !== null && (
                  <span className="whitespace-nowrap">Actualizado {formatTime(lastSuccessAt)}</span>
                )
              ) : (
                <span className="whitespace-nowrap">Actualizado {formatTime(now)}</span>
              )}
            </p>
          )}
        </div>
        {services.length > 0 && (
          <MenuServiceFilter
            services={services}
            value={selected}
            onChange={setService}
            total={inbox.newAlerts.length + inbox.active.length}
          />
        )}
      </header>

      {state && (
        <div
          role="status"
          className="flex flex-col gap-3 rounded-2xl border bg-card p-5 sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="max-w-xl text-sm text-muted-foreground">{state.body}</p>
          {state.action && (
            <Button variant="outline" onClick={() => (phase === "error" ? retry() : setConnectOpen(true))}>
              {state.action}
            </Button>
          )}
        </div>
      )}

      {live && stale && (
        <div
          role="status"
          className="rounded-lg border border-warning-line bg-warning-soft px-4 py-3 text-sm text-warning"
        >
          No pudimos actualizar las alertas. Se reintenta automáticamente.
        </div>
      )}

      {attention === 0 && working.length === 0 && newAlerts.length === 0 && !state && <EmptyState />}

      {(newAlerts.length > 0 || attention > 0) && (
        <Section title={live ? "Alertas en vivo" : "Necesita tu atención"} count={live ? newAlerts.length : attention}>
          {needsYou.map((incident) => (
            <Appear key={incident.id} id={incident.id}>
              <IncidentCard incident={incident} />
            </Appear>
          ))}
          {newAlerts.map((alert) => (
            <Appear key={alert.id} id={alert.id}>
              <AlertCard alert={alert} openIncidents={inbox.active} onDeclare={setDeclaring} />
            </Appear>
          ))}
        </Section>
      )}

      {working.length > 0 && (
        <Section title="El agente está trabajando" count={working.length}>
          {working.map((incident) => (
            <Appear key={incident.id} id={incident.id}>
              <IncidentCard incident={incident} />
            </Appear>
          ))}
        </Section>
      )}

      {inbox.recent.length > 0 && (
        <Collapsible open={recentOpen} onOpenChange={setRecentOpen}>
          <CollapsibleTrigger className="flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground">
            <CheckCircle2Icon className="size-4" aria-hidden="true" />
            Resuelto recientemente
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs tabular">{inbox.recent.length}</span>
            <ChevronDownIcon className={cn("size-4 transition-transform", recentOpen && "rotate-180")} />
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 rounded-xl border bg-card p-1">
            {inbox.recent.map((item) => (
              <RecentRow key={`${item.kind}-${item.kind === "closed" ? item.incident.id : item.alert.id}`} item={item} now={now} />
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}

      <DeclareDialog
        alert={dialogAlert}
        onOpenChange={(open) => {
          if (open) return;
          setDeclaring(null);
          if (declareParam) {
            params.delete("declarar");
            setParams(params, { replace: true });
          }
        }}
      />
      <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
    </div>
  );
}
