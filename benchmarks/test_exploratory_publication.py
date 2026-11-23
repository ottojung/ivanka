"""Public PX roster: honest current state and receipt-gated future results."""
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import exploratory_policy
from assembler_bench import exploratory_publication as pub
from assembler_bench.site_build import SITE, validate_public_site

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "benchmarks/assembler_bench/exploratory_candidates.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")
    return path


def registry_copy(root, promotions=None):
    data = json.loads(REGISTRY.read_text())
    for tool, changes in (promotions or {}).items():
        item = next(c for c in data["candidates"] if c["id"] == tool)
        item.update(changes)
    return write_json(root / "registry.json", data)


def receipt(root, item, kind, evidence, extra=None):
    data = {"schema": "ivanka.exploratory." + kind + ".receipt.v1",
            "tool_id": item["id"], "source_commit": item["source_commit"],
            "adapter_commit": item["adapter_commit"],
            "image_sha256": item["image_sha256"], "qualifying": False}
    data.update(extra or {})
    if kind == "image":
        data["native_binary_sha256"] = "a" * 64
    return {"path": str(write_json(
        root / "receipts" / (kind + "-" + item["id"] + ".json"), data)),
        "sha256": sha(root / "receipts" / (kind + "-" + item["id"] + ".json"))}


def results_file(root, item, status, cohort, rows, expected):
    return write_json(root / ("results-" + item["id"] + "-" + cohort + ".json"), {
        "schema": pub.RESULT_SCHEMA, "tool_id": item["id"], "status": status,
        "source_commit": item["source_commit"],
        "adapter_commit": item["adapter_commit"],
        "image_sha256": item["image_sha256"], "cohort": cohort,
        "expected_sample_count": expected, "samples": rows,
    })


