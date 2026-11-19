"""Regression tests for source-frozen, six-first synthetic orchestration."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from assembler_bench import six_comparators_first as stage
from expanded.adapters import ASSEMBLERS
from expanded.micall_checkpoint import identity
from expanded.micall_dominant import MULTITRUTH_SCORE_ORIGIN
from expanded.micall_synthetic_constants import TIMING_ORIGIN


class SixFirstTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.images = {t: (str(i + 1) * 64)[:64]
                       for i, t in enumerate(ASSEMBLERS)}
        self.truth = {"schema": "ivanka.mixed_viral_truth_validation.v4"}
        self.manifest = {
            "family": "clonal", "score_model_revision": 2,
            "sha256": {"reads/R1.fastq.gz": "abc",
                       "reads/R2.fastq.gz": "def"}}
        self.case = ("clonal-s007", self.root / "data", self.manifest)
        self.fields = identity(self.case[0], self.manifest, self.truth)
        self.manifest_sha = "f" * 64
        self.case_dir = self.root / self.case[0]

    def arm(self, tool, *, success=True):
        folder = self.case_dir / tool
        folder.mkdir(parents=True, exist_ok=True)
        record = {
            "sha256": self.images[tool],
            "score_origin": MULTITRUTH_SCORE_ORIGIN,
            "timing_origin": TIMING_ORIGIN,
            "status": "success" if success else "failed",
            "argv": ["podman", self.images[tool], "--all_projects"],
            "exit_code": 0 if success else 255,
        }
        if success:
            p = folder / "conseq.csv"
            p.write_bytes(b"ref,cov\nHXB2,1\n")
            record.update({
                "seconds": 1.0,
                "final_dominant": {
                    "source_output": "conseq.csv",
                    "conseq_csv_sha256": hashlib.sha256(p.read_bytes()).hexdigest()},
            })
        (folder / "execution.json").write_text(json.dumps(record))
        return record

    def fake_attempt(self, case, folder, tool, image, timeout):
        self.assertEqual(timeout, 3000)
        self.assertEqual(image, self.images[tool])
        self.assertNotEqual(tool, "ivanka")
        return self.arm(tool)

    def test_partial_arms_resume_without_any_ivanka_or_rerun(self):
        self.arm("iva")
        self.arm("spades", success=False)
        broken = self.case_dir / "velvet"
        broken.mkdir()
        (broken / "half-written.log").write_text("keep")
        with patch.object(stage, "attempt", side_effect=self.fake_attempt) as mocked:
            case, proof = stage.run_one(
                self.case, self.root, self.images,
                self.truth, self.manifest_sha)
        self.assertEqual(case, self.case[0])
        self.assertEqual(mocked.call_count, 4)
        self.assertFalse((self.case_dir / "ivanka").exists())
        self.assertTrue((self.case_dir / "_interrupted" /
                         "velvet-001/half-written.log").is_file())
        self.assertEqual(proof["statuses"]["spades"], "failed")
        self.assertEqual(set(proof["arms_sha256"]), set(stage.SIX))
        self.assertEqual(stage.verify_case(
            self.case_dir, self.fields, self.images,
            MULTITRUTH_SCORE_ORIGIN, self.manifest_sha), proof)
        with patch.object(stage, "attempt", side_effect=AssertionError):
            self.assertEqual(stage.run_one(
                self.case, self.root, self.images, self.truth,
                self.manifest_sha)[1], proof)

    def test_complete_seven_case_preserved_byte_for_byte(self):
        results = {tool: self.arm(tool) for tool in ASSEMBLERS}
        row = {**self.fields, "execution_order": list(ASSEMBLERS),
               "results": results}
        matrix = self.case_dir / "matrix.json"
        original = json.dumps(row, sort_keys=True) + "\n"
        matrix.write_text(original)
        with patch.object(stage, "attempt", side_effect=AssertionError):
            stage.run_one(self.case, self.root, self.images,
                          self.truth, self.manifest_sha)
        self.assertEqual(matrix.read_text(), original)
        self.assertEqual(results["ivanka"], json.loads(
            (self.case_dir / "ivanka/execution.json").read_text()))

    def test_tampering_with_six_arm_blocks_reuse(self):
        for t in stage.SIX:
            self.arm(t)
        stage.run_one(self.case, self.root, self.images,
                      self.truth, self.manifest_sha)
        p = self.case_dir / "iva/conseq.csv"
        p.write_text("altered")
        with self.assertRaises(ValueError):
            stage.run_one(self.case, self.root, self.images,
                          self.truth, self.manifest_sha)

    def test_only_verified_success_scratch_is_removed_and_failure_retained(self):
        for tool in stage.SIX:
            self.arm(tool, success=tool != "haploflow")
            scratch = self.case_dir / tool / "scratch"
            scratch.mkdir()
            (scratch / "expensive.tmp").write_bytes(b"reproducible"*100)
        _, proof = stage.run_one(
            self.case, self.root, self.images, self.truth,
            self.manifest_sha)
        for tool in stage.SIX:
            scratch = self.case_dir / tool / "scratch"
            if tool == "haploflow":
                self.assertTrue((scratch / "expensive.tmp").exists())
            else:
                self.assertFalse(scratch.exists())
            self.assertEqual(
                json.loads((self.case_dir / tool / "execution.json").read_text())
                ["status"], proof["statuses"][tool])
        self.assertTrue(stage.verify_case(
            self.case_dir, self.fields, self.images,
            MULTITRUTH_SCORE_ORIGIN, self.manifest_sha))
        with patch.object(stage, "attempt", side_effect=AssertionError):
            stage.run_one(self.case, self.root, self.images,
                          self.truth, self.manifest_sha)

    def test_invalid_six_evidence_cannot_delete_scratch(self):
        for tool in stage.SIX:
            self.arm(tool)
        scratch = self.case_dir / "iva/scratch"
        scratch.mkdir()
        (scratch / "keep.tmp").write_text("preserve")
        _, proof = stage.run_one(
            self.case, self.root, self.images, self.truth,
            self.manifest_sha)
        scratch.mkdir()
        (scratch / "keep.tmp").write_text("preserve")
        (self.case_dir / "iva/execution.json").write_text("tampered")
        with self.assertRaises(ValueError):
            stage.prune_verified_six(self.case_dir, proof, self.images,
                                     MULTITRUTH_SCORE_ORIGIN,
                                     self.manifest_sha)
        self.assertEqual((scratch / "keep.tmp").read_text(), "preserve")

    def test_interrupted_sidecar_write_is_preserved_on_resume(self):
        for t in stage.SIX:
            self.arm(t)
        temporary = self.case_dir / "six_arms.json.partial"
        temporary.write_text('{"incomplete":')
        _, result = stage.run_one(self.case, self.root, self.images,
                                  self.truth, self.manifest_sha)
        self.assertEqual(result["schema"], stage.SCHEMA)
        self.assertEqual(
            (self.case_dir / "six_arms.json.partial.interrupted-001").read_text(),
            '{"incomplete":')

    def test_complete_464_six_proofs_authorize_ivanka_gate(self):
        original = self.root / "run_manifest.json"
        original.write_text(json.dumps({
            "images": self.images, "truth_proof": self.truth}))
        original_sha = stage.digest(original)
        hashes = {}
        for i in range(464):
            identifier = f"clonal-s{i:03d}"
            self.case_dir = self.root / identifier
            for tool in stage.SIX:
                self.arm(tool, success=False)
            _, proof = stage.run_one(
                (identifier, self.case[1], self.manifest),
                self.root, self.images, self.truth, original_sha)
            self.assertEqual(proof["qualification"], "INCOMPLETE_UNTIL_IVANKA")
            hashes[identifier] = stage.digest(self.case_dir / "six_arms.json")
        stage.save_json(self.root / stage.SUMMARY, {
            "schema": stage.SCHEMA,
            "cases": 464, "tools_per_case": 6,
            "source_manifest_sha256": original_sha,
            "stage_source_sha256": stage.digest(stage.SOURCE),
            "case_checkpoints_sha256": hashes,
            "failed_comparator_arms": 464 * 6,
            "status": "SIX_TERMINAL_IVANKA_DEFERRED",
        })
        self.assertTrue(stage.verify_existing(self.root, self.images))
        self.assertFalse((self.root / "clonal-s017/ivanka").exists())
        (self.root / "clonal-s017/spades/execution.json").write_text(
            "tampered")
        with self.assertRaises(ValueError):
            stage.verify_existing(self.root, self.images)

    def test_zero_synthetic_seven_success_is_not_qualification(self):
        for t in stage.SIX:
            self.arm(t, success=False)
        _, proof = stage.run_one(self.case, self.root, self.images,
                                self.truth, self.manifest_sha)
        self.assertEqual(proof["qualification"], "INCOMPLETE_UNTIL_IVANKA")
        self.assertEqual(set(proof["statuses"]), set(ASSEMBLERS) - {"ivanka"})
        self.assertFalse((self.case_dir / "matrix.json").exists())

    def test_disk_headroom_fails_closed_without_touching_results(self):
        with patch.object(stage.os, "statvfs") as stats:
            stats.return_value.f_bavail = 20 * 1024**3 - 1
            stats.return_value.f_frsize = 1
            with self.assertRaisesRegex(OSError, "paused"):
                stage.ensure_disk_capacity(self.root)
        with patch.object(stage.os, "statvfs") as stats:
            stats.return_value.f_bavail = 20 * 1024**3
            stats.return_value.f_frsize = 1
            self.assertEqual(stage.ensure_disk_capacity(self.root), 20*1024**3)

    def test_two_worker_queue_stops_scheduling_when_disk_low(self):
        data = self.root / "source_data"
        data.mkdir()
        (data / "cohort.json").write_text("{}")
        out = self.root / "synthetic_output"
        out.mkdir()
        image_manifest = {"images": self.images}
        (out / "run_manifest.json").write_text(json.dumps(image_manifest))
        cases = [(f"clonal-s{i:03d}", data, self.manifest) for i in range(464)]
        invoked = []
        checked = 0

        def capacity(_):
            nonlocal checked
            checked += 1
            if checked > 2:
                raise OSError("disk below threshold")
            return 80 * 1024**3

        def execute(row, *_):
            invoked.append(row[0])
            return row[0], {"statuses": {tool: "success" for tool in stage.SIX}}

        with (patch.object(stage, "checked_images"),
              patch.object(stage, "attestation", return_value=self.truth),
              patch.object(stage, "cohort_rows", return_value=cases),
              patch.object(stage, "manifest", return_value=image_manifest),
              patch.object(stage, "run_one", side_effect=execute),
              patch.object(stage, "ensure_disk_capacity", side_effect=capacity),
              patch.object(stage, "verify_all", side_effect=AssertionError)):
            with self.assertRaisesRegex(OSError, "disk below threshold"):
                stage.run(data, out, self.images, data, "base", data, jobs=2)
        self.assertEqual(sorted(invoked),
                         ["clonal-s000", "clonal-s001"])
        self.assertFalse((out / stage.SUMMARY).exists())

    def test_requires_exact_six_arm_and_source(self):
        self.arm("iva")
        self.assertIsNone(stage.arm_records(
            self.case_dir, self.images, MULTITRUTH_SCORE_ORIGIN))
        with self.assertRaises(ValueError):
            stage.run_one(self.case, self.root, {**self.images, "iva": "wrong"},
                          self.truth, self.manifest_sha)


if __name__ == "__main__":
    unittest.main()
