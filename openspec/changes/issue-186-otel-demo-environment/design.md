# Design: OpenTelemetry Demo Environment

## Decision: Pin by image tag, verify by digest

The manifest declares image tags (`3.0.0-<service>`); `demo/digests.lock` records the digest each tag resolved to when the environment was validated. `verify` compares current digests against the lock.

A tag is a movable label: the registry owner can repoint it. A digest identifies content. Declaring only tags loses the reproducibility guarantee the deliverable claims; declaring only digests produces an unreadable, unreviewable manifest and 25 values to edit on every version bump. Splitting them keeps the declaration legible and the verification exact, and turns the lock from passive documentation into an active check. This mirrors `pyproject.toml` plus `uv.lock`, already used in this repository.

**Rejected:** digest-only pinning inside the composition. **Rejected:** tag-only pinning with no lock.

## Decision: Override `DEMO_VERSION` explicitly

The upstream `.env` at tag `3.0.0` sets `DEMO_VERSION=latest`. Cloning the tag pins the repository but resolves images against a moving tag, 163 commits ahead of the release at the time of writing. Observed consequence: under `latest` the `payment` service entered a restart loop; under `3.0.0` it starts healthy. The override is a correctness requirement, not a preference, and the manifest records why.

## Decision: Dedicated Compose project, not a shared one

`docker compose down -v` removes volumes belonging to the project it is invoked for. The project's own stack owns `postgres_data`, which holds the seeded principals that authorization depends on. Running the demo under `-p otel-demo` namespaces its containers, networks and volumes, so `reset` and `down` are structurally unable to reach project data rather than merely instructed not to.

Confirmed limitation: the 25 services declare fixed `container_name` values, and those names are global to the daemon. Project isolation does not prevent name collisions, so two demo instances cannot coexist and `up` must detect residue before starting.

## Decision: `up` verifies residue instead of assuming a clean host

Observed during validation: `docker compose down` invoked with a project name that does not match returns success and leaves every container running. A subsequent `up` fails midway with a name conflict, leaving a partially created environment. `up` therefore checks for conflicting names first and refuses to start rather than failing halfway.

## Decision: `reset` restores a declared baseline, not a global off

Of the 15 flags exposed by flagd, `loadGeneratorTraffic` ships `on` and sustains the synthetic traffic that CA2 requires to keep running. Switching every flag off would leave the environment without signals, so a subsequent `verify` would report a false negative. Two further flags carry a rate (`cartFailure`, `paymentFailure`) and one carries targeting rules (`productCatalogFailure`); restoring those means restoring a value, not clearing a boolean. The baseline lives in the manifest and `reset` restores it.

## Decision: `paymentUnreachable` over `paymentFailure` for CA2

Both are admissible under the acceptance criterion. `paymentUnreachable` is binary, so `reset` restores a state; `paymentFailure` is a percentage, so `reset` would have to restore an exact value. The binary flag also produces an unambiguous failure signal. Agreed with the issue author.

## Decision: Incremental `verify`

`verify` reports availability for frontend, load generator, Collector, Grafana, Prometheus and OpenSearch. Grafana MCP availability is added by the PR that introduces the MCP. Agreed with the issue author; the governed reachability check is conditioned on #187 and does not block this environment.

## Decision: Minimal profile excludes four upstream layers

`compose.agent.yaml` ships the upstream agent, MCP and chatbot, which the issue contract forbids running. `compose.full.yaml` adds Kafka, accounting and fraud-detection, none of which any acceptance criterion requires. `compose.profiling.yaml` and `compose.tests.yaml` add footprint without serving a criterion. The remaining two layers contain all six services CA1 requires to be verified.

`compose.extras.yaml` is an intentionally empty upstream extension seam, always loaded last. It is documented here as the supported customization point but is not modified, since modifying it would mean editing the upstream tree. The project's own additive overlay will be a separate file passed after it.

## Open question

Capability naming. `demo-environment` follows the existing kebab-case convention but is broader than the peer capabilities, which name behaviours rather than environments. An alternative is `demo-environment-operations`. Flagged for the maintainer.
