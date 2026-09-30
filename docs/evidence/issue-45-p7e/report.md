# Issue 45 P7-E published-origin evidence

Base `91aaca86f9b1fb5e49b23f805679d3b654d979ed` (owned PR #437 head). Candidate branch `codex/issue-45-07-published-origins-clean` adds mandatory `MCP_PUBLISHED_ENDPOINTS` inventory alongside host/port/IP, with root HTTP(S) validation and auth/path/query/fragment rejection before contact.

## Scope

Supplied-targets-only controlled probe. Keeps service-name/direct-IP behavior and symlink entrypoint fix; appends `published-port` observations. Missing/invalid complete inventory contacts no targets (`unverified`, exit 2). Any HTTP response is reachable/fail (exit 1). `coverage=supplied-targets-only`, `full_boundary=pending`. No total isolation, binding/topology, CA4/CA5, or human acceptance claimed.

## Verification

Cached Node v22.14.0 image `sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d`, `--pull never --network none`, 256 MiB memory/swap, read-only scripts/tests mounts, 20-second helper.

- RED on pre-E source `90ca3f79153c070ba000996241e7ce43030a2052f8a6b73dbb342b18e7a67879` with merged test `3f405f16e5aa56581c6f50988930292a379e9a9b9a2821f5a1270330921ab82e`: 1 pass (symlink) / 5 fail / 6 total. Capture `red-restacked-clean-20260930.log`, SHA `f259c3a3c0512142143c26bbbcb6d10fe241bd3073a69b6aa21c2f2956d7c288`.
- GREEN on fixed source `e7e4a835eac289bc38ba5da3fcafbfce82a139d7a69470d237e215288bde6513` with same test: 6/6 direct pass, no skips. Capture `green-clean-20260930.log`, SHA `eb5cd2f68989330419d16f01e7c89c56c4c8dd288a55741724a01b5f97b6df67`.
- Gateway suite unchanged: 3/3 pass, no skips. Capture `gateway-clean-20260930.log`, SHA `57f918ccae5161758ee3e9f68b2badb69015cdd0e172dba5d8d868d56c75f74c`.
- Four `node --check` passes (probe, direct test, gateway probe, gateway test) plus `git diff --check`, same pinned networkless image.

Actual [published-origins PNG](published-origins.png), 1600x2100/135529 bytes/SHA `2fd190d7cec681bd696f631f5c7e2496845746c152b0d797e304b7e3b3b71243`, shows the committed GREEN excerpt and safe assertions. Visually inspected/sanitized via sandboxed host Chromium/local CSP/no external assets. Full TAP is in the preserved logs, not pixels alone.

Sanitized: yes. No credentials, headers, personal data, or live targets. CA1-CA8 and human acceptance remain open.
