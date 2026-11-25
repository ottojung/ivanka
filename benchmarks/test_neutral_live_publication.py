"""Neutral live publication: source attestations and policy reports are scrubbed."""
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from assembler_bench.current_runs import write
from assembler_bench.public_view import sanitize_document
from assembler_bench.public_vocabulary import find_tokens
from assembler_bench.resource_policy_neutral import scrub as scrub_policy
from assembler_bench.site_build import SITE

ROOT = Path(__file__).resolve().parents[1]


class NeutralLivePublicationTests(unittest.TestCase):
    def test_write_accepts_scrubbed_attestation_document(self):
        source = SITE / "data/live-fork-attestation.json"
        document = sanitize_document(json.loads(source.read_text()))
        self.assertFalse(find_tokens(json.dumps(document)))
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            (site / "data").mkdir()
            report = json.loads((SITE / "data/runs.json").read_text())
            write(site, report, document)
            self.assertEqual(
                json.loads((site / "data/live-fork-attestation.json").read_text()),
                document)

    def test_resource_policy_scrub_preserves_limits_and_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "resource-policy.json"
            original = json.loads((SITE / "data/resource-policy.json").read_text())
            original["note"] = ("Sampled RSS is not an exact kernel hard cap; "
                                "no legacy success is silently requalified.")
            original["schema"] = "ivanka.external-caps-qualification.v1"
            path.write_text(json.dumps(original))
            result = scrub_policy(path)
            self.assertEqual(result["schema"], "ivanka.external-caps.v1")
            self.assertEqual(result["max_wall_seconds"], 2400)
            self.assertEqual(result["max_rss_bytes"], 4_000_000_000)
            self.assertEqual(result["results"], original["results"])
            self.assertFalse(find_tokens(path.read_text()))

    def test_current_publish_cli_accepts_legacy_exact_flags(self):
        help_text = subprocess.run(
            [sys.executable, "-m", "assembler_bench.current_publish", "--help"],
            text=True, capture_output=True, check=True,
            env={"PYTHONPATH": str(ROOT / "benchmarks"),
                 "PATH": "/usr/bin:/bin"}).stdout
        self.assertIn("--exact-real", help_text)
        self.assertIn("--exact-synthetic", help_text)
        self.assertIn("--migrate", help_text)

    def test_neutral_service_failed_commands_never_report_success(self):
        original = (ROOT / "scripts/neutral_bench_publish_service.sh").read_text()
        for failure in ("fetch", "push"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                tools = root / "bin"
                tools.mkdir()
                for name in (
                    "phase-synthetic464/run_manifest.json",
                    "live-comparator-pages/site/bench/data/runs.json",
                    "live-comparator-pages/site/bench/data/assembler-evidence.json",
                ):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                python = root / "bench-ci-venv/bin/python"
                python.parent.mkdir(parents=True)
                python.write_text("#!/bin/sh\nexit 0\n")
                python.chmod(0o755)
                git = tools / "git"
                git.write_text(
                    "#!/bin/sh\n"
                    "shift 2\n"
                    'echo "$1" >> "$MOCK_CALLS"\n'
                    'case "$1" in\n'
                    '  "$MOCK_FAILURE") exit 7 ;;\n'
                    '  log) echo 0 ;;\n'
                    '  rev-parse) echo f06da0e6fb151f092c8f0b8d9d70615a0cd2d0e3 ;;\n'
                    '  diff) exit 1 ;;\n'
                    'esac\n'
                )
                git.chmod(0o755)
                sleep = tools / "sleep"
                sleep.write_text("#!/bin/sh\nexit 91\n")
                sleep.chmod(0o755)
                script = root / "publisher.sh"
                lines = original.splitlines()
                script.write_text("\n".join(
                    "export PATH=" + shlex.quote(str(tools) + ":" + os.environ["PATH"])
                    if line.startswith("export PATH=") else
                    "R=" + str(root) if line.startswith("R=") else line
                    for line in lines
                ) + "\n")
                calls = root / "calls"
                env = dict(os.environ, MOCK_FAILURE=failure, MOCK_CALLS=str(calls))
                result = subprocess.run(
                    ["sh", str(script)], env=env, text=True,
                    capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 91, result.stderr)
                log = (root / "comparator-services/neutral-publisher.log").read_text()
                self.assertIn("NEUTRAL_PUBLICATION_RETRY rc=7", log)
                self.assertNotIn("NEUTRAL_SITE_PUSHED", log)
                commands = calls.read_text().splitlines()
                if failure == "fetch":
                    self.assertNotIn("commit", commands)
                else:
                    self.assertEqual(commands.count("push"), 2)
                self.assertEqual(commands[-2:], ["rebase", "reset"])

    def test_neutral_service_script_never_calls_retired_snapshot(self):
        script = (ROOT / "scripts/neutral_bench_publish_service.sh").read_text()
        self.assertNotIn("exploratory-candidates.json", script)
        self.assertNotIn("819cab4", script)
        self.assertIn("current_publish", script)
        self.assertIn("resource_policy_neutral", script)
        self.assertIn("public_vocabulary", script)
        self.assertIn("publish-neutral", script)


if __name__ == "__main__":
    unittest.main()
