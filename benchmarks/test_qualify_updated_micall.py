import hashlib
import tempfile
import unittest
from pathlib import Path

from qualify_updated_micall import verify, SAMPLE_COUNT


IVA_SHA = "a"*64
IVANKA_SHA = "b"*64


class UpdatedMiCallQualificationTests(unittest.TestCase):
    def _build(self, root):
        invocation = "one-authentic-physical-run"
        names = [f"sample{i:03d}" for i in range(SAMPLE_COUNT)]
        records = []
        for sample in names:
            arms = {}
            for arm, image, seconds, wall in (
                ("iva", IVA_SHA, 90, 100),
                ("ivanka", IVANKA_SHA, 80, 90),
            ):
                folder = root / invocation / sample / arm
                folder.mkdir(parents=True)
                conseq = folder / "conseq.csv"
                conseq.write_text("seed,consensus-percent-cutoff,sequence\nHCV,MAX,ACGT\n")
                digest = hashlib.sha256(conseq.read_bytes()).hexdigest()
                arms[arm] = {
                    "exit_code": 0, "image_id": image, "seconds": seconds,
                    "container_wall_seconds": wall,
                    "timing_origin": "micall_in_container_monotonic_v1",
                    "artifact_dir": str(folder),
                    "metrics": {"outputs": {"conseq.csv": {"sha256": digest}}},
                }
            records.append({
                "sample": sample, "status": "finished", "failed": False,
                "invocation": invocation, "provenance": {"original_fastq": "pinned"},
                "best_contig_acceptance": {
                    "iva_score": 100, "ivanka_score": 101,
                    "method": "best_final_max_contig_local_alignment_over_reference_panel",
                    "pass": True, "reference_count": 33,
                    "reference_panel_sha256":
                        "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8",
                }, **arms,
            })
        original_evidence = {r["sample"]: dict(r["provenance"]) for r in records}
        return names, records, original_evidence

    def test_all_real_powers_are_positive_when_every_sample_gains(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            names, records, original_evidence = self._build(root)
            report = verify(records, names, root, IVA_SHA, IVANKA_SHA, original_evidence)
            self.assertEqual(report["valid_pairs"], SAMPLE_COUNT)
            self.assertEqual(report["errors"], [])
            self.assertTrue(report["score_psi"]["positive_all_nonnegative"])
            self.assertTrue(report["time_psi"]["positive_all_nonnegative"])
            self.assertTrue(report["real_data_numeric_gate_pass"])
            self.assertFalse(report["biological_release_authorized"])

    def test_fails_closed_on_reused_arm_and_unequal_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            names, records, original_evidence = self._build(root)
            records[0]["iva_baseline_reused"] = True
            self.assertFalse(verify(records, names, root, IVA_SHA, IVANKA_SHA, original_evidence)[
                "real_data_numeric_gate_pass"])
            records[0]["iva_baseline_reused"] = False
            records[1]["best_contig_acceptance"]["ivanka_score"] = 89
            report = verify(records, names, root, IVA_SHA, IVANKA_SHA, original_evidence)
            self.assertFalse(report["real_data_numeric_gate_pass"])
            self.assertIn("alignment_below_90pct_IVA_floor", repr(report["errors"]))
            self.assertFalse(verify(records[:-1], names, root, IVA_SHA, IVANKA_SHA, original_evidence)[
                "real_data_numeric_gate_pass"])

    def test_rejects_forged_original_input_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            names, records, original_evidence = self._build(root)
            records[0]["provenance"]["fastq_sha256"] = ["forged"]
            report = verify(records, names, root, IVA_SHA, IVANKA_SHA,
                            original_evidence)
            self.assertFalse(report["real_data_numeric_gate_pass"])
            self.assertIn("original_fastq_provenance_mismatch", repr(report["errors"]))

    def test_rejects_forged_output_or_wall_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            names, records, original_evidence = self._build(root)
            records[0]["ivanka"]["container_wall_seconds"] = 1801
            report = verify(records, names, root, IVA_SHA, IVANKA_SHA, original_evidence)
            self.assertFalse(report["real_data_numeric_gate_pass"])
            records[0]["ivanka"]["container_wall_seconds"] = 90
            (Path(records[0]["ivanka"]["artifact_dir"]) / "conseq.csv").write_text(
                "seed,consensus-percent-cutoff,sequence\nHCV,MAX,FAKE\n")
            report = verify(records, names, root, IVA_SHA, IVANKA_SHA, original_evidence)
            self.assertIn("final_consensus_sha_mismatch", repr(report["errors"]))


if __name__ == "__main__":
    unittest.main()
