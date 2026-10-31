import { FileTextIcon, InboxIcon, LayersIcon, MonitorIcon, MoonIcon, SirenIcon, SunIcon } from "lucide-react";
import { useNavigate } from "react-router";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { useTheme } from "@/hooks/use-theme";
import { appMode } from "@/lib/mode";
import { incidentStatus } from "@/lib/status";
import { useStore } from "@/lib/store";
import { SEVERITY } from "@/lib/vocabulary";

export function CommandMenu({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate();
  const incidents = useStore((s) => s.incidents);
  const alerts = useStore((s) => s.alerts);
  const setTheme = useTheme((s) => s.setTheme);
  // The seeded alert commands belong to the simulator, not to the live inbox.
  const newAlerts = appMode === "mock" ? alerts.filter((alert) => alert.status === "new") : [];

  const go = (to: string) => {
    onOpenChange(false);
    navigate(to);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Buscar" description="Busca incidentes, alertas o acciones">
      <CommandInput placeholder="Busca un incidente, una alerta o una acción…" />
      <CommandList>
        <CommandEmpty>No encontramos nada con ese texto.</CommandEmpty>
        <CommandGroup heading="Ir a">
          <CommandItem onSelect={() => go("/")}>
            <InboxIcon /> Bandeja
          </CommandItem>
          <CommandItem onSelect={() => go("/incidentes")}>
            <LayersIcon /> Incidentes
          </CommandItem>
          <CommandItem onSelect={() => go("/postmortems")}>
            <FileTextIcon /> Postmortems
          </CommandItem>
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
        <CommandGroup heading="Incidentes">
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
        <CommandSeparator />
        <CommandGroup heading="Apariencia">
          <CommandItem onSelect={() => (setTheme("light"), onOpenChange(false))}>
            <SunIcon /> Tema claro
          </CommandItem>
          <CommandItem onSelect={() => (setTheme("dark"), onOpenChange(false))}>
            <MoonIcon /> Tema oscuro
          </CommandItem>
          <CommandItem onSelect={() => (setTheme("system"), onOpenChange(false))}>
            <MonitorIcon /> Tema del sistema
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
