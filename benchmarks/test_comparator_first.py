"""Hermetic comparator-only attestation and immutable restart semantics."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benchmarks.expanded.comparator_first import (
    TOOLS, history, preserve_orphan, prune, verify_record,
)
from benchmarks.expanded.micall_checkpoint import identity
from benchmarks.expanded.micall_dominant import SCORE_ORIGIN
from benchmarks.expanded.micall_synthetic_constants import TIMING_ORIGIN


class ComparatorFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case = "complex_mixture-s011"
        self.manifest = {"family": "complex_mixture",
                         "sha256": {"reads/R1.fastq.gz": "mate1",
                                    "reads/R2.fastq.gz": "mate2"}}
        self.truth = {"schema": "frozen", "valid": True}
        self.fields = identity(self.case, self.manifest, self.truth)
        self.images = {name: str(index + 1).zfill(64)
                       for index, name in enumerate(TOOLS)}
        (self.root / "run_manifest.json").write_text(json.dumps(
            {"truth_validation": self.truth}))

    def record(self, name="iva", success=True):
        arm = self.root / self.case / name
        arm.mkdir(parents=True, exist_ok=True)
        output = arm / "conseq.csv"
        output.write_text("region,sequence\n1,ACTG\n")
        result = {
            "status": "success" if success else "failed",
            "sha256": self.images[name],
            "score_origin": SCORE_ORIGIN,
            "timing_origin": TIMING_ORIGIN,
            "score": 4.0 if success else 0.0,
            "seconds": 1.4 if success else None,
            "exit_code": 0 if success else 1,
            "final_dominant": {
                "source_output": "conseq.csv",
                "conseq_csv_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            },
        }
        (arm / "execution.json").write_text(json.dumps(result))
        record = {**self.fields, "assembler": name, "result": result}
        with (self.root / "results.jsonl").open("a") as journal:
            journal.write(json.dumps(record) + "\n")
        return record

    def replay(self):
        return history(self.root, [(self.case, self.root / self.case,
                                    self.manifest)], self.images)

    def test_six_no_ivanka_contenders_are_explicit(self):
        self.assertEqual(set(TOOLS),
                         {"iva", "haploflow", "megahit", "abyss", "spades", "velvet"})
        self.assertNotIn("ivanka", TOOLS)

    def test_success_and_failed_arms_are_both_authentic_terminal_records(self):
        self.record("iva", True)
        self.record("abyss", False)
        observed = self.replay()
        self.assertEqual(set(observed), {(self.case, "iva"), (self.case, "abyss")})
        self.assertEqual(observed[(self.case, "abyss")]["result"]["status"], "failed")

    def test_replay_rejects_truncated_journal_and_double_execution(self):
        self.record()
        with (self.root / "results.jsonl").open("a") as journal:
            journal.write("{")
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.replay()
        path = self.root / "results.jsonl"
        original = path.read_text().splitlines()[0]
        path.write_text(original + "\n" + original + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.replay()

    def test_replay_refuses_mutation_of_input_or_post_assembly_truth(self):
        self.record()
        path = self.root / "results.jsonl"
        row = json.loads(path.read_text())
        row["input_sha256"] = "altered"
        path.write_text(json.dumps(row)+"\n")
        with self.assertRaisesRegex(ValueError, "input/independent truth"):
            self.replay()

    def test_cannot_relabel_failed_arm_as_success(self):
        self.record("iva", False)
        path = self.root / "results.jsonl"
        row = json.loads(path.read_text())
        row["result"]["status"] = "success"
        path.write_text(json.dumps(row)+"\n")
        with self.assertRaisesRegex(ValueError, "cached execution"):
            self.replay()

    def test_replay_rejects_tampered_final_max_output(self):
        self.record()
        (self.root / self.case / "iva" / "conseq.csv").write_text("wrong")
        with self.assertRaisesRegex(ValueError, "final MiCall MAX evidence"):
            self.replay()

    def test_unknown_assembler_cannot_become_comparator(self):
        self.record()
        path = self.root / "results.jsonl"
        row = json.loads(path.read_text())
        row["assembler"] = "ivanka"
        path.write_text(json.dumps(row)+"\n")
        with self.assertRaisesRegex(ValueError, "possibly Ivanka"):
            self.replay()

    def test_orphan_attempt_is_preserved_for_resume(self):
        partial = self.root / self.case / "iva"
        partial.mkdir(parents=True)
        (partial / "stdout.log").write_text("incomplete")
        preserve_orphan(self.root, self.case, "iva")
        self.assertFalse(partial.exists())
        files = list((self.root / "_interrupted").glob("*"))
        self.assertEqual(len(files), 1)
        self.assertEqual((files[0] / "stdout.log").read_text(), "incomplete")

    def test_verified_success_scratch_is_removed_but_failure_stays(self):
        good = self.record("iva", True)
        bad = self.record("spades", False)
        for name in ("iva", "spades"):
            scratch = self.root / self.case / name / "scratch"
            scratch.mkdir()
            (scratch / "large.tmp").write_text("scratch")
        prune(good, self.root)
        prune(bad, self.root)
        self.assertFalse((self.root / self.case / "iva" / "scratch").exists())
        self.assertTrue((self.root / self.case / "spades" / "scratch").exists())


if __name__ == "__main__":
    unittest.main()
