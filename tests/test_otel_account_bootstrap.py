from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
