/*
 * The scenario simulator of the console (mock mode): an in-browser backend that plays the
 * agent through the scripted OpenTelemetry demo failures, and the screens that read it. It is
 * loaded by src/lib/simulator.ts in a tab opened with `?mock`; production code reaches it only
 * through that module.
 */
import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { toast } from "sonner";
import { setClock } from "@/hooks/use-now";
import { subscribeNotices, useStore } from "./store";

export { InboxPage } from "./inbox-page";
export { IncidentPage } from "./incident-page";
export { IncidentsPage } from "./incidents-page";
export { useInbox } from "./selectors";
export { useStore } from "./store";

/** Drives the mock backend: the agent advances on its own while the app is open. */
function Advance() {
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

/** The simulator's clock and its notices, in place of the live poller. */
export function Ticker() {
  return (
    <>
      <Advance />
      <Notifier />
    </>
  );
}
