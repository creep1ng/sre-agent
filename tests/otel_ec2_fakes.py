from __future__ import annotations

from datetime import UTC, datetime

from scripts.otel_ec2 import DemoError


class FakeAws:
    def __init__(self, *, scheduler_ready: bool = True) -> None:
        self.scheduler_ready_value = scheduler_ready
        self.fail_schedule = False
        self.fail_command = False
        self.persisted_deadline = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
        self.shared_group_id: str | None = None
        self.current_instance: dict | None = {
            "instance_id": "i-123",
            "state": "running",
            "created_at": "2026-09-28T12:00:00Z",
            "expires_at": "2026-09-28T14:00:00Z",
        }
        self.calls: list[tuple[str, tuple, dict]] = []
        self.month_to_date_cost_value = 0.0
        self.fail_cost_query = False

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "scheduler_ready":
                return self.scheduler_ready_value
            if name == "month_to_date_cost":
                if self.fail_cost_query:
                    raise DemoError("Cost Explorer is unavailable")
                return self.month_to_date_cost_value
            if name == "find_shared_instance":
                if self.current_instance and self.current_instance.get("launched"):
                    return self.current_instance
                return None
            if name == "security_group_for_vpc":
                return self.shared_group_id
            if name == "default_network":
                return {"vpc_id": "vpc-123", "subnet_id": "subnet-123"}
            if name == "latest_ubuntu_ami":
                return "ami-123"
            if name == "create_security_group":
                self.shared_group_id = "sg-123"
                return "sg-123"
            if name == "run_instance":
                self.current_instance = {
                    "instance_id": "i-123",
                    "state": "pending",
                    "launched": True,
                    "created_at": args[0] if args else kwargs["created_at"],
                    "expires_at": kwargs["expires_at"].isoformat(),
                }
                self.persisted_deadline = kwargs["expires_at"]
                return self.current_instance
            if name == "schedule_termination":
                if getattr(self, "fail_schedule", False):
                    raise DemoError("schedule creation failed")
                self.persisted_deadline = kwargs["at"]
                return "schedule-123"
            if name == "termination_deadline":
                return self.persisted_deadline
            if name == "instance_status":
                return self.current_instance
            if name == "send_command":
                return {"command_id": "cmd-123"}
            if name == "wait_for_command":
                if self.fail_command:
                    raise DemoError("command did not succeed")
                return None
            if name == "set_expiration_tag":
                self.current_instance["expires_at"] = kwargs["deadline"].isoformat()
                return None
            if name == "wait_for_ssm":
                return None
            if name == "terminate_instance":
                self.current_instance = None
                return None
            if name == "delete_schedule":
                return None
            if name == "security_group_id":
                return "sg-123"
            return None

        return record
