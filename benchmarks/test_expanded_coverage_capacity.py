"""Scientific capacity bounds do not fabricate MiCall consensus output."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from expanded.coverage_capacity import audit, one_case, threshold


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        source = self.base / "micall/core"
        source.mkdir(parents=True)
        (source / "aln2counts.py").write_text(
            "CONSENSUS_MIN_COVERAGE = 100\n")

    def sample(self, name, pairs):
        folder = self.base / "cases" / name
        (folder / "hidden-truth").mkdir(parents=True)
        truth = folder / "hidden-truth/haplotypes.fasta"
        truth.write_text(">dominant\n" + "ACGT" * 2400 + "\n")
        inputs = {"reads/R1.fastq.gz": b"fake-r1-gzip-for-digest",
                  "reads/R2.fastq.gz": b"fake-r2-gzip-for-digest"}
        for name, contents in inputs.items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
        record = {"family": "low_depth", "pairs": pairs,
                  "read_length": 150, "nominal_fractions": [1.0],
                  "hidden_truth_file": "hidden-truth/haplotypes.fasta",
                  "sha256": {"hidden-truth/haplotypes.fasta":
                             hashlib.sha256(truth.read_bytes()).hexdigest(),
                             **{name: hashlib.sha256(raw).hexdigest()
                                for name, raw in inputs.items()}}}
        (folder / "manifest.json").write_text(json.dumps(record))
        return folder

    def test_below_global_depth_floor_does_not_claim_zero_consensus(self):
        root = self.sample("low_depth-s000", 2500)
        result = one_case(root, 100)
        self.assertAlmostEqual(result["all_reads_mean_depth_ceiling"], 78.125)
        self.assertTrue(result["below_global_depth_floor"])
        self.assertEqual(len(result["read_sha256"]), 2)
        self.assertNotIn("consensus_success", result)
        self.assertNotIn("score", result)

    def test_above_floor_is_not_claimed_qualifying(self):
        self.sample("higher-depth", 10_000)
        result = audit(self.base / "cases", self.base)
        self.assertEqual(result["case_count"], 1)
        self.assertEqual(result["qualification"], "NOT_EVALUATED")
        self.assertEqual(result["families"]["low_depth"]["below_floor"], 0)
        self.assertEqual(result["miCall_consensus_min_coverage"], 100)

    def test_modified_read_inputs_are_rejected(self):
        root = self.sample("sample", 2500)
        (root / "reads/R2.fastq.gz").write_bytes(b"mutated")
        with self.assertRaisesRegex(ValueError, "reads digest mismatch"):
            one_case(root, 100)

    def test_source_and_truth_digest_tampering_is_rejected(self):
        self.sample("sample", 2500)
        path = self.base / "cases/sample/hidden-truth/haplotypes.fasta"
        path.write_text(">altered\nATG\n")
        with self.assertRaisesRegex(ValueError, "digest"):
            audit(self.base / "cases", self.base)
        source = self.base / "micall/core/aln2counts.py"
        source.write_text("CONSENSUS_MIN_COVERAGE = x\n")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            threshold(self.base)


if __name__ == "__main__":
    unittest.main()
