import { ChevronDownIcon, RefreshCwIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { ToneBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useT } from "@/i18n";
import { adminApi, type AuditEvent, type AuditFilters, type Digest } from "@/lib/admin-api";
import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/vocabulary";
import { useAdminQuery } from "./use-admin-query";
import { AdminPage, Empty, ErrorNote, Facts, Field, Mono, Panel, ROW, Select, TD, TH, Table, Timestamp } from "./ui";

type FilterName = keyof AuditFilters;

const PRIMARY: FilterName[] = ["incident_id", "principal_id", "request_id"];
const MORE: FilterName[] = ["model_alias_id", "run_id", "task_id", "trace_id", "from", "to", "limit"];

const OUTCOME_TONE: Record<string, Tone> = { success: "success", denied: "critical", failure: "critical", error: "critical" };

const digest = (ref: Digest | undefined) => (ref?.digest ? <Mono>{ref.digest}</Mono> : "");

export function AuditPage() {
  const t = useT("admin");
  const [draft, setDraft] = useState<AuditFilters>({ limit: "100" });
  const [applied, setApplied] = useState<AuditFilters | null>(null);
  const [more, setMore] = useState(false);
  const [needFilter, setNeedFilter] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const events = useAdminQuery(applied ? () => adminApi.listAuditEvents(applied) : null, JSON.stringify(applied));
  const items = events.data?.items ?? [];

  const apply = () => {
    const filters = Object.fromEntries(
      Object.entries(draft)
        .map(([key, value]) => [key, value?.trim()])
        .filter(([, value]) => value),
    ) as AuditFilters;
    const { limit: _limit, ...rest } = filters;
    if (Object.keys(rest).length === 0) {
      setNeedFilter(true);
      return;
    }
    setNeedFilter(false);
    setApplied(filters);
  };

  const input = (name: FilterName) => (
    <Field key={name} id={`audit-${name}`} label={t(`audit.f.${name}`)}>
      <Input
        id={`audit-${name}`}
        className="font-mono"
        autoComplete="off"
        spellCheck={false}
        inputMode={name === "limit" ? "numeric" : undefined}
        placeholder={name === "from" ? "2026-11-01T00:00:00Z" : name === "to" ? "2026-11-30T23:59:59Z" : undefined}
        value={draft[name] ?? ""}
        onChange={(event) => setDraft((current) => ({ ...current, [name]: event.target.value }))}
      />
    </Field>
  );

  return (
    <AdminPage
      title={t("audit.title")}
      lead={t("audit.lead")}
      actions={
        <Button variant="outline" onClick={events.reload} disabled={!applied}>
          <RefreshCwIcon /> {t("common.refresh")}
        </Button>
      }
    >
      <Panel title={t("audit.filters")}>
        <form
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            apply();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {PRIMARY.map(input)}
            <Field id="audit-decision" label={t("audit.f.decision")}>
              <Select
                id="audit-decision"
                value={draft.decision ?? ""}
                onChange={(event) => setDraft((current) => ({ ...current, decision: event.target.value }))}
              >
                <option value="">{t("audit.decision.any")}</option>
                <option value="allow">{t("audit.decision.allow")}</option>
                <option value="deny">{t("audit.decision.deny")}</option>
              </Select>
            </Field>
            {more && MORE.map(input)}
          </div>
          {needFilter && (
            <p role="alert" className="text-sm text-critical">
              {t("audit.needFilter")}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit">{t("audit.apply")}</Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setDraft({ limit: "100" });
                setApplied(null);
                setNeedFilter(false);
              }}
            >
              {t("audit.clear")}
            </Button>
            <Button type="button" variant="link" className="ml-auto" aria-expanded={more} onClick={() => setMore(!more)}>
              {t(more ? "audit.less" : "audit.more")}
              <ChevronDownIcon className={cn("transition-transform", more && "rotate-180")} />
            </Button>
          </div>
        </form>
      </Panel>

      <Panel
        flush
        description={
          events.data
            ? `${t("common.count", { count: items.length })}${events.data.truncated ? ` · ${t("common.truncated")}` : ""}`
            : undefined
        }
      >
        {events.state.phase === "error" ? (
          <div className="px-6 py-5">
            <ErrorNote error={events.state.error} onRetry={events.reload} />
          </div>
        ) : !applied ? (
          <Empty>{t("audit.pickFirst")}</Empty>
        ) : !events.data ? (
          <Empty>{t("common.loading")}</Empty>
        ) : items.length === 0 ? (
          <Empty>{t("audit.empty")}</Empty>
        ) : (
          <Table
            label={t("audit.title")}
            head={
              <>
                <th className={TH}>{t("audit.col.occurred")}</th>
                <th className={TH}>{t("audit.col.operation")}</th>
                <th className={TH}>{t("audit.col.decision")}</th>
                <th className={TH}>{t("audit.col.outcome")}</th>
                <th className={TH}>{t("audit.col.actor")}</th>
                <th className={TH}>{t("audit.col.event")}</th>
              </>
            }
          >
            {items.map((item) => (
              <tr
                key={item.event_id}
                data-clickable
                data-event-row={item.event_id}
                tabIndex={0}
                aria-label={t("audit.open", { id: item.event_id })}
                onClick={() => setOpenId(item.event_id)}
                onKeyDown={(event) => event.key === "Enter" && setOpenId(item.event_id)}
                className={ROW}
              >
                <td className={TD}>
                  <Timestamp iso={item.occurred_at} />
                </td>
                <td className={TD}>
                  <Mono>{item.operation || "—"}</Mono>
                  <div className="text-sm text-muted-foreground">{item.resource?.resource_type || "—"}</div>
                </td>
                <td className={TD}>
                  <Decision item={item} />
                </td>
                <td className={TD}>
                  <Outcome outcome={item.outcome} />
                </td>
                <td className={`${TD} text-[var(--text-2)]`}>{item.identity?.principal_kind || "—"}</td>
                <td className={TD}>
                  <Mono className="text-muted-foreground">
                    {item.event_id.length > 13 ? `${item.event_id.slice(0, 13)}…` : item.event_id}
                  </Mono>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>

      <EventSheet eventId={openId} onClose={() => setOpenId(null)} />
    </AdminPage>
  );
}

/** "deny · no_matching_grant": the policy decision and its reason code, never a resource name. */
function Decision({ item }: { item: AuditEvent }) {
  const decision = item.policy_decision?.decision;
  const reason = item.policy_decision?.reason_code;
  if (!decision) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <ToneBadge tone={decision === "allow" ? "success" : decision === "deny" ? "critical" : "info"}>{decision}</ToneBadge>
      {reason && <Mono className="text-muted-foreground">{reason}</Mono>}
    </span>
  );
}

function Outcome({ outcome }: { outcome: string | undefined }) {
  if (!outcome) return <span className="text-muted-foreground">—</span>;
  return <ToneBadge tone={OUTCOME_TONE[outcome] ?? "neutral"}>{outcome}</ToneBadge>;
}

function EventSheet({ eventId, onClose }: { eventId: string | null; onClose: () => void }) {
  const t = useT("admin");
  const event = useAdminQuery(eventId ? () => adminApi.getAuditEvent(eventId) : null, `event:${eventId}`);
  const item = event.data;

  const group = (title: string, rows: [string, ReactNode][]) => (
    <section className="flex flex-col gap-3">
      <h3 className="font-mono text-[11px] tracking-[.08em] text-muted-foreground uppercase">{title}</h3>
      <Facts rows={rows} className="grid-cols-[11rem_minmax(0,1fr)]" />
    </section>
  );

  return (
    <Sheet open={eventId !== null} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="gap-2 px-6 pt-8">
          <SheetTitle className="font-display text-3xl font-light tracking-[-.015em]">{t("audit.detail")}</SheetTitle>
          <SheetDescription asChild>
            <Mono className="text-muted-foreground">{eventId}</Mono>
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-8 px-6 pb-8">
          {event.state.phase === "error" ? (
            <ErrorNote error={event.state.error} onRetry={event.reload} />
          ) : !item || item.event_id !== eventId ? (
            <p className="text-muted-foreground">{t("common.loading")}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Outcome outcome={item.outcome} />
                <Decision item={item} />
              </div>
              {group(t("audit.group.what"), [
                [t("audit.d.occurred"), <Timestamp iso={item.occurred_at} />],
                [t("audit.d.operation"), item.operation ? <Mono>{item.operation}</Mono> : ""],
                [t("audit.d.action"), item.action ? <Mono>{item.action}</Mono> : ""],
                [t("audit.d.stage"), item.stage ?? ""],
                [t("audit.d.outcome"), item.outcome ?? ""],
                [t("audit.d.reason"), item.reason_code ? <Mono>{item.reason_code}</Mono> : ""],
                [t("audit.d.status"), item.response_status === undefined ? "" : String(item.response_status)],
                [t("audit.d.latency"), item.latency_ms === undefined ? "" : String(item.latency_ms)],
              ])}
              {group(t("audit.group.who"), [
                [t("audit.d.actorKind"), item.identity?.principal_kind ?? ""],
                [t("audit.d.actorStatus"), item.identity?.principal_status ?? ""],
                [t("audit.d.actorRef"), digest(item.identity?.principal_ref)],
                [t("audit.d.resourceType"), item.resource?.resource_type ?? ""],
                [t("audit.d.resourceRef"), digest(item.resource?.resource_ref)],
                [t("audit.d.aliasRef"), digest(item.model_alias_ref)],
                [t("audit.d.router"), item.routing?.router ?? ""],
                [t("audit.d.modelRef"), digest(item.routing?.model_ref)],
                [t("audit.d.providerRef"), digest(item.routing?.provider_ref)],
              ])}
              {group(t("audit.group.policy"), [
                [t("audit.d.decision"), item.policy_decision?.decision ?? ""],
                [t("audit.d.decisionReason"), item.policy_decision?.reason_code ? <Mono>{item.policy_decision.reason_code}</Mono> : ""],
                [t("audit.d.denial"), item.authorization_denial_cause ?? ""],
                [t("audit.d.content"), item.content_state ?? ""],
              ])}
              {group(t("audit.group.correlation"), [
                [t("audit.d.request"), item.correlation?.request_id ? <Mono>{item.correlation.request_id}</Mono> : ""],
                [t("audit.d.incidentRef"), digest(item.correlation?.incident_ref)],
                [t("audit.d.runRef"), digest(item.correlation?.run_ref)],
                [t("audit.d.taskRef"), digest(item.correlation?.task_ref)],
                [t("audit.d.traceRef"), digest(item.correlation?.trace_ref)],
              ])}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
