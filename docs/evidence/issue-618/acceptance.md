# Issue 618 acceptance matrix — 2026-10-13

Implementation and the reviewed dependency stack are integrated in main. This is
**not full issue acceptance**: independent human reproduction remains pending.
Project midnight.agent was consulted live (issue OPEN/Todo). No paid LLM call
was performed; readiness and healthy containers do not satisfy an OKR.

## Final integrated main

[Actual report15](15-main-aws.txt) and [Chromium capture](15-main-aws.png) record
one fresh standalone main checkout at `220cd4625f1e7c9f719aedab71d0232e6ee40e73`.
First/repeated canonical setup, actual web/API200, workflow/denial/audit, real
owner fail/reset and isolation passed. Baseline14calls/0errors/6orders;
failure148calls/32errors/0orders/proxy500x13; recovery134calls/0errors/8orders.
Disconnected startup failed closed; SRE-only stop retained volumes and the
previous active project; reconnection/restart is recorded separately in report15.
See [container reproduction](15-main-reproduction.md). All reviewed slices
merged normally with current-head Quality/governance green and <=400 lines.
Main hosted CI is recorded separately; PR green is not asserted as main CI.
[Same-main controlled local report16](16-main-local-controlled.txt) verifies
local first/repeat, workflow/audit/denial, port conflict and prepared fixture
outage/recovery/stop/restart. This is not real local OTel or signal recovery.

## Observed evidence

- [HTTP/store report](01-provision.txt): triage200/declare201/start201, state/events200,
  restricted403, admin audit200. Stable principals/credential hashes/grants/incidents;
  revoked-grant rejection. Controlled FastAPI/PostgreSQL, not successful LLM inference.
- [CLI preflight report](02-preflight.txt): eight independent invalid inputs rejected,
  including missing key, duplicate prefix, placeholder, shell injection, unsafe project,
  invalid mode, blocked AWS and invalid port. No secret output or Docker mutation.
- [CLI repeat report](03-repeat.txt): first/repeated preparation, HTTP journey, stable
  data/audit, occupied port, owned MCP fixture outage/recovery, scoped stop/restart.
  Reproduced also from a Linux Docker container using the PR command.
- Existing compatibility suite: **73 passed44.95s**. Source lint and format pass; global source lint also passes.
  Harness container: provider/MCP secrets absent; direct upstream DNS denied.
- Hosted initial CI failed incident persistence: new fixture dropped/recreated public
  schema and lost default usage privileges. Fixed to preserve schema, drop only test
  tables/function; complete preserved suite now passes:1848 passed,1 live-smoke skip,2 deprecation warnings (468.59s). Do not cite initial
  CI as green. No existing test or runtime authorization boundary was weakened.

- [Real AWS bootstrap report](05-aws-bootstrap.txt): explicit launch, 2h scheduled
  expiry, no inbound security-group rules, SSM tunnel, storefront/Grafana HTTP200.
  This historical initial probe found no MCP (HTTP404). Reports07–09 below
  supersede that initial deployment gap, without rewriting historical evidence.
- Hosted CI run38465270699 passed all technical jobs for PR624 head39b8a2c,
  including contracts, Compose and production browser; draft/human gates remain.

- [Producer MCP report](07-aws-mcp.txt): explicit locked-image preparation and
  anonymous401; private SSM handoff, internal credential-free relay, owner fail/reset.
- [Real AWS journey](09-aws-journey.txt): baseline226calls/0errors/16orders; failure
  52calls/12errors/0orders/proxy500x11; recovery26calls/0errors/4orders/proxy200x4.
  Actual governed metric/log queries; triage/run/read/events/audit and restricted403.
  Second setup preserved domain state/credential digest and retained audit.
- [Real harness isolation](09-aws-isolation.txt): no MCP/provider/AWS secret env,
  direct MCP and external transport unreachable. No paid inference was enabled.
- [Current compatibility report](09-current-suite.txt): 1908passed,1 live-smoke skip,
  2 deprecation warnings,400.63s. Integrated source61a031c plus new E2E script;
  committed runtime/test tree8aabe3853a0920113ef22a856d74331aa4eeaa47 unchanged.
  Current global Ruff passes; hosted evidence for old624 is not new-candidate CI.

- [Containerized production API setup](11-container-setup.txt): canonical AWS
  readiness exit0 on refreshed candidate9d6de74; no AWS credentials in the
  orchestrator. Owner fail/reset container reproduction passed in report13; final-main proof is report15.
- Maintainer accepted #634/#635 guide/evidence in chat and this was recorded on
  both PRs. Independent final-main execution is not inferred from acceptance.

