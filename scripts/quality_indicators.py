#!/usr/bin/env python3
"""Measure the EP-14 code-quality indicators I01-I35 of a full git checkout (#1016).

Usage: quality_indicators.py [REPO] [--json]. Definitions, baselines and targets are in
docs/quality-indicators.md. The script needs git, ripgrep and a .git in REPO; when any of
them fails, or a file list it measures comes out empty, it exits 1 and prints no indicator,
so a broken tool can never pass for a met target.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CORE = ("incident", "investigator", "triage", "chat", "bok", "governance", "executor", "mcp")
LIVE = ("src/", "tests/", "web/", "agent/", "migrations/")
WORKFLOW = "agent/workflows/incident-response.yaml"


class MeasurementError(Exception):
    pass


def run(*command: str, allow_no_match: bool = False) -> list[str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise MeasurementError(f"{command[0]} is not installed") from error
    if result.returncode != 0 and not (allow_no_match and result.returncode == 1):
        raise MeasurementError(
            f"{' '.join(command)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return [line for line in result.stdout.splitlines() if line]


def git_files(*pathspecs: str) -> list[str]:
    return run("git", "ls-files", *pathspecs)


def required(name: str, files: list[str]) -> list[str]:
    if not files:
        raise MeasurementError(f"{name} is empty")
    return files


def package(module: str) -> str:
    parts = module.split(".")
    return ".".join(parts[:2]) if parts[0] == "sre_agent" else parts[0]


def imports(tree: ast.AST) -> set[str]:
    """Top-level packages, and `sre_agent.<package>` for the project's own imports."""
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {package(alias.name) for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(package(node.module))
            if node.module == "sre_agent":
                modules |= {f"sre_agent.{alias.name}" for alias in node.names}
    return modules


def is_authorization_partition(node: ast.AST) -> bool:
    """`authorization.partition(" ")`: a hand-written split of the Authorization header."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "partition"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "authorization"
        and [ast.literal_eval(arg) for arg in node.args if isinstance(arg, ast.Constant)] == [" "]
    )


def measure() -> dict[str, object]:
    root = run("git", "rev-parse", "--show-toplevel")[0]
    if Path(root).resolve() != Path.cwd().resolve():
        raise MeasurementError(f"{Path.cwd()} is not the top of a git checkout ({root})")
    out: dict[str, object] = {}

    src = required("git ls-files src/*.py", git_files("src/*.py"))
    text = {path: Path(path).read_text() for path in src}
    trees = {path: ast.parse(source) for path, source in text.items()}
    lines = {path: source.count("\n") + 1 for path, source in text.items()}
    functions = []  # (lines, parameters, "path:line name")
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = node.args
                params = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
                params -= 1 if args.args and args.args[0].arg in ("self", "cls") else 0
                functions.append(
                    (node.end_lineno - node.lineno + 1, params, f"{path}:{node.lineno} {node.name}")
                )

    largest = max(lines.items(), key=lambda item: item[1])
    out["I01 largest src module (lines)"] = f"{largest[1]} {largest[0]}"
    out["I02 src modules > 800 lines"] = sum(count > 800 for count in lines.values())
    longest = max(functions)
    out["I03 longest src function (lines)"] = f"{longest[0]} {longest[2]}"
    out["I04 src functions > 100 lines"] = sum(f[0] > 100 for f in functions)
    out["I05 src functions with > 6 params"] = sum(f[1] > 6 for f in functions)
    factory = [
        f[0]
        for f in functions
        if f[2].startswith("src/sre_agent/application.py:") and f[2].endswith(" create_application")
    ]
    out["I06 create_application (lines)"] = factory[0] if factory else "absent"

    imported = {path: imports(tree) for path, tree in trees.items()}
    core = [path for path in src if path.split("/")[2] in CORE]
    gateway = [path for path in src if path.startswith("src/sre_agent/gateway/")]
    out["I07 core files importing sqlalchemy"] = sum("sqlalchemy" in imported[p] for p in core)
    out["I08 core files importing fastapi/starlette"] = sum(
        bool({"fastapi", "starlette"} & imported[p]) for p in core
    )
    out["I09 core files importing sre_agent.gateway or sre_agent.persistence"] = sum(
        bool({"sre_agent.gateway", "sre_agent.persistence"} & imported[p]) for p in core
    )
    out["I10 gateway modules importing sqlalchemy"] = sum(
        "sqlalchemy" in imported[p] for p in gateway
    )
    jsonresponse = (
        "I11 gateway modules returning JSONResponse from non-router code"
        " (files mentioning JSONResponse)"
    )
    out[jsonresponse] = sum("JSONResponse" in text[p] for p in gateway)

    def count(pattern: str) -> int:
        return sum(len(re.findall(pattern, source)) for source in text.values())

    out["I12 `except Exception` in src"] = count(r"except Exception\b")
    out["I13 ID regex copies in src"] = count(re.escape("^[a-z][a-z0-9_-]{2,63}$"))
    out['I14 hand-written Authorization header parsing (authorization.partition(" ")) in src'] = (
        sum(is_authorization_partition(node) for tree in trees.values() for node in ast.walk(tree))
    )
    out["I15 error-envelope builder defs in src"] = count(
        r"def (_error|error_envelope|_error_response|_finish)\b"
    )
    out["I16 ErrorEnvelope-like model classes"] = count(
        r"class \w*Error(Envelope|Response|Detail)\b"
    )
    out["I17 issue references (#NNN) in src"] = count(r"#\d{2,4}\b")
    ids = re.findall(r"^\s*-?\s*id:\s*[\"']?([a-z_]+)[\"']?\s*$", Path(WORKFLOW).read_text(), re.M)
    transitions = set(required(f"transition ids in {WORKFLOW}", ids))
    literals = sum(
        isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in transitions
        for tree in trees.values()
        for node in ast.walk(tree)
    )
    out[
        f"I18 transition-id string literals in src ({len(transitions)} transitions of {WORKFLOW})"
    ] = f"{literals} over {len(transitions)} ids"
    out["I19 harness/ package present"] = Path("src/sre_agent/harness").exists()

    tracked = required("git ls-files", git_files())
    rg = ("rg", "--no-config", "--no-ignore-global")
    visible = required("rg --files", run(*rg, "--files", "--hidden", "-g", "!.git", "."))
    out["I20 files visible to rg by default / tracked"] = f"{len(visible)} / {len(tracked)}"
    hits = [
        hit.removeprefix("./") for hit in run(*rg, "-l", "-i", "grant", ".", allow_no_match=True)
    ]
    live = sum(hit.startswith(LIVE) for hit in hits)
    out["I21 `rg -l -i grant`: hits, % in live code"] = (
        f"{len(hits)}, {round(100 * live / max(1, len(hits)))}%"
    )

    evidence = git_files("docs/evidence")
    megabytes = sum(os.path.getsize(p) for p in evidence if os.path.exists(p)) / 1e6
    out["I22 docs/evidence tracked files / MB"] = f"{len(evidence)} / {round(megabytes, 1)}"
    scripts = [p for p in git_files("scripts") if "/" not in p.removeprefix("scripts/")]
    out["I23 top-level scripts/ files"] = len(scripts)
    out["I24 top-level scripts named after issues/POCs"] = sum(
        bool(re.search(r"issue\d|ht\d|ca\d|_poc|prove_|capture_", p)) for p in scripts
    )
    compose = [p for p in git_files("compose*.yaml") if "/" not in p]
    named = sum(bool(re.search(r"issue|triage\d", p)) for p in compose)
    out["I25 root compose files / issue-named"] = f"{len(compose)} / {named}"
    docs = [p for p in git_files("docs/*.md") if p.count("/") == 1]
    dated = sum(bool(re.search(r"issue-|\d{4}-\d{2}-\d{2}|sprint-|hu-|ht-", p)) for p in docs)
    out["I26 top-level docs / dated or issue-specific"] = f"{len(docs)} / {dated}"
    out["I27 docs index (docs/README.md) present"] = Path("docs/README.md").exists()

    tests = {
        path: Path(path).read_text()
        for path in required("git ls-files tests/*.py", git_files("tests/*.py"))
    }
    out["I28 tests/conftest.py present"] = Path("tests/conftest.py").exists()
    out["I29 `def migrated_database` definitions"] = sum(
        len(re.findall(r"def migrated_database\b", t)) for t in tests.values()
    )
    out["I30 test files with own DROP TABLE lists"] = sum("DROP TABLE" in t for t in tests.values())
    out["I31 tests reading public/ sources (change detectors)"] = sum(
        len(re.findall(r"^\s*(async )?def test_", t, re.M))
        for t in tests.values()
        if re.search(r"public/(incident-ui|console)|\"public\"\s*/", t) and "read_text" in t
    )
    out["I32 test files named after issues"] = sum(bool(re.search(r"issue_?\d", p)) for p in tests)
    workflows = " ".join(
        Path(p).read_text()
        for p in required("git ls-files .github/workflows", git_files(".github/workflows/*"))
    )
    out["I33 CI runs web/incident-console e2e"] = "incident-console" in workflows
    out["I34 legacy console paths tracked (index.html, public/, styles/)"] = len(
        git_files("index.html", "public", "styles")
    )
    store = Path("web/incident-console/src/lib/store.ts")
    store_lines = store.read_text().count("\n") if store.exists() else "absent"
    scenarios = Path("web/incident-console/src/lib/scenarios.ts").exists()
    out["I35 web store.ts lines / scenarios.ts in src/lib"] = f"{store_lines} / {scenarios}"
    dirty = bool(run("git", "status", "--porcelain"))
    return {"commit": run("git", "rev-parse", "HEAD")[0], "dirty": dirty, "indicators": out}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    options = parser.parse_args()
    try:
        os.chdir(options.repo)
        result = measure()
    except (MeasurementError, OSError) as error:
        print(f"quality_indicators: {error}", file=sys.stderr)
        return 1
    if options.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"commit: {result['commit']}" + (" (working tree differs)" * result["dirty"]))
        for name, value in result["indicators"].items():
            print(f"{name}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
