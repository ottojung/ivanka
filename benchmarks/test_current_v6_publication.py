"""New source-attested 464-case publication must reject fake viral recovery."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from assembler_bench.current_inputs_v6 import verified_arm
from assembler_bench.current_validation_v2 import check_sample
from assembler_bench.current_inputs import sample
from expanded.adapters import ASSEMBLERS
from expanded.micall_dominant import MULTITRUTH_SCORE_ORIGIN
from expanded.micall_synthetic_constants import TIMING_ORIGIN


class CurrentMultiTruthTests(unittest.TestCase):
    def test_accepts_only_matching_per_truth_evidence(self):
        image = "a"*64
        identities = {"truth_0": (100, "b"*64, 0.85),
                      "truth_1": (50, "c"*64, 0.15)}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final = root / "conseq.csv"
            final.write_text("real final MiCall output\n")
            record = {
                "status": "success",
                "score_origin": MULTITRUTH_SCORE_ORIGIN,
                "timing_origin": TIMING_ORIGIN,
                "sha256": image, "exit_code": 0,
                "seconds": 12., "score": 8000.,
                "argv": ["podman", "run", image, "--all_projects"],
                "final_dominant": {
                    "source_output": "conseq.csv",
                    "conseq_csv_sha256": hashlib.sha256(
                        final.read_bytes()).hexdigest()},
                "per_truth": {
                    "truth_0": {"score": 80, "length": 100,
                                "fraction": .8, "truth_sha256": "b"*64,
                                "nominal_abundance": .85},
                    "truth_1": {"score": 40, "length": 50,
                                "fraction": .8, "truth_sha256": "c"*64,
                                "nominal_abundance": .15}}}
            evidence = root / "execution.json"
            evidence.write_text(json.dumps(record))
            self.assertEqual(verified_arm(root,"iva",image,identities),record)
            record["per_truth"]["truth_1"]["truth_sha256"] = "f"*64
            evidence.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,"required-truth"):
                verified_arm(root,"iva",image,identities)
            record["per_truth"]["truth_1"]["truth_sha256"] = "c"*64
            record["score"] = 10000.
            evidence.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,"multi-truth"):
                verified_arm(root,"iva",image,identities)

    def test_public_row_cannot_hide_per_truth_recovery(self):
        images = {tool: ("%x"%(i+1))*64 for i,tool in enumerate(ASSEMBLERS)}
        row = sample("H001",images,"hcv_hiv_15pct")
        row["score"]["iva"] = 8000.
        row["seconds"]["iva"] = 12.
        row["truth_recovery"] = {"iva":{"truth_0":.8,"truth_1":.8}}
        row["truth_reference"] = {
            "truth_0": {"length": 100,"sequence_sha256": "b"*64,
                        "nominal_abundance": .85},
            "truth_1": {"length": 50,"sequence_sha256": "c"*64,
                        "nominal_abundance": .15}}
        run = {"cohort":"synthetic", "expected_sample_count":464,
               "tools":list(ASSEMBLERS)}
        check_sample(row,run)
        row["truth_recovery"]["iva"].pop("truth_1")
        with self.assertRaisesRegex(ValueError, "per-abundant-truth"):
            check_sample(row,run)


if __name__ == "__main__":
    unittest.main()
