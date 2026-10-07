from __future__ import annotations

import fcntl
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[2]
OPERATOR_PROFILE = "otel-demo"
OPERATOR_REGION = "us-east-1"
OPERATOR_USERNAME = "OTelDemoOperator"
EXPECTED_ACCOUNT_ENV = "OTEL_DEMO_EXPECTED_ACCOUNT_ID"
MANIFEST = ROOT / "demo/manifest.yaml"
DEMO_ENV = ROOT / "demo/demo.env"
DIGESTS = ROOT / "demo/digests.lock"
UPSTREAM = "https://github.com/open-telemetry/opentelemetry-demo.git"
MAX_USER_DATA_BYTES = 16 * 1024


class DemoError(RuntimeError):
    """Sanitized session-management error."""


class SchedulerNotProvisioned(DemoError):
    """Scheduler prerequisites have not been provisioned."""


class AwsApiError(DemoError):
    """Sanitized AWS failure carrying only the AWS error code for control flow."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DemoConfig:
    profile: str = "otel-demo"
    region: str = "us-east-1"
    instance_type: str = "t3a.xlarge"
    cpu_credits: str = "standard"
    default_ttl: timedelta = timedelta(hours=2)
    maximum_lifetime: timedelta = timedelta(hours=12)
    scheduler_group: str = "otel-demo"
    scheduler_role_name: str = "OTelDemoSchedulerExecutionRole"
    instance_profile_name: str = "OTelDemoInstanceProfile"
    image_size_gib: int = 30
    monthly_budget_usd: float = 10.0
    maximum_session_estimate_usd: float = 3.0
    lock_path: Path = Path(tempfile.gettempdir()) / "otel-demo-personal-us-east-1.lock"
    expected_account_id: str | None = None


class AwsApi(Protocol):
    def month_to_date_cost(self, *, today: datetime | None = None) -> float: ...
    def scheduler_ready(self) -> bool: ...
    def find_shared_instance(self) -> dict[str, Any] | None: ...
    def default_network(self) -> dict[str, str]: ...
    def latest_ubuntu_ami(self) -> str: ...
    def create_security_group(self, *, vpc_id: str, ingress: list[dict]) -> str: ...
    def security_group_for_vpc(self, *, vpc_id: str) -> str | None: ...
    def run_instance(self, **kwargs: Any) -> dict[str, Any]: ...
    def schedule_termination(
        self, *, instance_id: str, at: datetime, update: bool = False
    ) -> str: ...
    def termination_deadline(self, *, instance_id: str) -> datetime: ...
    def instance_status(self) -> dict[str, Any] | None: ...
    def send_command(self, *, instance_id: str, **kwargs: Any) -> dict[str, Any]: ...
    def wait_for_command(self, *, instance_id: str, command_id: str) -> None: ...
    def set_expiration_tag(self, *, instance_id: str, deadline: datetime) -> None: ...
    def wait_for_ssm(self, *, instance_id: str) -> None: ...
    def start_session(self, *, instance_id: str, parameters: dict[str, list[str]]) -> None: ...
    def terminate_instance(self, *, instance_id: str) -> None: ...
    def delete_schedule(self, *, instance_id: str) -> None: ...


def calculate_extended_deadline(
    *,
    created_at: datetime,
    current_deadline: datetime,
    now: datetime,
    extension: timedelta,
    maximum_lifetime: timedelta,
) -> datetime:
    """Extend from the later of now/deadline, without exceeding lifetime since creation."""
    if any(
        value.tzinfo is None or value.utcoffset() is None
        for value in (created_at, current_deadline, now)
    ):
        raise DemoError("session timestamps must include a timezone")
    if extension <= timedelta(0):
        raise DemoError("extension must be positive")
    deadline = max(now, current_deadline) + extension
    if deadline > created_at + maximum_lifetime:
        raise DemoError("requested extension would exceed the maximum session lifetime")
    return deadline.astimezone(UTC)


def _tags(*, created_at: datetime | None = None, expires_at: datetime | None = None) -> list[dict]:
    tags = [
        {"Key": "ManagedBy", "Value": "otel-demo-cli"},
        {"Key": "Project", "Value": "otel-demo"},
        {"Key": "SharedSession", "Value": "true"},
    ]
    if created_at:
        tags.append({"Key": "CreatedAt", "Value": created_at.astimezone(UTC).isoformat()})
    if expires_at:
        tags.append({"Key": "ExpiresAt", "Value": expires_at.astimezone(UTC).isoformat()})
    return tags


def _normalize_instance(instance: dict[str, Any]) -> dict[str, Any]:
    tags = {row["Key"]: row["Value"] for row in instance.get("Tags", [])}
    groups = instance.get("SecurityGroups", [])
    return {
        "instance_id": instance.get("InstanceId", instance.get("instance_id")),
        "state": instance.get("State", {}).get("Name", instance.get("state", "unknown")),
        "created_at": tags.get("CreatedAt", instance.get("created_at")),
        "expires_at": tags.get("ExpiresAt", instance.get("expires_at")),
        "security_group_id": groups[0]["GroupId"] if groups else None,
        "public_ip": instance.get("PublicIpAddress"),
    }


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _schedule_name(instance_id: str) -> str:
    return f"otel-demo-{instance_id}"


def _allowed_ports() -> set[int]:
    section = (
        MANIFEST.read_text(encoding="utf-8")
        .split("host_ports:", 1)[1]
        .split("observability_services:", 1)[0]
    )
    return {int(port) for port in re.findall(r"^\s+- port: (\d+)$", section, re.MULTILINE)}


@contextmanager
def _host_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
