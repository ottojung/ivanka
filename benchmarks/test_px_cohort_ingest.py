"""Neutral ingestion of immutable PX cohort receipts into public data."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_posthoc
from assembler_bench.current_validation_v2 import V6_COHORT_SHA
from assembler_bench.px_cohort_ingest import (assert_no_stale_scores,
                                               refresh_registry_provenance)
from assembler_bench import px_timing_semantics as timing

from assembler_bench.px_cohort_ingest import ingest
from assembler_bench.public_view import PHYSICAL_SCORE, SYNTHETIC_SCORE
from assembler_bench.px_ram_semantics import validate_publication
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
                         "score": 188.0, "peak_ram_observed_mib": 77.433594,
                         "method": "best_final_max_contig_local_alignment_over_reference_panel",
                         "reference_panel_sha256":
                             "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"}],
        }
        self.resource = {"schema": "ivanka.px.arm-resource.v1",
                         "tool_id": "skesa", "alias": "PX-R003",
                         "peak_ram_observed_mib": 77.433594,
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
        self.assertEqual(added, [("skesa", "real", "R003")])
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R003")
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

    def _attest_timing(self, seconds):
        self.receipt["seconds"] = seconds
        self.receipt.update({
            timing.ORIGIN_KEY: timing.ORIGIN,
            timing.VERSION_KEY: timing.METHOD_VERSION,
            timing.TIMER_KEY: timing.TIMER_SOURCE_SHA256,
            timing.FILE_KEY: "e" * 64,
        })
        self._write_all()

    def test_only_complete_timing_proof_joins_a_runtime(self):
        self._attest_timing(66.9)
        report = self._report()
        evidence, merged, added, _ = ingest(
            report, self.evidence, self.root, self.real)
        self.assertEqual(added, [("skesa", "real", "R003")])
        case = evidence["assemblers"][0]["cases"][0]
        self.assertEqual(case[timing.RUNTIME_KEY], 66.9)
        self.assertIsNone(case[timing.LAUNCHER_KEY])
        self.assertTrue(timing.attested(case))
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R003")
        self.assertEqual(sample["seconds"]["skesa"], 66.9)
        proof = sample["measurement_evidence"]["skesa"]
        self.assertTrue(timing.attested(proof))
        self.assertEqual(proof[timing.RUNTIME_KEY], 66.9)
        baseline_run = next(run for run in report["runs"]
                            if run["cohort"] == "real")
        baseline = next(row for row in baseline_run["samples"]
                        if row["alias"] == "R002")
        unchanged = next(row for row in real["samples"]
                         if row["alias"] == "R002")
        for tool, value in baseline["seconds"].items():
            if value is not None:
                self.assertEqual(unchanged["seconds"][tool], value)
        _, again, repeated, _ = ingest(merged, evidence, self.root, self.real)
        self.assertEqual(repeated, [])
        self.assertEqual(again, merged)

    def test_unattested_receipt_keeps_runtime_null(self):
        evidence, merged, _, _ = ingest(
            self._report(), self.evidence, self.root, self.real)
        case = evidence["assemblers"][0]["cases"][0]
        self.assertEqual(case["launcher_seconds"], 66.9)
        self.assertIsNone(case[timing.RUNTIME_KEY])
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R003")
        self.assertIsNone(sample["seconds"]["skesa"])

    def test_partial_timing_proof_is_not_a_runtime(self):
        self.receipt[timing.ORIGIN_KEY] = timing.ORIGIN
        self._write_all()
        with self.assertRaisesRegex(ValueError, "timing proof is incomplete"):
            ingest(self._report(), self.evidence, self.root, self.real)

    def test_publish_stamps_timestamp_without_rewriting_measurements(self):
        import shutil
        site = self.root / "site"
        shutil.copytree(SITE, site)
        (site / "data/assembler-evidence.json").write_text(
            json.dumps(self.evidence))
        (site / "data/runs.json").write_text(json.dumps(self._report()))
        original = json.loads((site / "data/runs.json").read_text())
        self._attest_timing(66.9)
        from assembler_bench.px_cohort_ingest import publish
        with patch("assembler_bench.site_build.validate_public_site",
                   return_value=True):
            updated, merged, added = publish(site, self.root, self.real)
        self.assertEqual(added, [("skesa", "real", "R003")])
        stamp = merged.get("published_at")
        self.assertIsNotNone(stamp)
        self.assertNotEqual(stamp, original.get("published_at"))
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R003")
        self.assertEqual(sample["seconds"]["skesa"], 66.9)
        baseline_run = next(run for run in original["runs"]
                            if run["cohort"] == "real")
        baseline = next(row for row in baseline_run["samples"]
                        if row["alias"] == "R002")
        unchanged = next(row for row in real["samples"]
                         if row["alias"] == "R002")
        for tool, value in baseline["seconds"].items():
            if value is not None:
                self.assertEqual(unchanged["seconds"][tool], value)
        with patch("assembler_bench.site_build.validate_public_site",
                   return_value=True):
            _, repeated_merged, repeated_added = publish(
                site, self.root, self.real)
        self.assertEqual(repeated_added, [])
        self.assertEqual(repeated_merged.get("published_at"), stamp)

    def _write_failure(self, reason, peak=None):
        self.receipt.update(outcome="failure", failure_reason=reason,
                            qualifying=False, output_sha256=None, seconds=None,
                            peak_rss_bytes=peak, attempt=1,
                            peak_ram_method="container_process_tree_sampled_rss",
                            peak_ram_method_version="ivanka.px.whole-container-rss.v2",
                            peak_ram_scope="whole_container_process_tree")
        self.resource.update(outcome="failure", cohort="physical", attempt=1,
                             peak_rss_bytes=peak, peak_ram_observed_mib=None)
        self._write_all()
        (self.root / "results" / (self.name + "-results.json")).unlink()
        (self.root / "diagnostics" / (self.name + ".json")).unlink()

    def test_terminal_failure_publishes_without_score_or_ram(self):
        self._write_failure("error")
        evidence, merged, added, _ = ingest(
            self._report(), self.evidence, self.root, self.real)
        self.assertEqual(added, [("skesa", "real", "R003")])
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        row = next(row for row in real["samples"] if row["alias"] == "R003")
        self.assertIn("skesa", row["failures"])
        self.assertEqual(row["measurement_evidence"]["skesa"]["failure_reason"],
                         "error")
        self.assertIsNone(row["score"]["skesa"])
        self.assertIsNone(row["seconds"]["skesa"])
        self.assertIsNone(row["diagnostics"]["skesa"]["peak_ram_observed_mib"])
        self.assertEqual(row["diagnostics"]["skesa"]["peak_ram_scope"],
                         "whole_container_process_tree")
        self.assertEqual(real["tool_progress"]["skesa"]["failed"], 1)
        self.assertEqual(real["tool_progress"]["skesa"]["finished"], 1)
        _, again, repeated, _ = ingest(merged, evidence, self.root, self.real)
        self.assertEqual(repeated, [])
        self.assertEqual(again, merged)

    def test_retryable_failure_does_not_count_as_finished(self):
        self._write_failure("identity_lost")
        _, merged, added, _ = ingest(
            self._report(), self.evidence, self.root, self.real)
        self.assertEqual(added, [])
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        self.assertEqual(real["tool_progress"]["skesa"]["finished"], 0)

    def test_terminal_failure_cannot_replace_a_genuine_score(self):
        self._write_failure("error")
        report = self._report()
        real = next(run for run in report["runs"] if run["cohort"] == "real")
        row = next(row for row in real["samples"] if row["alias"] == "R003")
        row["score"]["skesa"] = 42
        with self.assertRaisesRegex(ValueError, "overwrite a genuine score"):
            ingest(report, self.evidence, self.root, self.real)

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
        pair = self.real / "samples" / "S003" / "S003_L001_R1_001.fastq.gz"
        pair.write_bytes(b"tampered-read")
        with self.assertRaisesRegex(ValueError, "original source pair"):
            ingest(report, self.evidence, self.root, self.real)

    def test_exact_coverage_unavailable_is_never_fabricated(self):
        report = self._report()
        _, merged, _, _ = ingest(report, self.evidence, self.root, self.real)
        real = next(run for run in merged["runs"] if run["cohort"] == "real")
        sample = next(row for row in real["samples"] if row["alias"] == "R003")
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

    def _unpinned_activation(self, image):
        """A verified handoff against measured cases without case-level pins."""
        tool = "idba-ud"
        adapter = "ea51b5030edf6a6c89c36ffa3d48fac15b2cb1c9"
        source = "1" * 40
        image_receipt = {
            "schema": "ivanka.exploratory.image.receipt.v1",
            "tool_id": tool, "source_commit": source,
            "adapter_commit": adapter, "image_sha256": image,
            "qualifying": False, "native_binary_sha256": "d" * 64,
        }
        pilot_receipt = {
            "schema": "ivanka.exploratory.pilot.receipt.v1",
            "tool_id": tool, "source_commit": source,
            "adapter_commit": adapter, "image_sha256": image,
            "qualifying": False,
        }
        for cohort in ("physical", "synthetic"):
            pilot_receipt[cohort] = {"source_input_sha256": "e" * 64,
                                     "status": "success"}
        refs = {}
        for kind, data in (("image", image_receipt), ("pilot", pilot_receipt)):
            path = self.root / "receipts" / (kind + "-" + tool + ".json")
            path.write_text(json.dumps(data))
            refs[kind] = {"path": str(path), "sha256": _sha(path)}
        registry = {
            "schema": "ivanka.exploratory.assemblers.v1",
            "adapter_branch_commits": {tool: adapter},
            "candidates": [{
                "id": tool, "status": "pilot", "source_commit": source,
                "image_sha256": image, "image_evidence": refs["image"],
                "pilot_evidence": refs["pilot"],
            }],
        }
        registry_path = self.root / "registry.json"
        registry_path.write_text(json.dumps(registry))
        (self.root / "handoff" / (tool + ".json")).write_text(json.dumps({
            "schema": "ivanka.px.supervisor.handoff.v1", "tool_id": tool,
            "image_sha256": image,
            "image_receipt_sha256": refs["image"]["sha256"],
            "pilot_receipt_sha256": refs["pilot"]["sha256"],
        }))
        evidence = {"assemblers": [{
            "id": tool, "source_commit": source, "adapter_commit": adapter,
            "image_sha256": "c" * 64,
            "cases": [
                {"cohort": "real", "canonical_alias": "R053",
                 "score": 298.0},
                {"cohort": "synthetic", "canonical_alias": "H452",
                 "score": 9937.752878929348},
            ],
        }]}
        return registry_path, evidence

    def test_changed_image_cannot_rewrite_unpinned_measured_cases(self):
        registry_path, evidence = self._unpinned_activation("f" * 64)
        with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                   self.root):
            with self.assertRaisesRegex(ValueError,
                                        "measured case provenance"):
                refresh_registry_provenance(
                    evidence, registry_path, self.root / "handoff")
        self.assertEqual(evidence["assemblers"][0]["image_sha256"], "c" * 64)

    def test_same_image_adopts_unpinned_measured_cases(self):
        registry_path, evidence = self._unpinned_activation("c" * 64)
        with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                   self.root):
            adopted = refresh_registry_provenance(
                evidence, registry_path, self.root / "handoff")
        self.assertEqual(adopted, ["idba-ud"])
        self.assertEqual(evidence["assemblers"][0]["image_sha256"], "c" * 64)

    @staticmethod
    def _rewrite_pilot(registry_path, tool, physical="__keep__",
                       synthetic="__keep__"):
        """Change arm statuses while keeping the verified digest chain intact.

        ``None`` removes an arm; the default keeps it unchanged.
        """
        registry = json.loads(Path(registry_path).read_text())
        item = next(c for c in registry["candidates"] if c["id"] == tool)
        path = Path(item["pilot_evidence"]["path"])
        pilot = json.loads(path.read_text())
        for name, value in (("physical", physical), ("synthetic", synthetic)):
            if value == "__keep__":
                continue
            if value is None:
                pilot.pop(name, None)
            else:
                pilot[name] = value
        path.write_text(json.dumps(pilot))
        digest = _sha(path)
        item["pilot_evidence"]["sha256"] = digest
        Path(registry_path).write_text(json.dumps(registry))
        handoff_path = path.parent.parent / "handoff" / (tool + ".json")
        handoff = json.loads(handoff_path.read_text())
        handoff["pilot_receipt_sha256"] = digest
        handoff_path.write_text(json.dumps(handoff))
        return registry_path

    def test_verified_terminal_pair_with_honest_failure_adopted(self):
        """A real success plus a recorded failure publishes provenance verbatim."""
        tool = "soapdenovo2"
        registry_path = self._activate((tool,))
        registry_path = self._rewrite_pilot(
            registry_path, tool,
            synthetic={"source_input_sha256": "f" * 64,
                       "status": "failure",
                       "failure_cause": "guard soft trip; no final MAX"})
        with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                   self.root):
            adopted = refresh_registry_provenance(
                self.evidence, registry_path, self.root / "handoff")
        self.assertEqual(adopted, [tool])
        profile = next(a for a in self.evidence["assemblers"] if a["id"] == tool)
        self.assertEqual(profile["image_sha256"], "c" * 64)
        self.assertEqual(profile["pilot"]["outcomes"],
                         {"physical": "success", "synthetic": "failure"})
        self.assertNotIn("qualifying", profile["pilot"])
        self.assertEqual(profile.get("cases"), [])

    def test_partial_nonterminal_or_malformed_pair_refused(self):
        """Only a complete terminal pair may publish; no partial pilot."""
        tool = "skesa"
        cases = (
            {"synthetic": None},  # arm absent
            {"synthetic": {"status": "partial"}},  # non-terminal
            {"synthetic": "malformed"},  # malformed arm
        )
        for variant in cases:
            with self.subTest(variant=variant):
                self.setUp()
                registry_path = self._activate((tool,))
                self._rewrite_pilot(registry_path, tool, **variant)
                with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                           self.root):
                    try:
                        adopted = refresh_registry_provenance(
                            self.evidence, registry_path, self.root / "handoff")
                    except ValueError:
                        adopted = []  # fail closed is also refusal
                self.assertEqual(adopted, [])

    def test_unadmitted_tool_is_never_adopted(self):
        self._activate(("skesa",))
        handoff = json.loads((self.root / "handoff" / "skesa.json").read_text())
        handoff["tool_id"] = "not-in-registry"
        (self.root / "handoff" / "not-in-registry.json").write_text(
            json.dumps(handoff))
        registry_path = self.root / "registry.json"
        with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                   self.root):
            adopted = refresh_registry_provenance(
                self.evidence, registry_path, self.root / "handoff")
        self.assertNotIn("not-in-registry", adopted)

    def test_failure_pair_cannot_repoint_old_scores(self):
        registry_path, evidence = self._unpinned_activation("f" * 64)
        self._rewrite_pilot(
            registry_path, "idba-ud",
            synthetic={"source_input_sha256": "f" * 64,
                       "status": "failure", "failure_cause": "guard trip"})
        with patch("assembler_bench.exploratory_policy.PROVENANCE_ROOT",
                   self.root):
            with self.assertRaisesRegex(ValueError,
                                        "measured case provenance"):
                refresh_registry_provenance(
                    evidence, registry_path, self.root / "handoff")
        self.assertEqual(evidence["assemblers"][0]["image_sha256"], "c" * 64)


class PxCohortSyntheticIngestTests(unittest.TestCase):
    """Synthetic admission built only from the frozen 464-case source manifest."""

    ALIAS = "PX-H192"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("receipts", "receipts/attempts", "results", "diagnostics"):
            (self.root / folder).mkdir(parents=True)
        self.real = self.root / "source"  # synthetic binding never reads private data
        cases = json.loads(Path(sched.SYNTHETIC_COHORT).read_bytes())["cases"]
        aliases = sched.canonical_aliases((case["id"] for case in cases),
                                          "synthetic")
        source = next(item for item, alias in aliases.items()
                      if alias == self.ALIAS)
        self.record = next(case for case in cases if case["id"] == source)
        self.inputs = {mate: self.record["sha256"]["reads/" + mate + ".fastq.gz"]
                       for mate in ("R1", "R2")}
        published = json.loads(
            (SITE / "data/assembler-evidence.json").read_text())
        skesa = next(item for item in published["assemblers"]
                     if item["id"] == "skesa")
        # The score is SKESA's already published measurement for this exact
        # case; the fixture invents no measurement, truth or site data.
        self.score = next(case["score"] for case in skesa["cases"]
                          if case.get("cohort") == "synthetic"
                          and case.get("canonical_alias") == "H192")
        self.name = "skesa-synthetic-" + self.ALIAS
        self.receipt = {
            "schema": "ivanka.px.case.receipt.v1", "tool_id": "skesa",
            "alias": self.ALIAS, "cohort": "synthetic", "terminal": True,
            "qualifying": False, "outcome": "success", "failure_reason": None,
            "seconds": 90.16703, "peak_rss_bytes": None,
            "input_sha256": dict(self.inputs), "output_sha256": "a" * 64,
            "runner_receipt_sha256": "b" * 64,
            "source_commit": "1" * 40, "adapter_commit": "2" * 40,
            "image_sha256": "c" * 64,
        }
        self.result = {
            "schema": "ivanka.exploratory.per-sample.v1", "tool_id": "skesa",
            "cohort": "synthetic", "expected_sample_count": 464,
            "source_commit": "1" * 40, "adapter_commit": "2" * 40,
            "image_sha256": "c" * 64,
            "scorer_source_sha256": px_posthoc.source_sha256(),
            "samples": [{"alias": self.ALIAS, "outcome": "success",
                         "score": self.score, "method": SYNTHETIC_SCORE,
                         "truth_sha256": self.record[
                             "sha256"]["hidden-truth/haplotypes.fasta"],
                         "output_sha256": "a" * 64,
                         "runner_receipt_sha256": "b" * 64,
                         "synthetic_abundant_truth_count": 2}],
        }
        self.resource = {
            "schema": "ivanka.px.arm-resource.v1", "tool_id": "skesa",
            "alias": self.ALIAS, "cohort": "synthetic", "outcome": "success",
            "attempt": 1, "peak_rss_bytes": None,
            "peak_ram_observed_mib": None,
        }
        self.diagnostics = {
            "schema": "ivanka.px.diagnostics.v3", "tool_id": "skesa",
            "alias": self.ALIAS, "output_sha256": "a" * 64,
            "runner_receipt_sha256": "b" * 64,
            "metrics": {
                "canonical_micall": {"status": "extracted",
                                     "values": {"average_read_depth": 12.5}},
                "exact_coverage": {"status": "unavailable",
                                   "unavailable_reason": "module unavailable"},
            },
        }
        self._write_all()
        self.evidence = json.loads(
            (SITE / "data/assembler-evidence.json").read_text())
        item = next(item for item in self.evidence["assemblers"]
                    if item["id"] == "skesa")
        item["source_commit"] = "1" * 40
        item["adapter_commit"] = "2" * 40
        item["image_sha256"] = "c" * 64
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
        path.write_text(json.dumps(self.receipt, sort_keys=True))
        (self.root / "receipts" / "index.json").write_text(json.dumps({
            "schema": "ivanka.px.case.receipt-index.v1",
            "entries": {self.name: _sha(path)}}, sort_keys=True))
        (self.root / "results" / (self.name + "-results.json")).write_text(
            json.dumps(self.result, sort_keys=True))
        (self.root / "results" / (self.name + "-resource.json")).write_text(
            json.dumps(self.resource, sort_keys=True))
        (self.root / "diagnostics" / (self.name + ".json")).write_text(
            json.dumps(self.diagnostics, sort_keys=True))

    def test_synthetic_success_uses_frozen_inputs_and_public_score_unit(self):
        evidence, merged, added, _ = ingest(
            self._report(), self.evidence, self.root, self.real)
        self.assertEqual(added, [("skesa", "synthetic", "H192")])
        synthetic = next(run for run in merged["runs"]
                         if run["cohort"] == "synthetic")
        sample = next(row for row in synthetic["samples"]
                      if row["alias"] == "H192")
        self.assertEqual(sample["score"]["skesa"], self.score)
        proof = sample["measurement_evidence"]["skesa"]
        self.assertEqual(proof["canonical_manifest_sha256"], V6_COHORT_SHA)
        self.assertEqual(proof["score_origin"], SYNTHETIC_SCORE)
        self.assertEqual(proof["method"], SYNTHETIC_SCORE)
        self.assertEqual(proof["input_sha256"], self.inputs)
        self.assertIsNone(proof.get("reference_panel_sha256"))
        self.assertIsNone(sample["seconds"]["skesa"])
        self.assertIsNone(sample["diagnostics"]["skesa"][
            "peak_ram_observed_mib"])
        self.assertEqual(synthetic["tool_progress"]["skesa"]["finished"], 1)
        self.assertGreater(validate_publication(merged, evidence), 0)
        _, again, repeated, _ = ingest(merged, evidence, self.root, self.real)
        self.assertEqual(repeated, [])
        self.assertEqual(again, merged)

    def test_unknown_synthetic_alias_is_rejected(self):
        self.receipt["alias"] = "PX-H999"
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "not a canonical synthetic cohort case"):
            ingest(self._report(), self.evidence, self.root, self.real)

    def test_swapped_and_tampered_input_hashes_are_rejected(self):
        cases = json.loads(Path(sched.SYNTHETIC_COHORT).read_bytes())["cases"]
        aliases = sched.canonical_aliases((case["id"] for case in cases),
                                          "synthetic")
        other = next(case for case in cases
                     if aliases[case["id"]] == "PX-H001")
        self.receipt["input_sha256"] = {
            mate: other["sha256"]["reads/" + mate + ".fastq.gz"]
            for mate in ("R1", "R2")}
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "input hash differs from frozen synthetic cohort"):
            ingest(self._report(), self.evidence, self.root, self.real)
        # A tampered hash re-indexed with its receipt still disagrees with the
        # immutable cohort manifest.
        self.receipt["input_sha256"] = dict(self.inputs)
        self.receipt["input_sha256"]["R1"] = "e" * 64
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "input hash differs from frozen synthetic cohort"):
            ingest(self._report(), self.evidence, self.root, self.real)

    def test_declared_truth_hash_must_match_frozen_cohort(self):
        self.result["samples"][0]["truth_sha256"] = "f" * 64
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "truth hash differs from the frozen cohort"):
            ingest(self._report(), self.evidence, self.root, self.real)
        self.result["samples"][0]["truth_sha256"] = self.record[
            "sha256"]["hidden-truth/haplotypes.fasta"]
        self._write_all()
        _, _, added, _ = ingest(
            self._report(), self.evidence, self.root, self.real)
        self.assertEqual(added, [("skesa", "synthetic", "H192")])

    def test_incompatible_score_method_fails_closed(self):
        self.result["samples"][0]["method"] = PHYSICAL_SCORE
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "incompatible with the public synthetic metric"):
            ingest(self._report(), self.evidence, self.root, self.real)
        with self.assertRaisesRegex(ValueError, "prospective posthoc"):
            ingest(self._report(), self.evidence, self.root, self.real)

    def test_unbound_scorer_or_cohort_fails_closed(self):
        self.result["scorer_source_sha256"] = "e" * 64
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "does not verify the frozen truth hash"):
            ingest(self._report(), self.evidence, self.root, self.real)
        self.result["scorer_source_sha256"] = px_posthoc.source_sha256()
        self.result["expected_sample_count"] = 400
        self._write_all()
        with self.assertRaisesRegex(
                ValueError, "frozen 464-case cohort"):
            ingest(self._report(), self.evidence, self.root, self.real)

    def test_terminal_failure_retry_and_null_observation(self):
        self.receipt.update(outcome="failure", failure_reason="identity_lost",
                            output_sha256=None, seconds=None, attempt=1)
        self.resource.update(outcome="failure", attempt=1)
        (self.root / "results" / (self.name + "-results.json")).unlink()
        (self.root / "diagnostics" / (self.name + ".json")).unlink()
        self._write_all()
        _, merged, added, _ = ingest(
            self._report(), self.evidence, self.root, self.real)
        self.assertEqual(added, [])
        synthetic = next(run for run in merged["runs"]
                         if run["cohort"] == "synthetic")
        self.assertEqual(synthetic["tool_progress"]["skesa"]["finished"], 0)

        # A preserved infrastructure failure makes the second attempt accepted.
        (self.root / "receipts" / "attempts" / (
            self.name + ".attempt-001.json")).write_text(
                json.dumps(self.receipt, sort_keys=True))
        self.receipt.update(failure_reason="error", attempt=2)
        self.resource.update(attempt=2)
        self._write_all()
        evidence, merged, added, _ = ingest(
            self._report(), self.evidence, self.root, self.real)
        self.assertEqual(added, [("skesa", "synthetic", "H192")])
        synthetic = next(run for run in merged["runs"]
                         if run["cohort"] == "synthetic")
        row = next(row for row in synthetic["samples"]
                   if row["alias"] == "H192")
        self.assertIn("skesa", row["failures"])
        self.assertIsNone(row["score"]["skesa"])
        self.assertIsNone(row["diagnostics"]["skesa"][
            "peak_ram_observed_mib"])
        proof = row["measurement_evidence"]["skesa"]
        self.assertEqual(proof["canonical_manifest_sha256"], V6_COHORT_SHA)
        self.assertEqual(proof["score_origin"], SYNTHETIC_SCORE)
        self.assertEqual(proof["failure_reason"], "error")
        self.assertEqual(synthetic["tool_progress"]["skesa"]["failed"], 1)
        _, again, repeated, _ = ingest(merged, evidence, self.root,
                                       self.real)
        self.assertEqual(repeated, [])
        self.assertEqual(again, merged)


if __name__ == "__main__":
    unittest.main()
