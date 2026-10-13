# Publication boundary

The README, original manifest, replay, SQL, validator results and run receipts are
immutable records of the 03:38 UTC verification on runtime `763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9`.
Their statements about uncommitted work, two review units and unavailable new media
are **as-of that run**, not the later PR publication state. The preserved CA4
acceptance document likewise records the preceding documentation-only review;
the newer failed CA4 result is in this directory, not retroactively credited there.

Publication uses three focused PRs: CA4 documentation, verification helpers, then
this evidence package. Runtime, schema, existing tests and historical captures are
unchanged. Issue-body CA4 remains a copy-ready proposal; #30 is not accepted.

The Python helpers were formatted without changing their AST, values or expectations.
Their run-original source is preserved in [commit ae97464](https://github.com/creep1ng/sre-agent/commit/ae97464e8669269bcbb03f75507f0c8c25d92420).
`artifact-manifest.jsonl` retains those original hashes; `publication-manifest.jsonl`
hashes the delivered files instead, excluding itself. Do not replace one provenance
record with the other or relabel runtime execution with a publication commit SHA.

[Helper verification](helper-verification-receipts.jsonl) ran the formatted candidate
`5937d7a10dc4f24b28c2d2c66a9d94031f456620`: readiness first, unchanged API image,
complete SQL reread by the **original** IDs/window, four files byte-identical, and a
new 401-only repeat. Both full validators and the presence check exit 1, correctly
reporting the unchanged defects. This is not a new ten-scenario replay.

New PNGs are real Chromium captures of rendered documentation, helper source and
this report/actual results, using isolated local profiles without external assets.
They are not API browser runs, replacements for old PNGs, or proof of runtime fixes.
Human evidence acceptance and approved implementation of the three reported audit
corrections remain outstanding. PR publication does not authorize merge or closure.
