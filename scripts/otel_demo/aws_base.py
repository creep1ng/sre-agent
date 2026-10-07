from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .common import (
    OPERATOR_PROFILE,
    OPERATOR_REGION,
    OPERATOR_USERNAME,
    AwsApiError,
    DemoConfig,
    DemoError,
    SchedulerNotProvisioned,
    _normalize_instance,
    _tags,
)


class AwsBase:
    """Identity, API transport, cost, and network operations for AWS CLI."""

    def __init__(
        self,
        *,
        profile: str,
        region: str,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        config: DemoConfig | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if profile != OPERATOR_PROFILE or region != OPERATOR_REGION:
            raise ValueError("launcher is pinned to profile otel-demo and region us-east-1")
        self.profile, self.region, self.runner = profile, region, runner
        self.config = config or DemoConfig(profile=profile, region=region)
        self.sleeper = sleeper

    def verify_identity(self) -> None:
        """Fail closed unless the dedicated operator profile is the expected IAM user."""
        expected_account = self.config.expected_account_id
        if not expected_account or not re.fullmatch(r"[0-9]{12}", expected_account):
            raise DemoError(
                "set OTEL_DEMO_EXPECTED_ACCOUNT_ID to the private 12-digit AWS account ID"
            )
        try:
            result = self.runner(
                [
                    "aws",
                    "--profile",
                    OPERATOR_PROFILE,
                    "--region",
                    OPERATOR_REGION,
                    "--no-cli-pager",
                    "sts",
                    "get-caller-identity",
                    "--output",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise DemoError("unable to verify OTelDemoOperator identity") from exc
        try:
            identity = json.loads(result.stdout) if result.returncode == 0 else {}
        except (json.JSONDecodeError, TypeError):
            identity = {}
        expected_arn = f"arn:aws:iam::{expected_account}:user/{OPERATOR_USERNAME}"
        if (
            not isinstance(identity, dict)
            or identity.get("Account") != expected_account
            or identity.get("Arn") != expected_arn
        ):
            raise DemoError("AWS profile does not match configured OTelDemoOperator identity")

    def call(self, service: str, operation: str, *args: str, payload: dict | None = None) -> dict:
        command = [
            "aws",
            "--profile",
            self.profile,
            "--region",
            self.region,
            "--no-cli-pager",
            service,
            operation,
            *args,
        ]
        if payload is not None:
            command.extend(["--cli-input-json", json.dumps(payload)])
        command.extend(["--output", "json"])
        try:
            result = self.runner(command, input=None, text=True, capture_output=True, check=False)
        except OSError as exc:
            raise DemoError("unable to execute AWS CLI") from exc
        if result.returncode:
            match = re.search(r"\(([A-Za-z][A-Za-z0-9]+)\)", result.stderr)
            raise AwsApiError(
                f"AWS CLI request failed ({service} {operation})",
                code=match.group(1) if match else None,
            )
        output = result.stdout.strip()
        return json.loads(output) if output else {}

    def scheduler_ready(self) -> bool:
        try:
            self.call("scheduler", "get-schedule-group", "--name", self.config.scheduler_group)
            self.call("iam", "get-role", "--role-name", self.config.scheduler_role_name)
        except DemoError as exc:
            raise SchedulerNotProvisioned(
                "EventBridge Scheduler is not provisioned; run account bootstrap"
            ) from exc
        return True

    def month_to_date_cost(self, *, today: datetime | None = None) -> float:
        """Return account-wide month-to-date unblended cost in USD via Cost Explorer."""
        today = (today or datetime.now(UTC)).astimezone(UTC).date()
        start = today.replace(day=1)
        if today == start:
            # Cost Explorer requires a non-empty half-open interval; without a
            # complete in-month range the account spend cannot be checked safely.
            raise DemoError("Cost Explorer has no completed month-to-date period; refusing launch")
        response = self.call(
            "ce",
            "get-cost-and-usage",
            payload={
                "TimePeriod": {"Start": start.isoformat(), "End": today.isoformat()},
                "Granularity": "DAILY",
                "Metrics": ["UnblendedCost"],
            },
        )
        rows = response.get("ResultsByTime")
        if not isinstance(rows, list) or not rows:
            raise DemoError("Cost Explorer returned no account cost data; refusing launch")
        total = Decimal("0")
        try:
            for row in rows:
                unblended_cost = row.get("Total", {}).get("UnblendedCost", {})
                amount = unblended_cost.get("Amount")
                if unblended_cost.get("Unit") != "USD":
                    raise DemoError("Cost Explorer returned a non-USD currency; refusing launch")
                if amount is None:
                    raise InvalidOperation
                total += Decimal(str(amount))
        except (InvalidOperation, AttributeError, TypeError) as exc:
            raise DemoError(
                "Cost Explorer returned invalid account cost data; refusing launch"
            ) from exc
        if not total.is_finite() or total < 0:
            raise DemoError("Cost Explorer returned invalid account cost data; refusing launch")
        return float(total)

    def find_shared_instance(self) -> dict[str, Any] | None:
        result = self.call(
            "ec2",
            "describe-instances",
            "--filters",
            "Name=tag:ManagedBy,Values=otel-demo-cli",
            "Name=tag:SharedSession,Values=true",
            "Name=instance-state-name,Values=pending,running,stopping,stopped",
        )
        instances = [
            item
            for reservation in result.get("Reservations", [])
            for item in reservation.get("Instances", [])
        ]
        if len(instances) > 1:
            raise DemoError("multiple shared OTel Demo instances exist; refusing to choose one")
        return _normalize_instance(instances[0]) if instances else None

    def default_network(self) -> dict[str, str]:
        vpcs = self.call("ec2", "describe-vpcs", "--filters", "Name=isDefault,Values=true").get(
            "Vpcs", []
        )
        if not vpcs:
            raise DemoError("no default VPC found; configure networking before launch")
        vpc_id = vpcs[0]["VpcId"]
        offerings = self.call(
            "ec2",
            "describe-instance-type-offerings",
            "--location-type",
            "availability-zone",
            "--filters",
            f"Name=instance-type,Values={self.config.instance_type}",
        ).get("InstanceTypeOfferings", [])
        offered_zones = {offering["Location"] for offering in offerings if offering.get("Location")}
        result = self.call(
            "ec2",
            "describe-subnets",
            "--filters",
            f"Name=vpc-id,Values={vpc_id}",
            "Name=default-for-az,Values=true",
            "Name=state,Values=available",
        )
        subnets = [
            subnet for subnet in result.get("Subnets", []) if subnet.get("MapPublicIpOnLaunch")
        ]
        if not subnets:
            raise DemoError("no public default subnet found; NAT gateways are not provisioned")
        supported_subnets = [
            subnet for subnet in subnets if subnet.get("AvailabilityZone") in offered_zones
        ]
        if not supported_subnets:
            raise DemoError(
                f"no public default subnet in an availability zone offering "
                f"{self.config.instance_type}; refusing launch"
            )
        return {
            "vpc_id": vpc_id,
            "subnet_id": sorted(supported_subnets, key=lambda row: row["SubnetId"])[0]["SubnetId"],
        }

    def latest_ubuntu_ami(self) -> str:
        parameter = (
            "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
        )
        return self.call("ssm", "get-parameter", "--name", parameter)["Parameter"]["Value"]

    def create_security_group(self, *, vpc_id: str, ingress: list[dict]) -> str:
        if ingress:
            raise DemoError("shared demo security group must have zero ingress rules")
        result = self.call(
            "ec2",
            "create-security-group",
            "--group-name",
            f"otel-demo-shared-{self.region}",
            "--description",
            "Outbound-only security group for temporary OTel Demo",
            "--vpc-id",
            vpc_id,
            payload={"TagSpecifications": [{"ResourceType": "security-group", "Tags": _tags()}]},
        )
        return result["GroupId"]

    def security_group_for_vpc(self, *, vpc_id: str) -> str | None:
        result = self.call(
            "ec2",
            "describe-security-groups",
            "--filters",
            f"Name=vpc-id,Values={vpc_id}",
            "Name=tag:ManagedBy,Values=otel-demo-cli",
            "Name=tag:Project,Values=otel-demo",
        )
        groups = result.get("SecurityGroups", [])
        if len(groups) > 1:
            raise DemoError(
                "multiple owned OTel Demo security groups exist; refusing to choose one"
            )
        if not groups:
            return None
        group = groups[0]
        if group.get("VpcId") != vpc_id or group.get("IpPermissions"):
            raise DemoError(
                "owned OTel Demo security group is not zero-ingress; refusing to reuse it"
            )
        tags = {tag["Key"]: tag["Value"] for tag in group.get("Tags", [])}
        if tags.get("ManagedBy") != "otel-demo-cli" or tags.get("Project") != "otel-demo":
            raise DemoError("security group ownership tags do not match; refusing to reuse it")
        return group["GroupId"]
