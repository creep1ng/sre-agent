#!/usr/bin/env python3
"""Deploy personal OTel Demo account prerequisites and persist a scoped IAM profile."""

from __future__ import annotations

import argparse
import configparser
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATHS = {
    "operator": ROOT / "infra/otel-demo-operator.yaml",
    "runtime": ROOT / "infra/otel-demo-runtime.yaml",
    "budget": ROOT / "infra/otel-demo-budget.yaml",
}
STACKS = (
    ("operator", "otel-demo-operator"),
    ("runtime", "otel-demo-runtime"),
    ("budget", "otel-demo-budget"),
)
EXPECTED_ACCOUNT_ENV = "OTEL_DEMO_EXPECTED_ACCOUNT_ID"
ACCOUNT_ID_RE = re.compile(r"^\d{12}$")
REGION = "us-east-1"
ROOT_PROFILE = "personal"
CLI_PROFILE = "otel-demo"
IAM_USER = "OTelDemoOperator"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VPC_ID_RE = re.compile(r"^vpc-[0-9a-f]+$")
Runner = Callable[..., subprocess.CompletedProcess[str]]


class BootstrapError(RuntimeError):
    """Sanitized error from the explicit local bootstrap operation."""


def _aws(*args: str, runner: Runner) -> str:
    command = ["aws", "--profile", ROOT_PROFILE, "--region", REGION, "--no-cli-pager", *args]
    try:
        result = runner(command, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise BootstrapError("unable to execute AWS CLI") from exc
    if result.returncode:
        # AWS CLI stderr is deliberately discarded; it can contain environment-specific data.
        raise BootstrapError("AWS bootstrap request failed")
    return result.stdout


def _write_credentials(path: Path, access_key_id: str, secret_access_key: str) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if path.exists():
        with path.open(encoding="utf-8") as existing:
            parser.read_file(existing)
    if parser.has_section(CLI_PROFILE):
        raise BootstrapError("the otel-demo credentials profile already exists; refusing overwrite")
    parser[CLI_PROFILE] = {
        "aws_access_key_id": access_key_id,
        "aws_secret_access_key": secret_access_key,
    }
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".otel-demo-credentials-",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.fchmod(temporary.fileno(), 0o600)
            parser.write(temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _verify_operator_profile(runner: Runner, expected_account: str) -> None:
    """Verify an existing dedicated profile before treating bootstrap as idempotent."""
    try:
        identity = json.loads(
            _profile_aws("sts", "get-caller-identity", "--output", "json", runner=runner)
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise BootstrapError("unable to verify OTelDemoOperator profile identity") from exc
    operator_arn = f"arn:aws:iam::{expected_account}:user/{IAM_USER}"
    if (
        not isinstance(identity, dict)
        or identity.get("Account") != expected_account
        or identity.get("Arn") != operator_arn
    ):
        raise BootstrapError("existing profile does not match expected OTelDemoOperator identity")


def _profile_aws(*args: str, runner: Runner) -> str:
    command = ["aws", "--profile", CLI_PROFILE, "--region", REGION, "--no-cli-pager", *args]
    try:
        result = runner(command, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise BootstrapError("unable to execute AWS CLI") from exc
    if result.returncode:
        raise BootstrapError("unable to verify OTelDemoOperator profile identity")
    return result.stdout


def _bootstrap_account_locked(
    *,
    expected_account: str,
    alert_email: str,
    vpc_id: str,
    apply: bool,
    credentials_path: Path,
    template_paths: dict[str, Path],
    runner: Runner,
) -> dict[str, str]:
    """Deploy the operator, runtime, and budget stacks and create one profile.

    No AWS calls are made unless ``apply`` is true. The private account ID is
    used only for fail-closed STS identity checks and is never persisted.
    """
    if not apply:
        raise BootstrapError("explicit --apply is required before AWS bootstrap")
    if not EMAIL_RE.fullmatch(alert_email) or not VPC_ID_RE.fullmatch(vpc_id):
        raise BootstrapError("a valid alert email and VPC ID are required")
    parser = configparser.ConfigParser(interpolation=None)
    if credentials_path.exists():
        with credentials_path.open(encoding="utf-8") as existing:
            parser.read_file(existing)
    if parser.has_section(CLI_PROFILE):
        _verify_operator_profile(runner, expected_account)
        return {"profile": CLI_PROFILE, "status": "already-configured"}
    if set(template_paths) != {name for name, _ in STACKS} or any(
        not template_paths[name].is_file() for name, _ in STACKS
    ):
        raise BootstrapError("CloudFormation template is unavailable")

    try:
        identity = json.loads(_aws("sts", "get-caller-identity", "--output", "json", runner=runner))
    except (json.JSONDecodeError, TypeError) as exc:
        raise BootstrapError("unable to verify the personal AWS identity") from exc
    expected_root_arn = f"arn:aws:iam::{expected_account}:root"
    if (
        not isinstance(identity, dict)
        or identity.get("Account") != expected_account
        or identity.get("Arn") != expected_root_arn
    ):
        raise BootstrapError(
            "personal profile must authenticate as the configured account root principal"
        )

    # Validate the complete set before changing the account, then deploy in dependency order.
    for name, _ in STACKS:
        _aws(
            "cloudformation",
            "validate-template",
            "--template-body",
            f"file://{template_paths[name]}",
            "--output",
            "json",
            runner=runner,
        )
    for name, stack_name in STACKS:
        command = [
            "cloudformation",
            "deploy",
            "--stack-name",
            stack_name,
            "--template-file",
            str(template_paths[name]),
            "--region",
            REGION,
            "--capabilities",
            "CAPABILITY_NAMED_IAM",
        ]
        if name == "operator":
            command.extend(["--parameter-overrides", f"VpcId={vpc_id}"])
        elif name == "budget":
            command.extend(["--parameter-overrides", f"AlertEmail={alert_email}"])
        _aws(*command, runner=runner)

    try:
        stack = json.loads(
            _aws(
                "cloudformation",
                "describe-stacks",
                "--stack-name",
                "otel-demo-operator",
                "--output",
                "json",
                runner=runner,
            )
        )
        outputs = stack["Stacks"][0]["Outputs"]
        users = [
            item["OutputValue"] for item in outputs if item.get("OutputKey") == "OperatorUserName"
        ]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise BootstrapError("unable to verify operator user stack output") from exc
    if users != [IAM_USER]:
        raise BootstrapError("operator stack returned an unexpected IAM user")
    operator_user = users[0]

    try:
        access_keys = json.loads(
            _aws(
                "iam",
                "list-access-keys",
                "--user-name",
                operator_user,
                "--output",
                "json",
                runner=runner,
            )
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise BootstrapError("unable to inspect the dedicated IAM user's existing keys") from exc
    if not isinstance(access_keys, dict):
        raise BootstrapError("unable to inspect the dedicated IAM user's existing keys")
    if access_keys.get("AccessKeyMetadata"):
        raise BootstrapError(
            "dedicated IAM user already has an access key; refusing to create another"
        )

    try:
        created = json.loads(
            _aws(
                "iam",
                "create-access-key",
                "--user-name",
                operator_user,
                "--output",
                "json",
                runner=runner,
            )
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise BootstrapError("IAM did not return a usable dedicated-user key") from exc
    if not isinstance(created, dict):
        raise BootstrapError("IAM did not return a usable dedicated-user key")
    access_key = created.get("AccessKey", {})
    access_key_id = access_key.get("AccessKeyId") if isinstance(access_key, dict) else None
    secret_access_key = access_key.get("SecretAccessKey") if isinstance(access_key, dict) else None
    if not access_key_id or not secret_access_key:
        if access_key_id:
            try:
                _aws(
                    "iam",
                    "delete-access-key",
                    "--user-name",
                    operator_user,
                    "--access-key-id",
                    access_key_id,
                    runner=runner,
                )
            except BootstrapError as cleanup_error:
                raise BootstrapError(
                    "IAM key response was incomplete and cleanup could not be confirmed"
                ) from cleanup_error
        raise BootstrapError("IAM did not return a usable dedicated-user key")
    try:
        _write_credentials(credentials_path, access_key_id, secret_access_key)
    except (OSError, UnicodeError, configparser.Error, BootstrapError) as exc:
        try:
            _aws(
                "iam",
                "delete-access-key",
                "--user-name",
                operator_user,
                "--access-key-id",
                access_key_id,
                runner=runner,
            )
        except BootstrapError as cleanup_error:
            raise BootstrapError(
                "local profile write failed and access-key cleanup could not be confirmed"
            ) from cleanup_error
        raise BootstrapError(
            "local profile write failed; newly created access key was removed"
        ) from exc
    return {"profile": CLI_PROFILE, "status": "created"}


def bootstrap_account(
    *,
    alert_email: str,
    vpc_id: str,
    apply: bool,
    expected_account: str | None = None,
    credentials_path: Path | None = None,
    template_paths: dict[str, Path] | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, str]:
    """Serialize local bootstrap to prevent concurrent duplicate IAM keys."""
    if expected_account is None:
        expected_account = os.environ.get(EXPECTED_ACCOUNT_ENV)
    if not isinstance(expected_account, str) or not ACCOUNT_ID_RE.fullmatch(expected_account):
        raise BootstrapError(
            f"a 12-digit account ID is required via --expected-account or {EXPECTED_ACCOUNT_ENV}"
        )
    if not apply:
        raise BootstrapError("explicit --apply is required before AWS bootstrap")
    if not EMAIL_RE.fullmatch(alert_email) or not VPC_ID_RE.fullmatch(vpc_id):
        raise BootstrapError("a valid alert email and VPC ID are required")
    credentials_path = credentials_path or Path.home() / ".aws/credentials"
    template_paths = TEMPLATE_PATHS if template_paths is None else template_paths
    lock_path = credentials_path.parent / ".otel-demo-bootstrap.lock"
    try:
        lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_handle = lock_path.open("a", encoding="utf-8")
    except OSError as exc:
        raise BootstrapError("unable to acquire local bootstrap lock") from exc
    with lock_handle:
        try:
            os.fchmod(lock_handle.fileno(), 0o600)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            raise BootstrapError("unable to acquire local bootstrap lock") from exc
        return _bootstrap_account_locked(
            expected_account=expected_account,
            alert_email=alert_email,
            vpc_id=vpc_id,
            apply=apply,
            credentials_path=credentials_path,
            template_paths=template_paths,
            runner=runner,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--alert-email",
        required=True,
        help="recipient for the monthly USD 10 account budget alerts",
    )
    parser.add_argument(
        "--vpc-id",
        required=True,
        help="verified VPC ID used to scope the operator's EC2 permissions",
    )
    parser.add_argument(
        "--expected-account",
        default=os.environ.get(EXPECTED_ACCOUNT_ENV),
        help=f"12-digit AWS account ID (or set {EXPECTED_ACCOUNT_ENV})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="explicitly authorize stack deployment and profile creation",
    )
    args = parser.parse_args(argv)
    try:
        result = bootstrap_account(
            expected_account=args.expected_account,
            alert_email=args.alert_email,
            vpc_id=args.vpc_id,
            apply=args.apply,
        )
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
