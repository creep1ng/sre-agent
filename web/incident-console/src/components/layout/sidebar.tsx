import { ExternalLinkIcon, FileTextIcon, InboxIcon, LandmarkIcon, LayersIcon, SearchIcon } from "lucide-react";
import { NavLink } from "react-router";
import { AgentAvatar, Logo } from "@/components/brand";
import { StatusDot } from "@/components/badges";
import { Kbd } from "@/components/ui/kbd";
import type { InboxModel } from "@/lib/selectors";
import { incidentStatus } from "@/lib/status";
import { cn } from "@/lib/utils";
import { AccountMenu } from "./account-menu";

function NavItem({
  to,
  icon: Icon,
  label,
  count,
  highlight,
}: {
  to: string;
  icon: typeof InboxIcon;
  label: string;
  count?: number;
  highlight?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        cn(
          "group flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground",
          isActive && "bg-sidebar-accent text-foreground shadow-[inset_3px_0_0_var(--primary)]",
        )
      }
    >
      <Icon className="size-4" aria-hidden="true" />
      <span className="flex-1">{label}</span>
      {count !== undefined && count > 0 && (
        <span
          className={cn(
            "min-w-6 rounded-full px-1.5 py-0.5 text-center text-xs font-semibold tabular",
            highlight ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
          )}
        >
          {count}
        </span>
      )}
    </NavLink>
  );
}

function AgentPresence({ inbox }: { inbox: InboxModel }) {
  const stopped = inbox.active.find((incident) => incident.job?.failure);
  const busy = inbox.active.find((incident) => incidentStatus(incident).working);
  const label = stopped
    ? `Detenido · ${stopped.id}`
    : busy
      ? `${incidentStatus(busy).agentLabel ?? incidentStatus(busy).label} · ${busy.id}`
      : "Disponible";
  return (
    <div className="rounded-xl border border-sidebar-border bg-background/60 p-3">
      <div className="flex items-center gap-2.5">
        <AgentAvatar className="size-8" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">Agente de incidentes</div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <StatusDot tone={stopped ? "critical" : busy ? "info" : "success"} working={Boolean(busy) && !stopped} />
            <span className="truncate">{label}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Sidebar({
  inbox,
  onSearch,
  onConnect,
}: {
  inbox: InboxModel;
  onSearch: () => void;
  onConnect: () => void;
}) {
  return (
    <div className="flex h-full flex-col gap-6 p-4">
      <div className="px-2 pt-1">
        <Logo />
      </div>

      <button
        type="button"
        onClick={onSearch}
        className="flex h-9 items-center gap-2 rounded-lg border border-sidebar-border bg-background px-3 text-sm text-muted-foreground transition-colors hover:border-brand-line hover:text-foreground"
      >
        <SearchIcon className="size-4" aria-hidden="true" />
        <span className="flex-1 text-left">Buscar o ir a…</span>
        <Kbd>Ctrl K</Kbd>
      </button>

      <nav className="flex flex-col gap-1" aria-label="Principal">
        <NavItem to="/" icon={InboxIcon} label="Bandeja" count={inbox.attention} highlight />
        <NavItem to="/incidentes" icon={LayersIcon} label="Incidentes" count={inbox.active.length} />
        <NavItem to="/postmortems" icon={FileTextIcon} label="Postmortems" />
      </nav>

      {/* The administration console still lives outside the new console: one link, a new tab. */}
      <div className="mt-2 border-t border-sidebar-border pt-3">
        <nav aria-label="Administración">
          <a
            href="/public/admin/principals.html"
            target="_blank"
            rel="noopener noreferrer"
            className="flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
          >
            <LandmarkIcon className="size-4" aria-hidden="true" />
            <span className="flex-1">Gobierno de IA</span>
            <ExternalLinkIcon className="size-3.5 text-muted-foreground" aria-hidden="true" />
          </a>
        </nav>
      </div>

      <div className="mt-auto flex flex-col gap-3">
        <AgentPresence inbox={inbox} />
        <AccountMenu onConnect={onConnect} />
      </div>
    </div>
  );
}
