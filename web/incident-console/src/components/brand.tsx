import { cn } from "@/lib/utils";

/**
 * The Nocturno crescent. It follows the theme through currentColor; the pixel stays mist, because
 * amber is reserved for decisions.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <path fill="currentColor" d="M19 3.5A12.5 12.5 0 1 0 28.5 21 10.5 10.5 0 0 1 19 3.5z" />
      <rect x="21" y="8" width="5" height="5" fill="var(--mist)" />
    </svg>
  );
}

/** The wordmark stays mono and lowercase. */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 text-[var(--mark)]", className)}>
      <BrandMark className="size-6 shrink-0" />
      <span className="font-mono text-base leading-none font-medium text-foreground">midnight</span>
    </span>
  );
}

/** Avatar used wherever the agent is the actor, in the agent's identity color. */
export function AgentAvatar({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-agent-solid text-agent-solid-foreground ring-1 ring-border",
        className,
      )}
    >
      <BrandMark className="size-[78%]" />
    </span>
  );
}
