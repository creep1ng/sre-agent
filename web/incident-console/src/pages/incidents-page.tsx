import { SearchIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { ServiceChip, SeverityBadge, StatusPill } from "@/components/badges";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useNow } from "@/hooks/use-now";
import { formatDayTime, formatDuration } from "@/lib/format";
import { appMode } from "@/lib/mode";
import { incidentStatus } from "@/lib/status";
import { alertsOf, useStore } from "@/lib/store";
import type { Incident } from "@/lib/types";

export function IncidentsPage() {
  const now = useNow();
  const navigate = useNavigate();
  const incidents = useStore((s) => s.incidents);
  const alerts = useStore((s) => s.alerts);
  const [tab, setTab] = useState<"active" | "closed">(() =>
    incidents.some((i) => i.state !== "closed") ? "active" : "closed",
  );
  const [query, setQuery] = useState("");

  // The simulator's incidents are not shown as real ones; the API has no incident list yet.
  const listed = appMode === "mock" ? incidents : [];
  const active = listed.filter((i) => i.state !== "closed");
  const closed = listed.filter((i) => i.state === "closed");
  const rows = useMemo(() => {
    const list = tab === "active" ? active : closed;
    const q = query.trim().toLowerCase();
    return q ? list.filter((i) => `${i.id} ${i.title} ${i.service}`.toLowerCase().includes(q)) : list;
  }, [tab, active, closed, query]);

  const duration = (incident: Incident) => {
    const start = alertsOf({ alerts }, incident)[0]?.startedAt ?? incident.declaredAt;
    return formatDuration((incident.resolvedAt ?? now) - start);
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-8 lg:py-10">
      <header>
        <h1 className="font-display text-3xl tracking-tight sm:text-4xl">Incidentes</h1>
        <p className="mt-2 text-muted-foreground">Los abiertos y el historial con sus postmortems.</p>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={tab} onValueChange={(value) => setTab(value as "active" | "closed")}>
          <TabsList>
            <TabsTrigger value="active">Abiertos · {active.length}</TabsTrigger>
            <TabsTrigger value="closed">Cerrados · {closed.length}</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="relative sm:w-72">
          <SearchIcon className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar por título o servicio"
            className="pl-9"
            aria-label="Buscar incidentes"
          />
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border bg-card shadow-xs">
        {rows.length === 0 ? (
          <p className="px-5 py-12 text-center text-sm text-muted-foreground">
            {appMode === "live"
              ? "Abre los incidentes desde la bandeja."
              : tab === "active"
                ? "No hay incidentes abiertos."
                : "Todavía no hay incidentes cerrados."}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="hidden border-b bg-muted/40 text-left text-xs text-muted-foreground md:table-header-group">
              <tr>
                <th className="px-5 py-2.5 font-medium">Incidente</th>
                <th className="px-3 py-2.5 font-medium">Estado</th>
                <th className="px-3 py-2.5 font-medium">Declarado</th>
                <th className="px-5 py-2.5 text-right font-medium">Duración</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((incident) => (
                <tr
                  key={incident.id}
                  onClick={() => navigate(`/incidentes/${incident.id}`)}
                  onKeyDown={(event) => event.key === "Enter" && navigate(`/incidentes/${incident.id}`)}
                  tabIndex={0}
                  className="flex cursor-pointer flex-col gap-2 border-b px-5 py-4 transition-colors outline-none last:border-b-0 hover:bg-accent focus-visible:bg-accent md:table-row md:px-0 md:py-0"
                >
                  <td className="md:px-5 md:py-3.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{incident.id}</span>
                      <SeverityBadge severity={incident.severity} compact />
                      <ServiceChip service={incident.service} />
                    </div>
                    <div className="mt-1 font-medium">{incident.title}</div>
                  </td>
                  <td className="md:px-3 md:py-3.5">
                    <StatusPill status={incidentStatus(incident)} />
                  </td>
                  <td className="text-muted-foreground md:px-3 md:py-3.5">{formatDayTime(incident.declaredAt, now)}</td>
                  <td className="text-muted-foreground tabular md:px-5 md:py-3.5 md:text-right">{duration(incident)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