- [Actual expired AWS contract](12-expired-connection.txt): authorized expiry
  passed, canonical command exits1 before any Docker/AWS action. Production
  tooling rebuilt from pinned Dockerfile/uv.lock, without credentials in image.

## Criteria (every CA accounted for)

| CA | Status | Evidence / remaining acceptance |
| --- | --- | --- |
| CA1 | Verified main | Fresh standalone clean main220cd462: one canonical command prepares schema/seed/domain grants/API/web and URLs; no worktree imports or manual SQL/grants. |
| CA2 | Verified main | Controlled and real AWS repeat: IDs/key hashes/grants/incidents unchanged on repeat; audit retained; revoked grant/inactive catalog fail closed; occupied-port/MCP outage recovery and stop/restart. |
| CA3 | Partial local validation | Local prepared network/token consumption tested with controlled fixture also on main220cd462 (report16); real local OTel not executed. AWS private producer contract, destination and governed real metric/log calls verified on integrated feature candidate. Producer/SRE integrated and real AWS reproduced on main; real local OTel remains not executed, modes are not conflated. |
| CA4 | Verified main | Actual AWS-connected API operator triage/run grants; independent direct investigator MCP discovery/invocation and existing LLM seed grant; restricted403. No human-grant inheritance or agent approval grant. |
| CA5 | Verified main | Actual AWS schema/services/readiness and governed metric/log connectivity; invalid/missing input, occupied port and destination outage nonzero with bounded recovery. Empty data is connection-only proof. |
| CA6 | Verified main | Controlled/local and real AWS inputs; no keys/headers/payloads in reports/media/arguments; actual harness secret absence/upstream DNS denial. SRE setup creates no AWS resources or paid calls by default; separate AWS launch explicitly authorized, ingress empty, 2h default expiry explicitly extended1h; server-side Scheduler/guest expiry updated. No IAM bootstrap. New separate2h demo explicitly extended1h to04:28:03UTC; temporary owner-only credential holder removed after the main journey. |
| CA7 | Partial | Real API triage→investigate start→state/events→audit + denial and real owner fail/reset signals verified. No successful/paid LLM inference claimed. Independent reviewer following final-main guide remains required. |
| CA8 | Partial | README/operator guide, fresh reports/screenshots, pinned container commands and first/repeat/error/recovery results published. Main SHA/report15 now recorded; independent human reproduction remains pending. |

## Environment and reproduction

Docker29.9.0 / Compose5.6.0, Linux; pinned Python3.12/PostgreSQL17.4 images, uv.lock.
Controlled SRE journey uses synthetic owned MCP fixture, no live model.
Separate real AWS bootstrap and subsequent SRE readiness/signal journey are
recorded in reports05/07/08/09; only later reports prove governed behavior. Ignored owner-only .env from
.env.example, private token and pre-created internal fixture network. Runtime/consumer
CIDRs10.253.161.48/28 and10.253.161.64/28 avoid exhausted default pools; checks uses
10.253.161.0/28. No foreign container/network was stopped or deleted.

Host has3.9GB free vs OTel's documented15GB requirement. Local real OTel deployment and
fail/reset were **not attempted**; separate real AWS MCP deployment and fail/reset are verified.
AWS bridge/runtime/consumer CIDRs10.253.161.80/28,96/28,112/28 are test-host choices,
not defaults required for every operator.
No global pruning or unauthorized credential discovery used.
#494 remains OPEN; its remote acceptance cannot be replaced by a local fixture.

See [operator guide](../../setup-sre.md) for normal setup/config/diagnosis/stop and
[CLI E2E runner](../../../scripts/verify_setup_repeat.py) for exact controlled journey.
Earlier controlled suite source1b63d2129e2e6923f134e22fcf01a7e20c7bc176 remains
historical. Current integrated compatibility and real AWS E2E source is identified above.
Published drafts supply tested/base SHA, their <=400-line diff, containerized commands;
source slices were published, human-reviewed and normally integrated after fresh
hosted CI. This new report/matrix slice needs review; no partial merge is full
#618 acceptance.

## Risks / rollback / sanitization

Conflicts require reviewing existing domain state, never deleting the database or
reactivating revoked grants. Stop preserves volumes and independent OTel. Revert
or disable the entrypoint while retaining data; revoke explicit demo grants through
the administrative API if desired. API owns provider/MCP secrets, harness does not.

Sanitized: yes. Reports/media inspected; synthetic IDs only, no credentials, raw
provider payload, sensitive headers or personal data. Engram mirror unavailable:
runtime has no registered identity; local ODD tracker is retained.
