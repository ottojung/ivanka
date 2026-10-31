"""Regression tests for non-qualifying split-cohort audit."""
import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import composite198_diagnostic as audit


def record(sample, invocation, legacy=False):
    return dict(sample=sample, invocation=invocation, status="finished",
        failed=legacy, iva_baseline_reused=True, total_seconds=9,
        sample_time_limit_seconds=1800,
        iva=dict(image_id="a", exit_code=0, seconds=10, metrics={}),
        ivanka=dict(image_id="b", exit_code=0, seconds=8, metrics={}),
        provenance=dict(iva_image_id="a", fastq_sha256=["1"*64, "2"*64]),
        best_contig_acceptance=dict(
            method="best_final_max_contig_local_alignment_over_reference_panel",
            reference_panel_sha256=audit.PANEL_SHA256, reference_count=33,
            iva_score=100, ivanka_score=94 if legacy else 102,
            **{"pass": not legacy, "threshold": .95}))


class CompositeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.manifest = self.root / "manifest.tsv"
        self.names = [f"sample{i}" for i in range(198)]
        self.manifest.write_text("sample\n" + "\n".join(self.names) + "\n")
        self.rows = [record(s, "first" if i < 26 else "second", i in (12, 42))
                     for i, s in enumerate(self.names)]

    def run_audit(self):
        paths = []
        for name, rows in (("first", self.rows[:26]), ("second", self.rows[26:])):
            path = self.root / (name + ".jsonl")
            path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            paths.append(path)
        digest = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        with patch.object(audit, "MANIFEST_SHA256", digest):
            return audit.audit(paths, self.manifest)

    def test_198_valid_still_not_formal(self):
        r = self.run_audit()
        self.assertEqual((r["milestone198_valid_pairs"], r["time_psi"]["psi1"]), (198, 2))
        self.assertEqual((r["formal_qualification_pass"], len(r["legacy_95_flags_reinterpreted"])), (False, 2))

    def test_unexplained_failure_rejected(self):
        self.rows[12]["best_contig_acceptance"]["pass"] = True
        with self.assertRaisesRegex(ValueError, "Unexplained"): self.run_audit()

    def test_duplicate_sample_rejected(self):
        self.rows[1]["sample"] = "sample0"
        with self.assertRaisesRegex(ValueError, "frozen cohort"): self.run_audit()

    def test_mixed_image_rejected(self):
        self.rows[1]["ivanka"]["image_id"] = "c"
        with self.assertRaisesRegex(ValueError, "Mixed MiCall"): self.run_audit()

    def test_below_90_rejected(self):
        self.rows[1]["best_contig_acceptance"]["ivanka_score"] = 89
        self.assertEqual(self.run_audit()["milestone198_valid_pairs"], 197)
