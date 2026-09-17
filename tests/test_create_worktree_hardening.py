import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from test_create_worktree import (
    create_worktree,
    git,
    initialize_repository,
    make_dependency_dirs,
)


def test_generated_name_finds_the_only_available_combination(tmp_path: Path) -> None:
    with (
        patch.object(create_worktree, "ADJECTIVES", ("amber", "brisk")),
        patch.object(create_worktree, "NOUNS", ("otter", "raven")),
        patch.object(create_worktree.secrets, "choice", side_effect=lambda words: words[0]),
    ):
        for name in ("amber-otter", "amber-raven", "brisk-otter"):
            (tmp_path / name).mkdir()

        name = create_worktree.generate_unique_name(tmp_path, set())

    assert name == "brisk-raven"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not portable")
def test_creation_preserves_private_main_env_mode(tmp_path: Path) -> None:
    _main, caller = initialize_repository(tmp_path)

    target = create_worktree.create_worktree(caller, "quiet-heron")

    assert stat.S_IMODE((target / ".env").stat().st_mode) == 0o600


def test_dependency_reuse_falls_back_to_compatible_main_and_skips_mismatch(
    tmp_path: Path,
) -> None:
    main, caller = initialize_repository(tmp_path)
    make_dependency_dirs(main, caller)
    # Make the caller Python environment incompatible with its committed target.
    (caller / "uv.lock").write_text("version = 999\n")
    # Make both tooling environments incompatible, so this dependency is not linked.
    (main / "schemas" / "tooling" / "package-lock.json").write_text("main mismatch\n")
    (caller / "schemas" / "tooling" / "package-lock.json").write_text("caller mismatch\n")

    target = create_worktree.create_worktree(caller, "brisk-falcon")

    assert (target / ".venv").resolve() == (main / ".venv").resolve()
    assert (target / "node_modules").resolve() == (caller / "node_modules").resolve()
    assert not (target / "schemas" / "tooling" / "node_modules").exists()


def test_existing_path_or_branch_is_a_collision(tmp_path: Path) -> None:
    main, caller = initialize_repository(tmp_path)
    (main / ".worktrees" / "amber-otter").mkdir()
    git(main, "branch", "brisk-falcon")

    assert create_worktree.name_collides(main, "amber-otter")
    assert create_worktree.name_collides(main, "brisk-falcon")


def test_bootstrap_failure_removes_only_created_worktree_and_branch(tmp_path: Path) -> None:
    main, caller = initialize_repository(tmp_path, bootstrap_exit=7)
    make_dependency_dirs(main, caller)
    # Force Python dependency fallback to main while npm dependencies reuse caller.
    (caller / "uv.lock").write_text("version = 999\n")
    unrelated = main / ".worktrees" / "keep-me"
    unrelated.mkdir()

    with pytest.raises(subprocess.CalledProcessError):
        create_worktree.create_worktree(caller, "calm-raven")

    assert not (main / ".worktrees" / "calm-raven").exists()
    assert "calm-raven" not in git(main, "branch", "--format=%(refname:short)").splitlines()
    assert unrelated.is_dir()
    assert (main / ".venv" / "origin").read_text() == main.name
    assert (caller / "node_modules" / "origin").read_text() == caller.name
    assert (caller / "schemas" / "tooling" / "node_modules" / "origin").read_text() == caller.name


def test_rollback_does_not_delete_branch_when_worktree_creation_was_not_confirmed(
    tmp_path: Path,
) -> None:
    with (
        patch.object(create_worktree, "local_branches", return_value={"calm-raven"}),
        patch.object(create_worktree.subprocess, "run") as run,
    ):
        create_worktree.rollback(
            tmp_path, tmp_path / ".worktrees" / "calm-raven", "calm-raven", False
        )

    run.assert_not_called()


def test_windows_junction_keeps_metacharacter_paths_out_of_command_string(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source&whoami"
    destination = tmp_path / "destination&whoami"
    with (
        patch.object(create_worktree.os, "name", "nt"),
        patch.object(create_worktree.subprocess, "run") as run,
    ):
        create_worktree.link_directory(source, destination)

    args, kwargs = run.call_args
    command = args[0]
    assert command[:5] == ["cmd", "/d", "/v:off", "/s", "/c"]
    assert str(source) not in command[-1]
    assert str(destination) not in command[-1]
    assert command[-1] == 'mklink /J "%WT_DESTINATION%" "%WT_SOURCE%"'
    assert kwargs["env"]["WT_SOURCE"] == str(source.resolve())
    assert kwargs["env"]["WT_DESTINATION"] == str(destination)
