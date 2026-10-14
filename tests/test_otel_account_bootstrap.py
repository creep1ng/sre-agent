from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from scripts.bootstrap_otel_account import BootstrapError, bootstrap_account

TEST_ACCOUNT_ID = "123456789012"
TEMPLATE_PATHS = {
    "operator": Path("infra/otel-demo-operator.yaml"),
    "runtime": Path("infra/otel-demo-runtime.yaml"),
    "budget": Path("infra/otel-demo-budget.yaml"),
}


class PersonalBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.credentials = root / ".aws" / "credentials"
        self.templates = {name: root / f"{name}.yaml" for name in TEMPLATE_PATHS}
        for path in self.templates.values():
            path.write_text("template", encoding="utf-8")
        self.runner = Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "Account": TEST_ACCOUNT_ID,
                            "Arn": f"arn:aws:iam::{TEST_ACCOUNT_ID}:root",
                        }
                    ),
                    "",
                ),
                subprocess.CompletedProcess([], 0, "{}", ""),
                subprocess.CompletedProcess([], 0, "{}", ""),
                subprocess.CompletedProcess([], 0, "{}", ""),
                subprocess.CompletedProcess([], 0, "Stack ready", ""),
                subprocess.CompletedProcess([], 0, "Stack ready", ""),
                subprocess.CompletedProcess([], 0, "Stack ready", ""),
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "Stacks": [
                                {
                                    "Outputs": [
                                        {
                                            "OutputKey": "OperatorUserName",
                                            "OutputValue": "OTelDemoOperator",
                                        },
                                    ]
                                }
                            ]
                        }
                    ),
                    "",
                ),
                subprocess.CompletedProcess([], 0, json.dumps({"AccessKeyMetadata": []}), ""),
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "AccessKey": {
                                "AccessKeyId": "TEST_ACCESS_KEY_ID",
                                "SecretAccessKey": "TEST_SECRET_ACCESS_KEY",
                            }
                        }
                    ),
                    "",
                ),
            ]
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_bootstrap(self, **kwargs):
        return bootstrap_account(
            expected_account=TEST_ACCOUNT_ID,
            alert_email="ops@example.test",
            vpc_id="vpc-123",
            apply=True,
            credentials_path=self.credentials,
            template_paths=self.templates,
            runner=self.runner,
            **kwargs,
        )

    def test_deploys_with_personal_root_then_persists_only_iam_user_key(self) -> None:
        result = self.run_bootstrap()

        self.assertEqual(result, {"profile": "otel-demo", "status": "created"})
        calls = [call.args[0] for call in self.runner.call_args_list]
        self.assertEqual(len(calls), 10)
        self.assertTrue(all(command[:3] == ["aws", "--profile", "personal"] for command in calls))
        self.assertTrue(all("validate-template" in call for call in calls[1:4]))
        self.assertTrue(all("deploy" in call for call in calls[4:7]))
        self.assertTrue(all("--capabilities" in call for call in calls[4:7]))
        self.assertIn("describe-stacks", calls[7])
        self.assertIn("list-access-keys", calls[8])
        self.assertIn("create-access-key", calls[9])
        self.assertIn("OTelDemoOperator", calls[9])
        self.assertNotIn("create-access-key", calls[4])
        self.assertNotIn("TEST_SECRET_ACCESS_KEY", str(result))
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)
        lock_file = self.credentials.parent / ".otel-demo-bootstrap.lock"
        self.assertEqual(lock_file.stat().st_mode & 0o777, 0o600)
        contents = self.credentials.read_text(encoding="utf-8")
        self.assertIn("[otel-demo]", contents)
        self.assertIn("aws_access_key_id = TEST_ACCESS_KEY_ID", contents)
        self.assertIn("aws_secret_access_key = TEST_SECRET_ACCESS_KEY", contents)

    def test_requires_explicit_apply_and_never_calls_aws_without_it(self) -> None:
        with self.assertRaisesRegex(BootstrapError, "--apply"):
            bootstrap_account(
                expected_account=TEST_ACCOUNT_ID,
                alert_email="ops@example.test",
                vpc_id="vpc-123",
                apply=False,
                credentials_path=self.credentials,
                template_paths=self.templates,
                runner=self.runner,
            )
        self.runner.assert_not_called()

    def test_existing_profile_is_idempotent_only_after_operator_identity_check(self) -> None:
        self.credentials.parent.mkdir(parents=True)
        original = (
            "[otel-demo]\naws_access_key_id=existing\naws_secret_access_key=existing-secret\n"
        )
        self.credentials.write_text(original, encoding="utf-8")

        self.runner.side_effect = [
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
            )
        ]

        result = self.run_bootstrap()

        self.assertEqual(result, {"profile": "otel-demo", "status": "already-configured"})
        self.assertEqual(self.credentials.read_text(encoding="utf-8"), original)
        self.assertEqual(self.runner.call_count, 1)
        self.assertIn("get-caller-identity", self.runner.call_args.args[0])

    def test_existing_profile_with_wrong_identity_fails_closed(self) -> None:
        self.credentials.parent.mkdir(parents=True)
        original = (
            "[otel-demo]\naws_access_key_id=existing\naws_secret_access_key=existing-secret\n"
        )
        self.credentials.write_text(original, encoding="utf-8")
        self.runner.side_effect = [
            subprocess.CompletedProcess(
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
        ]

        with self.assertRaisesRegex(BootstrapError, "OTelDemoOperator.*identity"):
            self.run_bootstrap()

        self.assertEqual(self.runner.call_count, 1)
        self.assertEqual(self.credentials.read_text(encoding="utf-8"), original)

    def test_rejects_wrong_account_before_stack_deploy(self) -> None:
        self.runner.reset_mock(side_effect=True)
        self.runner.side_effect = [
            subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "Account": "123456789013",
                        "Arn": "arn:aws:iam::123456789013:root",
                    }
                ),
                "",
            )
        ]

        with self.assertRaisesRegex(BootstrapError, "configured account root principal"):
            self.run_bootstrap()

        self.assertEqual(self.runner.call_count, 1)

    def test_rejects_non_root_before_stack_deploy(self) -> None:
        self.runner.reset_mock(side_effect=True)
        self.runner.side_effect = [
            subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "Account": TEST_ACCOUNT_ID,
                        "Arn": f"arn:aws:iam::{TEST_ACCOUNT_ID}:user/operator",
                    }
                ),
                "",
            )
        ]

        with self.assertRaisesRegex(BootstrapError, "root principal"):
            self.run_bootstrap()

        self.assertEqual(self.runner.call_count, 1)

    def test_cloudformation_validation_precedes_stack_deployment(self) -> None:
        self.runner.side_effect = [
            subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "Account": TEST_ACCOUNT_ID,
                        "Arn": f"arn:aws:iam::{TEST_ACCOUNT_ID}:root",
                    }
                ),
                "",
            ),
            subprocess.CompletedProcess([], 255, "", "template rejected"),
        ]

        with self.assertRaisesRegex(BootstrapError, "AWS bootstrap request failed"):
            self.run_bootstrap()

        calls = [call.args[0] for call in self.runner.call_args_list]
        self.assertIn("validate-template", calls[1])
        self.assertFalse(any("deploy" in command for command in calls))

    def test_deletes_new_key_if_local_profile_write_fails(self) -> None:
        self.runner.side_effect = list(self.runner.side_effect) + [
            subprocess.CompletedProcess([], 0, "", ""),
        ]
        with patch("scripts.bootstrap_otel_account._write_credentials", side_effect=OSError):
            with self.assertRaisesRegex(BootstrapError, "removed"):
                self.run_bootstrap()

        command = self.runner.call_args.args[0]
        self.assertIn("delete-access-key", command)
        self.assertEqual(
            command[-4:],
            ["--user-name", "OTelDemoOperator", "--access-key-id", "TEST_ACCESS_KEY_ID"],
        )

    def test_deletes_created_key_if_aws_returns_no_secret(self) -> None:
        self.runner.side_effect = [
            subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "Account": TEST_ACCOUNT_ID,
                        "Arn": f"arn:aws:iam::{TEST_ACCOUNT_ID}:root",
                    }
                ),
                "",
            ),
            subprocess.CompletedProcess([], 0, "{}", ""),
            subprocess.CompletedProcess([], 0, "{}", ""),
            subprocess.CompletedProcess([], 0, "{}", ""),
            subprocess.CompletedProcess([], 0, "Stack ready", ""),
            subprocess.CompletedProcess([], 0, "Stack ready", ""),
            subprocess.CompletedProcess([], 0, "Stack ready", ""),
            subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "Stacks": [
                            {
                                "Outputs": [
                                    {
                                        "OutputKey": "OperatorUserName",
                                        "OutputValue": "OTelDemoOperator",
                                    },
                                ]
                            }
                        ]
                    }
                ),
                "",
            ),
            subprocess.CompletedProcess([], 0, json.dumps({"AccessKeyMetadata": []}), ""),
            subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "AccessKey": {
                            "AccessKeyId": "TEST_ACCESS_KEY_ID",
                        }
                    }
                ),
                "",
            ),
            subprocess.CompletedProcess([], 0, "", ""),
        ]

        with self.assertRaisesRegex(BootstrapError, "usable dedicated-user key"):
            self.run_bootstrap()

        self.assertIn("delete-access-key", self.runner.call_args.args[0])


