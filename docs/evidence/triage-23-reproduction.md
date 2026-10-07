# Issue 23 isolated browser evidence

The isolated review package rebuilds the candidate API, web and Playwright images
from their checked-in Dockerfiles, with the pinned PostgreSQL and Playwright
versions. It uses only the existing `db`, `seed`, `api`, `web` and `e2e` Compose
service names. The isolated file intentionally omits the default stack's public
ports, persistent database volume, generic demo seed and provider configuration.

Prerequisites: Git and Docker Compose. Run `scripts/run_triage23_review.sh`;
it creates a private temporary directory, empty mode-0600 credential file, scoped
Compose interpolation file, builds and runs the services, then removes only its
own uniquely named Compose project/network. The network is internal, project-scoped,
and has no fixed subnet by default. If Docker's address pool is exhausted, inspect
local ranges first (`docker network inspect $(docker network ls -q) --format
'{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}'`) and pass an unused private
CIDR via `T23_NETWORK_SUBNET=...`; the wrapper then adds the optional IPAM override.
Never attach this stack to an existing network. The printed evidence directory contains actual screenshots and private
runner logs (inspect and sanitize before sharing); the generated `credentials.env` is owner-only and must not be shared.
Retain the directory for review and remove it manually after evidence handling.

The seed runs migrations through `20260923_13`, inserts a dismissed legacy row
while provenance columns do not exist, then upgrades to head. It creates five
synthetic principals and only the workflow grants needed for operator, denied,
and authorized/denied producer journeys. No provider or ambient `.env` is read.
The browser runner requires every credential, selects all seven triage suites,
uses one worker, and rejects missing values, skips, failures, flakes, or a count
other than 41. Browser traces and video are disabled; screenshots are actual UI
captures, with no credential field filled when captured.

Expected evidence includes durable manual/automatic/legacy origin, authorized
producer dismiss and link over real HTTP, manual incident declaration with
operator impact and incident navigation, persistence/reload, stale recovery,
403/no-persistence, session isolation, and the mocked UI contract suite. This is
controlled local integration evidence, not hosted CI or complete issue acceptance:
the issue's inbox handoff/domain allowed-actions criteria and any separately
pending product criteria remain open.
