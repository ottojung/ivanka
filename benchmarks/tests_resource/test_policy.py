"""50-minute cohort policy is opt-in and preserves old attested measurements."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from benchmarks.expanded.micall_synthetic import command as original_command
from benchmarks.real_recovery.attempt import execute
from benchmarks.real_recovery.eligibility import selected
from benchmarks.resource_phase.synthetic_arm import command
from benchmarks.resource_phase.synthetic_verify import verify


class ResourcePolicyTests(TestCase):
    def test_original_invocation_unchanged_and_new_memory_is_five_gib(self):
        args = ("iva", "e" * 64, Path("/input"), Path("/output"), "s1")
        old = original_command(*args, 1800)
        new = command(*args, 3000)
        self.assertIn("--memory=4g", old)
        self.assertIn("--memory=5g", new)
        self.assertEqual(new[new.index("--timeout") + 1], "3000")

    def test_synthetic_verifier_recognizes_both_policy_regimes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "final.csv").write_bytes(b"final\n")
            digest = hashlib.sha256(b"final\n").hexdigest()
            for lifetime, memory, seconds in ((1800, "4g", 800),
                                              (3000, "5g", 2200)):
                record = {"status": "success", "sha256": "e" * 64,
                          "score_origin": "micall_final_max_reference_panel_v1",
                          "timing_origin": "micall_in_container_monotonic_v1",
                          "argv": ["podman", "--memory=" + memory, "--timeout",
                                   str(lifetime), "e" * 64, "--all_projects"],
                          "exit_code": 0, "seconds": seconds, "score": 98.0,
                          "final_dominant": {"source_output": "final.csv",
                                             "conseq_csv_sha256": digest}}
                (root / "execution.json").write_text(json.dumps(record))
                self.assertEqual(verify(root, "iva", "e" * 64), record)
            record["seconds"] = 3100
            (root / "execution.json").write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                verify(root, "iva", "e" * 64)

    def test_retry_eligibility_only_time_and_memory_problems(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)
            timing = path / "micall_internal_timing.json"
            timing.write_text('{"exit_code":-9}')
            def row(code, wall):
                return {"failed": True, "arm": {"exit_code": code,
                        "container_wall_seconds": wall,
                        "artifact_dir": str(path)}}
            self.assertTrue(selected(row(255, 1798)))
            self.assertTrue(selected(row(124, 1800)))
            self.assertTrue(selected(row(247, 800)))
            self.assertFalse(selected(row(255, 3)))
            self.assertFalse(selected(row(1, 3)))
            timing.write_text('{"exit_code":0}')
            self.assertFalse(selected(row(247, 800)))

    def test_physical_retry_uses_3000_seconds_and_retains_original(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original"
            sample = "sample"
            key = hashlib.sha256(sample.encode()).hexdigest()
            path = original / "abyss" / "checkpoints" / (key + ".json")
            path.parent.mkdir(parents=True)
            path.write_text('{"failed": true}\n')
            pm = Mock()
            pm.run_arm.return_value = {"exit_code": 255, "image_id": "a"}
            row = {"sample": sample, "input_sha256": "input", "project": ""}
            result = execute(row, "abyss", {"abyss": "a"}, None, None,
                             pm, root / "retry", original)
            self.assertTrue(result["failed"])
            self.assertEqual(pm.run_arm.call_args.args[4], 3000)
            self.assertEqual(result["resource_timeout_seconds"], 3000)
            self.assertEqual(json.loads(path.read_text()), {"failed": True})
            self.assertEqual(len(result["original_checkpoint_sha256"]), 64)
