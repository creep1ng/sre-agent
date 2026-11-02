import { ExternalLinkIcon, InboxIcon, LandmarkIcon, SearchIcon, SirenIcon } from "lucide-react";
import type { ReactElement } from "react";
import { NavLink } from "react-router";
import { AgentAvatar, BrandMark, Logo } from "@/components/brand";
import { StatusDot } from "@/components/badges";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useT } from "@/i18n";
import { appMode } from "@/lib/mode";
import type { InboxModel } from "@/lib/selectors";
import { incidentStatus } from "@/lib/status";
import { cn } from "@/lib/utils";
import { AccountMenu } from "./account-menu";
import { FoldButton } from "./fold-button";

export const SIDEBAR_ID = "console-sidebar";

const ITEM =
  "group relative flex h-10 items-center gap-3 rounded-lg px-3 text-base font-medium text-muted-foreground transition-colors outline-none hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50";

/** A folded rail keeps only icons: the label stays for assistive tech and shows as a tooltip. */
function RailTip({ folded, label, children }: { folded: boolean; label: string; children: ReactElement }) {
  if (!folded) return children;
  return (
    <Tooltip>
      {/* A wrapper, because Slot would stringify NavLink's className function. */}
      <TooltipTrigger asChild>
        <span className="block">{children}</span>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

function NavItem({
  to,
  icon: Icon,
  label,
  count,
  highlight,
  folded,
}: {
  to: string;
  icon: typeof InboxIcon;
  label: string;
  count?: number;
  highlight?: boolean;
  folded: boolean;
}) {
  const counted = count !== undefined && count > 0;
  return (
    <RailTip folded={folded} label={label}>
      <NavLink
        to={to}
        end={to === "/"}
        className={({ isActive }) =>
          cn(
            ITEM,
            folded && "justify-center px-0",
            isActive && "bg-sidebar-accent text-foreground shadow-[inset_3px_0_0_var(--primary)]",
          )
        }
      >
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        <span className={cn("flex-1", folded && "sr-only")}>{label}</span>
        {counted && (
          <span
            className={cn(
              "min-w-6 rounded-full px-1.5 py-0.5 text-center text-xs font-semibold tabular",
              highlight ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
              folded && "absolute -top-1 right-0 min-w-5 px-1 py-0 text-[11px]",
            )}
          >
            {count}
          </span>
        )}
      </NavLink>
    </RailTip>
  );
}

function AgentPresence({ inbox, folded }: { inbox: InboxModel; folded: boolean }) {
  const t = useT("shell");
  const stopped = inbox.active.find((incident) => incident.job?.failure);
  const busy = inbox.active.find((incident) => incidentStatus(incident).working);
  const label = stopped
    ? t("agent.stopped", { id: stopped.id })
    : busy
      ? `${incidentStatus(busy).agentLabel ?? incidentStatus(busy).label} · ${busy.id}`
      : t("agent.idle");
  const dot = <StatusDot tone={stopped ? "critical" : busy ? "info" : "success"} working={Boolean(busy) && !stopped} />;
  if (folded) {
    return (
      <div className="relative mx-auto" title={`${t("agent.name")} · ${label}`}>
        <AgentAvatar className="size-8" />
        <span className="absolute -right-0.5 -bottom-0.5 flex rounded-full bg-sidebar p-0.5">{dot}</span>
        <span className="sr-only">{`${t("agent.name")} · ${label}`}</span>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-sidebar-border bg-background/60 p-3">
      <div className="flex items-center gap-2.5">
        <AgentAvatar className="size-8" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{t("agent.name")}</div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {dot}
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
  folded = false,
  onFoldedChange,
}: {
  inbox: InboxModel;
  onSearch: () => void;
  onConnect: () => void;
  folded?: boolean;
  /** Only the desktop sidebar folds; the mobile sheet passes nothing. */
  onFoldedChange?: (folded: boolean) => void;
}) {
  const t = useT("shell");
  return (
    <div className={cn("flex h-full flex-col gap-6 p-4", folded && "items-stretch px-3")}>
      <div className={cn("flex items-center gap-2 pt-1", folded ? "flex-col" : "justify-between pl-2")}>
        {folded ? <BrandMark className="size-6 text-[var(--mark)]" /> : <Logo />}
        {onFoldedChange && (
          <FoldButton
            side="left"
            folded={folded}
            onFoldedChange={onFoldedChange}
            controls={SIDEBAR_ID}
            label={t(folded ? "nav.unfold" : "nav.fold")}
          />
        )}
      </div>

      <RailTip folded={folded} label={t("search.label")}>
        <button
          type="button"
          onClick={onSearch}
          aria-label={folded ? t("search.label") : undefined}
          className={cn(
            "flex h-9 w-full items-center gap-2 rounded-lg border border-sidebar-border bg-background px-3 text-sm text-muted-foreground transition-colors hover:border-brand-line hover:text-foreground",
            folded && "justify-center px-0",
          )}
        >
          <SearchIcon className="size-4 shrink-0" aria-hidden="true" />
          {!folded && (
            <>
              <span className="flex-1 text-left">{t("search.open")}</span>
              <Kbd>Ctrl K</Kbd>
            </>
          )}
        </button>
      </RailTip>

      <nav className="flex flex-col gap-1" aria-label={t("nav.main")}>
        <NavItem to="/" icon={InboxIcon} label={t("nav.inbox")} count={inbox.attention} highlight folded={folded} />
        {/* The incident list still reads the simulator only, so live mode leaves it out. */}
        {appMode === "mock" && (
          <NavItem to="/incidentes" icon={SirenIcon} label={t("nav.incidents")} count={inbox.active.length} folded={folded} />
        )}
      </nav>

      {/* The administration console still lives outside the new console: one link, a new tab. */}
      <div className="mt-2 border-t border-sidebar-border pt-3">
        <nav aria-label={t("nav.admin")}>
          <RailTip folded={folded} label={t("nav.governance")}>
            <a
              href="/public/admin/principals.html"
              target="_blank"
              rel="noopener noreferrer"
              className={cn(ITEM, folded && "justify-center px-0")}
            >
              <LandmarkIcon className="size-4 shrink-0" aria-hidden="true" />
              <span className={cn("flex-1", folded && "sr-only")}>{t("nav.governance")}</span>
              {!folded && <ExternalLinkIcon className="size-3.5 text-muted-foreground" aria-hidden="true" />}
            </a>
          </RailTip>
        </nav>
      </div>

      <div className="mt-auto flex flex-col gap-3">
        <AgentPresence inbox={inbox} folded={folded} />
        <AccountMenu onConnect={onConnect} folded={folded} />
      </div>
    </div>
  );
}
