import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "bootstrap-worktree.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_worktree", SCRIPT)
assert SPEC and SPEC.loader
bootstrap_worktree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bootstrap_worktree
SPEC.loader.exec_module(bootstrap_worktree)


def test_identity_depends_on_worktree_path_not_git_head(tmp_path: Path) -> None:
    first = tmp_path / "worktree-a"
    second = tmp_path / "worktree-b"

    assert bootstrap_worktree.worktree_identity(first) == bootstrap_worktree.worktree_identity(
        first
    )
    assert bootstrap_worktree.worktree_identity(first) != bootstrap_worktree.worktree_identity(
        second
    )


def test_port_validation_rejects_a_bound_port() -> None:
    occupied = 62000
    with patch.object(bootstrap_worktree, "local_bind_available", lambda port: port != occupied):
        try:
            bootstrap_worktree.validate_ports(
                {"API_PORT": occupied, "WEB_PORT": 62001, "POSTGRES_PORT": 62002}, set()
            )
        except ValueError as error:
            assert "already in use" in str(error)
        else:
            raise AssertionError("An occupied port must be rejected")


def test_bootstrap_is_idempotent_and_does_not_overwrite_env() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".env.example").write_text("POSTGRES_DB=sre_agent\n")
        ports = {"API_PORT": 62000, "WEB_PORT": 62001, "POSTGRES_PORT": 62002}

        with (
            patch.object(bootstrap_worktree, "repository_root", lambda: root),
            patch.object(
                bootstrap_worktree, "allocate_ports", lambda _identity, _docker_ports: ports
            ),
            patch.object(bootstrap_worktree, "local_bind_available", lambda _port: True),
            patch.object(
                bootstrap_worktree, "docker_port_inventory", lambda _project: (set(), set())
            ),
            patch.object(sys, "argv", [str(SCRIPT)]),
        ):
            assert bootstrap_worktree.main() == 0
            local_env = root / ".env"
            generated = root / ".env.worktree"
            original_generated = generated.read_text()
            local_env.write_text("USER_SETTING=preserve-me\n")

            assert bootstrap_worktree.main() == 0

        assert local_env.read_text() == "USER_SETTING=preserve-me\n"
        assert generated.read_text() == original_generated


def test_docker_published_port_is_rejected_when_local_listener_is_invisible() -> None:
    ports = {"API_PORT": 62000, "WEB_PORT": 62001, "POSTGRES_PORT": 62002}
    with patch.object(bootstrap_worktree, "local_bind_available", lambda _port: True):
        try:
            bootstrap_worktree.validate_ports(ports, {62000})
        except ValueError as error:
            assert "published by another Docker container" in str(error)
        else:
            raise AssertionError("A Docker-published host port must be rejected")


def test_reused_environment_rejects_out_of_range_port() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        identity = bootstrap_worktree.worktree_identity(root)
        (root / ".env.example").write_text("POSTGRES_DB=sre_agent\n")
        (root / ".env").write_text("POSTGRES_DB=sre_agent\n")
        (root / ".env.worktree").write_text(
            bootstrap_worktree.render_environment(
                identity,
                bootstrap_worktree.project_name(root, identity),
                {"API_PORT": 99999, "WEB_PORT": 62001, "POSTGRES_PORT": 62002},
            )
        )

        with (
            patch.object(bootstrap_worktree, "repository_root", lambda: root),
            patch.object(
                bootstrap_worktree, "docker_port_inventory", lambda _project: (set(), set())
            ),
            patch.object(bootstrap_worktree, "local_bind_available", lambda _port: True),
            patch.object(sys, "argv", [str(SCRIPT)]),
        ):
            try:
                bootstrap_worktree.main()
            except SystemExit as error:
                assert "between 1 and 65535" in str(error)
            else:
                raise AssertionError("An out-of-range reused port must be rejected")


def test_reused_environment_accepts_its_running_compose_ports() -> None:
    ports = {"API_PORT": 62000, "WEB_PORT": 62001, "POSTGRES_PORT": 62002}
    with patch.object(bootstrap_worktree, "local_bind_available", lambda _port: False):
        assert bootstrap_worktree.validate_ports(ports, set(), set(ports.values())) is True
