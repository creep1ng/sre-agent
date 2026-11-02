import {
  ChevronsUpDownIcon,
  FlaskConicalIcon,
  KeyRoundIcon,
  LogOutIcon,
  MonitorIcon,
  MoonIcon,
  RotateCcwIcon,
  SirenIcon,
  SunIcon,
} from "lucide-react";
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
import { useLanguage, useT, type Language } from "@/i18n";
import { useLive } from "@/lib/live";
import { appMode } from "@/lib/mode";
import { LIVE_SCENARIOS } from "@/lib/scenarios";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function AccountMenu({ onConnect }: { onConnect: () => void }) {
  const theme = useTheme((s) => s.theme);
  const setTheme = useTheme((s) => s.setTheme);
  const agentFailure = useStore((s) => s.settings.agentFailure);
  const setAgentFailure = useStore((s) => s.setAgentFailure);
  const spawnAlert = useStore((s) => s.spawnAlert);
  const reset = useStore((s) => s.reset);
  const token = useLive((s) => s.token);
  const disconnect = useLive((s) => s.disconnect);
  const navigate = useNavigate();
  const live = appMode === "live";
  const t = useT("shell");
  const language = useLanguage((s) => s.language);
  const setLanguage = useLanguage((s) => s.setLanguage);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 text-left transition-colors outline-none hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring/50">
        <span className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
          {live ? "API" : "DH"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-[13px]">{live ? t("account.apiSession") : "demo-human"}</span>
          <span
            className={cn(
              "flex items-center gap-1 text-xs",
              live && !token ? "text-muted-foreground" : "text-success",
            )}
          >
            <span
              className={cn("size-1.5 rounded-full", live && !token ? "bg-muted-foreground" : "bg-success")}
              aria-hidden="true"
            />
            {live ? t(token ? "account.connected" : "account.disconnected") : t("account.active")}
          </span>
        </span>
        <ChevronsUpDownIcon className="size-4 text-muted-foreground" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-64">
        <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">{t("account.theme")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(value as ThemePreference)}>
          <DropdownMenuRadioItem value="system">
            <MonitorIcon /> {t("theme.system")}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="light">
            <SunIcon /> {t("theme.light")}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <MoonIcon /> {t("theme.dark")}
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">{t("account.language")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={language} onValueChange={(value) => setLanguage(value as Language)}>
          {/* Each language is named in itself, so it reads the same from either side. */}
          <DropdownMenuRadioItem value="es" lang="es">
            Español
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="en" lang="en">
            English
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        {live ? (
          <>
            <DropdownMenuItem onSelect={onConnect}>
              <KeyRoundIcon /> {t("account.connect")}
            </DropdownMenuItem>
            {token && (
              <DropdownMenuItem
                onSelect={() => {
                  disconnect();
                  toast.success(t("account.disconnected.toast"));
                }}
              >
                <LogOutIcon /> {t("account.disconnect")}
              </DropdownMenuItem>
            )}
          </>
        ) : (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              <FlaskConicalIcon /> Escenario de demostración
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="w-72">
              <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">
                Simular una alerta nueva
              </DropdownMenuLabel>
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
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
