import { InboxIcon, ShieldCheckIcon, SirenIcon } from "lucide-react";
import { useNavigate } from "react-router";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useT } from "@/i18n";
import { ADMIN_NAV } from "./sidebar";
import { incidentStatus } from "@/lib/status";
import { simulator } from "@/lib/simulator";
import { SEVERITY } from "@/lib/vocabulary";

export function CommandMenu({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate();
  const t = useT("shell");
  const admin = useT("admin");
  // Seeded alerts and incidents belong to the simulator, not to the live console.
  const incidents = simulator?.useStore((s) => s.incidents) ?? [];
  const alerts = simulator?.useStore((s) => s.alerts) ?? [];
  const mock = Boolean(simulator);
  const newAlerts = alerts.filter((alert) => alert.status === "new");

  const go = (to: string) => {
    onOpenChange(false);
    navigate(to);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title={t("search.label")} description={t("command.description")}>
      <CommandInput placeholder={t("command.placeholder")} />
      <CommandList>
        <CommandEmpty>{t("command.empty")}</CommandEmpty>
        <CommandGroup heading={t("command.goTo")}>
          <CommandItem onSelect={() => go("/")}>
            <InboxIcon /> {t("nav.inbox")}
          </CommandItem>
          {mock && (
            <CommandItem onSelect={() => go("/incidentes")}>
              <SirenIcon /> {t("nav.incidents")}
            </CommandItem>
          )}
          <CommandItem onSelect={() => go("/acciones")}>
            <ShieldCheckIcon /> {t("nav.actions")}
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading={t("nav.admin")}>
          {ADMIN_NAV.map(({ to, icon: Icon, label }) => (
            <CommandItem key={to} onSelect={() => go(to)}>
              <Icon /> {admin(label)}
            </CommandItem>
          ))}
        </CommandGroup>
        {newAlerts.length > 0 && (
          <CommandGroup heading="Alertas nuevas">
            {newAlerts.map((alert) => (
              <CommandItem key={alert.id} value={`declarar ${alert.title} ${alert.service}`} onSelect={() => go(`/?declarar=${alert.id}`)}>
                <SirenIcon />
                <span className="flex-1">Declarar: {alert.title}</span>
                <span className="text-xs text-muted-foreground">{SEVERITY[alert.severity].short}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {incidents.length > 0 && (
          <CommandGroup heading={t("nav.incidents")}>
            {incidents.map((incident) => (
              <CommandItem
                key={incident.id}
                value={`${incident.id} ${incident.title} ${incident.service}`}
                onSelect={() => go(`/incidentes/${incident.id}`)}
              >
                <span className="font-mono text-xs text-muted-foreground">{incident.id}</span>
                <span className="flex-1 truncate">{incident.title}</span>
                <span className="text-xs text-muted-foreground">{incidentStatus(incident).label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
