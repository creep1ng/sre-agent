# Record the remaining Canva clips

Produce only the missing videos: approval and conflict prototypes, a real persisted
triage incident reread, and real restricted-identity denial with unchanged state.
The user already has the simulated alert/declaration and two postmortem clips.

## Authorized scope and route

- Delegated direct: one local recording writer; no product/source/test changes,
  declarations, resets, grant changes, remote work, provider calls, or installs.
- Reuse existing local Compose services/images and the pinned recording checkouts:
  triage `734fa82cb13ed09494414892c14af8483f59a3bd`; review
  `738c86dd742b83fe689f5fb92d1c328e20ef3b11`.
- Existing review tests deliberately mock API responses. Label those clips as
  prototypes, never real approval execution. Real clips must use API/PostgreSQL.
- Private capture configuration/scripts and evidence may live in ignored
  `.demo-state/canva-clips-20261005`; user deliverables are videos only.
- No commits, pushes, new abstractions, source normalization or review START.
- User-authorized recovery: one environment correction and approval-only capture
  at native secure-context origin `http://127.0.0.1`, using the existing supported
  recorder image in the verified `sre-rec-review-20261005` web network namespace.
  Keep the original test/assertions and prior failed video unchanged; no security
  flags, product fixes or repeats of conflict/real/MCP journeys. Stop if it fails.

## Checks and failure cases

Effective TDD: unknown in current project configuration; this is recording and
existing E2E verification, not product implementation or a new unit-test suite.
Runner: existing Compose `e2e` service and containerized Playwright. No host package
tools. List/discover selected tests before the single foreground capture run.

1. Wrong checkout, missing image, unhealthy runtime or test discovery failure:
   stop the affected clip, retain the actual error; do not build silently.
2. No persisted declared triage incident: return the gap; never declare the user's
   original alert or substitute a fabricated incident.
3. Credential values, headers or DSNs in frames/logs: reject the artifact. Use
   masked password fields, private evidence, no traces or raw request dumps.
4. Denial must be real HTTP 403 for GET and POST in an isolated browser context;
   compare authoritative operator reads before/after. Do not assert made-up counts.
5. A video can exist after a failed test. Preserve failures; inspect real first,
   middle and last frames and final screenshots before calling a clip usable.
6. Reuse existing ffmpeg only if available; otherwise deliver WebM honestly.
   No installations or duplicate captures of completed clips.

## Acceptance criteria

- Four missing local videos have legible pacing and accurate persistent labels.
- Real reread uses the same incident ID/version from the current backend and
  reloads from the authoritative API without a duplicate transition.
- Restricted-identity GET/POST denial leaves the operator-visible persisted state
  unchanged; no claim of fixing the candidate's known same-context session bug.
- Commands, SHA, exact observed results, failures and media checks are private and
  repeatable; original sources, containers, data and existing clips are preserved.
- Output directory is ignored and private; credentials never enter deliverables.

## Tasks and progress

- [x] T1: Verify pinned sources, supported runner and current real triage data.
  Observed: triage/review db/api/web healthy on their existing loopback ports;
  review e2e image absent, supported postmortem e2e image present. Readiness is
  PostgreSQL HTTP 200. `.demo-state` is already ignored. SELECT-only proof: original
  `alert-payment-002` is declared, version 2, actor `demo-human`, incident
  `inc-e351310575012c26ad5ac6816756361c`. Existing supported postmortem e2e image
  `sha256:1d2b661f79bd76bc335915a388d2f72c8147faf8fd59fa539126fffafa7dc371`
  contains Playwright 1.63.0 (matches both locks) and bundled ffmpeg. Reuse through
  a private e2e-only Compose override; read-only pinned inputs, no build/install.
  Discovery lists exactly 2 review and 2 real tests. Bundled ffmpeg provides only
  VP8/PNG encoders: deliver WebM, no MP4 install. Initial unsupported `run --no-build`
  flag was corrected after CLI help; no scenario ran. First capture startup failed
  before tests with EACCES clearing the bind root. Logs retained; parent approved
  child `outputDir` correction, then one actual journey execution.
- [x] T2: Record the two selected existing review journeys with honest prototype
  labeling and readable pauses, retaining exact test outcomes.
  One actual capture: 1 passed (409 conflict), 1 failed (approval UUID assertion),
  32.2 seconds; exit 1. Approval produced timestamp-review fallback on insecure
  `http://web`; existing assertion expects a UUID. Failed video/evidence retained;
  do not claim passing approval proof or change assertions/product to conceal it.
  Authorized single recovery: verified exact healthy review web ownership/source,
  reused the pinned recorder image with `--network container:<verified-web-id>`,
  and changed ONLY private `baseURL` from `http://web` to `http://127.0.0.1`.
  Metadata probe before: secure_context=false/randomUUID=undefined; after:
  HTTP200, secure_context=true/randomUUID=function. No unsafe browser flags.
  Discovery: exactly 1 approval test. One selected foreground run: 1 passed in
  15.7 seconds, exit0; original UUID/one-request/non-execution assertions unchanged.
  Failed previous result/video retained; conflict, real and MCP were not repeated.
