"""CI workflow guards for data-only publisher pushes."""

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github/workflows/ci.yml"


class CIWorkflowPathsIgnoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
        # PyYAML 1.1 parses the workflow key "on" as boolean True.
        cls.on = cls.workflow.get("on", cls.workflow.get(True))

    def test_push_ignores_only_verified_generated_data_paths(self):
        push = self.on["push"]
        self.assertEqual(push["branches"], ["main"])
        self.assertEqual(
            push["paths-ignore"],
            [
                "site/bench/data/runs.json",
                "site/bench/data/assembler-evidence.json",
            ],
        )

    def test_pull_request_and_dispatch_remain_unfiltered(self):
        self.assertIsNone(self.on["pull_request"])
        self.assertIsNone(self.on["workflow_dispatch"])

    def test_required_python_check_name_unchanged(self):
        self.assertEqual(
            self.workflow["jobs"]["python"]["name"],
            "Python tests and lint",
        )


if __name__ == "__main__":
    unittest.main()
