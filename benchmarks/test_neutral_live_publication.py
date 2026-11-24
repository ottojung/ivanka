"""Neutral live publication: source attestations and policy reports are scrubbed."""
import json
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
