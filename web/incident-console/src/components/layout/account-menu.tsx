import { ChevronsUpDownIcon, FlaskConicalIcon, MonitorIcon, MoonIcon, RotateCcwIcon, SirenIcon, SunIcon } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme, type ThemePreference } from "@/hooks/use-theme";
import { LIVE_SCENARIOS } from "@/lib/scenarios";
import { useStore } from "@/lib/store";

export function AccountMenu() {
  const theme = useTheme((s) => s.theme);
  const setTheme = useTheme((s) => s.setTheme);
  const agentFailure = useStore((s) => s.settings.agentFailure);
  const setAgentFailure = useStore((s) => s.setAgentFailure);
  const spawnAlert = useStore((s) => s.spawnAlert);
  const reset = useStore((s) => s.reset);
  const navigate = useNavigate();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 text-left transition-colors outline-none hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring/50">
        <span className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
          DH
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-[13px]">demo-human</span>
          <span className="flex items-center gap-1 text-xs text-success">
            <span className="size-1.5 rounded-full bg-success" aria-hidden="true" />
            Sesión activa
          </span>
        </span>
        <ChevronsUpDownIcon className="size-4 text-muted-foreground" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-64">
        <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">Apariencia</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(value as ThemePreference)}>
          <DropdownMenuRadioItem value="light">
            <SunIcon /> Claro
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <MoonIcon /> Oscuro
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <MonitorIcon /> Como el sistema
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <FlaskConicalIcon /> Escenario de demostración
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="w-72">
            <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">Simular una alerta nueva</DropdownMenuLabel>
            {LIVE_SCENARIOS.map((scenario) => (
              <DropdownMenuItem
                key={scenario.key}
                onSelect={() => {
                  const created = spawnAlert(scenario.key);
                  if (!created) toast.info("Esa alerta ya está en la bandeja o tiene un incidente abierto.");
                  navigate("/");
                }}
              >
                <SirenIcon /> {scenario.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuCheckboxItem checked={agentFailure} onCheckedChange={(value) => setAgentFailure(Boolean(value))}>
              El agente falla al investigar
            </DropdownMenuCheckboxItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                reset();
                navigate("/");
                toast.success("Escenario reiniciado");
              }}
            >
              <RotateCcwIcon /> Reiniciar escenario
            </DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
