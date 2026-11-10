# Code-quality indicators (EP-14)

Epic #1015 states its progress with the indicators I01–I35, and a story that declares one
outside them adds it to the script with its row here (#1025 added I36 and I37).
`scripts/quality_indicators.py` measures them on a full git checkout; this page records each definition, its baseline on `main`
at `0cb2ad441e4f9923f3ff6d804dc59a6cfc51aa63`, its target and the issue that moves it. An
indicator is evidence for a reviewer, not a goal in itself: a value reached by one of the routes
in the "Met without improving the code" column does not count as delivery.

## Run it

The `quality` Compose service builds `docker/quality.Dockerfile` (Python 3.12, Git, ripgrep
14.1.1), mounts the script and the checkout to measure read-only, and runs without a network.
The host needs Git and Docker only, plus the `.env` that every `compose.yaml` command needs (copy
`.env.example`; the service reads no value from it).

```sh
# The checkout that holds compose.yaml.
docker compose --profile quality run --build --rm quality
# One JSON object. Without --build, which writes the build log to stdout as well.
docker compose --profile quality run --rm quality --json
# Any other commit: measure a clone of it.
git clone --quiet . /tmp/quality-base
git -C /tmp/quality-base checkout --quiet --detach 0cb2ad441e4f9923f3ff6d804dc59a6cfc51aa63
QUALITY_REPO=/tmp/quality-base docker compose --profile quality run --build --rm quality
```

I36 reads the console's production build in `web/incident-console/dist` of the measured checkout,
which git ignores. Build it in the clone right before measuring, without `CONSOLE_SIMULATOR`;
with no build there, I36 prints `not measured`.

```sh
docker run --rm -u "$(id -u):$(id -g)" -e npm_config_cache=/tmp/npm \
  -v /tmp/quality-base/web/incident-console:/app -w /app \
  node:22.14-alpine@sha256:9bef0ef1e268f60627da9ba7d7605e8831d5b56ad07487d24d1aa386336d1944 \
  sh -c 'npm ci --no-audit --no-fund && npm run build'
```

Measure a normal clone. In a linked worktree `.git` is a file pointing at the common repository
outside the mount, so the command fails there; clone the worktree's commit as shown above.

The script exits 1 and prints no indicator when `git` or `rg` is missing or fails, when the
checkout has no `.git` (or is not the top of one), or when a file list or the transition ids it
measures come out empty. `rg` exit status 1 (no match) is a valid result only for I21.

`commit:` is the `HEAD` of the measured checkout, but the values come from its files. When they
differ from `HEAD` the line ends with `(working tree differs)` and `--json` has `"dirty": true`.
Evidence for a PR is measured on a clean clone of the tested SHA.

## Differences from the audit script

The baseline comes from the reference script in #1016. On `0cb2ad44` this script prints the same
values except where noted:

- I14 counts only `authorization.partition(" ")` calls, found in the syntax tree. The audit
  counted every `partition(" ")` (10), including the Telegram command split in
  `chat/outbox.py:139` and the webhook secret in `gateway/alert_intake.py:172`, which are not
  API-key parsing. Baseline 8, as #1016 and #1021 set.
- `rg` runs with `--no-config --no-ignore-global`, so a personal ripgrep config or global
  gitignore cannot change I20 and I21. The container's ripgrep 14.1.1 and the audit's 15.2.0 give
  the same I20 and I21 on `0cb2ad44`.
- I09 also counts `import sre_agent.persistence.x` and `from sre_agent import persistence` (the
  same for `gateway`), which the audit missed. No core file uses those forms on `0cb2ad44`, so the
  baseline stays 8.
- I18 also reads transition ids written in quotes, and fails when it finds none.
- The text output starts with `commit: <sha>` of the measured checkout.

## Indicators

"Core" is the packages `incident`, `investigator`, `triage`, `chat`, `bok`, `governance`,
`executor` and `mcp` under `src/sre_agent/`. "src" is the tracked `src/**/*.py`. Line counts
include blank lines, comments and docstrings.

| Indicator | Definition | Known false positives | Met without improving the code by | Baseline | Target | Issue |
| --- | --- | --- | --- | --- | --- | --- |
| I01 largest src module | Lines of the longest src file | A long but cohesive data or schema module | Joining lines; moving code out of `src/` | 4494 `control/service.py` | ≤ 800 | #1022 |
| I02 src modules > 800 lines | Count of src files over 800 lines | Same as I01 | Same as I01; splitting a file at an arbitrary line | 8 | ≤ 2 | #1015 (#1022, #1023) |
| I03 longest src function | `end_lineno - lineno + 1` of the longest function; nested functions also count inside their parent | A function whose body is one long literal | Hoisting nested handlers into module-level closures that keep the same coupling | 1114 `control_router` | ≤ 150 | #1022 |
| I04 src functions > 100 lines | Count of functions over 100 lines | Same as I03 | Cutting a function into sequential fragments that pass state along | 30 | ≤ 10 | #1015 (#1021, #1022, #1023) |
| I05 src functions with > 6 params | Positional-only, positional and keyword-only parameters, minus `self`/`cls` | Keyword-only constructors that mirror a model | `*args`/`**kwargs` or an untyped dict, which are not counted | 45 | ≤ 15 | #1015 (#1022, #1023) |
| I06 `create_application` lines | Length of `create_application` in `src/sre_agent/application.py`; `absent` if missing | None known | Moving the same wiring into another function of the same size | 243 | ≤ 80 | #1023 |
| I07 core files importing SQLAlchemy | Core files with an absolute `import`/`from` of `sqlalchemy` anywhere, including `TYPE_CHECKING` blocks | A `TYPE_CHECKING`-only import for an annotation | Moving a module out of the fixed core list; importing SQLAlchemy through a re-export module | 9 | 0 | #1023 |
| I08 core files importing FastAPI/Starlette | Same, for `fastapi` or `starlette` | `executor/app.py`, the app of a separate process | Same as I07 | 2 | only `executor/app.py` | #1023 |
| I09 core files importing gateway/persistence | Same, for absolute imports of `sre_agent.gateway` or `sre_agent.persistence`; relative imports are not counted | Same as I07 | Relative imports; moving a module out of the core list | 8 | 0 | #1023 |
| I10 gateway modules importing SQLAlchemy | `src/sre_agent/gateway/**` files importing `sqlalchemy` | A `TYPE_CHECKING`-only import | Importing SQLAlchemy through a re-export module outside `gateway/` | 11 | 0 | #1023 |
| I11 gateway modules mentioning `JSONResponse` | `gateway/` files whose text contains `JSONResponse` | Routers that legitimately return it; mentions in comments | Building responses as `Response(json.dumps(...))` or under an alias | 17 | only the error handler and routers returning non-JSON content | #1021 |
| I12 `except Exception` in src | Regex `except Exception\b` | Matches in comments or strings | Bare `except:`, `except BaseException` or `except (Exception, X)`, which are not counted | 96 | ≤ 40, each maps to a typed error or re-raises | #1021 |
| I13 ID regex copies in src | Occurrences of the literal text `^[a-z][a-z0-9_-]{2,63}$` | The same text in a docstring | A variant spelling such as `\A…\Z`, or a pattern built by concatenation | 35 | ≤ 2 | #1020 |
| I14 hand-written Authorization parsing | Calls `authorization.partition(" ")` in the syntax tree | None known | Renaming the variable, `split(" ", 1)`, `(authorization or "").partition(" ")` | 8 | 1 | #1021 |
| I15 error-envelope builders | Regex `def (_error\|error_envelope\|_error_response\|_finish)\b` | An unrelated function with one of those names | Renaming a builder | 16 | ≤ 2 | #1021 |
| I16 error-envelope model classes | Regex `class \w*Error(Envelope\|Response\|Detail)\b` | A class with that suffix that is not an envelope | Renaming a model | 6 | ≤ 2 (`ErrorEnvelope`, `ErrorDetail`) | #1021 |
| I17 issue references in src | Regex `#\d{2,4}\b` anywhere in src text | `#NN` that is not an issue (an anchor, a code) | Writing `issue 123` or `GH-123` instead | 187 | 0 | #1015 (each story in its files; final sweep #1023) |
| I18 transition-id literals in src | String constants in src equal to one of the `id:` values of `agent/workflows/incident-response.yaml` (13 today) | Agent action names that equal a transition id; the vocabulary module itself | f-strings or concatenation; renaming an id in the YAML only | 127 over 13 ids | 0 outside the vocabulary module, except agent action names listed in the PR | #1020 |
| I19 `harness/` package present | `src/sre_agent/harness` exists | None known | Renaming the package without removing what it duplicates | True | False | #1017 |
| I20 files visible to `rg` / tracked | `rg --files --hidden -g '!.git'` against `git ls-files`; depends on `rg` seeing `.git` | Untracked, unignored files in a dirty checkout | An `.rgignore` that also hides live code (I21 then drops) | 4489 / 4489 | ≤ 1500 visible | #1017 |
| I21 `rg -l -i grant`: hits, % in live code | Files matching `grant`; live is `src/`, `tests/`, `web/`, `agent/`, `migrations/` | `grant` in unrelated prose; `scripts/` and `schemas/` count as not live | Hiding a dead directory by a path pattern that also hides some live files | 1062, 17% | ≥ 45% | #1017 |
| I22 `docs/evidence` tracked files / MB | `git ls-files docs/evidence` and the size of those files | None known | Moving the same files to another tracked directory | 1014 / 101.8 | 0 / 0 | #1018 |
| I23 top-level `scripts/` files | Tracked files directly under `scripts/` | Live entrypoints that belong there | Moving files into subdirectories, which are not counted | 113 | ≤ 75 | #1017 |
| I24 top-level scripts named after issues/POCs | Names matching `issue\d\|ht\d\|ca\d\|_poc\|prove_\|capture_` | A live script named `capture_…` | Renaming | 36 | only those used by `tests/` or the live path, listed on this page | #1017 |
| I25 root compose files / issue-named | `compose*.yaml` at the root, and those matching `issue\|triage\d` | None known | Moving files into a subdirectory or renaming | 24 / 4 | ≤ 14 / 0 | #1017 |
| I26 top-level docs / dated or issue-specific | `docs/*.md`, and those matching `issue-\|\d{4}-\d{2}-\d{2}\|sprint-\|hu-\|ht-` | Decision and backlog records, dated by design | Renaming; moving into a subdirectory | 41 / 16 | ≤ 28 / only the decision and backlog records | #1017 |
| I27 `docs/README.md` present | The file exists | None known | An empty index | False | True | #1017 |
| I28 `tests/conftest.py` present | The file exists | None known | An empty conftest | False | True | #1024 |
| I29 `def migrated_database` definitions | Regex `def migrated_database\b` in tracked `tests/*.py` | None known | Renaming copies of the fixture | 10 | 1 | #1024 |
| I30 test files with own `DROP TABLE` lists | Test files containing the text `DROP TABLE` | A test asserting that a drop is rejected | `TRUNCATE`, or the same list behind a differently spelled helper | 43 | ≤ 1 | #1024 |
| I31 tests reading `public/` sources | `test_` functions in files that use `read_text` and name `public/incident-ui`, `public/console` or `"public" /` | None known | Reading the file with `open()` or through a helper | 12 | 0 | #1019 |
| I32 test files named after issues | `tests/*.py` paths matching `issue_?\d` | None known | Renaming without regrouping | 6 | 0 | #1024 |
| I33 CI runs `web/incident-console` e2e | Any tracked `.github/workflows/*` contains `incident-console` | A comment, or a job that only builds | Mentioning the path without running the e2e | False | True | #1019 |
| I34 legacy console paths tracked | Tracked files under `index.html`, `public/`, `styles/` | Assets the landing page uses | Moving the files to another directory | 39 | 0, except landing assets listed in the PR | #1019 |
| I35 `store.ts` lines / `scenarios.ts` in `src/lib` | Newlines in `web/incident-console/src/lib/store.ts`; whether `src/lib/scenarios.ts` exists | None known | Moving the simulator to another bundled path (I36 catches it) | 776 / True | ≤ 300 / False | #1025 |
| I36 `scenarios.ts` strings in the console bundle | Double-quoted literals of 20 or more characters without escapes, outside comments and template literals, in the tracked `web/incident-console/src/**/scenarios.ts`, and how many of them appear in `web/incident-console/dist/**/*.js` once `\u`/`\x` escapes are decoded; `not measured` without a build | A long literal that another module also bundles; a `dist` left from another commit or built with `CONSOLE_SIMULATOR=1` | Building the scripts' texts by concatenation or template literals, which are not counted | 162 of 162 | 0 of N in a build without `CONSOLE_SIMULATOR` | #1025 |
| I37 busy/error pairs in administration pages | Per tracked `web/incident-console/src/features/admin/*-page.tsx`, the smaller of its `const [busy, setBusy] = useState` and `const [error, setError] = useState` counts, summed | A page whose busy flag is not a form's write | Renaming the state, or a per-page hook that repeats the same pair | 13 | 0 | #1025 |

Adding this page and the script raised I23 and I26 by one each over the baseline, I20 by three
files (those two and `docker/quality.Dockerfile`) and I21 by two (both mention `grant`).

## Indicators the script does not measure

Two stories declare indicators outside I01–I35 that the script does not measure yet; the PR of
the owning story adds each one to the script and moves its row to the table above.

| Indicator | Baseline | Target | Issue |
| --- | --- | --- | --- |
| Places that declare the catalog's resource types | 5 | 1, plus the CHECK constraints derived from it | #1022 |
| Core packages covered by `.importlinter` | `incident`, `governance`, `investigator`, `executor` | also `triage`, `chat`, `bok` and the application | #1023 |
| `os.environ` reads outside the settings | 7 | 0 | #1023 |
