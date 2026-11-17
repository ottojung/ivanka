"""Observed RSS and retry epochs cannot fabricate successful original runs."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from assembler_bench.current_inputs import accept, sample
from assembler_bench.current_publish import monotone
from assembler_bench.resource_peak import load, peak_mib, physical_name
from assembler_bench.resource_retry import select, source_failure


class PeakMemoryTests(unittest.TestCase):
    def test_only_ended_observations_supply_an_observed_peak(self):
        with TemporaryDirectory() as temp:
            name = "ivanka-bench-ivanka-abyss-x-01234567"
            value = {"schema": "ivanka.memory.process-tree-sampling.v1",
                     "container_id": "f" * 12, "container_name": name,
                     "samples": 3, "observation_ended": False,
                     "peak_tree_rss_bytes_sampled": 3145728}
            path = Path(temp) / ("f" * 12 + ".json")
            path.write_text(json.dumps(value))
            self.assertIsNone(peak_mib(load(temp), name))
            value["observation_ended"] = True
            path.write_text(json.dumps(value))
            self.assertEqual(peak_mib(load(temp), name), 3)
            value["samples"] = 1
            path.write_text(json.dumps(value))
            self.assertIsNone(peak_mib(load(temp), name))

    def test_physical_observation_matches_original_container_name(self):
        import hashlib
        fn = lambda data: hashlib.sha256(data).hexdigest()
        arm = {"artifact_dir": "/tmp/artifacts/abyss-abc-def/sample/ivanka"}
        self.assertEqual(physical_name(arm, "abyss", "sample", fn),
                         "ivanka-bench-ivanka-abyss-abc-def-af2bdbe1")

    def test_retry_records_link_unmodified_original_checkpoint(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.json"
            base = {"failed": True, "arm": {"exit_code": 255,
                    "container_wall_seconds": 1798.0}}
            original.write_text(json.dumps(base))
            self.assertTrue(source_failure(base))
            path = root / "retries" / "abyss" / "checkpoints" / "original.json"
            path.parent.mkdir(parents=True)
            row = {"original_checkpoint_sha256":
                       hashlib.sha256(original.read_bytes()).hexdigest(),
                   "resource_timeout_seconds": 3000, "sample": "s",
                   "tool": "abyss", "image_id": "image",
                   "input_sha256": "reads",
                   "reference_panel_sha256": "panel",
                   "status": "finished", "failed": False}
            path.write_text(json.dumps(row))
            base.update(sample="s", tool="abyss", image_id="image",
                        input_sha256="reads", reference_panel_sha256="panel")
            updated, attestation = select(base, original, root/"retries",
                                          "abyss", "s", "image")
            self.assertEqual(updated, row)
            self.assertEqual(attestation["timeout_seconds"], 3000)
            row["input_sha256"] = "wrong"
            path.write_text(json.dumps(row))
            with self.assertRaises(ValueError):
                select(base, original, root/"retries", "abyss", "s", "image")

    def test_recovery_is_only_allowed_to_reverse_a_failure_with_a_proof(self):
        row = sample("R001", ["abyss"])
        row["failures"] = ["abyss"]
        def report(item):
            return {"runs": [{"cohort": "real", "id": "a", "images": {"abyss":"i"},
                 "expected_sample_count": 198, "tools": ["abyss"],
                 "tool_progress": {"abyss": {"finished":1}},
                 "samples": [item]}]}
        newer = sample("R001", ["abyss"])
        newer["score"]["abyss"] = 4
        newer["seconds"]["abyss"] = 6
        with self.assertRaises(ValueError):
            monotone(report(row), report(newer))
        newer["recovery"] = {"abyss": {
            "timeout_seconds": 3000, "status": "success",
            "original_checkpoint_sha256": "0" * 64,
            "retry_checkpoint_sha256": "1" * 64}}
        monotone(report(row), report(newer))

    def test_50_minute_success_is_not_accepted_under_old_policy(self):
        row = sample("R001", ["abyss"])
        evidence = {"status": "success", "score": 5, "seconds": 2100}
        with self.assertRaises(ValueError):
            accept(row, "abyss", evidence, {})
        evidence["time_budget_seconds"] = 3000
        accept(row, "abyss", evidence, {"peak_ram_observed_mib": 3})
        self.assertEqual(row["diagnostics"]["abyss"]["peak_ram_observed_mib"], 3)


if __name__ == "__main__":
    unittest.main()