class InfrastructureTemplateTests(unittest.TestCase):
    def test_operator_can_query_instance_type_availability_by_az(self) -> None:
        template = yaml.safe_load(Path("infra/otel-demo-operator.yaml").read_text())
        policy = template["Resources"]["OTelDemoOperatorNetworkPolicy"]["Properties"][
            "PolicyDocument"
        ]
        read_statement = next(
            item
            for item in policy["Statement"]
            if item.get("Sid") == "ReadNetworkAndOwnedInstances"
        )

        self.assertIn("ec2:DescribeInstanceTypeOfferings", read_statement["Action"])

    def test_ssm_instance_actions_restrict_owned_nodes_with_ssm_resource_tags(self) -> None:
        template = yaml.safe_load(Path("infra/otel-demo-operator.yaml").read_text())
        policy = template["Resources"]["OTelDemoOperatorSessionPolicy"]["Properties"][
            "PolicyDocument"
        ]
        statements = {item["Sid"]: item for item in policy["Statement"]}

        for sid in (
            "RunDeadlineUpdateOnlyOnOwnedInstances",
            "StartSessionsOnlyOnOwnedInstances",
        ):
            with self.subTest(sid=sid):
                statement = statements[sid]
                conditions = statement["Condition"]["StringEquals"]
                self.assertEqual(conditions["ssm:resourceTag/ManagedBy"], "otel-demo-cli")
                self.assertEqual(conditions["ssm:resourceTag/Project"], "otel-demo")
                self.assertEqual(conditions["aws:RequestedRegion"], "us-east-1")
                self.assertNotIn("ec2:ResourceTag", conditions)

    def test_create_security_group_uses_only_supported_authorization_context(self) -> None:
        template = yaml.safe_load(Path("infra/otel-demo-operator.yaml").read_text())
        policy = template["Resources"]["OTelDemoOperatorNetworkPolicy"]["Properties"][
            "PolicyDocument"
        ]
        statements = [
            item for item in policy["Statement"] if item.get("Action") == "ec2:CreateSecurityGroup"
        ]
        group_statement = next(
            item
            for item in statements
            if isinstance(item["Resource"], dict)
            and item["Resource"].get("Fn::Sub", "").endswith("security-group/*")
        )
        vpc_statement = next(
            item
            for item in statements
            if isinstance(item["Resource"], dict)
            and item["Resource"].get("Fn::Sub", "").endswith("vpc/${VpcId}")
        )

        self.assertEqual(
            len(statements),
            2,
        )
        self.assertEqual(
            group_statement["Resource"],
            {
                "Fn::Sub": "arn:${AWS::Partition}:ec2:${AWS::Region}:"
                "${AWS::AccountId}:security-group/*"
            },
        )
        self.assertEqual(
            group_statement["Condition"]["StringEquals"],
            {"aws:RequestedRegion": "us-east-1"},
        )
        self.assertNotIn("ec2:Vpc", str(group_statement.get("Condition", {})))
        self.assertNotIn("aws:RequestTag", str(group_statement.get("Condition", {})))
        self.assertEqual(
            vpc_statement["Resource"],
            {"Fn::Sub": "arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:vpc/${VpcId}"},
        )
        self.assertNotIn("ec2:Vpc", str(vpc_statement.get("Condition", {})))
        self.assertEqual(
            vpc_statement["Condition"]["StringEquals"]["aws:RequestedRegion"],
            "us-east-1",
        )
        tag_statement = next(
            item for item in policy["Statement"] if item.get("Action") == "ec2:CreateTags"
        )
        self.assertEqual(
            tag_statement["Condition"]["StringEquals"]["ec2:CreateAction"],
            "CreateSecurityGroup",
        )
        self.assertEqual(
            tag_statement["Condition"]["StringEquals"]["aws:RequestTag/ManagedBy"],
            "otel-demo-cli",
        )
        self.assertEqual(
            tag_statement["Condition"]["StringEquals"]["aws:RequestTag/Project"],
            "otel-demo",
        )
        self.assertNotIn("ec2:AuthorizeSecurityGroupIngress", str(policy))

    def test_template_scopes_scheduler_trust_and_termination_and_sets_monthly_budget(self) -> None:
        operator = Path("infra/otel-demo-operator.yaml").read_text(encoding="utf-8")
        runtime = Path("infra/otel-demo-runtime.yaml").read_text(encoding="utf-8")

        for required in (
            "AWS::IAM::User",
            "OTelDemoOperator",
            "iam:PassedToService",
            "iam:GetInstanceProfile",
            "ce:GetCostAndUsage",
        ):
            with self.subTest(required=required):
                self.assertIn(required, operator)
        for required in (
            "OTelDemoInstanceProfile",
            "AmazonSSMManagedInstanceCore",
            "OTelDemoSchedulerExecutionRole",
            "scheduler.amazonaws.com",
            "aws:SourceAccount",
            "AWS::AccountId",
            "aws:SourceArn",
            "schedule-group/otel-demo",
            "ec2:TerminateInstances",
            "ec2:ResourceTag/ManagedBy",
            "ScheduleGroup",
        ):
            with self.subTest(required=required):
                self.assertIn(required, runtime)
        self.assertNotIn("AWS::IAM::AccessKey", operator + runtime)
        budget = Path("infra/otel-demo-budget.yaml").read_text(encoding="utf-8")
        for required in (
            "AWS::Budgets::BudgetsAction",
            "COST",
            "MONTHLY",
            "10",
            "AlertEmail",
            "Budget",
        ):
            self.assertIn(required, budget)
        parsed = yaml.safe_load(runtime)
        scheduler_trust = parsed["Resources"]["OTelDemoSchedulerExecutionRole"]["Properties"]
        source_arn = scheduler_trust["AssumeRolePolicyDocument"]["Statement"][0]["Condition"][
            "ArnLike"
        ]["aws:SourceArn"]["Fn::Sub"]
        self.assertTrue(source_arn.endswith(":schedule-group/otel-demo"))

    def test_operator_policy_has_no_inbound_rule_mutation_permission(self) -> None:
        template = Path("infra/otel-demo-operator.yaml").read_text(encoding="utf-8")
        self.assertNotIn("ec2:AuthorizeSecurityGroupIngress", template)
        self.assertNotIn("ec2:ModifyInstanceAttribute", template)

    def test_customer_managed_operator_policies_stay_within_iam_size_quota(self) -> None:
        template = yaml.safe_load(Path("infra/otel-demo-operator.yaml").read_text())
        resources = template["Resources"]
        policies = [
            resource["Properties"]["PolicyDocument"]
            for name, resource in resources.items()
            if name.startswith("OTelDemoOperator")
            and resource.get("Type") == "AWS::IAM::ManagedPolicy"
        ]

        self.assertGreaterEqual(len(policies), 2)
        for policy in policies:
            compact = json.dumps(policy, separators=(",", ":"), ensure_ascii=True)
            self.assertLessEqual(len(compact), 6144, f"managed policy is {len(compact)} characters")

    def test_run_instances_policy_requires_amazon_owned_images_and_snapshots(self) -> None:
        template = yaml.safe_load(Path("infra/otel-demo-operator.yaml").read_text())
        policy = template["Resources"]["OTelDemoOperatorEc2Policy"]["Properties"]["PolicyDocument"]
        image_statement = next(
            item
            for item in policy["Statement"]
            if item.get("Sid") == "LaunchOnlyCanonicalUbuntuImagesAndSnapshots"
        )

        self.assertEqual(image_statement["Condition"]["StringEquals"]["ec2:Owner"], "amazon")
        self.assertEqual(
            image_statement["Resource"],
            [
                "arn:aws:ec2:us-east-1::image/*",
                "arn:aws:ec2:us-east-1:*:snapshot/*",
            ],
        )

    def test_budget_action_denies_new_run_instances_without_blocking_scheduler(self) -> None:
        template = yaml.safe_load(Path("infra/otel-demo-budget.yaml").read_text())
        resources = template["Resources"]
        actions = [
            value
            for value in resources.values()
            if value.get("Type") == "AWS::Budgets::BudgetsAction"
        ]
        self.assertEqual(len(actions), 1)
        action = actions[0]["Properties"]
        self.assertEqual(action["ActionType"], "APPLY_IAM_POLICY")
        self.assertEqual(action["ApprovalModel"], "AUTOMATIC")
        self.assertEqual(action["NotificationType"], "ACTUAL")
        self.assertEqual(action["ActionThreshold"], {"Type": "PERCENTAGE", "Value": 100})
        self.assertEqual(
            action["Subscribers"],
            [{"Address": {"Ref": "AlertEmail"}, "Type": "EMAIL"}],
        )
        self.assertEqual(
            action["Definition"]["IamActionDefinition"]["Users"],
            ["OTelDemoOperator"],
        )
        deny = resources["OTelDemoRunInstancesDenyPolicy"]["Properties"]["PolicyDocument"]
        self.assertEqual(deny["Statement"][0]["Effect"], "Deny")
        self.assertEqual(deny["Statement"][0]["Action"], "ec2:RunInstances")
        self.assertEqual(deny["Statement"][0]["Resource"], "*")
        role = resources["OTelDemoBudgetActionExecutionRole"]["Properties"]
        trust = role["AssumeRolePolicyDocument"]["Statement"][0]
        self.assertEqual(trust["Principal"]["Service"], "budgets.amazonaws.com")
        self.assertEqual(
            trust["Condition"]["ArnLike"]["aws:SourceArn"]["Fn::Sub"],
            "arn:${AWS::Partition}:budgets::${AWS::AccountId}:budget/"
            "otel-demo-monthly-account-budget",
        )
        permissions = role["Policies"][0]["PolicyDocument"]["Statement"][0]
        self.assertEqual(permissions["Action"], ["iam:AttachUserPolicy", "iam:DetachUserPolicy"])
        self.assertEqual(
            permissions["Resource"]["Fn::Sub"],
            "arn:${AWS::Partition}:iam::${AWS::AccountId}:user/OTelDemoOperator",
        )
        self.assertEqual(
            permissions["Condition"]["ArnEquals"]["iam:PolicyARN"],
            {"Ref": "OTelDemoRunInstancesDenyPolicy"},
        )


if __name__ == "__main__":
    unittest.main()
