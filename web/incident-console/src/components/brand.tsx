import { useId } from "react";
import { cn } from "@/lib/utils";

/** The midnight.agent moon mark, drawn with currentColor so it follows the theme. */
export function BrandMark({ className }: { className?: string }) {
  const mask = useId();
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <defs>
        <mask id={mask}>
          <rect width="64" height="64" fill="white" />
          <circle cx="39" cy="22" r="14" fill="black" />
        </mask>
      </defs>
      <circle cx="30" cy="30" r="17" fill="none" stroke="currentColor" strokeWidth="4.5" mask={`url(#${mask})`} />
      <circle cx="22" cy="38" r="3.2" fill="currentColor" />
      <circle cx="30.5" cy="37" r="1.8" fill="currentColor" opacity="0.55" />
      <path d="M40 32h11" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-primary", className)}>
      <BrandMark className="size-8 shrink-0" />
      <span className="font-display text-[1.35rem] leading-none tracking-tight text-foreground">midnight.agent</span>
    </span>
  );
}

/** Avatar used wherever the agent is the actor, in the agent's identity color. */
export function AgentAvatar({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-agent-solid text-agent-solid-foreground ring-1 ring-white/10",
        className,
      )}
    >
      <BrandMark className="size-[78%]" />
    </span>
  );
}
