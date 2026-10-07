from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from scripts.otel_ec2 import (
    AwsCli,
    DemoConfig,
    DemoError,
)

TEST_ACCOUNT_ID = "123456789012"


class OTelEc2Tests(unittest.TestCase):
    def test_aws_cli_always_uses_explicit_profile_and_region(self) -> None:
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"Reservations": []}', ""))
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        result = aws.call("ec2", "describe-instances", "--output", "json")

        self.assertEqual(result, {"Reservations": []})
        args = runner.call_args.args[0]
        self.assertEqual(
            args[:5],
            ["aws", "--profile", "otel-demo", "--region", "us-east-1"],
        )
        self.assertIn("--no-cli-pager", args)
        self.assertIn("ec2", args)
        self.assertIn("describe-instances", args)
        self.assertEqual(args[-2:], ["--output", "json"])

    def test_aws_cli_surfaces_failure_without_echoing_command_output(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess([], 255, "", "credential-token-secret")
        )
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        with self.assertRaisesRegex(DemoError, "AWS CLI request failed") as error:
            aws.call("ec2", "describe-instances")

        self.assertNotIn("credential-token-secret", str(error.exception))

    def test_aws_cli_serializes_api_payload_as_cli_input_json(self) -> None:
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "{}", ""))
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        aws.call("ec2", "run-instances", payload={"ImageId": "ami-test"})

        args = runner.call_args.args[0]
        self.assertIn("--cli-input-json", args)
        self.assertEqual(args[args.index("--cli-input-json") + 1], '{"ImageId": "ami-test"}')
        self.assertIsNone(runner.call_args.kwargs["input"])

    def test_run_instance_passes_ec2_hardening_and_base64_user_data(self) -> None:
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, '{"Instances": [{"InstanceId": "i-test"}]}', ""
            )
        )
        config = DemoConfig()
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner, config=config)
        created = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

        launch_kwargs = dict(
            ami_id="ami-test",
            subnet_id="subnet-test",
            security_group_id="sg-test",
            instance_type="t3a.xlarge",
            cpu_credits="standard",
            metadata_tokens="required",
            root_volume_gib=30,
            delete_on_termination=True,
            created_at=created,
            expires_at=created + timedelta(hours=2),
            user_data="#!/bin/bash\necho demo",
        )
        aws.run_instance(**launch_kwargs)
        aws.run_instance(**launch_kwargs)

        args = runner.call_args_list[0].args[0]
        request = json.loads(args[args.index("--cli-input-json") + 1])
        second_args = runner.call_args_list[1].args[0]
        second_request = json.loads(second_args[second_args.index("--cli-input-json") + 1])
        self.assertEqual(request["CreditSpecification"], {"CpuCredits": "standard"})
        self.assertEqual(request["MetadataOptions"]["HttpTokens"], "required")
        self.assertEqual(request["InstanceInitiatedShutdownBehavior"], "terminate")
        self.assertEqual(request["BlockDeviceMappings"][0]["Ebs"]["VolumeSize"], 30)
        self.assertTrue(request["BlockDeviceMappings"][0]["Ebs"]["DeleteOnTermination"])
        self.assertEqual(base64.b64decode(request["UserData"]).decode(), "#!/bin/bash\necho demo")
        expected_token = hashlib.sha256(
            json.dumps(
                {key: value for key, value in request.items() if key != "ClientToken"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self.assertEqual(request["ClientToken"], expected_token)
        self.assertEqual(second_request["ClientToken"], request["ClientToken"])

    def test_security_group_request_contains_no_ingress_permissions(self) -> None:
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '{"GroupId": "sg-test"}', ""))
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        group_id = aws.create_security_group(vpc_id="vpc-test", ingress=[])

        self.assertEqual(group_id, "sg-test")
        args = runner.call_args.args[0]
        request = json.loads(args[args.index("--cli-input-json") + 1])
        self.assertNotIn("IpPermissions", request)
        self.assertNotIn("--ip-permissions", args)

    def test_security_group_reuse_requires_owned_tags_and_zero_ingress(self) -> None:
        group = {
            "GroupId": "sg-existing",
            "VpcId": "vpc-test",
            "IpPermissions": [],
            "Tags": [
                {"Key": "ManagedBy", "Value": "otel-demo-cli"},
                {"Key": "Project", "Value": "otel-demo"},
            ],
        }
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, json.dumps({"SecurityGroups": [group]}), ""
            )
        )
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        self.assertEqual(aws.security_group_for_vpc(vpc_id="vpc-test"), "sg-existing")
        group["IpPermissions"] = [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22}]
        runner.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({"SecurityGroups": [group]}), ""
        )
        with self.assertRaisesRegex(DemoError, "zero-ingress"):
            aws.security_group_for_vpc(vpc_id="vpc-test")

    def test_launcher_rejects_any_profile_or_region_other_than_dedicated_operator(self) -> None:
        with self.assertRaisesRegex(ValueError, "otel-demo.*us-east-1"):
            AwsCli(profile="personal", region="us-east-1", runner=Mock())
        with self.assertRaisesRegex(ValueError, "otel-demo.*us-east-1"):
            AwsCli(profile="otel-demo", region="us-west-2", runner=Mock())

    def test_aws_cli_verifies_expected_operator_identity(self) -> None:
        runner = Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "Account": TEST_ACCOUNT_ID,
                            "Arn": f"arn:aws:iam::{TEST_ACCOUNT_ID}:user/OTelDemoOperator",
                        }
                    ),
                    "",
                ),
                subprocess.CompletedProcess([], 0, '{"Vpcs": []}', ""),
            ]
        )
        aws = AwsCli(
            profile="otel-demo",
            region="us-east-1",
            runner=runner,
            config=DemoConfig(expected_account_id=TEST_ACCOUNT_ID),
        )

        aws.verify_identity()

        commands = [call.args[0] for call in runner.call_args_list]
        self.assertIn("sts", commands[0])
        self.assertIn("get-caller-identity", commands[0])

    def test_default_network_selects_public_subnet_where_instance_type_is_offered(self) -> None:
        runner = Mock(
            side_effect=[
                subprocess.CompletedProcess([], 0, json.dumps({"Vpcs": [{"VpcId": "vpc-1"}]}), ""),
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "InstanceTypeOfferings": [
                                {"Location": "us-east-1a"},
                                {"Location": "us-east-1b"},
                            ],
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
                                {
                                    "SubnetId": "subnet-003",
                                    "AvailabilityZone": "us-east-1b",
                                    "MapPublicIpOnLaunch": True,
                                },
                                {
                                    "SubnetId": "subnet-002",
                                    "AvailabilityZone": "us-east-1a",
                                    "MapPublicIpOnLaunch": True,
                                },
                                {
                                    "SubnetId": "subnet-000",
                                    "AvailabilityZone": "us-east-1a",
                                    "MapPublicIpOnLaunch": False,
                                },
                            ]
                        }
                    ),
                    "",
                ),
            ]
        )
        aws = AwsCli(profile="otel-demo", region="us-east-1", runner=runner)

        network = aws.default_network()

        self.assertEqual(network, {"vpc_id": "vpc-1", "subnet_id": "subnet-002"})
        offerings_args = runner.call_args_list[1].args[0]
        self.assertIn("describe-instance-type-offerings", offerings_args)
        self.assertIn("availability-zone", offerings_args)
        self.assertIn("Name=instance-type,Values=t3a.xlarge", offerings_args)
