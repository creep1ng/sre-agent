from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from .common import AwsApiError, DemoError, _normalize_instance, _schedule_name, _tags


class AwsComputeMixin:
    """Instance lifecycle, deadline scheduling, and SSM command operations."""

    def run_instance(self, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "ImageId": kwargs["ami_id"],
            "InstanceType": kwargs["instance_type"],
            "MinCount": 1,
            "MaxCount": 1,
            "SubnetId": kwargs["subnet_id"],
            "SecurityGroupIds": [kwargs["security_group_id"]],
            "IamInstanceProfile": {"Name": self.config.instance_profile_name},
            "InstanceInitiatedShutdownBehavior": "terminate",
            "CreditSpecification": {"CpuCredits": kwargs["cpu_credits"]},
            "MetadataOptions": {
                "HttpEndpoint": "enabled",
                "HttpTokens": kwargs["metadata_tokens"],
                "HttpPutResponseHopLimit": 1,
            },
            "BlockDeviceMappings": [
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": kwargs["root_volume_gib"],
                        "VolumeType": "gp3",
                        "DeleteOnTermination": kwargs["delete_on_termination"],
                        "Encrypted": True,
                    },
                }
            ],
            "UserData": base64.b64encode(kwargs["user_data"].encode()).decode("ascii"),
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": _tags(created_at=kwargs["created_at"], expires_at=kwargs["expires_at"]),
                },
                {
                    "ResourceType": "volume",
                    "Tags": _tags(created_at=kwargs["created_at"], expires_at=kwargs["expires_at"]),
                },
            ],
        }
        payload["ClientToken"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        instance = self.call("ec2", "run-instances", payload=payload)["Instances"][0]
        return _normalize_instance(instance)

    def schedule_termination(self, *, instance_id: str, at: datetime, update: bool = False) -> str:
        role = self.call("iam", "get-role", "--role-name", self.config.scheduler_role_name)["Role"][
            "Arn"
        ]
        schedule = {
            "Name": _schedule_name(instance_id),
            "GroupName": self.config.scheduler_group,
            "ScheduleExpression": f"at({at.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S')})",
            "ScheduleExpressionTimezone": "UTC",
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "ActionAfterCompletion": "DELETE",
            "Target": {
                "Arn": "arn:aws:scheduler:::aws-sdk:ec2:terminateInstances",
                "RoleArn": role,
                "Input": json.dumps({"InstanceIds": [instance_id]}),
            },
        }
        operation = "update-schedule" if update else "create-schedule"
        self.call("scheduler", operation, payload=schedule)
        return schedule["Name"]

    def termination_deadline(self, *, instance_id: str) -> datetime:
        schedule = self.call(
            "scheduler",
            "get-schedule",
            "--group-name",
            self.config.scheduler_group,
            "--name",
            _schedule_name(instance_id),
        )
        match = re.fullmatch(r"at\(([^)]+)\)", schedule.get("ScheduleExpression", ""))
        if not match or schedule.get("ScheduleExpressionTimezone", "UTC") != "UTC":
            raise DemoError("existing Scheduler deadline is not a supported UTC one-time schedule")
        return datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)

    def instance_status(self) -> dict[str, Any] | None:
        return self.find_shared_instance()

    def send_command(self, *, instance_id: str, **kwargs: Any) -> dict[str, Any]:
        result = self.call(
            "ssm",
            "send-command",
            "--instance-ids",
            instance_id,
            "--document-name",
            kwargs["document_name"],
            "--parameters",
            json.dumps(kwargs["parameters"]),
        )
        return result.get("Command", {})

    def wait_for_command(self, *, instance_id: str, command_id: str) -> None:
        for attempt in range(12):
            try:
                result = self.call(
                    "ssm",
                    "get-command-invocation",
                    "--command-id",
                    command_id,
                    "--instance-id",
                    instance_id,
                )
            except AwsApiError as exc:
                if exc.code == "InvocationDoesNotExist" and attempt < 11:
                    self.sleeper(2)
                    continue
                raise DemoError("unable to confirm SSM command completion") from exc
            status = result.get("Status")
            if status == "Success":
                return
            if status in {"Pending", "InProgress", "Delayed"} and attempt < 11:
                self.sleeper(2)
                continue
            raise DemoError(
                f"SSM deadline update finished without success (status={status or 'unknown'})"
            )
        raise DemoError("SSM deadline update did not complete within the bounded wait")

    def set_expiration_tag(self, *, instance_id: str, deadline: datetime) -> None:
        self.call(
            "ec2",
            "create-tags",
            payload={
                "Resources": [instance_id],
                "Tags": [{"Key": "ExpiresAt", "Value": deadline.astimezone(UTC).isoformat()}],
            },
        )
