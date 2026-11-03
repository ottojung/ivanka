"""Fake-data tests for strict, checksum-verified sample recovery."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verified_resume198 as resume


class VerifiedResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sample = "S1"
        self.invocation = "first-run"
        self.folder = self.root / self.invocation / self.sample / "ivanka"
        self.folder.mkdir(parents=True)
        self.conseq = self.folder / "conseq.csv"
        self.conseq.write_text("region,sequence\nR,ACTG\n")
        self.timing = self.folder / "micall_internal_timing.json"
        self.timing.write_text(json.dumps({
            "seconds": 12.3, "exit_code": 0,
            "timing_origin": "micall_in_container_monotonic_v1"}))
        self.provenance = {
            "iva_image_id": "iva", "hxb2_sha256": "hxb2",
            "fastq_sha256": ["r1","r2"],"all_projects":True}
        self.cached_iva = {"artifact_dir": str(self.root / "cache"), "exit_code": 0}
        self.scored = {"reference_panel_sha256": resume.PANEL_SHA256,
                       "pass": True, "iva_score": 40, "ivanka_score": 40}
        self.record = {
            "sample": self.sample, "invocation": self.invocation,
            "status": "finished", "failed": False,
            "iva_baseline_reused": True, "iva": self.cached_iva,
            "provenance": self.provenance, "hxb2_sha256": "hxb2",
            "best_contig_acceptance": self.scored,
            "ivanka": {
                "exit_code": 0, "image_id": "candidate",
                "podman_lifecycle": "serialized_detached_v1",
                "timing_origin": "micall_in_container_monotonic_v1",
                "seconds": 12.3, "container_wall_seconds": 22,
                "artifact_dir": str(self.folder),
                "metrics": {"num_final_max_conseqs": 1, "outputs": {
                    "conseq.csv": {"exists":True,
                                   "sha256": self.hash_file(self.conseq)},
                    "other.csv": {"exists":False}}},
            }}
        self.source = self.root / "results.jsonl"
        self.write_records(self.record)

    @staticmethod
    def hash_file(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()

    def write_records(self, *records):
        self.source.write_text("".join(json.dumps(r)+"\n" for r in records))

    def load(self, files=None):
        with patch.object(resume, "panel_acceptance",
                          return_value=self.scored):
            return resume.load_verified(
                [self.source] if files is None else files,
                [{"sample":self.sample}], lambda row: self.provenance,
                lambda sample, provenance: self.cached_iva,
                "candidate", None, self.hash_file,
                ("conseq.csv", "other.csv"))

    def test_valid_original_artifacts_admitted_with_digest(self):
        result, digests = self.load()
        self.assertEqual(result[self.sample], self.record)
        self.assertEqual(digests[0]["sha256"], self.hash_file(self.source))

    def test_progress_emitted_only_after_successful_authentication(self):
        seen = []
        with patch.object(resume, "panel_acceptance", return_value=self.scored):
            resume.load_verified(
                [self.source], [{"sample": self.sample}],
                lambda row: self.provenance,
                lambda sample, provenance: self.cached_iva,
                "candidate", None, self.hash_file,
                ("conseq.csv", "other.csv"), on_progress=seen.append)
        self.assertEqual(seen, [1])
        self.conseq.write_text("changed")
        seen.clear()
        with patch.object(resume, "panel_acceptance", return_value=self.scored):
            with self.assertRaisesRegex(ValueError, "artifact missing or changed"):
                resume.load_verified(
                    [self.source], [{"sample": self.sample}],
                    lambda row: self.provenance,
                    lambda sample, provenance: self.cached_iva,
                    "candidate", None, self.hash_file,
                    ("conseq.csv", "other.csv"), on_progress=seen.append)
        self.assertEqual(seen, [])

    def test_missing_completed_result_is_not_reused(self):
        self.write_records({"sample":self.sample,"status":"started"})
        result, _ = self.load()
        self.assertEqual(result, {})

    def test_failed_terminal_result_blocks_reuse(self):
        failed = {"sample":self.sample, "status":"error","failed":True}
        self.write_records(self.record, failed)
        result, _ = self.load()
        self.assertEqual(result, {})

    def test_duplicate_success_refused_without_favorable_selection(self):
        self.write_records(self.record, self.record)
        with self.assertRaisesRegex(ValueError,"Duplicate completed"):
            self.load()

    def test_modified_consensus_is_rejected(self):
        self.conseq.write_text("region,sequence\nR,GGGG\n")
        with self.assertRaisesRegex(ValueError,"artifact missing or changed"):
            self.load()

    def test_modified_runtime_is_rejected(self):
        self.timing.write_text(json.dumps({
            "seconds": 8, "exit_code": 0,
            "timing_origin":"micall_in_container_monotonic_v1"}))
        with self.assertRaisesRegex(ValueError,"timing file changed"):
            self.load()

    def test_image_and_provenance_substitution_rejected(self):
        self.record["ivanka"]["image_id"]="other"
        self.write_records(self.record)
        with self.assertRaisesRegex(ValueError,"image or exit"):
            self.load()
        self.record["ivanka"]["image_id"]="candidate"
        self.record["provenance"]={"iva_image_id":"wrong"}
        self.write_records(self.record)
        with self.assertRaisesRegex(ValueError,"provenance differs"):
            self.load()

    def test_unverified_lifecycle_refused(self):
        self.record["ivanka"]["podman_lifecycle"]="unverified"
        self.write_records(self.record)
        with self.assertRaisesRegex(ValueError,"serialized container"):
            self.load()

    def test_cross_invocation_artifact_path_is_rejected(self):
        self.record["invocation"]="different-run"
        self.write_records(self.record)
        with self.assertRaisesRegex(ValueError,"artifact directory"):
            self.load()

    def test_changed_output_presence_refused(self):
        (self.folder/"other.csv").write_text("unexpected")
        with self.assertRaisesRegex(ValueError,"presence changed"):
            self.load()

    def test_unrecognized_sample_refused(self):
        self.write_records({"sample":"unknown","status":"started"})
        with self.assertRaisesRegex(ValueError,"Unknown or malformed"):
            self.load()

    def test_absent_hash_witness_refused(self):
        self.record["ivanka"]["metrics"]["outputs"]["conseq.csv"].pop("sha256")
        self.write_records(self.record)
        with self.assertRaisesRegex(ValueError,"artifact missing or changed"):
            self.load()


    def test_reused_marker_never_masquerades_as_original_artifacts(self):
        self.write_records({"sample":self.sample,"status":"reused_verified",
                            "invocation":"new","original_invocation":"old"})
        result, _ = self.load()
        self.assertEqual(result, {})

    def test_truncated_terminal_line_is_not_admitted(self):
        self.source.write_text(json.dumps(self.record) +
                               '\n{"sample":"S1","status":"fin')
        result, _ = self.load()
        self.assertEqual(result[self.sample], self.record)

    def test_malformed_middle_line_fails_closed(self):
        self.source.write_text('NOT_JSON\n' + json.dumps(self.record) + '\n')
        with self.assertRaisesRegex(ValueError,"Malformed historical result"):
            self.load()



if __name__ == "__main__":
    unittest.main()
