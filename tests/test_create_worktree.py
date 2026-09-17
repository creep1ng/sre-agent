import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "create-worktree.py"
SPEC = importlib.util.spec_from_file_location("create_worktree", SCRIPT)
assert SPEC and SPEC.loader
create_worktree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = create_worktree
SPEC.loader.exec_module(create_worktree)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def initialize_repository(tmp_path: Path, *, bootstrap_exit: int = 0) -> tuple[Path, Path]:
    main = tmp_path / "repo"
    main.mkdir()
    git(main, "init", "-b", "main")
    git(main, "config", "user.email", "tests@example.invalid")
    git(main, "config", "user.name", "Tests")
    (main / "scripts").mkdir()
    (main / "schemas" / "tooling").mkdir(parents=True)
    (main / ".gitignore").write_text(".env\n.env.worktree\n")
    (main / ".env").write_text("SECRET=from-main\n")
    (main / ".env").chmod(0o600)
    (main / ".env.worktree").write_text("MUST_NOT_COPY=1\n")
    (main / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    (main / "uv.lock").write_text("version = 1\n")
    (main / "package.json").write_text('{"name":"root"}\n')
    (main / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    (main / "schemas" / "tooling" / "package.json").write_text('{"name":"tooling"}\n')
    (main / "schemas" / "tooling" / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    (main / "scripts" / "bootstrap-worktree.py").write_text(
        "from pathlib import Path\n"
        "Path('.env.worktree').write_text('GENERATED=target\\n')\n"
        f"raise SystemExit({bootstrap_exit})\n"
    )
    git(main, "add", ".")
    git(main, "commit", "-m", "test fixture")

    caller = main / ".worktrees" / "caller"
    caller.parent.mkdir()
    git(main, "worktree", "add", "-b", "caller", str(caller))
    (caller / "caller-only.txt").write_text("caller head\n")
    git(caller, "add", "caller-only.txt")
    git(caller, "commit", "-m", "advance caller")
    return main, caller


def make_dependency_dirs(main: Path, caller: Path) -> None:
    for root in (main, caller):
        (root / ".venv").mkdir()
        (root / ".venv" / "origin").write_text(root.name)
        (root / "node_modules").mkdir()
        (root / "node_modules" / "origin").write_text(root.name)
        (root / "schemas" / "tooling" / "node_modules").mkdir()
        (root / "schemas" / "tooling" / "node_modules" / "origin").write_text(root.name)


def test_generated_name_is_two_words_and_retries_collisions(tmp_path: Path) -> None:
    (tmp_path / "amber-otter").mkdir()
    with (
        patch.object(create_worktree, "ADJECTIVES", ("amber", "brisk")),
        patch.object(create_worktree, "NOUNS", ("otter", "falcon")),
        patch.object(create_worktree.secrets, "SystemRandom") as random,
    ):
        random.return_value.shuffle.side_effect = lambda _candidates: None
        name = create_worktree.generate_unique_name(tmp_path, {"amber-falcon"})

    assert name == "brisk-otter"


def test_creation_uses_caller_head_main_env_and_prefers_caller_dependencies(
    tmp_path: Path,
) -> None:
    main, caller = initialize_repository(tmp_path)
    make_dependency_dirs(main, caller)
    (caller / ".env").write_text("SECRET=from-caller\n")

    target = create_worktree.create_worktree(caller, "amber-otter")

    assert target == main / ".worktrees" / "amber-otter"
    assert git(target, "branch", "--show-current") == "amber-otter"
    assert git(target, "rev-parse", "HEAD") == git(caller, "rev-parse", "HEAD")
    assert (target / "caller-only.txt").read_text() == "caller head\n"
    assert (target / ".env").read_text() == "SECRET=from-main\n"
    assert (target / ".env.worktree").read_text() == "GENERATED=target\n"
    for relative in (".venv", "node_modules", "schemas/tooling/node_modules"):
        assert (target / relative).is_symlink()
        assert (target / relative).resolve() == (caller / relative).resolve()


@pytest.mark.skipif(os.name == "nt", reason="POSIX launcher syntax is tested separately")
def test_posix_launcher_is_thin_and_invokes_shared_implementation() -> None:
    launcher = SCRIPT.with_name("create-worktree.sh").read_text()

    assert "create-worktree.py" in launcher
