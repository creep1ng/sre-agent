# Issue 30 invocation acceptance

## Objective / problem / why
Complete CA1–CA5 against the existing #187 gateway, not a second runtime.
Ricardo confirmed the matrix and controlled real server on 2026-10-03.
Project 8 midnight.agent: #30 Todo; #18/#129/#187/#29 Done.

## Authorized scope / constraints
Direct, delegated implementation: isolated real pinned Grafana MCP, Grafana and
Prometheus; vector(1) positive control; reuse #29 relay, capture and bounded audit.
No retries/fallbacks, autonomous tool calling, UI, Skills, BoK, merge or issue closure.
Preserve other worktrees, credentials and volumes; no prune/down -v.
Baseline main: 4a4515b99b6f5931f43969f7147c6ec90519344f (clean fast-forward).
RDD off (global). TDD ON: global Gentle AI state `strict_tdd=true`, found after
initial inventory; runner: python scripts/issue30_capture.py inside python-checks.
Write failure assertions first; observe real E2E RED before runtime fixes, then
GREEN and refactor. No post-hoc unit tests. Existing checks: containerized pytest.

## Checklist / acceptance / checks
- [ ] T1: Version controlled real stack and failure injection, isolated networks,
  pinned images, scoped token; observed Compose/build/health/image identity.
- [ ] T2: E2E CA1–CA5 matrix: deterministic 200 + exactly one tools/call;
  safe no-grant/nonvisible/401 with zero upstream calls; 422/timeout/failure;
  known ID allowed/denied before discovery; per-case counter deltas and bounded
  metadata-only audit (no MCP row for 401). Fix only observed defects if needed.
- [ ] T3: Execute exact documented recipe on committed candidate, mandatory
  checks, real screenshot, sanitized compact evidence and provenance.
- [ ] T4: Focused PR to main with real evidence, current base/tested SHA,
  line-size accounting and pending human/hosted checks; do not merge/close #30.

## Progress / evidence / next step
Inventory complete. #475 is merged; its 502 proves boundary crossing only.
Historical #187 78845c8 200/vector +1 and 403/+0 retained as historical evidence.
Current #29 counter overlay uses inert backend; adapt only the demo environment.
Real RED: 2026-10-03 22:39:25..22:40:08 UTC, main4a4515b: 200/vector1,
forwarded call1; 403/401/422 zero; 504/503/502 safe injected faults. Missing
public success correlation requires additive header; JSON null harness check corrected.
User chose exactly two PRs: infrastructure/control → acceptance (no size exception).
Next: verify committed candidates and bounded evidence; no merge/close authority.
