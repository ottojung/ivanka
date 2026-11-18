"""Read-only source, six-way checkpoint and selective retry gating tests."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from assembler_bench import physical_six_gate as gate


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class PhysicalSixGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images = {t: str(i + 1) * 64 for i, t in enumerate(gate.SIX)}
        self.orig = self.root / "phase-real198"
        self.retry = self.root / "phase-real198-memory-retries"
        self.manifest = self.orig / "run_manifest.json"
        write(self.manifest, {
            "schema": "ivanka.expanded.comparators_first_real.v1",
            "expected_samples": 198, "ivanka_deferred": True,
            "images": self.images})
        write(self.orig / "attempt_summary.json", {
            "schema": "ivanka.expanded.comparators_first_real.v1",
            "samples": 198, "ivanka_deferred": True,
            "tools": list(gate.SIX), "manifest_sha256": gate.digest(self.manifest)})
        eligibility = {t: [] for t in gate.SIX}
        for tool in gate.SIX:
            for n in range(198):
                name = f"sample-{n:03d}"
                key = hashlib.sha256(name.encode()).hexdigest() + ".json"
                write(self.orig / tool / "checkpoints" / key, {
                    "sample": name, "tool": tool, "failed": n % 2 == 1})
            if tool in ("haploflow", "abyss"):
                name = "sample-001"
                eligibility[tool].append(name)
                key = hashlib.sha256(name.encode()).hexdigest() + ".json"
                write(self.retry / tool / "checkpoints" / key, {
                    "sample": name, "tool": tool,
                    "image_id": self.images[tool],
                    "arm": {"image_id": self.images[tool], "exit_code": 0,
                            "container_wall_seconds": 32},
                    "failed": False, "resource_timeout_seconds": 3000,
                    "original_checkpoint_sha256":
                        gate.digest(self.orig / tool / "checkpoints" / key),
                })
        write(self.retry / "resource_policy_receipt.json", {
            "schema": "ivanka.expanded.physical-resource-retry.v1",
            "timeout_seconds": 3000, "concurrent_arms": 2,
            "do_not_rerun_original_successes": True,
            "original_run_manifest_sha256": gate.digest(self.manifest),
            "original_completed_summary_sha256":
                gate.digest(self.orig / "attempt_summary.json"),
            "eligibility": eligibility})
        write(self.retry / "attempt_summary.json", {
            "schema": "ivanka.expanded.physical-resource-retry.v1",
            "finished": True, "ivanka_deferred": True,
            "original": str(self.orig),
            "timeout_seconds": 3000,
            "eligible": {t: len(s) for t, s in eligibility.items()}})

    def test_full_source_and_retry_certificate(self):
        self.assertTrue(gate.ready(self.root, self.images))

    def test_missing_retry_checkpoint_blocks_handoff(self):
        p = next((self.retry / "abyss/checkpoints").glob("*.json"))
        p.rename(p.with_suffix(".interrupted"))
        with self.assertRaisesRegex(ValueError, "missing checkpoints"):
            gate.ready(self.root, self.images)

    def test_modified_original_checkpoint_blocks_handoff(self):
        name = hashlib.sha256(b"sample-001").hexdigest() + ".json"
        p = self.orig / "haploflow/checkpoints" / name
        p.write_text("altered")
        with self.assertRaises(ValueError):
            gate.ready(self.root, self.images)

    def test_source_or_image_change_blocks_handoff(self):
        with self.assertRaises(ValueError):
            gate.ready(self.root, {**self.images, "spades": "different"})
        self.manifest.write_text("tampered")
        with self.assertRaises(ValueError):
            gate.ready(self.root, self.images)

    def test_missing_final_summary_makes_handoff_wait(self):
        (self.retry / "attempt_summary.json").unlink()
        self.assertFalse(gate.ready(self.root, self.images))


if __name__ == "__main__":
    unittest.main()
