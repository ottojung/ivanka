"""A completed physical run can be extended with Ivanka without rerunning it."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from unittest import TestCase
from unittest.mock import Mock

from benchmarks.expanded.comparators_first_real import TOOLS, row_path
from benchmarks.expanded.real_resume import digest
from benchmarks.real_ivanka.attempt import execute
from benchmarks.real_ivanka.gate import prerequisites
from benchmarks.real_ivanka.replay import recover
from benchmarks.real_ivanka.runner import run


class PhysicalIvankaTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.original = self.root / "physical"
        self.retries = self.root / "retries"
        self.output = self.root / "ivanka"
        self.images = {name: "i" * 64 for name in TOOLS}
        self.images["ivanka"] = "j" * 64

    def fixture(self):
        self.original.mkdir()
        self.retries.mkdir()
        (self.original / "run_manifest.json").write_text(json.dumps({
            "expected_samples": 198, "ivanka_deferred": True,
            "images": {t: self.images[t] for t in TOOLS}}))
        (self.original / "attempt_summary.json").write_text(json.dumps({
            "samples": 198, "tools": list(TOOLS), "ivanka_deferred": True,
            "manifest_sha256": digest(self.original / "run_manifest.json")}))
        (self.retries / "resource_policy_receipt.json").write_text(json.dumps({
            "original_run_manifest_sha256": digest(
                self.original / "run_manifest.json"),
            "original_completed_summary_sha256": digest(
                self.original / "attempt_summary.json"),
            "timeout_seconds": 3000,
            "eligibility": {t: ["s1"] for t in TOOLS}}))
        (self.retries / "attempt_summary.json").write_text(json.dumps({
            "finished": True, "schema":
                "ivanka.expanded.physical-resource-retry.v1",
            "original": str(self.original.resolve()),
            "eligible": {t: 1 for t in TOOLS}}))
        for tool in TOOLS:
            original_dir = self.original / tool / "checkpoints"
            original_dir.mkdir(parents=True)
            for k in range(198):
                (original_dir / f"{k:064x}.json").write_text("{}")
            target = self.retries / tool / "checkpoints"
            target.mkdir(parents=True)
            (target / "sample.json").write_text("{}")

    def test_does_not_start_before_comparators_or_recovery(self):
        with self.assertRaisesRegex(ValueError, "not finished"):
            prerequisites(self.original, self.retries, self.images)
        with self.assertRaisesRegex(ValueError, "not finished"):
            run(None, self.output, self.original, self.retries,
                self.images, None, "8458f9e5d34c39a6694b1fb6a40e055d7ce89553",
                None)

    def test_parent_phase_identity_and_complete_retry_checkpoints(self):
        self.fixture()
        proof = prerequisites(self.original, self.retries, self.images)
        self.assertEqual(len(proof), 3)
        missing = self.retries / TOOLS[0] / "checkpoints" / "sample.json"
        missing.unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            prerequisites(self.original, self.retries, self.images)

    def test_2400_second_ivanka_completion_is_source_verified(self):
        from benchmarks.real_recovery.proof import verify
        import hashlib
        folder = self.output / "artifacts" / "try" / "s1" / "ivanka"
        folder.mkdir(parents=True)
        files = {}
        for i in range(11):
            filename = f"data-{i}.csv"
            contents = f"value,{i}\n".encode()
            (folder / filename).write_bytes(contents)
            files[filename] = {"exists": True,
                               "sha256": hashlib.sha256(contents).hexdigest()}
        (folder / "podman.stderr.log").write_text(
            "MiCall start\nmicall.process_run(): Done.\n")
        (folder / "micall_internal_timing.json").write_text(json.dumps({
            "exit_code": 0, "seconds": 2400.0,
            "timing_origin": "micall_in_container_monotonic_v1"}))
        pmm = Mock()
        pmm.RESULTS = self.output / "artifacts"
        pmm.run_arm.return_value = {
            "image_id": self.images["ivanka"], "exit_code": 0,
            "timing_origin": "micall_in_container_monotonic_v1",
            "seconds": 2400.0, "container_wall_seconds": 2400.5,
            "artifact_dir": str(folder), "metrics": {"outputs": files}}
        pmm.best_panel_alignment.return_value = {"score": 42.0}
        sample = {"sample": "s1", "input_sha256": "reads", "project": ""}
        record = execute(sample, self.images["ivanka"], None, [], pmm,
                         self.output)
        self.assertFalse(record["failed"])
        self.assertEqual(record["measurement"]["seconds"], 2400.0)
        self.assertEqual(pmm.run_arm.call_args.args[4], 3000)
        self.assertIs(verify(record, sample, "ivanka",
                             self.images["ivanka"], [], pmm), record)

    def test_ivanka_failure_is_checkpointed_once_and_recovered(self):
        self.output.mkdir()
        pmm = Mock()
        pmm.RESULTS = self.output / "artifacts"
        pmm.run_arm.return_value = {
            "image_id": self.images["ivanka"], "exit_code": 255,
            "container_wall_seconds": 3000}
        sample = {"sample": "s1", "input_sha256": "reads", "project": ""}
        result = execute(sample, self.images["ivanka"], None, None,
                         pmm, self.output)
        self.assertTrue(result["failed"])
        self.assertEqual(result["resource_timeout_seconds"], 3000)
        source = row_path(self.output / "ivanka", "s1")
        self.assertEqual(json.loads(source.read_text()), result)
        original_hash = digest(source)
        recovered = recover(self.output, [sample], self.images["ivanka"],
                            None, pmm)
        self.assertEqual(recovered, {"s1": result})
        self.assertEqual(digest(source), original_hash)
        recovered_again = recover(self.output, [sample],
                                  self.images["ivanka"], None, pmm)
        self.assertEqual(recovered_again, recovered)
        journal = (self.output / "ivanka" / "results.jsonl").read_text()
        self.assertEqual(len(journal.splitlines()), 1)
        self.assertEqual(pmm.run_arm.call_count, 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
