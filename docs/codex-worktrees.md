# Isolated Codex worktree environments

Give each Codex task its own Compose project and host ports. The identity comes from the canonical worktree path, so the workflow also works when Codex checks out a detached `HEAD`.

## Quick path

1. From the main worktree or another linked worktree, create an isolated checkout:

   ```bash
   scripts/create-worktree.sh
   ```

   On Windows Command Prompt, use `scripts\create-worktree.bat` instead. The command prints the
   generated path when it finishes.

2. Open the new checkout as the Codex task rather than reusing a running task's checkout.
3. In the new worktree, run:

   ```bash
   scripts/bootstrap-worktree.py
   scripts/worktree-compose up --build --wait
   ```

4. Run the issue-10 contract obligation when needed:

   ```bash
   scripts/worktree-compose --profile harness run --rm harness
   ```

5. Before archiving or deleting the Codex task/worktree, remove its containers and volumes:

   ```bash
   scripts/worktree-compose down -v --remove-orphans
   ```

Only archive or remove the worktree after the teardown command completes. This order prevents orphaned databases and networks. Harness dependencies are ephemeral: each run copies the versions locked into its image to a fresh in-memory filesystem, so no dependency volume survives the container.

## What creation owns

`create-worktree.sh` and `create-worktree.bat` are thin entrypoints for the same Python
implementation. It shuffles the complete built-in adjective/noun product and checks each
combination once, so it finds a free two-word name such as `amber-otter` whenever one exists. It
uses that exact name for both `.worktrees/amber-otter` and its new branch. The branch starts at the
invoking worktree's current `HEAD`, even when the command is launched from a linked worktree.

The creator copies `.env` from the primary worktree without printing its contents and preserves
its private permission mode on POSIX. It never copies or links `.env.worktree`; instead, it runs
`bootstrap-worktree.py` inside the new checkout to create that checkout's Compose identity and
ports.

When manifests and lockfiles match the new checkout, the creator reuses `.venv` and each detected
`node_modules` directory. It prefers the invoking worktree and falls back to the primary worktree.
Unix uses symbolic links; Windows uses directory junctions and therefore requires Git, Python 3,
and a filesystem that supports junctions.

These dependency directories are SHARED, mutable environments. Do not run `uv sync`, `npm
install`, package upgrades, or other dependency-mutating commands through the links. Remove the
link and create a worktree-local environment first. Python editable installs in a reused `.venv`
may also retain the source path of the worktree that originally created them; recreate `.venv`
locally whenever editable source resolution matters.

If creation fails, the command removes only the branch and worktree created by that invocation.

## What bootstrap owns

`scripts/bootstrap-worktree.py` performs three bounded operations:

- Copies `.env.example` to `.env` only when `.env` is absent. It never edits or replaces an existing `.env`.
- Hashes the canonical worktree path into a stable `COMPOSE_PROJECT_NAME`; it never reads the branch name or commit.
- Allocates three distinct loopback ports and writes them to the ignored `.env.worktree` override.

Rerunning the script reuses the generated identity and ports. To request a different free port set explicitly:

```bash
scripts/bootstrap-worktree.py --api-port 28100 --web-port 28101 --db-port 28102
```

The script always rejects duplicate values and values outside `1..65535`, including values reused from an existing `.env.worktree`. It combines a local bind check with Docker's published-port inventory. When the Codex sandbox blocks local binds, the Docker check still detects containers that are invisible inside the sandbox network namespace, but it cannot prove that every non-Docker host process is absent. The script reports that limitation rather than claiming deterministic validation. `docker compose up --wait` remains the fail-closed authority; if it reports a collision, choose another set with the command above and retry.

`scripts/worktree-compose` loads `.env` first and `.env.worktree` second. The generated file overrides only project identity and published ports; application and database settings still come from the developer-owned `.env`.

## Manual Git fallback

When a Codex client cannot create the worktree, create it outside any existing checkout and then open that directory as a new Codex task:

```bash
git worktree add ../sre-agent-issue-10 -b codex/issue-10
cd ../sre-agent-issue-10
scripts/bootstrap-worktree.py
```

The branch is a delivery convenience, not the environment identity.