- [x] T3: Record real incident reread/reload and restricted GET/POST denial using
  the current version and before/after authoritative state, without declarations.
  One actual capture: 2 passed in 1.1 minutes; exit 0. Real original alert v2,
  incident `inc-e351310575012c26ad5ac6816756361c` v1; refresh/reload recovered the
  same authoritative JSON and timeline. Fresh restricted browser: GET 403 and
  POST open_triage 403; operator reread leaves triage v2 and incident v1 unchanged.
  Screenshots/videos and private persistence/security JSON exist and were inspected.
- [x] T4: Inspect screenshots and first/middle/last frames, convert only with an
  existing ffmpeg, read back artifacts and hand off videos plus private proof.
  Bundled container ffmpeg decoded all 12 first/middle/last frames (exit 0); all four
  final screenshots were visually inspected. Nonblank product UI, legible labels,
  no unmasked keys/headers in samples. Containerized text evidence scan: 31 files,
  zero credential values (exit 0). Trace off; directories 700/files 600, ignored.
  Passing deliverables (WebM, 1440x1000):
  - `videos/01-review-approval-prototype.webm`: 15.44 seconds, 1,161,913 bytes.
  - `videos/02-review-conflict-prototype.webm`: 21.00 seconds.
  - `videos/03-persisted-incident-real.webm`: 33.84 seconds.
  - `videos/04-restricted-denial-real.webm`: 34.52 seconds.
  Failed approval retained only as `private/approval-FAILED-idempotency.webm`,
  11.44 seconds; screenshot shows receipt, but the existing test failed. No MP4
  because the available container encoder supports only VP8/PNG; no install.
  Recovery after interruption confirmed completed results and no active e2e runner.
  Sources remain at the pinned SHAs and tracked diffs unchanged; no commits/resets.
  Corrected approval: bundled container ffmpeg decoded first0.08/middle7.72/last15.28
  frames, exit0. All three and final screenshot visually inspected: nonblank,
  readable permanent simulated-API label, no credentials/headers. Private text scan
  now 48 files, zero configured credential values, exit0; prior scan retained.
  New native WebM hash `fde04709fe067b9ec687bc2c5a75a83b7b626b07834228214af730d39920832c`.
  Old three video hashes, failed approval hash and copied spec hash verified unchanged;
  exact review web ID remained healthy. New files600/directories700, ignored.

## Evidence and next step

Local recording batch finished with 4 usable clips; previous failed approval preserved.
Next: parent independent readback, then video-only handoff. Do not repeat journeys.
Exact commands and statuses: `.demo-state/canva-clips-20261005/private/run-captures.sh`
and `private/capture-status.txt`; original startup and discovery failures retained.
Authorized recovery command/status: `private/run-approval-localhost.sh`,
`private/approval-localhost-status.txt` and `private/capture-approval-localhost.log`.
Before/after origin proof: `private/origin-context.log` and
`private/origin-localhost-context.log`; corrected result under
`approval-localhost-results/results/`. New media and sanitization proof use the
`private/approval-localhost-` prefix; previous evidence was not overwritten.
All private artifact paths above are relative to `.demo-state/canva-clips-20261005`.
Known OTel/MCP remote gap remains outside this local batch; no remote provisioning.
Engram mirror: `odd/remaining-demo-clips/tasks` (full document plus relative locator).
Rollback: remove only this tracking document and new private capture artifacts.
No backend rollback is required because recording must not change authorized state.

## Authorized extension: isolated local MCP evidence

The user approved continuing the final MCP and allow/revoke/deny videos through the
local section-11 recipe. This extension changes only a NEW disposable Compose project
from base SHA `f9028a7764263d8e3a298b43737075b27b9d0b36`. The earlier no-grant-change
rule still applies to base/triage/review/postmortem services: only fresh synthetic
principals/credentials/grants in the NEW project's database are authorized here.

Use the versioned overlays in order: `compose.yaml`, `compose.mcp.yaml`,
`compose.issue29-counter.yaml`, `compose.issue30.yaml`. Real Grafana/Prometheus,
instrumentation and audited HTTP are required; inert Issue29-only output is not proof.
No AWS, remote/tunnel, provider/model call, host install, socket mount, source or existing
`.env` modification. Prefer existing pinned images and Compose build cache; only the
versioned Compose build recipe may run. The new project must have no preexisting resources
and publishes no host ports. Preserve the prior usable videos and failed approval.

