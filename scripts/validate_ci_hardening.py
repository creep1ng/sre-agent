"""Validate repository-owned CI hardening invariants."""

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"
SHA_ACTION = re.compile(r"uses:\s+[^\s@]+@[0-9a-f]{40}\s+#\s+v\d+\.\d+\.\d+\s*$")


def validate(workflow: str) -> list[str]:
    errors: list[str] = []
    document = yaml.safe_load(workflow)
    jobs = document.get("jobs", {}) if isinstance(document, dict) else {}

    if not jobs:
        errors.append("workflow must define at least one job")
    for job_name, job in jobs.items():
        timeout = job.get("timeout-minutes") if isinstance(job, dict) else None
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            errors.append(f"job {job_name} must set a positive timeout-minutes")

    action_lines = [line.strip() for line in workflow.splitlines() if "uses:" in line]
    for line in action_lines:
        if not SHA_ACTION.fullmatch(line.removeprefix("- ")):
            errors.append(f"action must use a full SHA with version annotation: {line}")

    expected_group = (
        "group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
    )
    if expected_group not in workflow or "cancel-in-progress: true" not in workflow:
        errors.append("concurrency must isolate PRs and cancel obsolete runs")
    if document.get("permissions") != {"contents": "read"}:
        errors.append("workflow permissions must remain contents: read")
    if re.search(r"\$\{\{\s*secrets\.", workflow):
        errors.append("pull-request CI must not reference repository secrets")

    return errors


if __name__ == "__main__":
    failures = validate(WORKFLOW.read_text())
    if failures:
        raise SystemExit("\n".join(failures))
