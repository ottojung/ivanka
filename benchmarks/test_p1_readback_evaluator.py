"""Immutable readback tests: no fabricated truth panels or silent missing arms."""
import json
from pathlib import Path
import tempfile
import unittest

from expanded.p1_full464_controller import sha256
from expanded.p1_readback_evaluator import (
    evaluate_readback,
    recompute_case,
)

RIVALS = ("iva", "abyss", "haploflow", "megahit", "spades", "velvet")


def panel(fraction):
    return {"truth_0": {
        "score": int(1000 * fraction), "length": 1000,
        "fraction": fraction, "truth_sha256": "b" * 64,
        "nominal_abundance": 1.0,
    }}


def arm(score, fraction=0.95, status="success"):
    panel_data = panel(fraction) if status == "success" else {}
    return {
        "status": status, "score": score, "seconds": 10,
        "sha256": "a" * 64, "per_truth": panel_data,
        "score_origin": "micall_final_max_abundant_truths_balanced_v2",
        "timing_origin": "micall_in_container_monotonic_v1",
    }


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "attempt"
        self.root.mkdir()
        self.frozen = self.base / "frozen.jsonl"
        self.gate = self.base / "gate.json"
        self.case_ids = ["clonal-s000", "clonal-s001"]

    def write_attempt(self, candidate_fraction=0.95, failed_rival=False):
        frozen_rows = []
        attempt_rows = []
        for case_id in self.case_ids:
            rivals = {name: arm(1000, 0.95) for name in RIVALS}
            if failed_rival:
                rivals["abyss"] = arm(0, status="failed")
            frozen_rows.append({"id": case_id, "family": "clonal",
                                "results": {"ivanka": arm(1000, 0.95), **rivals}})
            reused = {name: {**value, "reused_from": {
                "case_id": case_id, "results_sha256": "f" * 64,
                "image_sha256": value["sha256"]}}
                for name, value in rivals.items()}
            attempt_rows.append({"id": case_id, "family": "clonal",
                                 "results": {
                                     "ivanka": arm(int(1000 * candidate_fraction),
                                                   candidate_fraction),
                                     **reused}})
        self.frozen.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                       for row in frozen_rows))
        results = self.root / "results.jsonl"
        results.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                   for row in attempt_rows))
        (self.root / "attempt_summary.json").write_text(json.dumps({
            "result_sha256": sha256(results)}, sort_keys=True) + "\n")
        self.gate.write_text(json.dumps({
            "observed": {"real": 1, "synthetic": len(self.case_ids)},
            "errors": ["clonal-s000:ivanka_below_90pct_for_truth_0",
                       "R001:failed_or_unrun_assembler"],
        }, sort_keys=True) + "\n")
        frozen_hash = sha256(self.frozen)
        gate_hash = sha256(self.gate)
        # Rebind the frozen reuse proof to the actual pinned frozen digest.
        for path in (self.frozen, results):
            rows = [json.loads(line) for line in path.read_text().splitlines()
                    if line.strip()]
            if path == results:
                for row in rows:
                    for rival in row["results"].values():
                        if isinstance(rival, dict) and "reused_from" in rival:
                            rival["reused_from"]["results_sha256"] = frozen_hash
                path.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                        for row in rows))
        results_hash = sha256(results)
        (self.root / "attempt_summary.json").write_text(json.dumps({
            "result_sha256": results_hash}, sort_keys=True) + "\n")
        return frozen_hash, gate_hash

    def test_readback_recomputes_and_marks_full_seven_blocked(self):
        frozen_hash, gate_hash = self.write_attempt(
            candidate_fraction=0.80, failed_rival=True)
        report = evaluate_readback(
            self.root, frozen_path=self.frozen, gate_path=self.gate,
            expected_cases=len(self.case_ids), frozen_hash=frozen_hash,
            gate_hash=gate_hash)
        self.assertEqual(report["identity_errors"], [])
        self.assertEqual(report["attempt_results_sha256"],
                         sha256(self.root / "results.jsonl"))
        self.assertTrue(report["full_seven_blocked_reasons"])
        self.assertFalse(report["full_seven_complete"])
        self.assertEqual(report["attested_gate_deficits"]["per_truth_failures"],
                         {"clonal-s000": ["truth_0"]})
        first = report["recomputed_comparisons"][0]
        self.assertFalse(first["combined_pass"])
        self.assertEqual(first["available_rivals"],
                         sorted(set(RIVALS) - {"abyss"}))
        self.assertEqual(len(first["truths"]), 1)

    def test_mutated_attempt_is_rejected(self):
        frozen_hash, gate_hash = self.write_attempt()
        path = self.root / "results.jsonl"
        path.write_text(path.read_text() + "\n")
        with self.assertRaises(ValueError):
            evaluate_readback(
                self.root, frozen_path=self.frozen, gate_path=self.gate,
                expected_cases=len(self.case_ids), frozen_hash=frozen_hash,
                gate_hash=gate_hash)

    def test_no_truth_panel_is_fabricated_for_failed_rival(self):
        row = {"id": "x", "family": "clonal", "results": {
            "ivanka": arm(1000, 0.95),
            "iva": arm(1000, 0.95),
            "abyss": arm(0, status="failed"),
        }}
        result = recompute_case(row)
        self.assertIn("abyss", {name for name in ("abyss",)
                                if name not in result["available_rivals"]})
        self.assertEqual(result["available_rivals"], ["iva"])
        self.assertNotIn("abyss", {truth["truth"] for truth in result["truths"]})


if __name__ == "__main__":
    unittest.main()
