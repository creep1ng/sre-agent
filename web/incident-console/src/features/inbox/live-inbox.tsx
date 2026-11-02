import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { ConnectDialog } from "@/features/inbox/connect-dialog";
import { useNow } from "@/hooks/use-now";
import { LOCALES, useLanguage, useT } from "@/i18n";
import { useLive } from "@/lib/live";
import { useInboxData, watchInbox, type InboxIncident } from "./live-data";
import { firstSentence, headlineOf, inboxSections, type NightEvent } from "./sections";

const SEEN_KEY = "midnight-inbox-seen";
const DAY_MS = 24 * 60 * 60 * 1000;
let lastSeen: number | undefined;

/** When the operator last opened the inbox (a day ago the first time); this visit becomes the next one. */
function lastSeenOnce(): number {
  if (lastSeen !== undefined) return lastSeen;
  let stored = Number.NaN;
  try {
    stored = Number(localStorage.getItem(SEEN_KEY));
    localStorage.setItem(SEEN_KEY, String(Date.now()));
  } catch {
    // Without storage every visit looks back one day.
  }
  lastSeen = stored > 0 ? stored : Date.now() - DAY_MS;
  return lastSeen;
}

/** A span as a number and its unit, the way the decision and the digest lead with it. */
function span(ms: number): [string, string] {
  const minutes = Math.max(1, Math.round(ms / 60_000));
  if (minutes < 60) return [String(minutes), "min"];
  const hours = Math.round(minutes / 60);
  return hours < 48 ? [String(hours), "h"] : [String(Math.round(hours / 24)), "d"];
}

