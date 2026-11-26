"""Prospective synthetic PX admission bound to source-only frozen fixtures."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_posthoc
from assembler_bench.px_cohort_ingest import _case
from assembler_bench.public_view import SYNTHETIC_SCORE

ALIAS = "PX-H192"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _frozen_record(alias):
    cases = json.loads(Path(sched.SYNTHETIC_COHORT).read_bytes())["cases"]
    aliases = sched.canonical_aliases((case["id"] for case in cases),
                                      "synthetic")
    source = next(item for item, name in aliases.items() if name == alias)
    return next(case for case in cases if case["id"] == source)


class SyntheticProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("receipts", "results", "diagnostics"):
            (self.root / folder).mkdir()
        self.record = _frozen_record(ALIAS)
        self.truth = self.record["sha256"]["hidden-truth/haplotypes.fasta"]
        self.inputs = {mate: self.record["sha256"]["reads/" + mate + ".fastq.gz"]
                       for mate in ("R1", "R2")}
        self.output_sha = _sha(b"region,MAX\nHIV1,ACGT\n")
        self.runner_sha = _sha(b'{"runner":"source-fixture"}')
        self.name = "skesa-synthetic-" + ALIAS
        self.receipt = {
            "schema": "ivanka.px.case.receipt.v1", "tool_id": "skesa",
            "alias": ALIAS, "cohort": "synthetic", "terminal": True,
            "qualifying": False, "outcome": "success", "failure_reason": None,
            "seconds": 90.16703, "peak_rss_bytes": None,
            "input_sha256": dict(self.inputs), "output_sha256": self.output_sha,
            "runner_receipt_sha256": self.runner_sha,
            "source_commit": "1" * 40, "adapter_commit": "2" * 40,
            "image_sha256": "c" * 64,
        }
        self.result = {
            "schema": "ivanka.exploratory.per-sample.v1", "tool_id": "skesa",
            "cohort": "synthetic", "expected_sample_count": 464,
            "source_commit": "1" * 40, "adapter_commit": "2" * 40,
            "image_sha256": "c" * 64,
            "scorer_source_sha256": px_posthoc.source_sha256(),
            "samples": [{"alias": ALIAS, "outcome": "success", "score": 4863.0,
                         "method": SYNTHETIC_SCORE, "truth_sha256": self.truth,
                         "output_sha256": self.output_sha,
                         "runner_receipt_sha256": self.runner_sha,
                         "synthetic_abundant_truth_count": 2}],
        }
        self.resource = {
            "schema": "ivanka.px.arm-resource.v1", "tool_id": "skesa",
            "alias": ALIAS, "cohort": "synthetic", "outcome": "success",
            "attempt": 1, "peak_rss_bytes": None,
            "peak_ram_observed_mib": None,
        }
        self.diagnostics = {
            "schema": "ivanka.px.diagnostics.v3", "tool_id": "skesa",
            "alias": ALIAS, "output_sha256": self.output_sha,
            "runner_receipt_sha256": self.runner_sha,
            "metrics": {
                "canonical_micall": {"status": "extracted",
                                     "values": {"average_read_depth": 12.5}},
                "exact_coverage": {"status": "unavailable",
                                   "unavailable_reason": "module unavailable"},
            },
        }
        self.assembler = {"id": "skesa", "source_commit": "1" * 40,
                          "adapter_commit": "2" * 40, "image_sha256": "c" * 64}
        self._write_all()

    def _write_all(self):
        path = self.root / "receipts" / (self.name + ".json")
        path.write_text(json.dumps(self.receipt, sort_keys=True))
        (self.root / "receipts" / "index.json").write_text(json.dumps({
            "schema": "ivanka.px.case.receipt-index.v1",
            "entries": {self.name: _sha(path.read_bytes())}}, sort_keys=True))
        (self.root / "results" / (self.name + "-results.json")).write_text(
            json.dumps(self.result, sort_keys=True))
        (self.root / "results" / (self.name + "-resource.json")).write_text(
            json.dumps(self.resource, sort_keys=True))
        (self.root / "diagnostics" / (self.name + ".json")).write_text(
            json.dumps(self.diagnostics, sort_keys=True))

    def _case(self):
        return _case(self.root, self.name, self.receipt, self.assembler,
                     self.root / "source")

    def test_empty_output_still_binds_truth_and_receipt(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({
            "sha256": self.record["sha256"],
            "hidden_truth_file": "hidden-truth/haplotypes.fasta",
            "nominal_fractions": [1.0], "score_model_revision": 2}))
        with patch.object(px_posthoc.PxScorer, "_synthetic_inputs",
                          return_value=(manifest, self.root / "truth.fasta")
                          ) as inputs:
            row = px_posthoc.PxScorer()._score_synthetic(
                ALIAS, [], case=None, receipt=self.receipt,
                output_sha256=self.output_sha)
        self.assertEqual(inputs.call_count, 1)
        self.assertEqual(row["score"], 0.0)
        self.assertEqual(row["method"], SYNTHETIC_SCORE)
        self.assertEqual(row["truth_sha256"], self.truth)
        self.assertEqual(row["output_sha256"], self.output_sha)
        self.assertEqual(row["runner_receipt_sha256"], self.runner_sha)
        self.assertEqual(row["synthetic_abundant_truth_count"], 0)

    def test_zero_contig_score_with_exact_truth_is_admitted(self):
        self.result["samples"][0].update(
            score=0.0, truth_sha256=self.truth,
            output_sha256=self.output_sha,
            runner_receipt_sha256=self.runner_sha,
            synthetic_abundant_truth_count=0)
        self._write_all()
        fields = self._case()
        self.assertEqual(fields["score"], 0.0)
        self.assertEqual(fields["cohort"], "synthetic")
        self.assertEqual(fields["canonical_alias"], "H192")

    def test_absent_or_wrong_truth_hash_fails_closed(self):
        row = self.result["samples"][0]
        row.pop("truth_sha256")
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "truth hash differs from the frozen cohort"):
            self._case()
        row["truth_sha256"] = "f" * 64
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "truth hash differs from the frozen cohort"):
            self._case()

    def test_swapped_output_and_runner_hash_fails_closed(self):
        row = self.result["samples"][0]
        row["output_sha256"] = "e" * 64
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "output_sha256 differs from receipt"):
            self._case()
        row["output_sha256"] = self.output_sha
        row["runner_receipt_sha256"] = "d" * 64
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "runner_receipt_sha256 differs from receipt"):
            self._case()

    def test_wrong_result_provenance_fails_closed(self):
        for key, wrong in (("source_commit", "a" * 40),
                           ("adapter_commit", "b" * 40),
                           ("image_sha256", "e" * 64)):
            with self.subTest(key=key):
                self.result[key] = wrong
                self._write_all()
                with self.assertRaisesRegex(
                        ValueError, "result provenance differs from receipt"):
                    self._case()
                self.result[key] = self.receipt[key]

    def test_non_singleton_result_fails_closed(self):
        self.result["samples"].append(dict(self.result["samples"][0]))
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "exactly one receipt-bound sample"):
            self._case()

    def test_empty_scorer_rejects_unbound_receipt(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"sha256": self.record["sha256"],
                                        "hidden_truth_file":
                                            "hidden-truth/haplotypes.fasta"}))
        with patch.object(px_posthoc.PxScorer, "_synthetic_inputs",
                          return_value=(manifest, self.root / "truth.fasta")):
            with self.assertRaisesRegex(ValueError, "immutable receipt"):
                px_posthoc.PxScorer()._score_synthetic(ALIAS, [])
            with self.assertRaisesRegex(ValueError, "output hash differs"):
                px_posthoc.PxScorer()._score_synthetic(
                    ALIAS, [], receipt=self.receipt, output_sha256="e" * 64)


if __name__ == "__main__":
    unittest.main()
