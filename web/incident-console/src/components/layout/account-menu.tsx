import {
  FlaskConicalIcon,
  KeyRoundIcon,
  LogOutIcon,
  MonitorIcon,
  MoonIcon,
  RotateCcwIcon,
  SirenIcon,
  SunIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useTheme, type ThemePreference } from "@/hooks/use-theme";
import { useLanguage, useT, type Language } from "@/i18n";
import { useLive } from "@/lib/live";
import { appMode } from "@/lib/mode";
import { LIVE_SCENARIOS } from "@/lib/scenarios";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

/** A segmented choice: every option stays visible, the current one is pressed. */
function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; icon?: typeof SunIcon; lang?: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="border-t border-border py-3.5">
      <span className="mb-2 block text-sm text-muted-foreground">{label}</span>
      <div role="group" aria-label={label} className="flex rounded-[11px] border border-border bg-secondary p-[3px]">
        {options.map(({ value: option, label: text, icon: Icon, lang }) => (
          <button
            key={option}
            type="button"
            lang={lang}
            aria-pressed={value === option}
            onClick={() => onChange(option)}
            className={cn(
              "inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg px-1.5 py-2 text-sm font-medium text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
              value === option && "bg-panel text-foreground shadow-[0_0_0_1px_var(--rule)]",
            )}
          >
            {Icon && <Icon className="size-[15px]" aria-hidden="true" />}
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

const ROW =
  "flex w-full items-center gap-2.5 rounded-lg px-2 py-2.5 text-left text-sm text-[var(--text-2)] transition-colors outline-none hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50";

/** The simulator's controls, only in mock mode. */
function DemoScenario({ onDone }: { onDone: () => void }) {
  const agentFailure = useStore((s) => s.settings.agentFailure);
  const setAgentFailure = useStore((s) => s.setAgentFailure);
  const spawnAlert = useStore((s) => s.spawnAlert);
  const reset = useStore((s) => s.reset);
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className={ROW}>
        <FlaskConicalIcon className="size-4" aria-hidden="true" /> Escenario de demostración
      </DropdownMenuTrigger>
      <DropdownMenuContent side="right" align="end" className="w-72">
        <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">Simular una alerta nueva</DropdownMenuLabel>
        {LIVE_SCENARIOS.map((scenario) => (
          <DropdownMenuItem
            key={scenario.key}
            onSelect={() => {
              const created = spawnAlert(scenario.key);
              if (!created) toast.info("Esa alerta ya está en la bandeja o tiene un incidente abierto.");
              onDone();
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
            onDone();
            navigate("/");
            toast.success("Escenario reiniciado");
          }}
        >
          <RotateCcwIcon /> Reiniciar escenario
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Action({ icon: Icon, onClick, children }: { icon: typeof SunIcon; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className={ROW}>
      <Icon className="size-4" aria-hidden="true" /> {children}
    </button>
  );
}

/** The avatar opens language, theme and the session in one popover. */
export function AccountMenu({ onConnect, folded = false }: { onConnect: () => void; folded?: boolean }) {
  const theme = useTheme((s) => s.theme);
  const setTheme = useTheme((s) => s.setTheme);
  const language = useLanguage((s) => s.language);
  const setLanguage = useLanguage((s) => s.setLanguage);
  const token = useLive((s) => s.token);
  const disconnect = useLive((s) => s.disconnect);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const t = useT("shell");
  const live = appMode === "live";
  const name = live ? t("account.apiSession") : "demo-human";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-label={t("account.menu")}
        className={cn(
          "flex items-center gap-2.5 rounded-xl p-1.5 text-left transition-colors outline-none hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring/50 data-[state=open]:shadow-[0_0_0_3px_var(--mist-line)]",
          folded ? "mx-auto rounded-full" : "w-full",
        )}
      >
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[var(--avatar)] text-xs font-medium text-[var(--on-avatar)]">
          {live ? "API" : "DH"}
        </span>
        {!folded && <span className="min-w-0 flex-1 truncate text-sm">{name}</span>}
      </PopoverTrigger>
      <PopoverContent side={folded ? "right" : "top"} align="start" className="w-[300px] rounded-2xl p-[18px] pb-2">
        <span className="mb-4 block font-display text-[22px] leading-none">{name}</span>
        <Segmented<Language>
          label={t("account.language")}
          value={language}
          onChange={setLanguage}
          // Each language is named in itself, so it reads the same from either side.
          options={[
            { value: "es", label: "Español", lang: "es" },
            { value: "en", label: "English", lang: "en" },
          ]}
        />
        <Segmented<ThemePreference>
          label={t("account.theme")}
          value={theme}
          onChange={setTheme}
          options={[
            { value: "system", label: t("theme.system"), icon: MonitorIcon },
            { value: "light", label: t("theme.light"), icon: SunIcon },
            { value: "dark", label: t("theme.dark"), icon: MoonIcon },
          ]}
        />
        <div className="-mx-2 border-t border-border pt-1.5">
          {!live ? (
            <DemoScenario onDone={() => setOpen(false)} />
          ) : token ? (
            <Action
              icon={LogOutIcon}
              onClick={() => {
                // The credential only lives in memory: dropping it is the whole sign-out.
                disconnect();
                setOpen(false);
                navigate("/");
              }}
            >
              {t("account.signOut")}
            </Action>
          ) : (
            <Action
              icon={KeyRoundIcon}
              onClick={() => {
                setOpen(false);
                onConnect();
              }}
            >
              {t("account.connect")}
            </Action>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
