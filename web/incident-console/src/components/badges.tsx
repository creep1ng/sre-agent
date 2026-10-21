import { CircleAlertIcon, InfoIcon, OctagonAlertIcon, ServerIcon, TriangleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { IncidentStatus } from "@/lib/status";
import type { Severity } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SEVERITY, TONE_CLASSES, TONE_DOT, TONE_TEXT, type Tone } from "@/lib/vocabulary";

const SEVERITY_ICON = {
  sev1: OctagonAlertIcon,
  sev2: TriangleAlertIcon,
  sev3: CircleAlertIcon,
  sev4: InfoIcon,
} as const;

export function SeverityBadge({ severity, compact = false }: { severity: Severity; compact?: boolean }) {
  const meta = SEVERITY[severity];
  const Icon = SEVERITY_ICON[severity];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
        TONE_CLASSES[meta.tone],
      )}
      title={meta.description}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {meta.short}
      {!compact && <span className="font-medium">· {meta.label}</span>}
    </span>
  );
}

export function ToneBadge({
  tone,
  children,
  className,
  icon,
}: {
  tone: Tone;
  children: ReactNode;
  className?: string;
  icon?: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

export function ServiceChip({ service, className }: { service: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-border bg-card px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground",
        className,
      )}
      title="Servicio afectado"
    >
      <ServerIcon className="size-3" aria-hidden="true" />
      {service}
    </span>
  );
}

export function StatusDot({ tone, working }: { tone: Tone; working?: boolean }) {
  return (
    <span
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        TONE_DOT[tone],
        working && ["animate-pulse-ring", TONE_TEXT[tone]],
      )}
      aria-hidden="true"
    />
  );
}

export function StatusPill({ status, className }: { status: IncidentStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-semibold whitespace-nowrap",
        TONE_CLASSES[status.tone],
        className,
      )}
    >
      <StatusDot tone={status.tone} working={status.working} />
      {status.label}
    </span>
  );
}
