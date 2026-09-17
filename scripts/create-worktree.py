#!/usr/bin/env python3
"""Create a named Git worktree while reusing compatible local dependencies."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ADJECTIVES = (
    "amber",
    "brisk",
    "calm",
    "clear",
    "eager",
    "gentle",
    "lively",
    "quiet",
    "rapid",
    "steady",
)
NOUNS = (
    "badger",
    "falcon",
    "heron",
    "otter",
    "raven",
    "tiger",
    "willow",
    "wolf",
)
LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock")


@dataclass(frozen=True)
class Dependency:
    path: Path
    manifests: tuple[Path, ...]


def run_git(cwd: Path, *args: str, capture: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=capture,
        text=True,
    )
    return result.stdout.strip() if capture else ""


def repository_root(cwd: Path) -> Path:
    return Path(run_git(cwd, "rev-parse", "--show-toplevel")).resolve()


def primary_worktree(cwd: Path) -> Path:
    listing = run_git(cwd, "worktree", "list", "--porcelain")
    first = next((line[9:] for line in listing.splitlines() if line.startswith("worktree ")), None)
    if first is None:
        raise RuntimeError("Git did not report a primary worktree")
    return Path(first).resolve()


def local_branches(cwd: Path) -> set[str]:
    output = run_git(cwd, "branch", "--format=%(refname:short)")
    return set(output.splitlines())


def name_collides(main: Path, name: str) -> bool:
    return (main / ".worktrees" / name).exists() or name in local_branches(main)


def generate_unique_name(worktrees: Path, branches: set[str]) -> str:
    candidates = [f"{adjective}-{noun}" for adjective in ADJECTIVES for noun in NOUNS]
    secrets.SystemRandom().shuffle(candidates)
    for name in candidates:
        if not (worktrees / name).exists() and name not in branches:
            return name
    raise RuntimeError("Every built-in worktree name is already in use")


def same_files(source: Path, target: Path, relatives: tuple[Path, ...]) -> bool:
    if not relatives:
        return False
    for relative in relatives:
        source_file = source / relative
        target_file = target / relative
        if not source_file.is_file() or not target_file.is_file():
            return False
        if source_file.read_bytes() != target_file.read_bytes():
            return False
    return True


def dependencies(target: Path) -> list[Dependency]:
    result: list[Dependency] = []
    python_manifests = tuple(
        Path(name) for name in ("pyproject.toml", "uv.lock") if (target / name).is_file()
    )
    if python_manifests:
        result.append(Dependency(Path(".venv"), python_manifests))

    ignored = {".git", ".worktrees", "node_modules"}
    for package_json in sorted(target.rglob("package.json")):
        relative_dir = package_json.parent.relative_to(target)
        if any(part in ignored for part in relative_dir.parts):
            continue
        manifests = [relative_dir / "package.json"]
        manifests.extend(
            relative_dir / lockfile
            for lockfile in LOCKFILES
            if (target / relative_dir / lockfile).is_file()
        )
        result.append(Dependency(relative_dir / "node_modules", tuple(manifests)))
    return result


def link_directory(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        environment = os.environ.copy()
        environment["WT_SOURCE"] = str(source.resolve())
        environment["WT_DESTINATION"] = str(destination)
        subprocess.run(
            [
                "cmd",
                "/d",
                "/v:off",
                "/s",
                "/c",
                'mklink /J "%WT_DESTINATION%" "%WT_SOURCE%"',
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
    else:
        destination.symlink_to(source.resolve(), target_is_directory=True)


def reuse_dependencies(caller: Path, main: Path, target: Path) -> list[tuple[Path, Path]]:
    linked: list[tuple[Path, Path]] = []
    sources = (caller, main) if caller != main else (caller,)
    for dependency in dependencies(target):
        destination = target / dependency.path
        for source_root in sources:
            source = source_root / dependency.path
            if source.is_dir() and same_files(source_root, target, dependency.manifests):
                link_directory(source, destination)
                linked.append((dependency.path, source_root))
                break
    return linked


def rollback(main: Path, target: Path, branch: str, worktree_created: bool) -> None:
    if worktree_created:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(target)],
            cwd=main,
            check=False,
            capture_output=True,
            text=True,
        )
        if branch in local_branches(main):
            subprocess.run(
                ["git", "branch", "-D", branch],
                cwd=main,
                check=False,
                capture_output=True,
                text=True,
            )


def create_worktree(cwd: Path, name: str) -> Path:
    caller = repository_root(cwd)
    main = primary_worktree(caller)
    target = main / ".worktrees" / name
    if name_collides(main, name):
        raise ValueError(f"Worktree path or branch already exists: {name}")
    source_env = main / ".env"
    if not source_env.is_file():
        raise FileNotFoundError(f"Main worktree does not contain {source_env.name}")

    target.parent.mkdir(parents=True, exist_ok=True)
    head = run_git(caller, "rev-parse", "HEAD")
    worktree_created = False
    try:
        run_git(main, "worktree", "add", "-b", name, str(target), head, capture=False)
        worktree_created = True
        shutil.copy2(source_env, target / ".env")
        linked = reuse_dependencies(caller, main, target)
        subprocess.run(
            [sys.executable, str(target / "scripts" / "bootstrap-worktree.py")],
            cwd=target,
            check=True,
        )
    except BaseException:
        rollback(main, target, name, worktree_created)
        raise

    print(f"Created worktree and branch: {name}")
    print(f"Path: {target}")
    for relative, source in linked:
        print(f"Reused {relative} from {source}")
    return target


def main() -> int:
    cwd = Path.cwd()
    primary = primary_worktree(repository_root(cwd))
    name = generate_unique_name(primary / ".worktrees", local_branches(primary))
    create_worktree(cwd, name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
