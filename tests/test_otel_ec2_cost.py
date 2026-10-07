from __future__ import annotations

import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from otel_ec2_fakes import FakeAws

from scripts.otel_ec2 import (
    AwsCli,
    DemoConfig,
    DemoController,
    DemoError,
    _arguments,
    calculate_extended_deadline,
    main,
)

TEST_ACCOUNT_ID = "123456789012"


class OTelEc2Tests(unittest.TestCase):
    def test_default_network_fails_closed_without_supported_public_default_subnet(self) -> None:
        runner = Mock(
            side_effect=[
                subprocess.CompletedProcess([], 0, json.dumps({"Vpcs": [{"VpcId": "vpc-1"}]}), ""),
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "InstanceTypeOfferings": [{"Location": "us-east-1a"}],
                        }
                    ),
                    "",
                ),
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "Subnets": [
                                {
                                    "SubnetId": "subnet-001",
                                    "AvailabilityZone": "us-east-1e",
                                    "MapPublicIpOnLaunch": True,
                                },
                            ]
                        }
                    ),
                    "",
                ),
            ]
        )
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        with self.assertRaisesRegex(DemoError, "availability zone offering t3a.xlarge"):
            aws.default_network()

    def test_aws_cli_rejects_wrong_identity_before_requested_operation(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "Account": TEST_ACCOUNT_ID,
                        "Arn": f"arn:aws:iam::{TEST_ACCOUNT_ID}:root",
                    }
                ),
                "",
            )
        )
        aws = AwsCli(
            profile="otel-demo",
            region="us-east-1",
            runner=runner,
            config=DemoConfig(expected_account_id=TEST_ACCOUNT_ID),
        )

        with self.assertRaisesRegex(DemoError, "OTelDemoOperator.*identity"):
            aws.verify_identity()

        self.assertEqual(runner.call_count, 1)

    def test_launcher_checks_identity_before_session_operation(self) -> None:
        ordering = Mock()
        with (
            patch.dict(os.environ, {"OTEL_DEMO_EXPECTED_ACCOUNT_ID": TEST_ACCOUNT_ID}),
            patch.object(AwsCli, "verify_identity", side_effect=lambda: ordering("identity")),
            patch.object(DemoController, "up", side_effect=lambda **_: ordering("up") and {}),
        ):
            self.assertEqual(main(["up"]), 0)

        self.assertEqual([call.args[0] for call in ordering.call_args_list], ["identity", "up"])

    def test_default_configuration_is_cost_bounded(self) -> None:
        config = DemoConfig()

        self.assertEqual(config.profile, "otel-demo")
        self.assertEqual(config.region, "us-east-1")
        self.assertEqual(config.instance_type, "t3a.xlarge")
        self.assertEqual(config.cpu_credits, "standard")
        self.assertEqual(config.default_ttl, timedelta(hours=2))
        self.assertEqual(config.maximum_lifetime, timedelta(hours=12))
        self.assertEqual(config.scheduler_group, "otel-demo")
        self.assertEqual(config.scheduler_role_name, "OTelDemoSchedulerExecutionRole")
        self.assertEqual(config.monthly_budget_usd, 10.0)
        self.assertEqual(config.maximum_session_estimate_usd, 3.0)

    def test_cli_defaults_to_persistent_operator_profile(self) -> None:
        args = _arguments(["up"])

        self.assertEqual(args.action, "up")

    def test_cli_does_not_accept_profile_or_region_overrides(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                _arguments(["--profile", "personal", "up"])
            with self.assertRaises(SystemExit):
                _arguments(["--region", "us-west-2", "up"])

    def test_up_fails_closed_when_cost_explorer_is_unavailable(self) -> None:
        aws = FakeAws()
        aws.fail_cost_query = True
        controller = DemoController(aws=aws, config=DemoConfig())

        with self.assertRaisesRegex(DemoError, "Cost Explorer"):
            controller.up(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))

        names = [name for name, _, _ in aws.calls]
        self.assertEqual(names, ["month_to_date_cost"])
        self.assertNotIn("run_instance", names)

    def test_up_blocks_when_account_monthly_budget_would_be_exceeded(self) -> None:
        aws = FakeAws()
        aws.month_to_date_cost_value = 7.01
        controller = DemoController(aws=aws, config=DemoConfig())

        with self.assertRaisesRegex(DemoError, "monthly budget"):
            controller.up(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))

        names = [name for name, _, _ in aws.calls]
        self.assertEqual(names, ["month_to_date_cost"])
        self.assertNotIn("run_instance", names)

    def test_aws_cli_reads_account_wide_current_month_cost(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "ResultsByTime": [
                            {"Total": {"UnblendedCost": {"Amount": "3.25", "Unit": "USD"}}}
                        ]
                    }
                ),
                "",
            )
        )
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        cost = aws.month_to_date_cost(today=datetime(2026, 9, 28, tzinfo=UTC))

        self.assertEqual(cost, 3.25)
        args = runner.call_args.args[0]
        self.assertEqual(args[1:5], ["--profile", "otel-demo", "--region", "us-east-1"])
        self.assertIn("get-cost-and-usage", args)
        payload = json.loads(args[args.index("--cli-input-json") + 1])
        self.assertEqual(payload["TimePeriod"], {"Start": "2026-09-01", "End": "2026-09-28"})
        self.assertNotIn("Filter", payload)

    def test_cost_guard_rejects_non_usd_currency(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "ResultsByTime": [
                            {"Total": {"UnblendedCost": {"Amount": "3.25", "Unit": "EUR"}}}
                        ]
                    }
                ),
                "",
            )
        )
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        with self.assertRaisesRegex(DemoError, "USD currency"):
            aws.month_to_date_cost(today=datetime(2026, 9, 28, tzinfo=UTC))

    def test_cost_guard_fails_closed_when_month_has_no_completed_day(self) -> None:
        runner = Mock()
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        with self.assertRaisesRegex(DemoError, "completed month-to-date"):
            aws.month_to_date_cost(today=datetime(2026, 10, 1, tzinfo=UTC))

        runner.assert_not_called()

    def test_extension_cannot_exceed_twelve_hours_from_creation(self) -> None:
        created = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
        current_deadline = created + timedelta(hours=2)

        extended = calculate_extended_deadline(
            created_at=created,
            current_deadline=current_deadline,
            now=created + timedelta(hours=1),
            extension=timedelta(hours=2),
            maximum_lifetime=timedelta(hours=12),
        )

        self.assertEqual(extended, created + timedelta(hours=4))
        with self.assertRaisesRegex(DemoError, "maximum session lifetime"):
            calculate_extended_deadline(
                created_at=created,
                current_deadline=created + timedelta(hours=11),
                now=created + timedelta(hours=1),
                extension=timedelta(hours=2),
                maximum_lifetime=timedelta(hours=12),
            )
