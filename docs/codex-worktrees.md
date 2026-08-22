# Isolated Codex worktree environments

Give each Codex task its own Compose project and host ports. The identity comes from the canonical worktree path, so the workflow also works when Codex checks out a detached `HEAD`.

## Quick path

1. Create the Codex task with a new worktree rather than reusing a running task's checkout.
2. In the new worktree, run:

   ```bash
   scripts/bootstrap-worktree.py
   scripts/worktree-compose up --build --wait
   ```

3. Run the issue-10 contract obligation when needed:

   ```bash
   scripts/worktree-compose --profile harness run --rm harness
   ```

4. Before archiving or deleting the Codex task/worktree, remove its containers and volumes:

   ```bash
   scripts/worktree-compose down -v --remove-orphans
   ```

Only archive or remove the worktree after the teardown command completes. This order prevents orphaned databases and networks. Harness dependencies are ephemeral: each run copies the versions locked into its image to a fresh in-memory filesystem, so no dependency volume survives the container.

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
