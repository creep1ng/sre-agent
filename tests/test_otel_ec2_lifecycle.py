from __future__ import annotations

import base64
import io
import re
import subprocess
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from otel_ec2_fakes import FakeAws

from scripts.otel_ec2 import (
    AwsCli,
    DemoConfig,
    DemoController,
    DemoError,
    SchedulerNotProvisioned,
    build_user_data,
    main,
)

TEST_ACCOUNT_ID = "123456789012"


class OTelEc2Tests(unittest.TestCase):
    def test_user_data_arms_absolute_deadline_and_pinned_images(self) -> None:
        user_data = build_user_data(
            expires_at=datetime(2026, 9, 28, 14, 0, tzinfo=UTC),
            manifest_path=Path("demo/manifest.yaml"),
            env_path=Path("demo/demo.env"),
            digest_path=Path("demo/digests.lock"),
        )

        self.assertIn("OnCalendar=2026-09-28 14:00:00 UTC", user_data)
        self.assertIn("Persistent=true", user_data)
        self.assertIn("apt-get install -y docker.io curl", user_data)
        self.assertNotIn("dnf install", user_data)
        self.assertIn("docker-compose-linux-x86_64.sha256", user_data)
        self.assertIn("-o /tmp/docker-compose-linux-x86_64\n", user_data)
        self.assertIn("sha256sum -c", user_data)
        self.assertNotIn("InstanceInitiatedShutdownBehavior=terminate", user_data)
        self.assertIn("1755859a9de82c2e5e225be68abc401a5ebf2b4f", user_data)
        digest_blob = user_data.split("printf '%s' '", 2)[2].split("' | base64 -d", 1)[0]
        self.assertIn(
            "sha256:32234e63c1d0634883aabd31cbd46802934aaaef0153dfd653b5d1017940bb4e",
            base64.b64decode(digest_blob).decode(),
        )
        env_blob = user_data.split("printf '%s' '", 1)[1].split("' | base64 -d", 1)[0]
        self.assertIn("DEMO_VERSION=3.0.0", base64.b64decode(env_blob).decode())
        self.assertLessEqual(len(base64.b64encode(user_data.encode())), 16 * 1024)

    def test_user_data_embeds_valid_base64_for_demo_env_and_image_lock(self) -> None:
        user_data = build_user_data(
            expires_at=datetime(2026, 9, 28, 14, 0, tzinfo=UTC),
            env_path=Path("demo/demo.env"),
            digest_path=Path("demo/digests.lock"),
        )
        matches = re.findall(
            r"printf '%s' '([^']+)' \| base64 -d >/opt/otel-demo/(demo\.env|digests\.lock)",
            user_data,
        )
        embedded = {filename: blob for blob, filename in matches}

        self.assertEqual(set(embedded), {"demo.env", "digests.lock"})
        decoded_env = base64.b64decode(embedded["demo.env"], validate=True)
        decoded_lock = base64.b64decode(embedded["digests.lock"], validate=True)
        expected_lock = (
            "\n".join(
                line
                for line in Path("demo/digests.lock").read_text().splitlines()
                if line and not line.startswith("#")
            )
            + "\n"
        )
        self.assertEqual(decoded_env, Path("demo/demo.env").read_bytes())
        self.assertEqual(decoded_lock, expected_lock.encode())

    def test_generated_user_data_has_valid_bash_syntax(self) -> None:
        user_data = build_user_data(
            expires_at=datetime(2026, 9, 28, 14, 0, tzinfo=UTC),
        )

        result = subprocess.run(["bash", "-n"], input=user_data, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_user_data_does_not_chmod_compose_plugin_before_install(self) -> None:
        user_data = build_user_data(
            expires_at=datetime(2026, 9, 28, 14, 0, tzinfo=UTC),
        )

        self.assertNotIn(
            "chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose",
            user_data,
        )
        self.assertIn(
            "install -m 0755 /tmp/docker-compose-linux-x86_64 "
            "/usr/local/lib/docker/cli-plugins/docker-compose",
            user_data,
        )

    def test_user_data_checks_out_full_upstream_tree_at_pinned_commit(self) -> None:
        user_data = build_user_data(
            expires_at=datetime(2026, 9, 28, 14, 0, tzinfo=UTC),
        )

        self.assertIn("apt-get install -y docker.io curl git", user_data)
        self.assertIn("git -C /opt/otel-demo init", user_data)
        self.assertIn(
            "git -C /opt/otel-demo remote add origin "
            "https://github.com/open-telemetry/opentelemetry-demo.git",
            user_data,
        )
        self.assertIn(
            "git -C /opt/otel-demo fetch --depth=1 origin 1755859a9de82c2e5e225be68abc401a5ebf2b4f",
            user_data,
        )
        self.assertIn("git -C /opt/otel-demo checkout --detach FETCH_HEAD", user_data)
        self.assertIn(
            '[[ "$(git -C /opt/otel-demo rev-parse HEAD)" == '
            '"1755859a9de82c2e5e225be68abc401a5ebf2b4f" ]]',
            user_data,
        )
        self.assertNotIn("for file in compose.yaml compose.observability.yaml .env", user_data)

    def test_up_reuses_existing_scheduled_session_without_new_launch(self) -> None:
        aws = FakeAws()
        aws.current_instance["launched"] = True
        controller = DemoController(aws=aws, config=DemoConfig())

        result = controller.up(now=datetime(2026, 9, 28, 13, 0, tzinfo=UTC))

        self.assertEqual(result["instance_id"], "i-123")
        names = [name for name, _, _ in aws.calls]
        self.assertIn("termination_deadline", names)
        self.assertNotIn("month_to_date_cost", names)
        self.assertNotIn("run_instance", names)

    def test_down_is_noop_when_shared_session_is_absent(self) -> None:
        aws = FakeAws()
        aws.current_instance = None
        controller = DemoController(aws=aws, config=DemoConfig())

        controller.down()

        self.assertNotIn("terminate_instance", [name for name, _, _ in aws.calls])

    def test_up_requires_scheduler_before_instance_launch(self) -> None:
        aws = FakeAws(scheduler_ready=False)
        controller = DemoController(aws=aws, config=DemoConfig())

        with self.assertRaisesRegex(SchedulerNotProvisioned, "Scheduler"):
            controller.up(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))

        names = [name for name, _, _ in aws.calls]
        self.assertIn("scheduler_ready", names)
        self.assertNotIn("run_instance", names)

    def test_up_launches_hardened_no_ingress_instance_and_schedules_deadline(self) -> None:
        aws = FakeAws()
        controller = DemoController(aws=aws, config=DemoConfig())

        instance = controller.up(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))

        self.assertEqual(instance["instance_id"], "i-123")
        calls = {name: (args, kwargs) for name, args, kwargs in aws.calls}
        self.assertEqual(calls["create_security_group"][1]["ingress"], [])
        launch = calls["run_instance"][1]
        self.assertEqual(launch["instance_type"], "t3a.xlarge")
        self.assertEqual(launch["cpu_credits"], "standard")
        self.assertEqual(launch["metadata_tokens"], "required")
        self.assertEqual(launch["root_volume_gib"], 30)
        self.assertIs(launch["delete_on_termination"], True)
        self.assertTrue(launch["user_data"])
        self.assertEqual(calls["schedule_termination"][1]["instance_id"], "i-123")
        self.assertEqual(
            calls["schedule_termination"][1]["at"],
            datetime(2026, 9, 28, 14, 0, tzinfo=UTC),
        )

    def test_schedule_failure_terminates_instance_instead_of_leaving_it_running(self) -> None:
        aws = FakeAws()
        aws.fail_schedule = True
        controller = DemoController(aws=aws, config=DemoConfig())

        with self.assertRaisesRegex(DemoError, "Scheduler creation failed"):
            controller.up(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))

        names = [name for name, _, _ in aws.calls]
        self.assertIn("terminate_instance", names)
        self.assertLess(names.index("run_instance"), names.index("terminate_instance"))

    def test_second_session_reuses_existing_owned_security_group(self) -> None:
        aws = FakeAws()
        controller = DemoController(aws=aws, config=DemoConfig())

        controller.up(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))
        controller.down()
        controller.up(now=datetime(2026, 9, 28, 16, 0, tzinfo=UTC))

        create_calls = [call for call in aws.calls if call[0] == "create_security_group"]
        group_lookups = [call for call in aws.calls if call[0] == "security_group_for_vpc"]
        self.assertEqual(len(create_calls), 1)
        self.assertEqual(len(group_lookups), 2)

    def test_status_reports_shared_instance_without_creating_resources(self) -> None:
        aws = FakeAws()
        controller = DemoController(aws=aws, config=DemoConfig())

        status = controller.status()

        self.assertEqual(status["instance_id"], "i-123")
        self.assertEqual([name for name, _, _ in aws.calls], ["instance_status"])

    def test_extend_updates_guest_and_scheduler_to_same_deadline(self) -> None:
        aws = FakeAws()
        controller = DemoController(aws=aws, config=DemoConfig())
        now = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)

        deadline = controller.extend(extension=timedelta(hours=2), now=now)

        self.assertEqual(deadline, datetime(2026, 9, 28, 16, 0, tzinfo=UTC))
        calls = {name: (args, kwargs) for name, args, kwargs in aws.calls}
        self.assertEqual(calls["send_command"][1]["deadline"], deadline)
        self.assertEqual(calls["schedule_termination"][1]["at"], deadline)
        self.assertIs(calls["schedule_termination"][1]["update"], True)
        names = [name for name, _, _ in aws.calls]
        self.assertLess(names.index("send_command"), names.index("wait_for_command"))
        self.assertLess(names.index("wait_for_command"), names.index("set_expiration_tag"))
        self.assertLess(names.index("set_expiration_tag"), names.index("schedule_termination", 2))

    def test_repeated_extension_uses_persisted_deadline_not_initial_expiry(self) -> None:
        aws = FakeAws()
        controller = DemoController(aws=aws, config=DemoConfig())

        first = controller.extend(
            extension=timedelta(hours=2), now=datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
        )
        second = controller.extend(
            extension=timedelta(hours=1), now=datetime(2026, 9, 28, 13, 30, tzinfo=UTC)
        )

        self.assertEqual(first, datetime(2026, 9, 28, 16, 0, tzinfo=UTC))
        self.assertEqual(second, datetime(2026, 9, 28, 17, 0, tzinfo=UTC))
        self.assertEqual(aws.current_instance["expires_at"], second.isoformat())

    def test_failed_guest_deadline_command_does_not_update_tag_or_schedule(self) -> None:
        aws = FakeAws()
        aws.fail_command = True
        controller = DemoController(aws=aws, config=DemoConfig())

        with self.assertRaisesRegex(DemoError, "command did not succeed"):
            controller.extend(
                extension=timedelta(hours=1), now=datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
            )

        names = [name for name, _, _ in aws.calls]
        self.assertNotIn("set_expiration_tag", names)
        self.assertNotIn("schedule_termination", names)

    def test_connect_uses_loopback_ssm_port_forward(self) -> None:
        aws = FakeAws()
        controller = DemoController(aws=aws, config=DemoConfig())

        controller.connect(local_port=18090, remote_port=8090)

        calls = {name: (args, kwargs) for name, args, kwargs in aws.calls}
        self.assertEqual(calls["wait_for_ssm"][1]["instance_id"], "i-123")
        self.assertEqual(
            calls["start_session"][1]["parameters"],
            {"portNumber": ["8090"], "localPortNumber": ["18090"]},
        )

    def test_connect_interrupt_exits_cleanly_without_traceback(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(AwsCli, "verify_identity"),
            patch.object(DemoController, "connect", side_effect=KeyboardInterrupt),
            redirect_stderr(stderr),
        ):
            exit_code = main(["connect", "--local-port", "18090"])

        self.assertEqual(exit_code, 130)
        self.assertIn("SSM port-forwarding session interrupted", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_down_requests_termination_and_retains_schedule_fallback(self) -> None:
        aws = FakeAws()
        controller = DemoController(aws=aws, config=DemoConfig())

        controller.down()

        names = [name for name, _, _ in aws.calls]
        self.assertEqual(names, ["instance_status", "scheduler_ready", "terminate_instance"])
        self.assertNotIn("delete_schedule", names)

    def test_ssm_wait_retries_only_invocation_does_not_exist(self) -> None:
        runner = Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    [], 254, "", "An error occurred (InvocationDoesNotExist) while reading"
                ),
                subprocess.CompletedProcess([], 0, '{"Status": "Success"}', ""),
            ]
        )
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner, sleeper=Mock())

        aws.wait_for_command(instance_id="i-test", command_id="cmd-test")

        self.assertEqual(runner.call_count, 2)
        self.assertTrue(
            all("get-command-invocation" in call.args[0] for call in runner.call_args_list)
        )

    def test_ssm_wait_fails_without_retrying_other_aws_errors(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [], 254, "", "An error occurred (AccessDeniedException) while reading"
            )
        )
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner, sleeper=Mock())

        with self.assertRaises(DemoError):
            aws.wait_for_command(instance_id="i-test", command_id="cmd-test")

        self.assertEqual(runner.call_count, 1)