Private artifacts/scripts may be written under the already-ignored local `.demo-state`
or `/tmp`, mode 700 directories/600 evidence. Retain original JSON and synthetic audit
rows. Stop only the new project at completion/failure; never remove volumes or prune.
Forecast: ten recipe services, two scoped networks, one PostgreSQL volume, cached API/
checks builds; one replay, one derived revocation proof, one video-only recording batch.

The deliverable is explicitly a technical API-evidence presentation generated from actual
sanitized JSON, NOT product UI. Show observed 200/vector(1)/tools-call1/request correlation,
then real revoke204/deny403/calls0 and unchanged API identity. `vector(1)` does not prove
payment recovery. Keep audit/UUID/windows and HTTP/forwarding proof independently readable.
Effective TDD remains unspecified: execute the existing containerized replay and ordinary
functional/media checks, not an invented TDD mode or new product/unit tests.

- [x] T5: Verify fresh-project absence, pinned base and overlays; bootstrap only the new
  Issue30 runtime with no published ports and compare protected-resource identities.
  Observed: `runbook-mcp-20261005-82d780df` verified absent before setup; all four pinned
  third-party images and recorder image existed. Versioned Compose builds reused cache;
  setup exit0. Ten recipe services created, runtime/boundary scoped networks, DB named
  volume plus one Prometheus image-managed anonymous data volume; Grafana has no
  volume mount. No host ports.
  DB/API/Grafana/Prometheus healthy; migrate/seed/MCP seed completed. Existing-resource
  identities and original `.env` digest unchanged. A postcheck initially compared
  hash output including different filenames; corrected digest-only comparison passed.
  Private state/capture root:
  `.demo-state/canva-mcp-20261005-82d780df`; ephemeral MCP token file mode600.
- [x] T6: Run `issue30_capture.py` once, then the exact runbook synthetic allow/revoke/deny
  extension; inspect real counters/UUID/audit and compare API ID/start/restarts/PID.
  One foreground replay: exit0, 10 cases, no failures; 9 correlated audit rows (401
  intentionally has none). Cold real request `2b7f1a75-aad2-42b9-a6a9-27e206a5c644`:
  HTTP200, vector_count1/sample_value1, handshake1 plus tools/call1 and real forward1.
  Exact derived extension: exit0, allow200/tools1, revoke204, deny403/tools0 with zero
  HTTP/upstream attempts and no forwarded methods; revoked synthetic grant retained.
  UUIDs `300be8f0-0c18-4eed-8fac-80e75bbc34ab` and
  `27ecf12b-2e9f-4659-afaf-9c1fbe859715`; two metadata-only audit rows with matching
  response/authorization stages. API ID/start/restart-count/PID comparison passed.
  Original sanitized JSON and identity snapshots retained in private `captures/`.
- [x] T7: Record readable WebM evidence clip(s) using the existing pinned Playwright
  container; inspect screenshots/first-middle-last frames and exclude credentials.
  One offline recording batch exit0, Playwright1.63.0; native WebM/VP8/1440x1000:
  `media/videos/05-mcp-vector1-real-evidence.webm` 49.20 seconds (3,380,715 bytes),
  `media/videos/06-grant-revoke-deny-real-evidence.webm` 48.16 seconds (3,758,235 bytes).
  Six screenshots and six decoded first/middle/last frames inspected: nonblank,
  readable actual statuses/counters/UUID/audit, permanent technical-evidence/not-UI
  label; no credentials. No shortening, speeding, generated screenshot or rerun.
  Initial decoder command omitted stdin forwarding and did nothing; mounted-script
  correction ran. Initial self-imposed 30–45s gate rejected native duration; parent
  clarified it is advisory and accepted readable 48–49s. Failures/clarification kept.
  Corrected metadata/decode check exit0; ten JSON/snapshot/panel text files scanned,
  zero credential values. Native JSON hashes unchanged; directories700/files600.
  Only fresh project stopped exit0, containers/volumes/synthetic audit retained;
  protected preexisting containers/volumes and `.env` digest remain unchanged.
  Stop metadata: `grafana-mcp` and `issue30-fault-proxy` exited137, OOMKilled=false;
  other eight exited0. These codes are from after completed proof, not replay failures.

Extension next step: parent independent readback of private JSON, identity and media proof,
then hand off the two untouched native videos. T1–T7 complete; approval prototype T2
passed its explicitly authorized localhost recovery. Historical failures are retained.
No AWS decision or model call occurred.
