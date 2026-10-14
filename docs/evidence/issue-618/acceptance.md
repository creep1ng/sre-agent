# Issue 618 acceptance matrix — 2026-10-13

This is partial feature-branch delivery, **not full issue acceptance**. No merge,
issue closure, AWS operation or paid LLM call was performed. Project midnight.agent
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

## Criteria (every CA accounted for)

| CA | Status | Evidence / remaining acceptance |
| --- | --- | --- |
| CA1 | Partial | Canonical command prepares controlled local stack and URLs. Final clean **integrated main** checkout pending; no branch/worktree instruction is an operator prerequisite. |
| CA2 | Verified, controlled | IDs/key hashes/grants/incidents unchanged on repeat; audit retained; revoked grant/inactive catalog fail closed; occupied-port/MCP outage recovery and stop/restart. |
| CA3 | Blocked/partial | Prepared private local network/token consumed; real OTel not executed here. AWS blocked before mutation: #494 producer PRs495–513 not integrated; no invented export/interface. |
| CA4 | Verified, controlled | Operator triage/run grants; independent direct investigator MCP discovery/invocation and existing LLM seed grant; restricted403. No human-grant inheritance or agent approval grant. |
| CA5 | Verified, controlled | Schema/services/readiness and governed metric/log connectivity; invalid/missing input, occupied port and destination outage nonzero with bounded recovery. Empty data is connection-only proof. |
| CA6 | Verified, local | Private inputs; no keys/headers/payloads in reports/media/arguments; actual harness secret absence/upstream DNS denial. No AWS resources, network-access expansion or paid default calls. |
| CA7 | Partial | Current API controlled triage→investigate start→state/events→audit + denial verified. Independent reviewer, real OTel fail/reset signal changes, and any explicitly enabled live LLM demonstration pending. |
| CA8 | Partial | README/operator guide, fresh reports/screenshots, pinned container commands and first/repeat/error/recovery results published. Final main SHA and human reproduction pending. |

## Environment and reproduction

Docker29.9.0 / Compose5.6.0, Linux; pinned Python3.12/PostgreSQL17.4 images, uv.lock.
Synthetic owned MCP fixture, no real OTel/AWS/model. Ignored owner-only .env from
.env.example, private token and pre-created internal fixture network. Runtime/consumer
CIDRs10.253.161.48/28 and10.253.161.64/28 avoid exhausted default pools; checks uses
10.253.161.0/28. No foreign container/network was stopped or deleted.

Host has3.9GB free vs OTel's documented15GB requirement. Real OTel deployment and
fail/reset were **not attempted**; no global pruning or credential discovery used.
#494 remains OPEN; its remote acceptance cannot be replaced by a local fixture.

See [operator guide](../../setup-sre.md) for normal setup/config/diagnosis/stop and
[CLI E2E runner](../../../scripts/verify_setup_repeat.py) for exact controlled journey.
Full local suite tested source tree1b63d2129e2e6923f134e22fcf01a7e20c7bc176; subsequent report/tracker-only changes do not alter runtime/test source.
Each draft PR supplies tested/base SHA, its <=400-line diff, containerized commands,
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
