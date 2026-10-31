import { useEffect, useRef } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { setClock } from "@/hooks/use-now";
import { useApplyTheme } from "@/hooks/use-theme";
import { resumePolling, stopPolling } from "@/lib/live";
import { appMode } from "@/lib/mode";
import { subscribeNotices, useStore } from "@/lib/store";
import { InboxPage } from "@/pages/inbox-page";
import { IncidentPage } from "@/pages/incident-page";
import { IncidentsPage } from "@/pages/incidents-page";

/** Drives the mock backend: the agent advances on its own while the app is open. */
function Simulator() {
  useEffect(() => {
    let lastSecond = 0;
    const id = window.setInterval(() => {
      const now = Date.now();
      useStore.getState().tick(now);
      const second = Math.floor(now / 1000);
      if (second !== lastSecond) {
        lastSecond = second;
        setClock(now);
      }
    }, 400);
    return () => window.clearInterval(id);
  }, []);
  return null;
}

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

function Notifier() {
  const navigate = useNavigate();
  const location = useLocation();
  const pathRef = useRef(location.pathname);
  pathRef.current = location.pathname;
  useEffect(
    () =>
      subscribeNotices((notice) => {
        if (notice.href && notice.href !== "/" && notice.href === pathRef.current) return;
        const show =
          notice.tone === "success"
            ? toast.success
            : notice.tone === "warning"
              ? toast.warning
              : notice.tone === "error"
                ? toast.error
                : toast.info;
        show(notice.title, {
          description: notice.description,
          duration: 7000,
          action:
            notice.href && notice.actionLabel
              ? { label: notice.actionLabel, onClick: () => navigate(notice.href!) }
              : undefined,
        });
      }),
    [navigate],
  );
  return null;
}

export function App() {
  useApplyTheme();
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <TooltipProvider delayDuration={250}>
        {appMode === "mock" ? <Simulator /> : <LivePoller />}
        <Notifier />
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<InboxPage />} />
            <Route path="incidentes" element={<IncidentsPage />} />
            <Route path="incidentes/:incidentId" element={<IncidentPage />} />
            <Route path="postmortems" element={<IncidentsPage key="postmortems" initialTab="closed" />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
        <Toaster position="bottom-right" closeButton />
      </TooltipProvider>
    </BrowserRouter>
  );
}
