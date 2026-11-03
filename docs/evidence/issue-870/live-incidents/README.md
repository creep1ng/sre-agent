# Issue 870 / 715: live `/app/incidentes` opens the inbox

`incidentes-en-vivo.png`: `web/incident-console/e2e/landing.spec.ts` after it opened `/app/incidentes` in live mode on
the web proxy of `compose.yaml` alone (tested SHA 7ac22fcc80e1d7d4c749fcf407f3b7fcf11ee102). The page is the inbox
(`/app/`), asking for an API key, and no simulated `INC-…` incident shows. The same journey checks that
`/?view=war-room` without an incident lands on `/app/` too.

Repeat: the commands of `docs/evidence/issue-870/landing/README.md`.
