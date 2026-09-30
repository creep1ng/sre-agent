# Issue 45 documentation-only tracker recovery prerequisite

**Evidence kind:** controlled containerized tracker-file inspection. **Route:** delegated direct.
Base: P6 `529b2105a5f2ee841c804713b5e32b605edb965a`. This candidate changes only the full task tracker and this report; source, tests, runbook and runtime are untouched.

The complete current task, including P6 history, the full historical P7 direct-target RED/GREEN/deadline/split checkpoints, and current P7-D/P7-E tasks, was copied from the separate service/IP worktree. The copy before candidate-specific header/checklist updates was 79,393 bytes with SHA-256 `4bbfbe9a3f9e948c51590fd5cd01968c4f8d517e0ee313b0a0c042af81b75239`. Parent-preserved combined P7 candidate `05970c1ddcf38ab3c0543000ffdaf5d5865abe7b` and backup ref `codex/issue-45-06-full-boundary-backup-20260930` remain intact.

The top stage label now describes this documentation-only recovery prerequisite. It does not ship or execute P7 source/tests. The service/IP implementation is separately local and unpublished: source SHA-256 `8d639e4c36cfc0fed5017cd692e2236b54a27fc487d442a8f67afe377bee3283`, test SHA-256 `205885029a70adda1e9cd424f87efe446db473790d7334e93ff077b3bf7514c6`. Parent independently observed that separate candidate's controlled HTTP/CLI tests 7/7 and four syntax checks; those results do not attest to this documentation candidate or close any CA. P7-E published-origin tests remain pending. All CA1–CA8 and human acceptance remain open.

Repeat a read-only inspection of selected current and historical task markers using the cached Node 22.14 image. This checks that the mounted tracker contains the named sections; it does not execute application code or render Markdown:

```sh
docker run --pull never --network none --rm --read-only --entrypoint node \
  --tmpfs /tmp:rw,nosuid,size=16m \
  -v "$PWD/odd/tasks/issue-45-grafana-mcp-verification.md:/source/issue45-tracker.md:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  -e 'const fs=require("node:fs");const text=fs.readFileSync("/source/issue45-tracker.md","utf8");const markers=["Current delivery stage:","Historical full-P7 candidate record","P7-D service-name and direct-IP slice","P7-E follow-up retained from complete P7 candidate","Documentation-only tracker recovery prerequisite","MCP45-P7-TR-A","MCP45-P7-TR-B"];for(const marker of markers){const line=text.split("\n").find((entry)=>entry.includes(marker));if(!line){console.error("MISSING "+marker);process.exitCode=1;continue;}console.log(line.slice(0,240));}'
```

Expected output is the seven selected heading/checklist lines from the actual mounted task. Parent owns command execution, readback, and a genuine screenshot. The output is not a Markdown-rendering proof and does not fix the separately recorded PR #424 preview gap. No runtime probes, live service, demo, network, build, pull, provider, or credential were used for this candidate. Parent owns final base-relative size accounting, real screenshot, mirror update, commit/publication/current hosted CI, and human-review request; no acceptance or issue closure is claimed. Current documentation-only diff against base is 74 additions + 1 deletion = 75 text changes before screenshot representation; parent must account for it.

The first parent inspection attempt used the cached harness entrypoint and exited before reading the tracker because `/source/schemas` was not mounted. The corrected documentation-only command selects the image's Node executable directly; it does not initialize or execute the application harness. The failed capture is retained separately.
