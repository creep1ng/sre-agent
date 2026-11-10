import { RefreshCwIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ToneBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useT } from "@/i18n";
import {
  adminApi,
  TOKENS,
  USD,
  type ConsumptionFilter,
  type ConsumptionLimits,
  type ConsumptionSummary,
  type UsageRequest,
} from "@/lib/admin-api";
import type { Tone } from "@/lib/vocabulary";
import { useAdminMutation, useAdminQuery, useRetryKey } from "./use-admin-query";
import { AdminPage, Empty, ErrorNote, Field, Mono, Panel, Timestamp, useNumber } from "./ui";

type Scope = "month" | "incident" | "request";

const currentMonth = () => new Date().toISOString().slice(0, 7);

/** The filter of a scope, or null while its value is empty. */
function filterOf(scope: Scope, value: string): ConsumptionFilter | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (scope === "month") return { month: trimmed };
  if (scope === "incident") return { incident_id: trimmed };
  return { request_id: trimmed };
}

export function ConsumptionPage() {
  const t = useT("admin");
  const [scope, setScope] = useState<Scope>("month");
  const [values, setValues] = useState<Record<Scope, string>>({ month: currentMonth(), incident: "", request: "" });
  const [applied, setApplied] = useState<ConsumptionFilter | null>(() => ({ month: currentMonth() }));
  const appliedKey = JSON.stringify(applied);
  const summary = useAdminQuery(applied ? () => adminApi.readConsumption(applied) : null, `summary:${appliedKey}`);
  const requests = useAdminQuery(applied ? () => adminApi.readUsageRequests(applied) : null, `requests:${appliedKey}`);
  const limits = useAdminQuery(adminApi.getLimits, "limits");

  const refresh = () => {
    limits.reload();
    summary.reload();
    requests.reload();
  };

  return (
    <AdminPage
      title={t("consumption.title")}
      lead={t("consumption.lead")}
      actions={
        <Button variant="outline" onClick={refresh}>
          <RefreshCwIcon /> {t("common.refresh")}
        </Button>
      }
    >
      <LimitsPanel query={limits} />

      <Panel title={t("query.title")}>
        <form
          className="flex flex-col gap-4 md:flex-row md:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            setApplied(filterOf(scope, values[scope]));
          }}
        >
          <div className="grid gap-1.5">
            <span className="text-sm font-medium">{t("query.by")}</span>
            <Tabs value={scope} onValueChange={(value) => setScope(value as Scope)}>
              <TabsList>
                <TabsTrigger value="month">{t("query.month")}</TabsTrigger>
                <TabsTrigger value="incident">{t("query.incident")}</TabsTrigger>
                <TabsTrigger value="request">{t("query.request")}</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <Field id={`consumption-${scope}`} label={t(`query.field.${scope}`)} className="md:w-80">
            <Input
              id={`consumption-${scope}`}
              type={scope === "month" ? "month" : "text"}
              className="font-mono"
              autoComplete="off"
              spellCheck={false}
              maxLength={128}
              placeholder={scope === "request" ? "123e4567-e89b-12d3-a456-426614174000" : scope === "incident" ? "INC-0001" : undefined}
              value={values[scope]}
              onChange={(event) => setValues((current) => ({ ...current, [scope]: event.target.value }))}
            />
          </Field>
          <Button type="submit" disabled={!values[scope].trim()}>
            {t("query.submit")}
          </Button>
        </form>
      </Panel>

      {!applied ? (
        <Panel>
          <Empty>{t("query.pick")}</Empty>
        </Panel>
      ) : (
        <>
          {summary.state.phase === "error" ? (
            <ErrorNote error={summary.state.error} onRetry={summary.reload} />
          ) : summary.data ? (
            <Summary summary={summary.data} />
          ) : (
            <Panel>
              <Empty>{t("common.loading")}</Empty>
            </Panel>
          )}
          <Panel flush title={t("requests.title")}>
            {requests.state.phase === "error" ? (
              <div className="px-6 py-5">
                <ErrorNote error={requests.state.error} onRetry={requests.reload} />
              </div>
            ) : !requests.data ? (
              <Empty>{t("common.loading")}</Empty>
            ) : requests.data.items.length === 0 ? (
              <Empty>{t("requests.empty")}</Empty>
            ) : (
              <ul className="divide-y">
                {requests.data.items.map((item) => (
                  <RequestRow key={item.request_id} item={item} />
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </AdminPage>
  );
}

function LimitsPanel({ query }: { query: ReturnType<typeof useAdminQuery<ConsumptionLimits>> }) {
  const t = useT("admin");
  const number = useNumber();
  const [editing, setEditing] = useState(false);
  const policy = query.data;

  const shown = (value: string | number | null | undefined, format?: (value: number) => string | null) =>
    value === null || value === undefined ? (
      <span className="text-muted-foreground">{t("common.notConfigured")}</span>
    ) : (
      (typeof value === "number" && format?.(value)) || String(value)
    );

  return (
    <Panel
      title={t("limits.title")}
      description={t("limits.lead")}
      actions={
        policy &&
        !editing && (
          <Button variant="outline" onClick={() => setEditing(true)}>
            {t("limits.edit")}
          </Button>
        )
      }
    >
      {query.state.phase === "error" ? (
        <ErrorNote error={query.state.error} onRetry={query.reload} />
      ) : !policy ? (
        <p className="text-muted-foreground">{t("common.loading")}</p>
      ) : editing ? (
        <LimitsForm
          policy={policy}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            query.reload();
          }}
          onConflict={query.reload}
        />
      ) : (
        <div className="flex flex-col gap-5">
          <div className="grid gap-6 sm:grid-cols-2">
            <Stat label={t("limits.incident")} value={shown(policy.incident_token_limit, number)} />
            <Stat label={t("limits.monthly")} value={shown(policy.monthly_usd_limit)} />
          </div>
          <p className="flex flex-wrap gap-x-4 font-mono text-[13px] text-muted-foreground">
            <span>{t("limits.version", { version: policy.version })}</span>
            {policy.updated_at && <Timestamp iso={policy.updated_at} />}
          </p>
        </div>
      )}
    </Panel>
  );
}

function LimitsForm({
  policy,
  onCancel,
  onSaved,
  onConflict,
}: {
  policy: ConsumptionLimits;
  onCancel: () => void;
  onSaved: () => void;
  onConflict: () => void;
}) {
  const t = useT("admin");
  const [tokens, setTokens] = useState(policy.incident_token_limit === null ? "" : String(policy.incident_token_limit));
  const [usd, setUsd] = useState(policy.monthly_usd_limit === null ? "" : String(policy.monthly_usd_limit));
  const { busy, error, setError, run } = useAdminMutation<"local">();
  const retry = useRetryKey("limits");

  const tokensOk = tokens.trim() === "" || TOKENS.test(tokens.trim());
  const usdOk = usd.trim() === "" || USD.test(usd.trim());

  const submit = async () => {
    if (!tokensOk || !usdOk) {
      setError("local");
      return;
    }
    const body = {
      expected_version: policy.version,
      incident_token_limit: tokens.trim() ? Number(tokens.trim()) : null,
      monthly_usd_limit: usd.trim() || null,
    };
    const result = await run(() => adminApi.replaceLimits(body, retry.keyFor(body)));
    if (!result.ok) {
      if (result.error === "conflict") {
        retry.settle();
        onConflict();
      }
      return;
    }
    retry.settle();
    toast.success(t("limits.saved", { version: result.body.version }));
    onSaved();
  };

  return (
    <form
      className="grid gap-4"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      {error === "local" ? (
        <p role="alert" className="text-sm text-critical">
          {t("limits.invalid")}
        </p>
      ) : (
        error && <ErrorNote error={error} />
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="limits-tokens" label={t("limits.incident")}>
          <Input
            id="limits-tokens"
            className="font-mono"
            inputMode="numeric"
            autoComplete="off"
            placeholder={t("common.notConfigured")}
            aria-invalid={!tokensOk}
            value={tokens}
            onChange={(event) => setTokens(event.target.value)}
            autoFocus
          />
        </Field>
        <Field id="limits-usd" label={t("limits.monthly")}>
          <Input
            id="limits-usd"
            className="font-mono"
            inputMode="decimal"
            autoComplete="off"
            placeholder={t("common.notConfigured")}
            aria-invalid={!usdOk}
            value={usd}
            onChange={(event) => setUsd(event.target.value)}
          />
        </Field>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy}>
          {t("limits.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}

function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="font-mono text-[11px] tracking-[.08em] text-muted-foreground uppercase">{label}</span>
      <span className="font-display text-4xl leading-none font-light tracking-[-.02em] tabular">{value}</span>
      {note && <span className="text-sm text-muted-foreground">{note}</span>}
    </div>
  );
}

const COVERAGE_TONE: Record<string, Tone> = { complete: "success", partial: "neutral" };

function Summary({ summary }: { summary: ConsumptionSummary }) {
  const t = useT("admin");
  const number = useNumber();
  const totals = summary.totals ?? {};
  const cost = totals.cost ?? {};
  const coverage = summary.coverage ?? {};
  const missing = <span className="text-muted-foreground">{t("common.unavailable")}</span>;
  const count = (value: number | null | undefined) => number(value) ?? missing;
  const versions = (cost.price_versions ?? []).filter((version) => typeof version === "string");
  const costMissing = cost.amount === null || cost.amount === undefined;
  const coverageStatus = coverage.status && coverage.status in COVERAGE_TONE ? coverage.status : "unknown";
  const empty = summary.request_count === 0 && coverage.status === "complete";

  return (
    <Panel
      title={summary.filter?.month ? t("summary.month", { month: summary.filter.month }) : t("query.title")}
      actions={
        <ToneBadge tone={COVERAGE_TONE[coverageStatus] ?? "info"}>
          {t("summary.coverage")} · {t(`coverage.${coverageStatus as "complete"}`)}
        </ToneBadge>
      }
    >
      {empty ? (
        <p className="text-muted-foreground">{t("summary.empty")}</p>
      ) : (
        <div className="flex flex-col gap-8">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            <Stat
              label={t("summary.cost")}
              value={costMissing ? missing : `${cost.amount} USD`}
              note={
                versions.length > 0
                  ? `${t("summary.priceVersions", { versions: versions.join(", ") })}${costMissing ? ` · ${t("summary.costUnavailable")}` : ""}`
                  : undefined
              }
            />
            <Stat label={t("summary.requests")} value={count(summary.request_count)} />
            <Stat label={t("summary.runs")} value={count(summary.incident_runs)} />
            <Stat label={t("summary.total")} value={count(totals.total_tokens)} />
            <Stat label={t("summary.input")} value={count(totals.input_tokens)} />
            <Stat label={t("summary.output")} value={count(totals.output_tokens)} />
          </div>
          <p className="font-mono text-[13px] text-muted-foreground">
            {t("summary.coverageDetail", {
              known: number(coverage.known) ?? "—",
              incomplete: number(coverage.incomplete) ?? "—",
              unknown: number(coverage.unknown) ?? "—",
            })}
          </p>
        </div>
      )}
    </Panel>
  );
}

const ATTRIBUTION_TONE: Record<string, Tone> = {
  available: "success",
  partial: "neutral",
  legacy: "neutral",
  unavailable: "critical",
};

function RequestRow({ item }: { item: UsageRequest }) {
  const t = useT("admin");
  const number = useNumber();
  const status = item.attribution_status ?? "";
  const requested = item.requested_assignment ?? {};
  const consumption = item.consumption;
  const value = (text: string | null | undefined) => text || "—";

  return (
    <li className="flex flex-col gap-3 px-6 py-5" data-request-row={item.request_id}>
      <div className="flex flex-wrap items-center gap-3">
        <Mono>{item.request_id}</Mono>
        {item.month && <span className="font-mono text-[13px] text-muted-foreground">{item.month}</span>}
        {status in ATTRIBUTION_TONE && (
          <ToneBadge tone={ATTRIBUTION_TONE[status]}>{t(`attribution.${status as "available"}`)}</ToneBadge>
        )}
      </div>
      <dl className="grid gap-x-6 gap-y-2 text-[15px] sm:grid-cols-[8rem_minmax(0,1fr)]">
        <dt className="text-muted-foreground">{t("requests.requested")}</dt>
        <dd>
          {requested.availability === "available" ? (
            <Mono>
              {value(requested.alias)} → {value(requested.model)} · {value(requested.provider)} · {value(requested.router)}
            </Mono>
          ) : (
            <span className="text-muted-foreground">{requested.availability ?? t("common.unavailable")}</span>
          )}
        </dd>
        <dt className="text-muted-foreground">{t("requests.credited")}</dt>
        <dd>
          <Mono>
            {value(item.credited_model?.value)} · {value(item.credited_provider?.value)}
          </Mono>
        </dd>
        <dt className="text-muted-foreground">{t("requests.tokens")}</dt>
        <dd>
          {consumption ? (
            <span className="tabular">
              {t("requests.tokensDetail", {
                input: number(consumption.input_tokens) ?? "—",
                output: number(consumption.output_tokens) ?? "—",
                total: number(consumption.total_tokens) ?? "—",
              })}
            </span>
          ) : (
            <span className="text-muted-foreground">{t("requests.noConsumption")}</span>
          )}
        </dd>
        <dt className="text-muted-foreground">{t("requests.billed")}</dt>
        <dd>
          {consumption?.billed_usd === null || consumption?.billed_usd === undefined ? (
            <span className="text-muted-foreground">{t("common.unavailable")}</span>
          ) : (
            <span className="tabular">{consumption.billed_usd} USD</span>
          )}
          {consumption?.pricing_context && (
            <span className="ml-3 font-mono text-[13px] text-muted-foreground">
              {t("requests.price", {
                version: consumption.pricing_context.price_version ?? "—",
                at: consumption.pricing_context.observed_at ?? "—",
              })}
            </span>
          )}
        </dd>
      </dl>
    </li>
  );
}
