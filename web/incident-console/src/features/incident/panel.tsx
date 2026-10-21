import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** The "now" card of the incident: the one thing that is happening or needs you. */
export function Panel({
  icon,
  title,
  meta,
  description,
  children,
  footer,
  tone = "default",
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  tone?: "default" | "attention" | "critical" | "success";
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-2xl border bg-card shadow-sm",
        tone === "attention" && "border-brand-line ring-4 ring-brand-soft/60",
        tone === "critical" && "border-critical-line ring-4 ring-critical-soft",
        tone === "success" && "border-success-line ring-4 ring-success-soft",
        className,
      )}
    >
      <header className="flex items-start gap-3 p-5 pb-4">
        {icon}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2 className="text-lg leading-snug font-semibold">{title}</h2>
            {meta && <div className="text-xs text-muted-foreground">{meta}</div>}
          </div>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
      </header>
      {children && <div className="px-5 pb-5">{children}</div>}
      {footer && (
        <footer className="sticky bottom-0 z-10 flex flex-wrap items-center gap-2 rounded-b-2xl border-t bg-card/95 px-5 py-3.5 backdrop-blur">
          {footer}
        </footer>
      )}
    </section>
  );
}

export function PanelSection({ title, aside, children, className }: { title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("border-t pt-4 first:border-t-0 first:pt-0", className)}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {aside}
      </div>
      {children}
    </div>
  );
}
