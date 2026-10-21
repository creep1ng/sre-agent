import { ChevronDownIcon, ServerIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Severity } from "@/lib/types";
import { cn } from "@/lib/utils";
import { SEVERITY, TONE_TEXT } from "@/lib/vocabulary";

export interface ServiceStatus {
  service: string;
  /** New alerts and open incidents of the service in the inbox. */
  count: number;
  /** Worst severity among them; absent when the service is quiet. */
  severity?: Severity;
}

interface FilterProps {
  services: ServiceStatus[];
  value: string;
  onChange: (value: string) => void;
  total: number;
}

/** A single button beside the headline; scales to many services. */
export function MenuServiceFilter({ services, value, onChange, total }: FilterProps) {
  const active = services.filter((s) => s.count > 0);
  const selected = active.find((s) => s.service === value);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="self-start sm:self-auto">
          <ServerIcon />
          <span className="sr-only">Filtrar por servicio: </span>
          {selected ? selected.service : "Todos los servicios"}
          <span className="text-xs text-muted-foreground tabular">{selected ? selected.count : total}</span>
          <ChevronDownIcon className="text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="text-xs font-medium text-muted-foreground">Mostrar</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={selected ? selected.service : "all"} onValueChange={onChange}>
          <DropdownMenuRadioItem value="all">
            <span className="flex-1">Todos los servicios</span>
            <span className="text-xs text-muted-foreground tabular">{total}</span>
          </DropdownMenuRadioItem>
          <DropdownMenuSeparator />
          {active.map((s) => (
            <DropdownMenuRadioItem key={s.service} value={s.service}>
              <span className="flex-1">{s.service}</span>
              {s.severity && (
                <span className={cn("text-xs font-semibold", TONE_TEXT[SEVERITY[s.severity].tone])}>
                  {SEVERITY[s.severity].short}
                </span>
              )}
              <span className="w-4 text-right text-xs text-muted-foreground tabular">{s.count}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
