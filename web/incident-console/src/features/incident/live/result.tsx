import { LOCALES, useLanguage, useT } from "@/i18n";
import { cn } from "@/lib/utils";

/*
 * What a query returned, from the evidence's stored summary: a Prometheus vector as a small
 * table, a log search as its hit count and its most telling lines, the recent changes as their
 * list. A summary is cut at 8000 characters (investigator/client.py), so a log search is often
 * not whole JSON: its lines are read field by field.
 */

export interface Result {
  tool: string;
  summary: string;
}

type Shown =
  | { kind: "vector"; rows: { label: string; value: number }[] }
  | { kind: "logs"; total: number | null; lines: { at: string | null; service: string | null; level: string | null; body: string }[] }
  | { kind: "changes"; changes: { kind: string; status: string; version: string | null; at: string }[] };

function parse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

const field = (chunk: string, pattern: RegExp) => pattern.exec(chunk)?.[1] ?? null;
const SEVERE = /^(fatal|error|err|warn|warning)$/i;

function vector(summary: string): Shown | null {
  const body = parse(summary) as { result?: unknown; data?: { result?: unknown } } | undefined;
  const series = body?.result ?? body?.data?.result;
  if (!Array.isArray(series)) return null;
  const rows = series.flatMap((item: { metric?: Record<string, string>; value?: [number, string]; values?: [number, string][] }) => {
    const sample = item.value ?? item.values?.at(-1);
    const value = Number(sample?.[1]);
    if (!Number.isFinite(value)) return [];
    const labels = Object.entries(item.metric ?? {}).filter(([name]) => name !== "__name__");
    return [{ label: labels.map(([, label]) => label).join(", ") || "—", value }];
  });
  return { kind: "vector", rows: rows.sort((a, b) => b.value - a.value).slice(0, 8) };
}

function logs(summary: string): Shown | null {
  const body = parse(summary) as { total?: number; documents?: unknown[] } | undefined;
  const total = typeof body?.total === "number" ? body.total : Number(field(summary, /"total"\s*:\s*(\d+)/) ?? NaN);
  const chunks = Array.isArray(body?.documents) ? body.documents.map((item) => JSON.stringify(item)) : summary.split(/(?=\{"_index")|(?="_source"\s*:)/).slice(1);
  const lines = chunks.flatMap((chunk) => {
    const raw = field(chunk, /"body"\s*:\s*("(?:[^"\\]|\\.)*")/);
    const text = raw ? (parse(raw) as string | undefined) : undefined;
    if (!text) return [];
    // Raw OpenTelemetry documents, or the compact records the investigator keeps since #996.
    return [
      {
        at: field(chunk, /"@?timestamp"\s*:\s*"([^"]+)"/),
        service: field(chunk, /"service(?:\.name)?"\s*:\s*"([^"]+)"/),
        level: field(chunk, /"severity"\s*:\s*(?:\{[^}]*?"text"\s*:\s*)?"([^"]+)"/),
        body: text,
      },
    ];
  });
  if (!Number.isFinite(total) && lines.length === 0) return null;
  // Errors and warnings first, then the newest.
  lines.sort((a, b) => Number(SEVERE.test(b.level ?? "")) - Number(SEVERE.test(a.level ?? "")) || (b.at ?? "").localeCompare(a.at ?? ""));
  return { kind: "logs", total: Number.isFinite(total) ? total : null, lines: lines.slice(0, 5) };
}

function changes(summary: string): Shown | null {
  const body = parse(summary);
  if (!Array.isArray(body)) return null;
  return {
    kind: "changes",
    changes: body.flatMap((item: Record<string, unknown>) =>
      typeof item?.kind === "string" && typeof item.occurred_at === "string"
        ? [{ kind: item.kind, status: String(item.status ?? ""), version: typeof item.version === "string" ? item.version : null, at: item.occurred_at }]
        : [],
    ),
  };
}

export function shownOf(result: Result): Shown | null {
  if (result.tool === "query_prometheus") return vector(result.summary);
  if (result.tool === "query_elasticsearch") return logs(result.summary);
  if (result.tool === "midnight_recent_changes") return changes(result.summary);
  return null;
}

const CELL = "border-t border-[var(--mist-line)] py-1 align-top";

/** The query's result, readable, with the raw summary behind its own disclosure. */
export function QueryResult({ result }: { result: Result }) {
  const t = useT("incident");
  const locale = LOCALES[useLanguage((state) => state.language)];
  const shown = shownOf(result);
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
  const time = (iso: string | null) => (iso && Number.isFinite(Date.parse(iso)) ? new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(Date.parse(iso)) : "");
  const day = (iso: string) => new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(Date.parse(iso));
  return (
    <div data-result="" className="mt-2 min-w-0 font-mono text-xs text-[var(--text-2)]">
      {shown?.kind === "vector" &&
        (shown.rows.length ? (
          <table className="w-full max-w-[52ch] border-collapse">
            <tbody>
              {shown.rows.map((row, index) => (
                <tr key={index}>
                  <td className={cn(CELL, "pr-4 break-all")}>{row.label}</td>
                  <td className={cn(CELL, "text-right whitespace-nowrap tabular-nums")}>{number.format(row.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>{t("result.none")}</p>
        ))}
      {shown?.kind === "logs" && (
        <>
          {shown.total !== null && <p className="mb-1 text-[var(--dim)]">{t("result.hits", { count: shown.total })}</p>}
          <ul className="list-none p-0">
            {shown.lines.map((line, index) => (
              <li key={index} className={cn(CELL, "grid grid-cols-[auto_minmax(0,1fr)] gap-x-3")}>
                <span className="text-[var(--dim)] tabular-nums">{time(line.at)}</span>
                <span className="min-w-0 break-words">
                  {line.level && <b className={cn("mr-2 font-medium", SEVERE.test(line.level) ? "text-[var(--danger)]" : "text-[var(--dim)]")}>{line.level}</b>}
                  {line.service && <span className="mr-2 text-[var(--mist)]">{line.service}</span>}
                  {line.body}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {shown?.kind === "changes" &&
        (shown.changes.length ? (
          <ul className="list-none p-0">
            {shown.changes.map((change, index) => (
              <li key={index} className={cn(CELL, "flex flex-wrap gap-x-3")}>
                <span className="text-[var(--dim)]">{day(change.at)}</span>
                <span>{[change.kind, change.version, change.status].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>{t("result.none")}</p>
        ))}
      {!shown && result.summary.length <= 300 && <p className="break-words">{result.summary}</p>}
      {(shown || result.summary.length > 300) && <details className="mt-1.5">
        <summary className="cursor-pointer text-[var(--mist)]">{t("result.raw")}</summary>
        <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-code p-2 break-all whitespace-pre-wrap">{result.summary}</pre>
      </details>}
    </div>
  );
}