function useClockTime() {
  const language = useLanguage((state) => state.language);
  return useMemo(() => {
    const format = new Intl.DateTimeFormat(LOCALES[language], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    return (iso: string | number) => format.format(new Date(iso));
  }, [language]);
}

const incidentPath = (incident: InboxIncident) => `/incidentes/${incident.incident_id}`;

function Decision({ incident, words, now }: { incident: InboxIncident; words: string | null; now: number }) {
  const t = useT("inbox");
  const clock = useClockTime();
  const decision = incident.pending_decision!;
  const [value, unit] = span(now - Date.parse(decision.waiting_since));
  const text = words ?? (decision.command === "escalate" ? t("decision.escalate") : null);
  return (
    <article
      data-decision
      className="grid gap-6 rounded-[18px] border border-l-[6px] border-star bg-star/10 px-6 py-7 sm:grid-cols-[220px_minmax(0,1fr)] sm:gap-10 sm:px-9 sm:py-8"
    >
      <div className="font-display text-[88px] leading-[.85] font-light tracking-[-.04em] text-star-ink sm:text-[112px]">
        {value}
        <small className="text-[.45em] tracking-normal">&nbsp;{unit}</small>
      </div>
      <div className="min-w-0">
        <div className="mb-3.5 flex flex-wrap gap-3 font-mono text-[13px] text-star-ink">
          <span>{incident.service ?? incident.incident_id}</span>
          <span className="text-muted-foreground">{t("decision.waiting", { time: clock(decision.waiting_since) })}</span>
        </div>
        <h3 className="mb-3 font-display text-3xl leading-[1.1] tracking-[-.015em] sm:text-[38px]">{headlineOf(incident)}</h3>
        {text && <p className="mb-5 max-w-[56ch] text-[var(--text-2)]">{text}</p>}
        <Link
          to={incidentPath(incident)}
          className="inline-flex rounded-[10px] bg-star px-5 py-4 text-[15px] font-medium text-on-star transition-opacity hover:opacity-90"
        >
          {t("decision.open")}
        </Link>
      </div>
    </article>
  );
}

function Tip({ incident }: { incident: InboxIncident }) {
  const t = useT("inbox");
  const recovered = incident.latest_run?.status !== "terminated";
  const [value, unit] = span(Date.parse(incident.updated_at) - Date.parse(incident.opened_at));
  return (
    <Link
      to={incidentPath(incident)}
      className="rounded-2xl border bg-panel px-7 py-6 transition-colors hover:bg-accent"
    >
      <b className="mb-3 block font-display text-6xl leading-none font-light tracking-[-.03em]">
        {value}&nbsp;{unit}
      </b>
      <p className="text-[var(--text-2)]">
        <strong className="font-medium text-foreground">{incident.service ?? incident.incident_id}</strong>{" "}
        {t(recovered ? "coffee.recovered" : "coffee.ended")} {headlineOf(incident)}
      </p>
    </Link>
  );
}

function NightRow({ event }: { event: NightEvent }) {
  const t = useT("inbox");
  const clock = useClockTime();
  let what: ReactNode;
  if (event.kind === "alert") {
    what = (
      <>
        <b className="font-medium text-foreground">{event.alert.service}</b> {firstSentence(event.alert.summary)}
      </>
    );
  } else if (event.kind === "incident") {
    what = (
      <Link to={incidentPath(event.incident)} className="hover:underline">
        {t("night.incident")} <b className="font-medium text-foreground">{event.incident.service ?? event.incident.incident_id}</b>:{" "}
        {headlineOf(event.incident)}
      </Link>
    );
  } else {
    const change = event.change;
    what = (
      <>
        {t(`night.${change.kind}`)} <b className="font-medium text-foreground">{change.service}</b>
        {change.version ? ` ${change.version}.` : "."} {change.status === "failed" && t("night.failed")}
      </>
    );
  }
  return (
    <li className="grid grid-cols-[70px_minmax(0,1fr)] items-baseline gap-5 border-t py-4 text-[var(--text-2)]">
      <time className="font-mono text-sm font-medium text-info">{clock(event.at)}</time>
      <span>{what}</span>
    </li>
  );
}

export function LiveInbox() {
  const t = useT("inbox");
  const now = useNow();
  const token = useLive((state) => state.token);
  const alerts = useLive((state) => state.alerts);
  const { phase, incidents, changes, proposals } = useInboxData();
  const [connectOpen, setConnectOpen] = useState(false);
  useEffect(() => watchInbox(), []);
  const seen = lastSeenOnce();
  const { decisions, coffee, night } = useMemo(
    () => inboxSections(incidents, alerts, changes, now, seen),
    [incidents, alerts, changes, now, seen],
  );

  const state = !token ? "connect" : phase === "ready" ? null : phase === "idle" ? "loading" : phase;
  if (state) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col items-start gap-6 px-4 py-10 sm:px-14 sm:py-14">
        <h1 className="font-display text-4xl font-light tracking-[-.02em] sm:text-5xl">{t(`state.${state}`)}</h1>
        {(state === "connect" || state === "auth" || state === "forbidden") && (
          <Button variant="outline" onClick={() => setConnectOpen(true)}>
            {t("state.action")}
          </Button>
        )}
        <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col px-4 py-10 sm:px-14 sm:py-14">
      <h1 className="mb-10 font-display text-4xl font-light tracking-[-.02em] sm:text-5xl">
        {decisions.length === 0 ? (
          t("headline.none")
        ) : (
          <>
            <em data-decision className="text-star-ink">{decisions.length === 1 ? t("headline.one") : t("headline.many", { count: decisions.length })}</em>{" "}
            {t(decisions.length === 1 ? "headline.one.rest" : "headline.many.rest")}
          </>
        )}
      </h1>

      {decisions.length > 0 && (
        <div className="flex flex-col gap-6">
          {decisions.map((incident) => (
            <Decision key={incident.incident_id} incident={incident} words={proposals[incident.incident_id] ?? null} now={now} />
          ))}
        </div>
      )}

      {coffee.length > 0 && (
        <section className="mt-16">
          <h2 className="mb-6 font-display text-4xl leading-[1.05] font-light tracking-[-.02em]">
            {t("coffee.lead")} <em>{t("coffee.em")}</em>.
          </h2>
          <div className="grid gap-5 sm:grid-cols-2">
            {coffee.map((incident) => (
              <Tip key={incident.incident_id} incident={incident} />
            ))}
          </div>
        </section>
      )}

      {night.length > 0 && (
        <section className="mt-16">
          <h2 className="mb-4 font-display text-2xl text-[var(--text-2)]">{t("night.title")}</h2>
          <ol>
            {night.map((event) => (
              <NightRow key={`${event.kind}-${event.at}-${event.kind === "alert" ? event.alert.alert_id : event.kind === "incident" ? event.incident.incident_id : event.change.change_id}`} event={event} />
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
