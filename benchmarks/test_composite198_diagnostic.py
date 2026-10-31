"""Tests for the deliberately non-qualifying composite 198 diagnostic."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import composite198_diagnostic as diag


def make_record(name, invocation, legacy=False):
    return {
        "sample": name, "status": "finished", "invocation": invocation,
        "failed": legacy, "iva_baseline_reused": True,
        "sample_time_limit_seconds": 1800, "total_seconds": 9,
        "iva": {"image_id": "a", "exit_code": 0, "seconds": 10, "metrics": {}},
        "ivanka": {"image_id": "b", "exit_code": 0, "seconds": 8, "metrics": {}},
        "best_contig_acceptance": {
            "method": "best_final_max_contig_local_alignment_over_reference_panel",
            "reference_panel_sha256": diag.PANEL_SHA256, "reference_count": 33,
            "iva_score": 100, "ivanka_score": 94 if legacy else 102,
            "pass": not legacy, "threshold": .95},
        "provenance": {"iva_image_id": "a", "fastq_sha256": ["1"*64, "2"*64],
                       "micall_project_code": "V3LOOP"},
    }


class CompositeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "manifest.tsv"
        self.names = [f"sample{i}" for i in range(198)]
        self.manifest.write_text("sample\n" + "\n".join(self.names) + "\n")
        self.manifest_hash = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.rows = [make_record(s, "first" if i < 26 else "second",
                                 legacy=i in (12, 42))
                     for i, s in enumerate(self.names)]

    def audit(self):
        paths = []
        for name, rows in (("first", self.rows[:26]), ("second", self.rows[26:])):
            p = self.root / (name + ".jsonl")
            p.write_text("".join(json.dumps(row) + "\n" for row in rows))
            paths.append(p)
        with patch.object(diag, "MANIFEST_SHA256", self.manifest_hash):
            return diag.audit(paths, self.manifest)

    def test_complete_but_not_formal(self):
        report = self.audit()
        self.assertEqual(report["strict_score_runtime_valid_pairs"], 198)
        self.assertEqual(report["runtime_psi"]["psi1"], 2)
        self.assertFalse(report["formal_qualification_pass"])
        self.assertEqual(len(report["legacy_95_percent_flags_reinterpreted"]), 2)

    def test_unexplained_failure_cannot_be_reinterpreted(self):
        self.rows[12]["best_contig_acceptance"]["pass"] = True
        report = self.audit()
        self.assertEqual(report["errors"]["sample12"], "unexplained_failure")
        self.assertIsNone(report["score_psi"])

    def test_duplicate_sample_rejected(self):
        self.rows[1]["sample"] = "sample0"
        with self.assertRaisesRegex(ValueError, "exact frozen cohort"):
            self.audit()

    def test_mixed_image_rejected(self):
        self.rows[1]["ivanka"]["image_id"] = "different"
        with self.assertRaisesRegex(ValueError, "Mixed MiCall"):
            self.audit()

    def test_manifest_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, "manifest SHA256 mismatch"):
            diag.audit([], self.manifest)

    def test_low_alignment_rejected(self):
        self.rows[1]["best_contig_acceptance"]["ivanka_score"] = 89
        report = self.audit()
        self.assertEqual(report["errors"]["sample1"], "below_strict_90_percent_floor")


if __name__ == "__main__":
    unittest.main()
