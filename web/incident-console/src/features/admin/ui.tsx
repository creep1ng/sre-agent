import { useMemo, useState, type ComponentProps, type ReactNode } from "react";
import { ToneBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ConnectDialog } from "@/features/inbox/connect-dialog";
import { LOCALES, useLanguage, useT } from "@/i18n";
import { GRANT_ACTIONS, type AdminError } from "@/lib/admin-api";
import { useLive } from "@/lib/live";
import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/vocabulary";

/** A page of the administration plane: the same measure and display type as the inbox. */
export function AdminPage({
  title,
  lead,
  actions,
  children,
}: {
  title: string;
  lead: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const token = useLive((state) => state.token);
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-10 sm:px-14 sm:py-14">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-4xl font-light tracking-[-.02em] sm:text-5xl">{title}</h1>
          <p className="mt-3 max-w-[60ch] text-lg text-[var(--text-2)]">{lead}</p>
        </div>
        {token && actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </header>
      {token ? children : <ConnectGate />}
    </div>
  );
}

function ConnectGate() {
  const t = useT("admin");
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col items-start gap-5 rounded-[18px] border border-dashed border-[var(--mist-line)] px-6 py-10 sm:px-9">
      <p className="font-display text-2xl leading-snug">{t("gate.title")}</p>
      <Button variant="outline" onClick={() => setOpen(true)}>
        {t("gate.action")}
      </Button>
      <ConnectDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

/** A titled surface; `flush` lets a table run edge to edge. */
export function Panel({
  title,
  description,
  actions,
  flush = false,
  children,
  className,
  ...props
}: {
  title?: string;
  description?: ReactNode;
  actions?: ReactNode;
  flush?: boolean;
  children: ReactNode;
} & Omit<ComponentProps<"section">, "title">) {
  return (
    <section className={cn("overflow-hidden rounded-[18px] border bg-card", className)} {...props}>
      {(title || description || actions) && (
        <div className="flex flex-col gap-3 border-b px-6 py-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            {title && <h2 className="font-display text-2xl leading-tight tracking-[-.01em]">{title}</h2>}
            {description && <div className="mt-1 text-[15px] text-muted-foreground">{description}</div>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={cn(!flush && "px-6 py-5")}>{children}</div>
    </section>
  );
}

export const TH = "px-4 py-2.5 text-left font-mono text-[11px] font-medium tracking-[.08em] text-muted-foreground uppercase first:pl-6 last:pr-6";
export const TD = "px-4 py-3.5 align-middle first:pl-6 last:pr-6";
export const ROW =
  "border-b transition-colors outline-none last:border-b-0 hover:bg-accent focus-visible:bg-accent data-[clickable]:cursor-pointer";

export function Table({ head, children, label }: { head: ReactNode; children: ReactNode; label?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[15px]" aria-label={label}>
        <thead className="border-b bg-muted/50">
          <tr>{head}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono text-[13px] break-words", className)}>{children}</span>;
}

const STATUS_TONE: Record<string, Tone> = {
  active: "success",
  published: "info",
  inactive: "neutral",
  revoked: "neutral",
  expired: "neutral",
};

export function StatusBadge({ status }: { status: string | undefined }) {
  const t = useT("admin");
  const known = status && status in STATUS_TONE ? status : "unknown";
  return (
    <ToneBadge tone={STATUS_TONE[known] ?? "info"}>
      {known === "unknown" && status ? status : t(`status.${known as "active"}`)}
    </ToneBadge>
  );
}

/** A quiet line in place of rows: loading, nothing yet, nothing found. */
export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-6 py-12 text-center text-[15px] text-muted-foreground">{children}</p>;
}

/** What failed, in words; never the server's code or message. */
export function ErrorNote({ error, onRetry, className }: { error: AdminError; onRetry?: () => void; className?: string }) {
  const t = useT("admin");
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-critical-line bg-critical-soft px-5 py-4 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <div>
        <p className="font-medium text-critical">{t(`error.${error}`)}</p>
        <p className="text-sm text-[var(--text-2)]">{t(`error.${error}.detail`)}</p>
      </div>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}

export function Field({
  id,
  label,
  hint,
  children,
  className,
}: {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid content-start gap-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-[13px] text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

/** A native select dressed as the console's input: keyboard, forms and tests behave as the platform does. */
export function Select({ className, ...props }: ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-xs outline-none md:text-sm dark:bg-input/30",
        "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:border-destructive [&>option]:bg-popover [&>option]:text-popover-foreground",
        className,
      )}
      {...props}
    />
  );
}

/** Label and value pairs; values are shown as the server sent them. */
export function Facts({ rows, className }: { rows: [string, ReactNode][]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[minmax(8rem,auto)_minmax(0,1fr)] gap-x-6 gap-y-2.5 text-[15px]", className)}>
      {rows.map(([term, value]) => (
        <div key={term} className="contents">
          <dt className="text-muted-foreground">{term}</dt>
          <dd className="min-w-0">{value === "" || value === null || value === undefined ? "—" : value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A server timestamp in the reader's language, with the raw value on hover. */
export function useDateTime() {
  const language = useLanguage((state) => state.language);
  return useMemo(() => {
    const format = new Intl.DateTimeFormat(LOCALES[language], { dateStyle: "medium", timeStyle: "short" });
    return (iso: string | null | undefined) => {
      if (!iso) return "—";
      const time = Date.parse(iso);
      return Number.isFinite(time) ? format.format(time) : iso;
    };
  }, [language]);
}

export function Timestamp({ iso }: { iso: string | null | undefined }) {
  const format = useDateTime();
  return (
    <time dateTime={iso ?? undefined} title={iso ?? undefined} className="whitespace-nowrap text-muted-foreground tabular">
      {format(iso)}
    </time>
  );
}

export function useNumber() {
  const language = useLanguage((state) => state.language);
  return useMemo(() => {
    const format = new Intl.NumberFormat(LOCALES[language]);
    return (value: number | null | undefined) => (typeof value === "number" ? format.format(value) : null);
  }, [language]);
}

/** A resource type in words; a type the console does not know is shown as sent. */
export function useResourceType() {
  const t = useT("admin");
  return (type: string) => (type in GRANT_ACTIONS ? t(`type.${type as "skill"}`) : type);
}
