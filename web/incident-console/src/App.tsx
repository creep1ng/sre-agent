import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AppShell } from "@/components/layout/app-shell";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { setClock } from "@/hooks/use-now";
import { useApplyTheme } from "@/hooks/use-theme";
import { resumePolling, stopPolling } from "@/lib/live";
import { simulator } from "@/lib/simulator";
import { CatalogPage } from "@/pages/catalog-page";
import { AuditPage } from "@/features/admin/audit-page";
import { ConsumptionPage } from "@/features/admin/consumption-page";
import { IdentitiesPage } from "@/features/admin/identities-page";
import { KnowledgePage } from "@/features/admin/knowledge-page";
import { PermissionsPage } from "@/features/admin/permissions-page";
import { ResourcesPage } from "@/features/admin/resources-page";
import { SkillsPage } from "@/features/admin/skills-page";
import { LiveInbox } from "@/features/inbox/live-inbox";
import { LiveIncidentPage } from "@/pages/live-incident-page";

/** Keeps relative times fresh without the mock simulator. */
function Clock() {
  useEffect(() => {
    const id = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return null;
}

/** Live mode: the inbox polls the real API while the page is open. */
function LivePoller() {
  useEffect(() => {
    resumePolling();
    return () => stopPolling();
  }, []);
  return <Clock />;
}

export function App() {
  useApplyTheme();
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <TooltipProvider delayDuration={250}>
        {simulator ? <simulator.Ticker /> : <LivePoller />}
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={simulator ? <simulator.InboxPage /> : <LiveInbox />} />
            {/* The incident list reads the simulator only; live mode sends its address to the inbox. */}
            <Route path="incidentes" element={simulator ? <simulator.IncidentsPage /> : <Navigate to="/" replace />} />
            <Route path="incidentes/:incidentId" element={simulator ? <simulator.IncidentPage /> : <LiveIncidentPage />} />
            <Route path="acciones" element={<CatalogPage />} />
            <Route path="admin">
              <Route index element={<Navigate to="identidades" replace />} />
              <Route path="identidades" element={<IdentitiesPage />} />
              <Route path="permisos" element={<PermissionsPage />} />
              <Route path="recursos" element={<ResourcesPage />} />
              <Route path="skills" element={<SkillsPage />} />
              <Route path="conocimiento" element={<KnowledgePage />} />
              <Route path="consumo" element={<ConsumptionPage />} />
              <Route path="auditoria" element={<AuditPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
        <Toaster position="bottom-right" closeButton />
      </TooltipProvider>
    </BrowserRouter>
  );
}
