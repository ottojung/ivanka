import json
import tempfile
import unittest
from pathlib import Path

from report_updated_micall import render, main


def sample(name, iva_seconds=10, ivanka_seconds=8, iva_score=100, ivanka_score=110):
    return {
        "sample": name, "status": "finished", "failed": False,
        "invocation": "physical-1",
        "best_contig_acceptance": {
            "iva_score": iva_score, "ivanka_score": ivanka_score},
        "iva": {
            "exit_code": 0, "seconds": iva_seconds,
            "image_id": "same-micall-base/iva"},
        "ivanka": {
            "exit_code": 0, "seconds": ivanka_seconds,
            "image_id": "same-micall-base/ivanka"},
    }


class UpdatedMicallReportTests(unittest.TestCase):
    def test_partial_success_does_not_claim_qualification(self):
        report = render([sample("A")], "hash", expected=198)
        self.assertIn("NOT ATTESTED", report)
        self.assertIn("| Successful paired rows | 1 |", report)
        self.assertIn("Both require", report)

    def test_timeout_excluded_from_scored_psi_but_visible(self):
        failed = sample("B", ivanka_seconds=1000, ivanka_score=1000)
        failed["status"] = "sample_timeout"
        failed["failed"] = True
        failed["total_seconds"] = 1801
        report = render([sample("A"), failed], "hash")
        self.assertIn("| Failed or incomplete terminal rows | 1 |", report)
        self.assertIn("| B | sample_timeout |", report)
        self.assertIn("| Final MAX alignment, Ivanka−IVA | 1 / 0 / 0 |", report)
        self.assertNotIn("NUMERIC GATE PASSED", report)

    def test_runtime_no_go_certificate_is_conservative(self):
        records = [
            sample("A", iva_seconds=12, ivanka_seconds=10),
            sample("B", iva_seconds=10, ivanka_seconds=12),
            sample("C", iva_seconds=10, ivanka_seconds=13),
        ]
        report = render(records, "hash", expected=4)
        self.assertIn("Mathematical runtime no-go", report)
        self.assertIn("2 wins against", report)
        self.assertIn("2 observed losses", report)
        report = render(records, "hash", expected=5)
        self.assertNotIn("Mathematical runtime no-go", report)

    def test_strict_attestation_is_sha_bound(self):
        records = [sample("A"), sample("B")]
        strict = {
            "results_jsonl_sha256": "right-sha", "valid_pairs": 2,
            "samples_found": 2, "samples_expected": 2,
            "identical_micall_base_layers_verified": True,
            "original_fastq_sha256_verified": True, "errors": [],
            "real_data_numeric_gate_pass": True}
        attested = render(records, "right-sha", expected=2, strict=strict)
        self.assertIn("NUMERIC GATE PASSED", attested)
        unattested = render(records, "wrong-sha", expected=2, strict=strict)
        self.assertIn("NOT ATTESTED", unattested)
        strict["errors"] = ["authentic source FASTQ mismatch"]
        rejected = render(records, "right-sha", expected=2, strict=strict)
        self.assertIn("STRICT EVALUATOR REJECTED", rejected)
        self.assertIn("authentic source FASTQ mismatch", rejected)

    def test_optional_metrics_missing_and_signed_psi(self):
        diagnostics = {"samples_seen": 1, "successful_paired_samples": 1,
                       "metrics": {
                           "soft_clips_count": {
                               "paired_samples": 1,
                               "missing_samples": [],
                               "psi": {"psi0": 1.0, "psi1": 42.0,
                                       "psi2": 1764.0,
                                       "positive_all_nonnegative": True}},
                           "exact_uncovered_bases": {
                               "paired_samples": 0,
                               "missing_samples": ["A"],
                               "psi": None}}}
        report = render([sample("A")], "hash", diagnostics=diagnostics)
        self.assertIn("| soft_clips_count | 1 | 0 | 1 | 42 | 1,764 | True |", report)
        self.assertIn("| exact_uncovered_bases | 0 | 1 | n/a |", report)
        self.assertIn("never certify data provenance", report)

    def test_exclusive_output(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            inp = d / "results.jsonl"
            out = d / "human.md"
            inp.write_text(json.dumps(sample("A")) + "\n")
            main([str(inp), "--output", str(out)])
            self.assertIn("NOT ATTESTED", out.read_text())
            with self.assertRaises(FileExistsError):
                main([str(inp), "--output", str(out)])


if __name__ == "__main__":
    unittest.main()
