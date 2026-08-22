# Runtime boundaries

Issue 10 establishes one deployable FastAPI runtime while keeping the four system boundaries explicit. It adds infrastructure only; domain endpoints, authentication, migrations, and seed data remain out of scope.

## Composition

| Boundary | Python package | Current responsibility |
| --- | --- | --- |
| Control plane | `sre_agent.control` | Reserved boundary for governed configuration and administration |
| Incident-resolution plane | `sre_agent.incident` | Reserved boundary for incident analysis and remediation |
| Harness | `sre_agent.harness` | Contract and fixture execution boundary |
| Gateway | `sre_agent.gateway` | HTTP transport and health probes |

`sre_agent.application.create_application` is the only composition root. The current runtime exposes infrastructure health routes only:

- `GET /health/live` is dependency-free and proves the Python process can serve requests.
- `GET /health/ready` executes `SELECT 1` against PostgreSQL. Failures return a fixed `503` response that excludes driver messages, DSNs, and credentials.

The schema releases remain the contract authority. Runtime models must not replace or rewrite files under `schemas/releases/`.
