import { BellIcon } from "lucide-react";
import type { Actor } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AgentAvatar } from "./brand";

const ACTOR_NAME: Record<Actor, string> = { system: "Sistema", you: "Tú", agent: "Agente" };

/** Who did it: the agent wears its identity color, you the ink, the system stays quiet. */
const ACTOR_CLASS: Record<Actor, string> = {
  agent: "font-semibold text-agent",
  you: "font-semibold text-foreground",
  system: "font-medium text-muted-foreground",
};

export function ActorName({ actor, className }: { actor: Actor; className?: string }) {
  return <span className={cn(ACTOR_CLASS[actor], className)}>{ACTOR_NAME[actor]}</span>;
}

export function ActorAvatar({ actor, className }: { actor: Actor; className?: string }) {
  if (actor === "agent") return <AgentAvatar className={cn("size-6 rounded-md", className)} />;
  if (actor === "you")
    return (
      <span
        className={cn(
          "flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground",
          className,
        )}
      >
        DH
      </span>
    );
  return (
    <span
      className={cn("flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground", className)}
    >
      <BellIcon className="size-3" aria-hidden="true" />
    </span>
  );
}
