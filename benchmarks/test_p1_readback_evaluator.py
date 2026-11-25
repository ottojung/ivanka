"""Adversarial fixtures for the fail-closed P1 readback evaluator."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from expanded.p1_full464_controller import PINS, atomic_json, sha256
from expanded.p1_readback_evaluator import (
    evaluate_readback,
    main,
    recompute_case,
)

RIVALS = ("iva", "abyss", "haploflow", "megahit", "spades", "velvet")
IMAGE = "a" * 64
COMMIT = "1" * 40
TRUTH_DIGEST = "b" * 64


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def truth_item(fraction, *, truth=TRUTH_DIGEST, length=1000, abundance=1.0):
    raw = int(length * fraction)
    return {"score": raw, "length": length, "fraction": raw / length,
            "truth_sha256": truth, "nominal_abundance": abundance}


def arm(fraction, seconds=10, *, status="success", final_dominant=None):
    panel = ({"truth_0": truth_item(fraction)} if status == "success" else {})
    record = {"status": status, "score": int(10000 * fraction),
              "seconds": seconds, "sha256": "c" * 64,
              "score_origin": "micall_final_max_abundant_truths_balanced_v2",
              "timing_origin": "micall_in_container_monotonic_v1",
              "per_truth": panel}
    if final_dominant is not None:
        record["final_dominant"] = final_dominant
    return record


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "attempt"
        self.data = self.base / "data"
        self.root.mkdir()
        self.data.mkdir()
        self.case_ids = ("clonal-s000", "clonal-s001")

    def fixture(self, *, candidate_fraction=0.95, failed_rival=False,
                extra_truth=False):
        case_hashes = {}
        for case_id in self.case_ids:
            case_dir = self.data / case_id
            (case_dir / "reads").mkdir(parents=True, exist_ok=True)
            hashes = {}
            for name in ("reads/R1.fastq.gz", "reads/R2.fastq.gz",
                         "hidden-truth/haplotypes.fasta"):
                path = case_dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = (case_id + name).encode()
                path.write_bytes(payload)
                hashes[name] = digest_bytes(payload)
            case_hashes[case_id] = hashes
        cohort = {"schema": "ivanka.expanded.cohort.hxb2.v4",
                  "samples": len(self.case_ids),
                  "cases": [{"id": case_id, "sha256": case_hashes[case_id]}
                            for case_id in self.case_ids]}
        cohort_path = self.data / "cohort.json"
        atomic_json(cohort_path, cohort)
        cohort_hash = sha256(cohort_path)

        frozen_path = self.base / "frozen.jsonl"
        frozen_rows = []
        for case_id in self.case_ids:
            rivals = {name: arm(0.95) for name in RIVALS}
            if failed_rival:
                rivals["abyss"] = arm(0, status="failed")
            frozen_rows.append({"id": case_id, "family": "clonal",
                                "results": {"ivanka": arm(0.95), **rivals}})
        frozen_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                       for row in frozen_rows))
        frozen_hash = sha256(frozen_path)

        rows = []
        for case_id in self.case_ids:
            rivals = {}
            for name, value in frozen_rows[self.case_ids.index(case_id)][
                    "results"].items():
                if name == "ivanka":
                    continue
                rivals[name] = {**value, "reused_from": {
                    "case_id": case_id, "results_sha256": frozen_hash,
                    "image_sha256": value["sha256"]}}
            folder = self.root / case_id
            folder.mkdir(parents=True, exist_ok=True)
            consensus = folder / "conseq.csv"
            consensus.write_text("sample,contig\nS,ACGT\n")
            consensus_sha = sha256(consensus)
            candidate = arm(candidate_fraction, final_dominant={
                "source_output": "conseq.csv",
                "conseq_csv_sha256": consensus_sha})
            candidate["sha256"] = IMAGE
            if extra_truth:
                candidate["per_truth"]["truth_1"] = truth_item(
                    0.95, truth="d" * 64)
            row = {"id": case_id, "cohort": "synthetic", "family": "clonal",
                   "truth_validation": {"schema": "ivanka.mixed_viral_truth_validation.v4"},
                   "input_sha256": digest_bytes((
                       case_hashes[case_id]["reads/R1.fastq.gz"] +
                       case_hashes[case_id]["reads/R2.fastq.gz"]).encode()),
                   "results": {"ivanka": candidate, **rivals},
                   "provenance": {"candidate_image": IMAGE,
                                  "candidate_source_commit": COMMIT,
                                  "original_arms_rerun": False}}
            rows.append(row)
            atomic_json(folder / "case.json", row)
            evidence = folder / "terminal_evidence.json"
            atomic_json(evidence, {
                "schema": "ivanka.retention.terminal.v1", "sealed": True,
                "source_hashes": {**case_hashes[case_id],
                                  "image_id": IMAGE},
                "metrics": {"outputs": {
                    "conseq.csv": {"sha256": consensus_sha}}}})
            (folder / "terminal_evidence.json.sha256").write_text(
                sha256(evidence) + "\n")
            atomic_json(folder / "receipt.json", {
                "image": IMAGE, "case_hashes": case_hashes[case_id],
                "receipt_sha256": sha256(folder / "case.json")})
        results_path = self.root / "results.jsonl"
        results_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                        for row in rows))
        summary = {"qualified": False, "cases_attempted": len(rows),
                   "result_sha256": sha256(results_path)}
        atomic_json(self.root / "attempt_summary.json", summary)
        pins = dict(PINS)
        pins["cohort.json"] = cohort_hash
        pins["phase-synthetic464/results.jsonl"] = frozen_hash
        atomic_json(self.root / "run_manifest.json", {
            "pins": pins, "candidate_image": IMAGE,
            "candidate_source_commit": COMMIT})
        gate_path = self.base / "gate.json"
        atomic_json(gate_path, {
            "observed": {"real": 1, "synthetic": len(self.case_ids)},
            "errors": ["clonal-s000:ivanka_below_90pct_for_truth_0",
                       "clonal-s001:ivanka_below_90pct_best_competitor",
                       "clonal-s000:failed_or_unrun_assembler",
                       "R001:failed_or_unrun_assembler"]})
        return {"cohort_hash": cohort_hash, "frozen_hash": frozen_hash,
                "gate_hash": sha256(gate_path), "pins": pins,
                "frozen_path": frozen_path, "gate_path": gate_path}

    def run_evaluator(self, setup, **changes):
        kwargs = {"frozen_path": setup["frozen_path"],
                  "gate_path": setup["gate_path"],
                  "cohort_root": self.data,
                  "expected_cases": len(self.case_ids),
                  "frozen_hash": setup["frozen_hash"],
                  "gate_hash": setup["gate_hash"],
                  "cohort_hash": setup["cohort_hash"],
                  "pins": setup["pins"]}
        kwargs.update(changes)
        return evaluate_readback(self.root, **kwargs)

    def test_sealed_prefix_fixture_is_accepted_fail_closed(self):
        setup = self.fixture(candidate_fraction=0.80, failed_rival=True)
        report = self.run_evaluator(setup)
        self.assertEqual(report["receipt_integrity"]["cases"], 2)
        self.assertTrue(report["receipt_integrity"]["all_verified"])
        self.assertEqual(report["identity_errors"], [])
        self.assertEqual(report["qualification_claim"], "NONE")
        self.assertFalse(report["pass"])
        self.assertFalse(report["full_seven_complete"])
        self.assertEqual(
            report["full_seven_blocked_counts"]["physical_failed_arms"], 1)
        self.assertGreaterEqual(
            report["full_seven_blocked_counts"]["cases_with_failed_rivals"], 1)
        self.assertEqual(
            report["attested_gate_deficits"]["per_truth_failures"],
            {"clonal-s000": ["truth_0"]})
        case = report["recomputed_comparisons"][0]
        self.assertFalse(case["combined_pass"])
        self.assertNotIn("abyss", case["available_rivals"])

    def test_missing_summary_or_manifest_is_rejected(self):
        setup = self.fixture()
        (self.root / "attempt_summary.json").unlink()
        with self.assertRaisesRegex(ValueError, "summary is missing"):
            self.run_evaluator(setup)
        self.fixture()
        atomic_json(self.root / "run_manifest.json", {"pins": {}})
        with self.assertRaisesRegex(ValueError, "source pins differ"):
            self.run_evaluator(setup)

    def test_tampered_case_receipt_is_rejected(self):
        setup = self.fixture()
        path = self.root / "clonal-s000" / "case.json"
        row = json.loads(path.read_text())
        row["results"]["ivanka"]["score"] = 1
        path.write_text(json.dumps(row, sort_keys=True) + "\n")
        with self.assertRaisesRegex(ValueError, "case receipt digest differs"):
            self.run_evaluator(setup)

    def test_output_inside_attempt_root_is_rejected(self):
        setup = self.fixture()
        output = self.root / "report.json"
        argv = ["--root", str(self.root), "--output", str(output),
                "--frozen-results", str(setup["frozen_path"]),
                "--gate-json", str(setup["gate_path"]), "--data", str(self.data)]
        with self.assertRaisesRegex(ValueError, "outside the attempt root"):
            main(argv)

    def test_extra_or_changed_truth_entry_is_rejected(self):
        setup = self.fixture(extra_truth=True)
        report = self.run_evaluator(setup)
        self.assertTrue(any("truth_keys_missing_or_extra" in error
                            for case in report["recomputed_comparisons"]
                            for error in case["errors"]))
        setup = self.fixture()
        row = {"id": "x", "family": "clonal", "results": {
            "ivanka": arm(0.95), **{name: arm(0.95) for name in RIVALS}}}
        row["results"]["ivanka"]["per_truth"]["truth_0"][
            "truth_sha256"] = "e" * 64
        result = recompute_case(
            row, {"truth_0": (TRUTH_DIGEST, 1000, 1.0)})
        self.assertTrue(any("truth_identity_mismatch" in error
                            for error in result["errors"]))

    def test_nonfinite_and_nonpositive_numeric_evidence_is_rejected(self):
        setup = self.fixture()
        path = self.root / "results.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()
                if line.strip()]
        rows[0]["results"]["ivanka"]["score"] = "950"
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                for row in rows))
        with self.assertRaises(ValueError):
            self.run_evaluator(setup)
        self.fixture()
        row = {"id": "x", "family": "clonal", "results": {
            "ivanka": arm(0.95), **{name: arm(0.95) for name in RIVALS}}}
        row["results"]["ivanka"]["seconds"] = -1
        result = recompute_case(
            row, {"truth_0": (TRUTH_DIGEST, 1000, 1.0)})
        self.assertTrue(any("invalid_seconds" in error
                            for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
