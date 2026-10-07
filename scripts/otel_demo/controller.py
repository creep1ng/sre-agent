from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from .common import (
    AwsApi,
    DemoConfig,
    DemoError,
    SchedulerNotProvisioned,
    _allowed_ports,
    _host_lock,
    _parse_datetime,
    calculate_extended_deadline,
)
from .guest import build_user_data


class DemoController:
    """One-resource orchestration, independent from CLI process mechanics."""

    def __init__(self, *, aws: AwsApi, config: DemoConfig | None = None) -> None:
        self.aws, self.config = aws, config or DemoConfig()

    def _scheduler_preflight(self) -> None:
        if not self.aws.scheduler_ready():
            raise SchedulerNotProvisioned(
                "EventBridge Scheduler is not provisioned; refusing an unscheduled launch"
            )

    def _current(self) -> dict[str, Any]:
        status = self.aws.instance_status()
        if status is None:
            raise DemoError("no shared OTel Demo session exists")
        return status

    def up(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
        with _host_lock(self.config.lock_path):
            existing = self.aws.find_shared_instance()
            if existing:
                self._scheduler_preflight()
                if existing["state"] not in {"pending", "running"}:
                    raise DemoError("shared OTel Demo instance is not active; refusing reuse")
                try:
                    deadline = self.aws.termination_deadline(instance_id=existing["instance_id"])
                except DemoError as exc:
                    raise DemoError(
                        "shared OTel Demo instance has no verified termination schedule"
                    ) from exc
                if deadline <= now:
                    raise DemoError("shared OTel Demo termination deadline has passed")
                return existing
            try:
                month_to_date = self.aws.month_to_date_cost(today=now)
            except DemoError as exc:
                raise DemoError("Cost Explorer prelaunch guard failed; refusing launch") from exc
            projected = month_to_date + self.config.maximum_session_estimate_usd
            if projected > self.config.monthly_budget_usd:
                raise DemoError(
                    "estimated session would exceed the USD monthly budget "
                    f"(month-to-date ${month_to_date:.2f}, reserve "
                    f"${self.config.maximum_session_estimate_usd:.2f}, "
                    f"budget ${self.config.monthly_budget_usd:.2f})"
                )
            self._scheduler_preflight()
            expires = now + self.config.default_ttl
            network = self.aws.default_network()
            ami = self.aws.latest_ubuntu_ami()
            data = build_user_data(expires_at=expires)
            group = self.aws.security_group_for_vpc(vpc_id=network["vpc_id"])
            if group is None:
                group = self.aws.create_security_group(vpc_id=network["vpc_id"], ingress=[])
            instance = self.aws.run_instance(
                ami_id=ami,
                subnet_id=network["subnet_id"],
                security_group_id=group,
                instance_type=self.config.instance_type,
                cpu_credits=self.config.cpu_credits,
                metadata_tokens="required",
                root_volume_gib=self.config.image_size_gib,
                delete_on_termination=True,
                created_at=now,
                expires_at=expires,
                user_data=data,
            )
            try:
                self.aws.schedule_termination(instance_id=instance["instance_id"], at=expires)
            except DemoError as exc:
                try:
                    self.aws.terminate_instance(instance_id=instance["instance_id"])
                except DemoError as cleanup_error:
                    raise DemoError(
                        "Scheduler creation failed and immediate instance cleanup failed; "
                        "the guest deadline remains best-effort"
                    ) from cleanup_error
                raise DemoError(
                    "Scheduler creation failed; the instance was sent for termination"
                ) from exc
            return instance

    def status(self) -> dict[str, Any]:
        return self.aws.instance_status() or {"state": "absent"}

    def extend(self, *, extension: timedelta, now: datetime | None = None) -> datetime:
        self._scheduler_preflight()
        status = self._current()
        scheduled_deadline = self.aws.termination_deadline(instance_id=status["instance_id"])
        persisted_deadline = max(_parse_datetime(status["expires_at"]), scheduled_deadline)
        deadline = calculate_extended_deadline(
            created_at=_parse_datetime(status["created_at"]),
            current_deadline=persisted_deadline,
            now=(now or datetime.now(UTC)).astimezone(UTC),
            extension=extension,
            maximum_lifetime=self.config.maximum_lifetime,
        )
        instance_id = status["instance_id"]
        command = (
            "sudo /usr/local/sbin/otel-demo-set-deadline "
            f"'{deadline.strftime('%Y-%m-%d %H:%M:%S UTC')}'"
        )
        command_result = self.aws.send_command(
            instance_id=instance_id,
            document_name="AWS-RunShellScript",
            parameters={"commands": [command]},
            deadline=deadline,
        )
        command_id = command_result.get("CommandId", command_result.get("command_id"))
        if not command_id:
            raise DemoError("SSM did not return a command id; deadline update remains unconfirmed")
        self.aws.wait_for_command(instance_id=instance_id, command_id=command_id)
        tag_error: DemoError | None = None
        schedule_error: DemoError | None = None
        try:
            self.aws.set_expiration_tag(instance_id=instance_id, deadline=deadline)
        except DemoError as exc:
            tag_error = exc
        try:
            self.aws.schedule_termination(instance_id=instance_id, at=deadline, update=True)
        except DemoError as exc:
            schedule_error = exc
        if tag_error or schedule_error:
            raise DemoError(
                "guest deadline changed, but a persisted deadline record could not be updated"
            ) from (tag_error or schedule_error)
        return deadline

    def connect(self, *, local_port: int, remote_port: int) -> None:
        if not 1 <= local_port <= 65535 or remote_port not in _allowed_ports():
            raise DemoError(
                "remote port must be declared in demo/manifest.yaml and local port valid"
            )
        instance_id = self._current()["instance_id"]
        self.aws.wait_for_ssm(instance_id=instance_id)
        self.aws.start_session(
            instance_id=instance_id,
            parameters={"portNumber": [str(remote_port)], "localPortNumber": [str(local_port)]},
        )

    def down(self) -> None:
        with _host_lock(self.config.lock_path):
            # EC2 can temporarily omit a just-launched instance from DescribeInstances.
            # Retry a missing result before accepting an idempotent absent-session no-op.
            for attempt in range(5):
                status = self.aws.instance_status()
                if status is not None:
                    break
                if attempt == 4:
                    return
                time.sleep(2 ** (attempt + 1))
            self._scheduler_preflight()
            # Keep Scheduler's safety net through its deadline; termination may be
            # accepted asynchronously, and deleting first would remove the fallback.
            self.aws.terminate_instance(instance_id=status["instance_id"])
