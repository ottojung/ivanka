"""Fail-closed tests for the P1 full-464 candidate controller."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from expanded.p1_full464_controller import (
    FLOOR,
    MEMORY_BYTES,
    PODMAN_TIMEOUT_SECONDS,
    assert_reference_blind,
    assemble_row,
    atomic_json,
    build_command,
    candidate_source_hashes,
    disk_admission,
    evaluate,
    load_committed,
    sha256,
    verify_case_hashes,
)


def arm(score, seconds, *, status="success", fraction=0.95):
    length = 1000
    raw = int(length * fraction)
    return {
        "status": status,
        "score": score,
        "seconds": seconds,
        "sha256": "a" * 64,
        "score_origin": "micall_final_max_abundant_truths_balanced_v2",
        "timing_origin": "micall_in_container_monotonic_v1",
        "per_truth": {"truth_0": {
            "score": raw, "length": length, "fraction": raw / length,
            "truth_sha256": "b" * 64, "nominal_abundance": 1.0,
        }},
    }


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_command_and_reference_blindness(self):
        case = self.base / "case"
        out = self.base / "out"
        timer = self.base / "timer.py"
        command = build_command(case, out, "c" * 64, timer, "container")
        self.assertIn("--memory=" + str(MEMORY_BYTES), command)
        self.assertIn(str(PODMAN_TIMEOUT_SECONDS), command)
        assert_reference_blind(command)
        leaked = command + ["-v", "/data/hidden-truth/haplotypes.fasta:/truth:ro"]
        with self.assertRaises(ValueError):
            assert_reference_blind(leaked)

    def test_case_hash_gate(self):
        case = self.base / "case"
        case.mkdir()
        target = case / "reads_R1"
        target.write_bytes(b"reads")
        expected = hashlib.sha256(b"reads").hexdigest()
        self.assertEqual(verify_case_hashes(case, {"reads_R1": expected}),
                         {"reads_R1": expected})
        with self.assertRaises(ValueError):
            verify_case_hashes(case, {"reads_R1": "0" * 64})

    def test_frozen_rival_reuse_is_marked(self):
        frozen = {"results": {"ivanka": arm(1000, 10),
                              "iva": arm(1000, 12),
                              "abyss": arm(900, 20, status="failed")}}
        row = assemble_row("case-0", arm(990, 11), frozen, "f" * 64,
                           {"reads/R1.fastq.gz": "1" * 64,
                            "reads/R2.fastq.gz": "2" * 64},
                           {"schema": "ivanka.mixed_viral_truth_validation.v4"},
                           "clonal", "c" * 40, "d" * 64)
        self.assertNotIn("reused_from", row["results"]["ivanka"])
        self.assertEqual(row["results"]["iva"]["reused_from"]["results_sha256"],
                         "f" * 64)
        self.assertEqual(row["results"]["abyss"]["reused_from"]["case_id"],
                         "case-0")
        self.assertFalse(row["provenance"]["original_arms_rerun"])

    def test_evaluate_reports_floor_failure_and_never_qualifies(self):
        rows = []
        for index in range(464):
            case = f"clonal-s{index:03d}"
            candidate = arm(5000 if index == 0 else 9500, 12)
            rivals = {name: arm(10000, 20)
                      for name in ("iva", "abyss", "spades", "velvet",
                                   "megahit", "haploflow")}
            rows.append({"id": case, "family": "clonal",
                         "results": {"ivanka": candidate, **rivals}})
        report = evaluate(rows)
        self.assertEqual(report["cases"], 464)
        self.assertFalse(report["pass"])
        self.assertEqual(report["qualification_claim"], "NONE")
        self.assertTrue(any("below_90pct_best_available_rival" in error
                            for error in report["errors"]))

    def test_resume_receipt_is_atomic_and_tamper_evident(self):
        folder = self.base / "case"
        folder.mkdir()
        row = {"results": {"ivanka": {"status": "success", "sha256": "d" * 64}}}
        case_path = folder / "case.json"
        atomic_json(case_path, row)
        evidence = folder / "terminal_evidence.json"
        atomic_json(evidence, {
            "schema": "ivanka.retention.terminal.v1", "sealed": True})
        (folder / "terminal_evidence.json.sha256").write_text(
            sha256(evidence) + "\n")
        atomic_json(folder / "receipt.json", {
            "image": "d" * 64,
            "case_hashes": {"reads/R1.fastq.gz": "1" * 64},
            "receipt_sha256": sha256(case_path),
        })
        hashes = {"reads/R1.fastq.gz": "1" * 64}
        self.assertEqual(load_committed(folder, hashes, "d" * 64), row)
        (folder / "receipt.json").write_text(json.dumps({
            "image": "d" * 64, "case_hashes": hashes,
            "receipt_sha256": "0" * 64,
        }))
        with self.assertRaises(ValueError):
            load_committed(folder, hashes, "d" * 64)

    def test_source_hash_seal_and_disk_admission(self):
        folder = self.base / "case"
        folder.mkdir()
        (folder / "podman.log").write_bytes(b"log")
        hashes = candidate_source_hashes(
            folder, {"reads/R1.fastq.gz": "1" * 64}, "d" * 64)
        self.assertEqual(hashes["image_id"], "d" * 64)
        self.assertEqual(hashes["reads/R1.fastq.gz"], "1" * 64)
        self.assertIn("podman.log", hashes)
        with self.assertRaises(RuntimeError):
            disk_admission(self.base, reserve_gib=10_000, allocation_gib=0)


if __name__ == "__main__":
    unittest.main()
