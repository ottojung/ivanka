"""Public RAM scope semantics: legacy launcher group vs whole container."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.px_cohort_ingest import (assert_no_stale_scores,
                                              ingest,
                                              refresh_registry_provenance)
from assembler_bench.exploratory_runtime.monitor import attest
from assembler_bench.px_ram_semantics import (COMPARABLE_KEY,
                                              COMPARABLE_METHOD,
                                              COMPARABLE_METHOD_VERSION,
                                              COMPARABLE_SCOPE,
                                              LAUNCHER_DIAGNOSTIC,
                                              LEGACY_SCOPE,
                                              METHOD_KEY, SCOPE_KEY,
                                              VERSION_KEY, attested,
                                              normalize_case,
                                              validate_publication)
from assembler_bench.site_build import SITE

ROOT = Path(__file__).resolve().parents[1]
RAW = 83197952
MIB = 79.34375


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RamScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("receipts", "results", "diagnostics", "samples"):
            (self.root / folder).mkdir()
        self.source = self.root / "source"
        sample = self.source / "samples" / "S037"
        sample.mkdir(parents=True)
        (self.source / "manifest.tsv").write_text(
            "sample\tother\n" +
            "".join("S%03d\t1\n" % i for i in range(1, 38)))
        self.mates = {}
        for mate in ("R1", "R2"):
            path = sample / ("S037_L001_" + mate + "_001.fastq.gz")
            path.write_bytes(("read" + mate).encode())
            self.mates[mate] = sha(path)
        self.name = "skesa-physical-PX-R037"
        self.receipt = {
            "schema": "ivanka.px.case.receipt.v1", "tool_id": "skesa",
            "alias": "PX-R037", "cohort": "physical", "terminal": True,
            "outcome": "success", "failure_reason": None,
            "seconds": 826.8, "peak_rss_bytes": RAW,
            "input_sha256": self.mates, "output_sha256": "a" * 64,
            "runner_receipt_sha256": "b" * 64,
            "source_commit": "1" * 40, "adapter_commit": "2" * 40,
            "image_sha256": "c" * 64,
        }
        self.result = {
            "schema": "ivanka.exploratory.per-sample.v1", "tool_id": "skesa",
            "cohort": "physical", "scorer_source_sha256": "d" * 64,
            "samples": [{"alias": "PX-R037", "outcome": "success",
                         "score": 234.0, "peak_ram_observed_mib": MIB,
                         "method":
                             "best_final_max_contig_local_alignment_over_reference_panel",
                         "reference_panel_sha256":
                             "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"}],
        }
        self.resource = {"schema": "ivanka.px.arm-resource.v1",
                         "tool_id": "skesa", "alias": "PX-R037",
                         "peak_ram_observed_mib": MIB,
                         "peak_rss_bytes": RAW, "outcome": "success"}
        self.diagnostics = {
            "schema": "ivanka.px.diagnostics.v3", "tool_id": "skesa",
            "alias": "PX-R037", "output_sha256": "a" * 64,
            "runner_receipt_sha256": "b" * 64,
            "metrics": {"canonical_micall": {"status": "extracted",
                                             "values": {}},
                        "exact_coverage": {"status": "unavailable"}},
        }
        self.evidence = json.loads(
            (SITE / "data/assembler-evidence.json").read_text())
        item = next(item for item in self.evidence["assemblers"]
                    if item["id"] == "skesa")
        item.update({"source_commit": "1" * 40, "adapter_commit": "2" * 40,
                     "image_sha256": "c" * 64, "cases": []})
        report = json.loads((SITE / "data/runs.json").read_text())
        for run in report["runs"]:
            for sample in run["samples"]:
                for key in ("score", "seconds", "diagnostics",
                            "measurement_evidence"):
                    sample.get(key, {}).pop("skesa", None)
                if "skesa" in sample.get("failures", []):
                    sample["failures"].remove("skesa")
        self.report = report

    def _write(self):
        path = self.root / "receipts" / (self.name + ".json")
        path.write_text(json.dumps(self.receipt))
        (self.root / "receipts" / "index.json").write_text(json.dumps({
            "schema": "ivanka.px.case.receipt-index.v1",
            "entries": {self.name: sha(path)}}))
        (self.root / "results" / (self.name + "-results.json")).write_text(
            json.dumps(self.result))
        (self.root / "results" / (self.name + "-resource.json")).write_text(
            json.dumps(self.resource))
        (self.root / "diagnostics" / (self.name + ".json")).write_text(
            json.dumps(self.diagnostics))

    def test_legacy_receipt_keeps_raw_bytes_without_comparable_peak(self):
        self._write()
        _, merged, _, _ = ingest(self.report, self.evidence,
                                 self.root, self.source)
        real = next(r for r in merged["runs"] if r["cohort"] == "real")
        row = next(s for s in real["samples"] if s["alias"] == "R037")
        arm = row["diagnostics"]["skesa"]
        proof = row["measurement_evidence"]["skesa"]
        self.assertIsNone(arm[COMPARABLE_KEY])
        self.assertIsNone(proof[COMPARABLE_KEY])
        self.assertEqual(arm[LAUNCHER_DIAGNOSTIC], MIB)
        self.assertEqual(arm["peak_ram_scope"], LEGACY_SCOPE)
        self.assertEqual(proof["peak_rss_bytes"], RAW)
        validate_publication(merged, self.evidence)

    def test_attested_container_receipt_publishes_comparable_peak(self):
        attestation = {
            "peak_ram_method": COMPARABLE_METHOD,
            "peak_ram_method_version": COMPARABLE_METHOD_VERSION,
            "peak_ram_scope": COMPARABLE_SCOPE,
        }
        self.receipt.update(attestation)
        self.resource.update(attestation)
        self._write()
        _, merged, _, _ = ingest(self.report, self.evidence,
                                 self.root, self.source)
        real = next(r for r in merged["runs"] if r["cohort"] == "real")
        row = next(s for s in real["samples"] if s["alias"] == "R037")
        arm = row["diagnostics"]["skesa"]
        proof = row["measurement_evidence"]["skesa"]
        self.assertEqual(arm[COMPARABLE_KEY], MIB)
        self.assertEqual(proof[COMPARABLE_KEY], MIB)
        self.assertEqual(proof["peak_ram_method_version"],
                         COMPARABLE_METHOD_VERSION)
        self.assertNotIn(LAUNCHER_DIAGNOSTIC, arm)
        validate_publication(merged, self.evidence)

    def test_forged_side_file_attestation_never_promotes_legacy_peak(self):
        # The receipt stays legacy; only the unbound side files are forged.
        attestation = {
            "peak_ram_method": COMPARABLE_METHOD,
            "peak_ram_method_version": COMPARABLE_METHOD_VERSION,
            "peak_ram_scope": COMPARABLE_SCOPE,
        }
        self.resource.update(attestation)
        self.result["samples"][0].update(attestation)
        self._write()
        _, merged, _, _ = ingest(self.report, self.evidence,
                                 self.root, self.source)
        real = next(r for r in merged["runs"] if r["cohort"] == "real")
        row = next(s for s in real["samples"] if s["alias"] == "R037")
        arm = row["diagnostics"]["skesa"]
        proof = row["measurement_evidence"]["skesa"]
        self.assertIsNone(arm[COMPARABLE_KEY])
        self.assertIsNone(proof[COMPARABLE_KEY])
        self.assertEqual(arm[LAUNCHER_DIAGNOSTIC], MIB)
        self.assertEqual(arm["peak_ram_scope"], LEGACY_SCOPE)
        self.assertEqual(proof["peak_rss_bytes"], RAW)
        validate_publication(merged, self.evidence)

    def test_receipt_alone_attests_comparable_peak(self):
        # Side files carry no attestation; the bound receipt is authoritative.
        self.receipt.update({
            "peak_ram_method": COMPARABLE_METHOD,
            "peak_ram_method_version": COMPARABLE_METHOD_VERSION,
            "peak_ram_scope": COMPARABLE_SCOPE,
        })
        self._write()
        _, merged, _, _ = ingest(self.report, self.evidence,
                                 self.root, self.source)
        real = next(r for r in merged["runs"] if r["cohort"] == "real")
        row = next(s for s in real["samples"] if s["alias"] == "R037")
        arm = row["diagnostics"]["skesa"]
        self.assertEqual(arm[COMPARABLE_KEY], MIB)
        self.assertEqual(arm["peak_ram_method_version"],
                         COMPARABLE_METHOD_VERSION)
        self.assertNotIn(LAUNCHER_DIAGNOSTIC, arm)
        validate_publication(merged, self.evidence)

    def test_unknown_method_never_claims_whole_container(self):
        self.receipt.update({"peak_ram_method": "container_tree",
                             "peak_ram_scope": COMPARABLE_SCOPE})
        self._write()
        _, merged, _, _ = ingest(self.report, self.evidence,
                                 self.root, self.source)
        real = next(r for r in merged["runs"] if r["cohort"] == "real")
        row = next(s for s in real["samples"] if s["alias"] == "R037")
        self.assertIsNone(row["diagnostics"]["skesa"][COMPARABLE_KEY])

    def test_published_legacy_peak_is_withdrawn_on_reread(self):
        case = {"peak_rss_bytes": RAW, "peak_ram_observed_mib": MIB,
                "canonical_alias": "R037", "cohort": "real", "score": 234.0,
                "diagnostics": {"peak_ram_observed_mib": MIB}}
        normalize_case(case)
        self.assertIsNone(case["peak_ram_observed_mib"])
        self.assertEqual(case["diagnostics"][LAUNCHER_DIAGNOSTIC], MIB)
        self.assertIsNone(case["diagnostics"][COMPARABLE_KEY])
        normalize_case(case)
        self.assertEqual(case["diagnostics"][LAUNCHER_DIAGNOSTIC], MIB)

    def test_incoming_receipt_conflict_blocks_provenance_change(self):
        incoming = [{"id": "skesa", "cases": [{"cohort": "real",
                                               "canonical_alias": "R004",
                                               "score": 999.0}]}]
        report = {"runs": [{"cohort": "real", "samples": [
            {"alias": "R004", "score": {"skesa": 188.0}}]}]}
        with self.assertRaisesRegex(ValueError, "preexisting sample score"):
            assert_no_stale_scores(report, {"assemblers": []}, incoming)

    def test_all_seventeen_tool_rows_validate(self):
        report = json.loads((SITE / "data/runs.json").read_text())
        evidence = json.loads((SITE / "data/assembler-evidence.json").read_text())
        for run in report["runs"]:
            self.assertEqual(len(run["tools"]), 17)
        self.assertGreater(validate_publication(report, evidence), 0)


class MonitorAttestationTests(unittest.TestCase):
    def test_legacy_sampler_is_labelled_launcher_group(self):
        fields = attest(RAW)
        self.assertEqual(fields[SCOPE_KEY], LEGACY_SCOPE)
        self.assertFalse(attested(fields))
        self.assertNotIn(VERSION_KEY, fields)

    def test_corrected_sampler_states_method_version_and_scope(self):
        observation = {METHOD_KEY: COMPARABLE_METHOD,
                       VERSION_KEY: COMPARABLE_METHOD_VERSION,
                       SCOPE_KEY: COMPARABLE_SCOPE, "peak_rss": RAW}
        fields = attest(observation)
        self.assertTrue(attested(fields))
        self.assertEqual(fields["peak_rss_bytes"], RAW)
        self.assertEqual(fields[VERSION_KEY], COMPARABLE_METHOD_VERSION)


class ExactAdapterPinTests(unittest.TestCase):
    """Generic handoff adoption works for Ray, Tadpole and PenguiN pins."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "handoff").mkdir()
        (self.root / "receipts").mkdir()

    def _receipt(self, tool, kind, adapter, digest_source):
        data = {"schema": "ivanka.exploratory." + kind + ".receipt.v1",
                "tool_id": tool, "source_commit": "1" * 40,
                "adapter_commit": adapter, "image_sha256": "c" * 64,
                "qualifying": False}
        if kind == "image":
            data["native_binary_sha256"] = "d" * 64
        else:
            for cohort in ("physical", "synthetic"):
                data[cohort] = {"source_input_sha256": "e" * 64,
                                "status": "success"}
        path = self.root / "receipts" / (kind + "-" + tool + ".json")
        path.write_text(json.dumps(data))
        return {"path": str(path),
                "sha256": digest_source(path)}

    def test_exact_pins_adopt_provenance_without_hardcoded_map(self):
        pins = {
            "ray": "9e02a9205fc338e1be4f0cd4a8dd4a13b406ae88",
            "tadpole": "3fd7f695c378875fd7b3b80ca263601a66476c2f",
            "penguin": "8e7c55a3ebcaa4584cb09b1ac743bb5320bd1257",
        }
        registry = {"schema": "ivanka.exploratory.assemblers.v1",
                    "adapter_branch_commits": pins, "candidates": []}
        evidence = {"assemblers": [
            {"id": tool, "source_commit": "1" * 40,
             "adapter_commit": "0" * 40, "image_sha256": "c" * 64,
             "cases": []} for tool in pins]}
        for tool, adapter in pins.items():
            image = self._receipt(tool, "image", adapter, sha)
            pilot = self._receipt(tool, "pilot", adapter, sha)
            registry["candidates"].append({
                "id": tool, "status": "pilot", "source_commit": "1" * 40,
                "image_sha256": "c" * 64, "image_evidence": image,
                "pilot_evidence": pilot})
            (self.root / "handoff" / (tool + ".json")).write_text(json.dumps({
                "schema": "ivanka.px.supervisor.handoff.v1", "tool_id": tool,
                "image_sha256": "c" * 64,
                "image_receipt_sha256": image["sha256"],
                "pilot_receipt_sha256": pilot["sha256"]}))
        registry_path = self.root / "registry.json"
        registry_path.write_text(json.dumps(registry))
        with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                   self.root):
            adopted = refresh_registry_provenance(
                evidence, registry_path, self.root / "handoff")
        self.assertEqual(set(adopted), set(pins))
        for item in evidence["assemblers"]:
            self.assertEqual(item["adapter_commit"], pins[item["id"]])
            self.assertTrue(item["source_url"].endswith(
                pins[item["id"]]))
            self.assertTrue(item["source_branch"].startswith("bench/"))


if __name__ == "__main__":
    unittest.main()
