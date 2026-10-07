from __future__ import annotations

import json
import time

from .common import DemoError, _schedule_name


class AwsSsmMixin:
    """Systems Manager readiness and interactive port-forwarding operations."""

    def wait_for_ssm(self, *, instance_id: str) -> None:
        for attempt in range(12):
            result = self.call(
                "ssm",
                "describe-instance-information",
                "--filters",
                f"Key=InstanceIds,Values={instance_id}",
            )
            rows = result.get("InstanceInformationList", [])
            if rows and rows[0].get("PingStatus") == "Online":
                return
            if attempt < 11:
                time.sleep(5)
        raise DemoError("instance did not register with Systems Manager within 60 seconds")

    def start_session(self, *, instance_id: str, parameters: dict[str, list[str]]) -> None:
        command = [
            "aws",
            "--profile",
            self.profile,
            "--region",
            self.region,
            "--no-cli-pager",
            "ssm",
            "start-session",
            "--target",
            instance_id,
            "--document-name",
            "AWS-StartPortForwardingSession",
            "--parameters",
            json.dumps(parameters),
        ]
        result = self.runner(command, text=True, check=False)
        if result.returncode:
            raise DemoError("Systems Manager port forwarding failed")

    def terminate_instance(self, *, instance_id: str) -> None:
        self.call("ec2", "terminate-instances", "--instance-ids", instance_id)

    def delete_schedule(self, *, instance_id: str) -> None:
        self.call(
            "scheduler",
            "delete-schedule",
            "--group-name",
            self.config.scheduler_group,
            "--name",
            _schedule_name(instance_id),
        )
