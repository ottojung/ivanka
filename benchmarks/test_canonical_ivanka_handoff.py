"""The 50-minute canonical Ivanka runner satisfies the physical-first gate."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
import hashlib
import json

from benchmarks.expanded.comparators_first_real import PANEL, SCHEMA, TOOLS, row_path
from benchmarks.expanded.real_resume import digest
from benchmarks.real_ivanka.canonical import run, priority_module


class CanonicalHandoffTests(TestCase):
    def test_reuses_198_arm_checkpoints_and_issues_existing_completion_proof(self):
        with TemporaryDirectory() as tmp:
            original = Path(tmp) / "phase-real198"
            retry = Path(tmp) / "retries"
            original.mkdir()
            retry.mkdir()
            images = {tool: hashlib.sha256(tool.encode()).hexdigest()
                      for tool in (*TOOLS, "ivanka")}
            manifest = {"schema": SCHEMA, "expected_samples": 198,
                        "ivanka_deferred": True,
                        "images": {tool: images[tool] for tool in TOOLS}}
            (original / "run_manifest.json").write_text(json.dumps(manifest))
            (original / "attempt_summary.json").write_text(json.dumps({
                "schema": SCHEMA, "samples": 198, "tools": list(TOOLS),
                "ivanka_deferred": True,
                "manifest_sha256": digest(original / "run_manifest.json")}))
            eligibility = {tool: [] for tool in TOOLS}
            (retry / "resource_policy_receipt.json").write_text(json.dumps({
                "original_run_manifest_sha256": digest(original / "run_manifest.json"),
                "original_completed_summary_sha256":
                    digest(original / "attempt_summary.json"),
                "timeout_seconds": 3000, "eligibility": eligibility}))
            (retry / "attempt_summary.json").write_text(json.dumps({
                "schema": "ivanka.expanded.physical-resource-retry.v1",
                "finished": True, "original": str(original),
                "eligible": {tool: 0 for tool in TOOLS}}))
            for tool in TOOLS:
                folder = original / tool / "checkpoints"
                folder.mkdir(parents=True)
                for n in range(198):
                    (folder / f"{n:064x}.json").write_text("{}")
            cases = []
            checkpoint_hashes = {}
            for n in range(198):
                sample = f"s{n:03d}"
                row = {"sample": sample, "input_sha256": f"read{n}"}
                cases.append(row)
                result = {"sample": sample, "input_sha256": row["input_sha256"],
                          "tool": "ivanka", "image_id": images["ivanka"],
                          "reference_panel_sha256": PANEL, "status": "finished",
                          "failed": True, "arm": {"image_id": images["ivanka"],
                          "exit_code": 255}, "measurement": None,
                          "error": "reusable failed attempt",
                          "resource_timeout_seconds": 3000}
                path = row_path(original / "ivanka", sample)
                path.parent.mkdir(exist_ok=True, parents=True)
                path.write_text(json.dumps(result))
                checkpoint_hashes[sample] = digest(path)
            pmm = Mock()
            pmm.RESULTS = original / "artifacts"
            with patch("benchmarks.real_ivanka.canonical.prepare",
                       return_value=(cases, None, [], pmm)):
                result = run(None, original, retry, images, None,
                             "8458f9e5d34c39a6694b1fb6a40e055d7ce89553",
                             "/workspace/micall-frozen-seven-20261117"
                             "/minimal-images-attestation-v2.json")
                self.assertEqual(result, "COMPLETE")
                self.assertTrue(priority_module().completed(original, images))
                self.assertFalse(pmm.run_arm.called)
                for sample in (cases[0]["sample"], cases[-1]["sample"]):
                    self.assertEqual(digest(row_path(original/"ivanka", sample)),
                                     checkpoint_hashes[sample])
                self.assertEqual(
                    json.loads((original/"ivanka/attempt_summary.json").read_text()
                              )["resource_budget_seconds"], 3000)
                self.assertEqual(json.loads(
                    (original/"run_manifest.json").read_text()), manifest)
