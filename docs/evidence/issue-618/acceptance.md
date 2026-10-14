# Issue 618 acceptance matrix — 2026-10-13

This is partial feature-branch delivery, **not full issue acceptance**. No main merge,
issue closure or paid LLM call was performed. Separate AWS launch was explicitly
authorized. Feature-candidate SRE AWS/MCP and signal behavior are now verified
below; main release and human acceptance are not complete. Project midnight.agent
was consulted live (issue OPEN/Todo). Human acceptance and final integrated main
reproduction are still required; successful containers/CI do not satisfy an OKR.

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
  orchestrator. Owner fail/reset container reproduction is still pending.
- Maintainer accepted #634/#635 guide/evidence in chat and this was recorded on
  both PRs. Independent final-main execution is not inferred from acceptance.

## Criteria (every CA accounted for)

| CA | Status | Evidence / remaining acceptance |
| --- | --- | --- |
| CA1 | Partial | Canonical command prepares controlled local stack and URLs. Final clean **integrated main** checkout pending; no branch/worktree instruction is an operator prerequisite. |
| CA2 | Verified, feature | Controlled and real AWS repeat: IDs/key hashes/grants/incidents unchanged on repeat; audit retained; revoked grant/inactive catalog fail closed; occupied-port/MCP outage recovery and stop/restart. |
| CA3 | Partial release | Local prepared network/token consumption tested with controlled fixture; real local OTel not executed. AWS private producer contract, destination and governed real metric/log calls verified on integrated feature candidate. Producer/SRE main integration pending; modes are not conflated. |
| CA4 | Verified, feature | Actual AWS-connected API operator triage/run grants; independent direct investigator MCP discovery/invocation and existing LLM seed grant; restricted403. No human-grant inheritance or agent approval grant. |
| CA5 | Verified, feature | Actual AWS schema/services/readiness and governed metric/log connectivity; invalid/missing input, occupied port and destination outage nonzero with bounded recovery. Empty data is connection-only proof. |
| CA6 | Verified, feature | Controlled/local and real AWS inputs; no keys/headers/payloads in reports/media/arguments; actual harness secret absence/upstream DNS denial. SRE setup creates no AWS resources or paid calls by default; separate AWS launch explicitly authorized, ingress empty, 2h default expiry explicitly extended1h; server-side Scheduler/guest expiry updated. No IAM bootstrap. |
| CA7 | Partial | Real API triage→investigate start→state/events→audit + denial and real owner fail/reset signals verified. No successful/paid LLM inference claimed. Independent reviewer following final-main guide remains required. |
| CA8 | Partial | README/operator guide, fresh reports/screenshots, pinned container commands and first/repeat/error/recovery results published. Final main SHA and human reproduction pending. |

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
new local slices still require publication/current hosted CI and review, alongside
a real Chromium capture and media-storage deferral. Stack into the feature branch
only after review; do not merge a partial slice to main as complete #618 acceptance.

## Risks / rollback / sanitization

Conflicts require reviewing existing domain state, never deleting the database or
reactivating revoked grants. Stop preserves volumes and independent OTel. Revert
or disable the entrypoint while retaining data; revoke explicit demo grants through
the administrative API if desired. API owns provider/MCP secrets, harness does not.

Sanitized: yes. Reports/media inspected; synthetic IDs only, no credentials, raw
provider payload, sensitive headers or personal data. Engram mirror unavailable:
runtime has no registered identity; local ODD tracker is retained.
