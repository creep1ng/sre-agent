"""Execute the operator CLI as documented, not only as an imported module."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OTelCliEntrypointTests(unittest.TestCase):
    def test_script_help_works_without_pythonpath_override(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/otel_ec2.py", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up", result.stdout)
        self.assertIn("extend", result.stdout)


if __name__ == "__main__":
    unittest.main()
