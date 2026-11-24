"""Neutral ingestion of immutable PX cohort receipts into public data."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from assembler_bench.px_cohort_ingest import ingest
from assembler_bench.site_build import SITE

ROOT = Path(__file__).resolve().parents[1]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PxCohortIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("receipts", "results", "diagnostics", "samples"):
            (self.root / folder).mkdir()
        self.real = self.root / "source"
        self.real.mkdir()
        (self.real / "manifest.tsv").write_text(
            "sample\tother\n" + "".join("S%03d\t1\n" % i for i in range(1, 5)))
        sample = self.real / "samples" / "S003"
        sample.mkdir(parents=True)
        self.mates = {}
        for mate in ("R1", "R2"):
            path = sample / ("S003_L001_" + mate + "_001.fastq.gz")
            path.write_bytes(("read" + mate).encode())
            self.mates[mate] = _sha(path)
        self.name = "skesa-physical-PX-R003"
        self.receipt = {
            "schema": "ivanka.px.case.receipt.v1", "tool_id": "skesa",
            "alias": "PX-R003", "cohort": "physical", "terminal": True,
            "outcome": "success", "failure_reason": None,
            "seconds": 66.9, "peak_rss_bytes": 81195008,
            "input_sha256": self.mates, "output_sha256": "a" * 64,
            "runner_receipt_sha256": "b" * 64,
            "source_commit": "1" * 40, "adapter_commit": "2" * 40,
            "image_sha256": "c" * 64,
        }
        self.result = {
            "schema": "ivanka.exploratory.per-sample.v1", "tool_id": "skesa",
            "cohort": "physical", "scorer_source_sha256": "d" * 64,
            "samples": [{"alias": "PX-R003", "outcome": "success",
                         "score": 188.0, "peak_ram_observed_mib": 77.5,
                         "method": "best_final_max_contig_local_alignment_over_reference_panel",
                         "reference_panel_sha256":
                             "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"}],
        }
        self.resource = {"schema": "ivanka.px.arm-resource.v1",
                         "tool_id": "skesa", "alias": "PX-R003",
                         "peak_ram_observed_mib": 77.5,
                         "peak_rss_bytes": 81195008, "outcome": "success"}
        self.diagnostics = {
            "schema": "ivanka.px.diagnostics.v3", "tool_id": "skesa",
            "alias": "PX-R003", "output_sha256": "a" * 64,
            "runner_receipt_sha256": "b" * 64,
            "metrics": {
                "canonical_micall": {"status": "extracted",
                                     "values": {"average_read_depth": 12.5,
                                                "soft_clips_count": 3}},
                "exact_coverage": {"status": "unavailable",
                                   "unavailable_reason": "module unavailable"}},
        }
        self._write_all()
        self.evidence = json.loads(
            (SITE / "data/assembler-evidence.json").read_text())
        item = next(item for item in self.evidence["assemblers"]
                    if item["id"] == "skesa")
        item["source_commit"] = "1" * 40
        item["adapter_commit"] = "2" * 40
        item["image_sha256"] = "c" * 64

    def _write_all(self):
        path = self.root / "receipts" / (self.name + ".json")
        path.write_text(json.dumps(self.receipt))
        (self.root / "receipts" / "index.json").write_text(json.dumps({
            "schema": "ivanka.px.case.receipt-index.v1",
            "entries": {self.name: _sha(path)}}))
        (self.root / "results" / (self.name + "-results.json")).write_text(
            json.dumps(self.result))
        (self.root / "results" / (self.name + "-resource.json")).write_text(
            json.dumps(self.resource))
        (self.root / "diagnostics" / (self.name + ".json")).write_text(
            json.dumps(self.diagnostics))

    def test_genuine_receipt_joins_score_diagnostics_and_progress(self):
        report = json.loads((SITE / "data/runs.json").read_text())
        evidence, merged, added, joined = ingest(
            report, self.evidence, self.root, self.real)
        self.assertEqual(added, [("skesa", "real", "R003")])
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R003")
        self.assertEqual(sample["score"]["skesa"], 188.0)
        self.assertIsNone(sample["seconds"]["skesa"])
        self.assertEqual(sample["diagnostics"]["skesa"][
            "nuc_soft_clips_count"], 3)
        proof = sample["measurement_evidence"]["skesa"]
        self.assertEqual(proof["peak_ram_observed_mib"], 77.5)
        self.assertEqual(proof["input_sha256"], self.mates)
        self.assertGreaterEqual(real["tool_progress"]["skesa"]["finished"], 2)

    def test_tampered_indexed_receipt_or_source_pair_is_rejected(self):
        report = json.loads((SITE / "data/runs.json").read_text())
        # The index binds the receipt bytes; editing a receipt breaks the digest.
        self.receipt["input_sha256"]["R1"] = "e" * 64
        (self.root / "receipts" / (self.name + ".json")).write_text(
            json.dumps(self.receipt))
        with self.assertRaisesRegex(ValueError, "differs from index"):
            ingest(report, self.evidence, self.root, self.real)
        # Restoring the receipt still rejects a pair that is not the original
        # source FASTQ bytes for the canonical alias.
        self.receipt["input_sha256"]["R1"] = self.mates["R1"]
        self._write_all()
        pair = self.real / "samples" / "S003" / "S003_L001_R1_001.fastq.gz"
        pair.write_bytes(b"tampered-read")
        with self.assertRaisesRegex(ValueError, "original source pair"):
            ingest(report, self.evidence, self.root, self.real)

    def test_exact_coverage_unavailable_is_never_fabricated(self):
        report = json.loads((SITE / "data/runs.json").read_text())
        _, merged, _, _ = ingest(report, self.evidence, self.root, self.real)
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R003")
        self.assertNotIn("skesa", sample.get("exact_profiles", {}))
        proof = sample["measurement_evidence"]["skesa"]["exact_coverage"]
        self.assertEqual(proof["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
