import type { Messages } from "@/i18n";
import type inbox from "../es/inbox";

export default {
  "headline.one": "One",
  "headline.one.rest": "decision is waiting for you.",
  "headline.many": "{count}",
  "headline.many.rest": "decisions are waiting for you.",
  "headline.none": "Nothing is waiting for you.",
  "decision.waiting": "waiting since {time}",
  "decision.open": "Review and decide",
  "decision.escalate": "Midnight needs your permission to continue.",
  "coffee.lead": "While you have your coffee,",
  "coffee.em": "look at this",
  "coffee.recovered": "recovered.",
  "coffee.ended": "finished its investigation without proposing an action.",
  "night.title": "Last night",
  "night.incident": "Incident opened.",
  "night.deploy": "Deploy of",
  "night.rollback": "Rollback of",
  "night.ci": "CI run of",
  "night.failed": "Failed.",
  "state.connect": "Connect the API to see your inbox.",
  "state.auth": "The API rejected the key.",
  "state.forbidden": "Your key cannot read incidents.",
  "state.error": "We could not read your inbox. It retries on its own.",
  "state.loading": "Reading your inbox…",
  "state.action": "Connect API",
} satisfies Messages<typeof inbox>;