class ExploratoryPublicationTests(unittest.TestCase):
    def test_current_snapshot_reports_only_source_pins(self):
        snapshot = pub.build(REGISTRY)
        self.assertEqual(pub.validate(snapshot), 10)
        self.assertEqual(snapshot["status"], "source-pinned-no-results")
        self.assertFalse(snapshot["qualifying"])
        self.assertEqual(len(snapshot["candidates"]), 10)
        for item in snapshot["candidates"]:
            with self.subTest(tool=item["id"]):
                self.assertEqual(item["status"], "source-pinned")
                self.assertIsNone(item["image_sha256"])
                self.assertEqual(item["results_status"], "no-image")
                self.assertEqual(item["samples"], [])
                self.assertFalse(item["qualifying"])
                self.assertFalse(any(item["evidence"].values()))
                self.assertNotIn("results", item)
                self.assertNotIn('"score"', json.dumps(item))
                self.assertNotIn('"seconds"', json.dumps(item))
        self.assertEqual({row["id"] for row in
                          snapshot["blocked_original_candidates"]},
                         {"vicuna", "pehaplo"})

    def test_unrun_candidate_cannot_be_given_metrics_by_editing_data(self):
        snapshot = pub.build(REGISTRY)
        snapshot["candidates"][0]["samples"] = [
            {"alias": "PX-R001", "outcome": "success", "score": 100,
             "seconds": 12}]
        with self.assertRaisesRegex(ValueError, "unrun|fabricated"):
            pub.validate(snapshot)
        snapshot = pub.build(REGISTRY)
        snapshot["candidates"][0]["results_status"] = "verified-benchmark"
        with self.assertRaisesRegex(ValueError, "unbuilt|inconsistent"):
            pub.validate(snapshot)

    def test_status_promotion_requires_a_source_bound_image_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = registry_copy(root, {"skesa": {
                "status": "image-pinned", "image_sha256": "b" * 64}})
            with (patch.object(exploratory_policy, "PROVENANCE_ROOT", root),
                  self.assertRaisesRegex(ValueError, "image proof|image receipt")):
                pub.build(registry)

    def test_image_only_promotion_still_has_no_pilot_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = json.loads(REGISTRY.read_text())
            item = next(c for c in data["candidates"] if c["id"] == "skesa")
            item.update(status="image-pinned", image_sha256="b" * 64,
                        adapter_commit=data["adapter_branch_commits"]["skesa"])
            item["image_evidence"] = receipt(root, item, "image", None)
            registry = write_json(root / "registry.json", data)
            with patch.object(exploratory_policy, "PROVENANCE_ROOT", root):
                snapshot = pub.build(registry)
                pub.validate(snapshot)
            entry = next(c for c in snapshot["candidates"]
                         if c["id"] == "skesa")
            self.assertEqual(entry["results_status"], "image-only")
            self.assertEqual(entry["samples"], [])
            self.assertNotIn("results", entry)

    def test_verified_pilot_and_benchmark_rows_are_published(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = json.loads(REGISTRY.read_text())
            skesa = next(c for c in data["candidates"] if c["id"] == "skesa")
            idba = next(c for c in data["candidates"] if c["id"] == "idba-ud")
            skesa.update(status="pilot", image_sha256="b" * 64,
                         adapter_commit=data["adapter_branch_commits"]["skesa"])
            idba.update(status="benchmarked", image_sha256="c" * 64,
                        adapter_commit=data["adapter_branch_commits"]["idba-ud"])

            physical = results_file(root, skesa, "pilot", "physical", [
                {"alias": "PX-R001", "outcome": "success", "score": 1234.5,
                 "seconds": 88.2},
                {"alias": "PX-R002", "outcome": "failure",
                 "failure_reason": "timeout"}], 198)
            synthetic = results_file(root, skesa, "pilot", "synthetic", [
                {"alias": "PX-H001", "outcome": "success", "score": 99.5,
                 "seconds": 51.0}], 464)
            benchmark = results_file(root, idba, "benchmarked", "synthetic", [
                {"alias": "PX-H001", "outcome": "success", "score": 500,
                 "seconds": 71.5}], 464)
            skesa["image_evidence"] = receipt(root, skesa, "image", None)
            skesa["pilot_evidence"] = receipt(root, skesa, "pilot", None, {
                "physical": {"source_input_sha256": "d" * 64,
                             "status": "success"},
                "synthetic": {"source_input_sha256": "e" * 64,
                              "status": "success"},
                "per_sample_results_sha256": {
                    "physical": sha(physical), "synthetic": sha(synthetic)}})
            idba["image_evidence"] = receipt(root, idba, "image", None)
            idba["pilot_evidence"] = receipt(root, idba, "pilot", None, {
                "physical": {"source_input_sha256": "d" * 64,
                             "status": "success"},
                "synthetic": {"source_input_sha256": "e" * 64,
                              "status": "success"}})
            idba["benchmark_evidence"] = receipt(root, idba, "benchmark", None, {
                "completed_nonqualifying_cohort": True,
                "per_sample_results_sha256": {
                    "synthetic": sha(benchmark)}})
            registry = write_json(root / "registry.json", data)
            mapping = {"skesa": [str(physical), str(synthetic)],
                       "idba-ud": [str(benchmark)]}
            with patch.object(exploratory_policy, "PROVENANCE_ROOT", root):
                snapshot = pub.build(registry, mapping)
                pub.validate(snapshot)
                by_id = {c["id"]: c for c in snapshot["candidates"]}
                self.assertEqual(by_id["skesa"]["results_status"],
                                 "verified-pilot")
                self.assertEqual(len(by_id["skesa"]["samples"]), 3)
                self.assertEqual({s["alias"] for s in
                                  by_id["skesa"]["samples"]},
                                 {"PX-R001", "PX-R002", "PX-H001"})
                self.assertEqual(by_id["idba-ud"]["results_status"],
                                 "verified-benchmark")
                self.assertEqual(by_id["idba-ud"]["samples"][0]["score"], 500)
                self.assertIsNone(by_id["idba-ud"]["samples"][0].get(
                    "failure_reason"))
                self.assertEqual(by_id["minia"]["results_status"],
                                 "no-image")
                site = Path(temp) / "site"
                shutil.copytree(SITE, site)
                (site / pub.DATA_FILE).write_text(
                    json.dumps(snapshot, sort_keys=True) + "\n")
                validate_public_site(site)

    def test_changed_results_no_longer_match_the_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = json.loads(REGISTRY.read_text())
            item = next(c for c in data["candidates"] if c["id"] == "skesa")
            item.update(status="pilot", image_sha256="b" * 64,
                        adapter_commit=data["adapter_branch_commits"]["skesa"])
            item["image_evidence"] = receipt(root, item, "image", None)
            item["pilot_evidence"] = receipt(root, item, "pilot", None, {
                "physical": {"source_input_sha256": "d" * 64,
                             "status": "success"},
                "synthetic": {"source_input_sha256": "e" * 64,
                              "status": "success"},
                "per_sample_results_sha256": {"physical": "a" * 64}})
            registry = write_json(root / "registry.json", data)
            rows = [{"alias": "PX-R001", "outcome": "success", "score": 5,
                     "seconds": 2}]
            results = results_file(root, item, "pilot", "physical", rows, 198)
            rows.append({"alias": "PX-R002", "outcome": "success", "score": 6,
                         "seconds": 3})
            write_json(results, {
                "schema": pub.RESULT_SCHEMA, "tool_id": item["id"],
                "status": "pilot", "source_commit": item["source_commit"],
                "adapter_commit": item["adapter_commit"],
                "image_sha256": item["image_sha256"], "cohort": "physical",
                "expected_sample_count": 198, "samples": rows})
            with (patch.object(exploratory_policy, "PROVENANCE_ROOT", root),
                  self.assertRaisesRegex(ValueError, "differ from attested")):
                pub.build(registry, {"skesa": [str(results)]})

    def test_publisher_writes_only_the_new_public_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp) / "site"
            shutil.copytree(SITE, site)
            frozen = ("data/runs.json", "data/history.json",
                      "data/mapping-diagnostics.json",
                      "data/live-fork-attestation.json")
            before = {name: sha(site / name) for name in frozen}
            snapshot = pub.publish(site, REGISTRY)
            self.assertEqual(pub.validate(snapshot), 10)
            for name, value in before.items():
                self.assertEqual(sha(site / name), value, name)
            self.assertFalse(list((site / "data").glob("*.pending")))
            written = json.loads((site / pub.DATA_FILE).read_text())
            self.assertEqual(written, snapshot)
            validate_public_site(site)

    def test_browser_renders_honest_state_and_only_verified_rows(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        with tempfile.TemporaryDirectory() as temp:
            verified = Path(temp) / "verified.json"
            snapshot = copy.deepcopy(pub.build(REGISTRY))
            item = snapshot["candidates"][0]
            item["status"] = "pilot"
            item["image_sha256"] = "b" * 64
            item["evidence"]["image_receipt_verified"] = True
            item["evidence"]["pilot_receipt_verified"] = True
            item["results_status"] = "verified-pilot"
            item["results"] = {"evidence_sha256": "d" * 64,
                               "results_sha256": {"physical": "e" * 64},
                               "cohorts": ["physical"],
                               "expected_sample_count": {"physical": 198}}
            item["samples"] = [{"alias": "PX-R001", "outcome": "success",
                                "score": 145.5, "seconds": 72.25}]
            write_json(verified, snapshot)
            code = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const P=require(process.argv[1]);
const current=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const verified=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const mount={innerHTML:'',textContent:''},context={textContent:''};
P.render(current,mount,context);
assert.equal(current.candidates.length,10);
assert(mount.innerHTML.includes('No image built'));
assert(!mount.innerHTML.includes('PX-R001'));
assert(!mount.innerHTML.includes('align'));
assert(context.textContent.includes('0 qualifying'));
P.render(verified,mount,context);
assert(mount.innerHTML.includes('PX-R001'));
assert(mount.innerHTML.includes('145.5'));
assert(mount.innerHTML.includes('72.25'));
assert(mount.innerHTML.includes('Pilot verified'));
assert(context.textContent.includes('1 with receipt-verified cases'));
console.log('PX_ROSTER_RENDER_OK');
"""
            process = subprocess.run(
                [node, "-e", code, str(ROOT / "site/bench/exploratory.js"),
                 str(SITE / pub.DATA_FILE), str(verified)],
                capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn("PX_ROSTER_RENDER_OK", process.stdout)


if __name__ == "__main__":
    unittest.main()
