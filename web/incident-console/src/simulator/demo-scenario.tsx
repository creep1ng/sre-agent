import { FlaskConicalIcon, RotateCcwIcon, SirenIcon } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { ROW } from "@/components/layout/account-menu";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LIVE_SCENARIOS } from "./scenarios";
import { useStore } from "./store";

/** The simulator's controls, only in mock mode. */
export function DemoScenario({ onDone }: { onDone: () => void }) {
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
