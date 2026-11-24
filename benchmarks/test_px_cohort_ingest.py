"""Neutral ingestion of immutable PX cohort receipts into public data."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.px_cohort_ingest import (assert_no_stale_scores,
                                               refresh_registry_provenance)

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
        sample = self.real / "samples" / "S004"
        sample.mkdir(parents=True)
        self.mates = {}
        for mate in ("R1", "R2"):
            path = sample / ("S004_L001_" + mate + "_001.fastq.gz")
            path.write_bytes(("read" + mate).encode())
            self.mates[mate] = _sha(path)
        self.name = "skesa-physical-PX-R004"
        self.receipt = {
            "schema": "ivanka.px.case.receipt.v1", "tool_id": "skesa",
            "alias": "PX-R004", "cohort": "physical", "terminal": True,
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
            "samples": [{"alias": "PX-R004", "outcome": "success",
                         "score": 188.0, "peak_ram_observed_mib": 77.433594,
                         "method": "best_final_max_contig_local_alignment_over_reference_panel",
                         "reference_panel_sha256":
                             "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"}],
        }
        self.resource = {"schema": "ivanka.px.arm-resource.v1",
                         "tool_id": "skesa", "alias": "PX-R004",
                         "peak_ram_observed_mib": 77.433594,
                         "peak_rss_bytes": 81195008, "outcome": "success"}
        self.diagnostics = {
            "schema": "ivanka.px.diagnostics.v3", "tool_id": "skesa",
            "alias": "PX-R004", "output_sha256": "a" * 64,
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
        # This is an independent fabricated SKESA receipt, not a second
        # measurement of any already-published SKESA case.
        item["cases"] = []

    def _report(self):
        report = json.loads((SITE / "data/runs.json").read_text())
        for run in report["runs"]:
            for sample in run["samples"]:
                for key in ("score", "seconds", "diagnostics",
                            "measurement_evidence", "exact_profiles"):
                    sample.get(key, {}).pop("skesa", None)
                if "skesa" in sample.get("failures", []):
                    sample["failures"].remove("skesa")
        return report

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
        report = self._report()
        evidence, merged, added, joined = ingest(
            report, self.evidence, self.root, self.real)
        self.assertEqual(added, [("skesa", "real", "R004")])
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R004")
        self.assertEqual(sample["score"]["skesa"], 188.0)
        self.assertIsNone(sample["seconds"]["skesa"])
        self.assertEqual(sample["diagnostics"]["skesa"][
            "nuc_soft_clips_count"], 3)
        diag = sample["diagnostics"]["skesa"]
        proof = sample["measurement_evidence"]["skesa"]
        # Legacy launcher-group RSS is real evidence but never comparable RAM.
        self.assertIsNone(diag.get("peak_ram_observed_mib"))
        self.assertIsNone(proof["peak_ram_observed_mib"])
        self.assertEqual(diag["observed_launcher_group_peak_rss_mib"],
                         77.433594)
        self.assertEqual(diag["peak_ram_scope"], "launcher_process_group")
        self.assertIn("excludes container MiCall",
                      diag["peak_ram_unavailable_reason"])
        self.assertEqual(proof["peak_rss_bytes"], 81195008)
        self.assertEqual(proof["input_sha256"], self.mates)
        self.assertEqual(real["tool_progress"]["skesa"]["finished"], 1)
        _, _, repeated, _ = ingest(merged, evidence, self.root, self.real)
        self.assertEqual(repeated, [])

    def test_tampered_indexed_receipt_or_source_pair_is_rejected(self):
        report = self._report()
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
        pair = self.real / "samples" / "S004" / "S004_L001_R1_001.fastq.gz"
        pair.write_bytes(b"tampered-read")
        with self.assertRaisesRegex(ValueError, "original source pair"):
            ingest(report, self.evidence, self.root, self.real)

    def test_exact_coverage_unavailable_is_never_fabricated(self):
        report = self._report()
        _, merged, _, _ = ingest(report, self.evidence, self.root, self.real)
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R004")
        self.assertNotIn("skesa", sample.get("exact_profiles", {}))
        proof = sample["measurement_evidence"]["skesa"]["exact_coverage"]
        self.assertEqual(proof["status"], "unavailable")

class RegistryActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "handoff").mkdir()
        (self.root / "receipts").mkdir()
        self.registry = {
            "schema": "ivanka.exploratory.assemblers.v1",
            "adapter_branch_commits": {},
            "candidates": [],
        }
        self.evidence = {"assemblers": [
            {"id": tool, "source_commit": "1" * 40,
             "adapter_commit": "2" * 40, "image_sha256": "c" * 64,
             "cases": []} for tool in ("skesa", "soapdenovo2")]}

    def _receipt(self, tool, kind, adapter):
        data = {"schema": "ivanka.exploratory." + kind + ".receipt.v1",
                "tool_id": tool, "source_commit": "1" * 40,
                "adapter_commit": adapter, "image_sha256": "c" * 64,
                "qualifying": False}
        if kind == "image":
            data["native_binary_sha256"] = "d" * 64
        else:
            data["physical"] = {"source_input_sha256": "e" * 64,
                                "status": "success"}
            data["synthetic"] = {"source_input_sha256": "f" * 64,
                                 "status": "success"}
        path = self.root / "receipts" / (kind + "-" + tool + ".json")
        path.write_text(json.dumps(data))
        return {"path": str(path), "sha256": _sha(path)}

    def _activate(self, tools, spoof=None):
        for tool in tools:
            adapter = ("2fb3cd5af8769f834635b21187738cf90565c349" if tool == "skesa"
                       else "39cfa22fad92157680382d1ea124b70b2e8515b3")
            image = self._receipt(tool, "image", adapter)
            pilot = self._receipt(tool, "pilot", adapter)
            if spoof == tool:
                pilot["sha256"] = "0" * 64
            self.registry["adapter_branch_commits"][tool] = adapter
            self.registry["candidates"].append({
                "id": tool, "status": "pilot", "source_commit": "1" * 40,
                "image_sha256": "c" * 64,
                "image_evidence": image, "pilot_evidence": pilot})
            handoff = {"schema": "ivanka.px.supervisor.handoff.v1",
                       "tool_id": tool, "image_sha256": "c" * 64,
                       "image_receipt_sha256": image["sha256"],
                       "pilot_receipt_sha256": pilot["sha256"]}
            (self.root / "handoff" / (tool + ".json")).write_text(
                json.dumps(handoff))
        registry_path = self.root / "registry.json"
        registry_path.write_text(json.dumps(self.registry))
        return registry_path

    def test_multiple_verified_activations_adopted(self):
        registry = self._activate(("skesa", "soapdenovo2"))
        with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                   self.root):
            adopted = refresh_registry_provenance(
                self.evidence, registry, self.root / "handoff")
        self.assertEqual(set(adopted), {"skesa", "soapdenovo2"})
        with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                   self.root):
            again = refresh_registry_provenance(
                self.evidence, registry, self.root / "handoff")
        self.assertEqual(again, [], "idempotent activation adds nothing")

    def test_spoofed_handoff_is_rejected(self):
        registry = self._activate(("skesa",), spoof="skesa")
        with self.assertRaisesRegex(ValueError, "handoff receipt digests"):
            refresh_registry_provenance(
                self.evidence, registry, self.root / "handoff")

    def test_stale_sample_score_blocks_provenance_change(self):
        report = {"runs": [{"samples": [{"alias": "R004", "score": {
            "skesa": 999.0}}]}]}
        evidence = {"assemblers": [{"id": "skesa", "cases": [
            {"canonical_alias": "R004", "score": 188.0}]}]}
        with self.assertRaisesRegex(ValueError, "preexisting sample score"):
            assert_no_stale_scores(report, evidence)


if __name__ == "__main__":
    unittest.main()
