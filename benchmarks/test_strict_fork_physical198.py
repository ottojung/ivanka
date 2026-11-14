"""Synthetic public fixtures for fresh physical-198 qualification."""
from pathlib import Path
import json
import tempfile
import unittest

from benchmarks.expanded.real_matrix import PANEL
from benchmarks.expanded.strict_fork_physical198 import (
    check_arm, evaluate, read_records,
)

IMAGES = {"iva": "a" * 64, "ivanka": "b" * 64}
NAMES = {f"case-{i:03d}" for i in range(198)}


def arm(which, seconds):
    return {"image_id": IMAGES[which], "exit_code": 0,
            "metrics": {}, "timing_origin": "micall_in_container_monotonic_v1",
            "seconds": seconds, "container_wall_seconds": seconds + 1}


def result(sample):
    return {"sample": sample, "invocation": "once", "status": "finished",
            "failed": False, "total_seconds": 122.0,
            "iva_baseline_reused": False,
            "iva": arm("iva", 120.0), "ivanka": arm("ivanka", 100.0),
            "best_contig_acceptance": {
                "method": "best_final_max_contig_local_alignment_over_reference_panel",
                "reference_panel_sha256": PANEL, "reference_count": 33,
                "iva_score": 100.0, "ivanka_score": 101.0, "pass": True}}


class PhysicalGateTests(unittest.TestCase):
    def setUp(self):
        self.records = {name: result(name) for name in NAMES}

    def test_complete_fresh_positive_all_real_exponents(self):
        out = evaluate(self.records, IMAGES, NAMES)
        self.assertTrue(out["pass"])
        self.assertEqual(out["samples_valid"], 198)
        self.assertTrue(out["time_psi"]["positive_all_nonnegative"])

    def test_missing_and_failed_cases_never_pass(self):
        self.records.pop(next(iter(NAMES)))
        self.assertFalse(evaluate(self.records, IMAGES, NAMES)["pass"])
        self.records = {name: result(name) for name in NAMES}
        self.records[next(iter(NAMES))]["failed"] = True
        out = evaluate(self.records, IMAGES, NAMES)
        self.assertFalse(out["pass"])
        self.assertEqual(out["invalid_arms"], 1)

    def test_reject_old_cached_control(self):
        self.records[next(iter(NAMES))]["iva_baseline_reused"] = True
        self.assertFalse(evaluate(self.records, IMAGES, NAMES)["pass"])

    def test_reject_nonboolean_reused_control_and_overcap_sample(self):
        name = next(iter(NAMES))
        self.records[name]["iva_baseline_reused"] = "truthy"
        self.assertFalse(evaluate(self.records, IMAGES, NAMES)["pass"])
        self.records[name]["iva_baseline_reused"] = False
        self.records[name]["total_seconds"] = 1800.01
        out = evaluate(self.records, IMAGES, NAMES)
        self.assertFalse(out["pass"])
        self.assertEqual(out["invalid_arms"], 1)

    def test_reject_wrong_image_timer_and_panel(self):
        name = next(iter(NAMES))
        for arm_key, new in (
            ("image_id", "f" * 64),
            ("seconds", 1800.1),
            ("timing_origin", "outer_clock"),
        ):
            old = self.records[name]["ivanka"][arm_key]
            self.records[name]["ivanka"][arm_key] = new
            self.assertFalse(evaluate(self.records, IMAGES, NAMES)["pass"])
            self.records[name]["ivanka"][arm_key] = old
        self.records[name]["best_contig_acceptance"]["reference_panel_sha256"] = "x"
        self.assertFalse(evaluate(self.records, IMAGES, NAMES)["pass"])

    def test_alignment_floor_and_tail_runtime_both_binding(self):
        name = next(iter(NAMES))
        e = self.records[name]["best_contig_acceptance"]
        e.update({"ivanka_score": 89.0, "pass": False})
        self.assertFalse(evaluate(self.records, IMAGES, NAMES)["pass"])
        e.update({"ivanka_score": 101.0, "pass": True})
        self.records[name]["ivanka"]["seconds"] = 161.0
        self.records[name]["ivanka"]["container_wall_seconds"] = 162.0
        out = evaluate(self.records, IMAGES, NAMES)
        self.assertFalse(out["time_psi"]["positive_all_nonnegative"])
        self.assertFalse(out["pass"])

    def test_journal_requires_one_invocation_and_unique_pairs(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "results.jsonl"
            lines = []
            for name in sorted(NAMES):
                lines.append({"sample": name, "invocation": "once",
                              "status": "started"})
                lines.append(result(name))
            path.write_text("".join(json.dumps(x) + "\n" for x in lines))
            rows, digest = read_records(path, NAMES)
            self.assertEqual(len(rows), 198)
            self.assertEqual(len(digest), 64)
            lines[-1]["invocation"] = "other"
            path.write_text("".join(json.dumps(x) + "\n" for x in lines))
            with self.assertRaisesRegex(ValueError, "invocation"):
                read_records(path, NAMES)
            lines[-1] = result(sorted(NAMES)[-1])
            lines.append(lines[-1])
            path.write_text("".join(json.dumps(x) + "\n" for x in lines))
            with self.assertRaisesRegex(ValueError, "duplicate terminal"):
                read_records(path, NAMES)

    def test_fail_closed_arm_clock(self):
        broken = arm("iva", 3.0)
        broken["container_wall_seconds"] = 0.1
        with self.assertRaisesRegex(ValueError, "timer"):
            check_arm(broken, IMAGES["iva"])


if __name__ == "__main__":
    unittest.main()
