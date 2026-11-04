"""Negative controls for read-only physical 198-sample attestation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import attest_physical198 as audit
from milestone198 import IVA_IMAGE_SHA256
from attest_physical198 import sha


class Physical198AttestationTests(unittest.TestCase):
    def test_event_log_requires_matching_start_finish_and_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.jsonl"
            starts = [{"sample": n, "status": "started", "invocation": "run"}
                      for n in ("S1", "S2")]
            ends = [{"sample": n, "status": "finished", "invocation": "run"}
                    for n in ("S1", "S2")]
            def write(rows):
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with patch.object(audit, "SAMPLE_COUNT", 2):
                write(starts + ends)
                self.assertEqual(len(audit.completed_events(path, "run", ["S1", "S2"])), 2)
                write(starts + [ends[0], ends[0]])
                with self.assertRaises(ValueError):
                    audit.completed_events(path, "run", ["S1", "S2"])
                write(starts + [ends[0], dict(ends[1], invocation="other")])
                with self.assertRaises(ValueError):
                    audit.completed_events(path, "run", ["S1", "S2"])
                write(starts + ends[:1])
                with self.assertRaises(ValueError):
                    audit.completed_events(path, "run", ["S1", "S2"])
                write(starts + [ends[0], dict(ends[1], status="failed")])
                with self.assertRaises(ValueError):
                    audit.completed_events(path, "run", ["S1", "S2"])

    def test_final_consensus_and_cached_control_are_attested(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            results, cache = base / "results", base / "cache"
            folder = results / "run" / "S1" / "ivanka"
            original = cache / "S1"
            folder.mkdir(parents=True)
            original.mkdir(parents=True)
            (folder / "conseq.csv").write_text("candidate")
            (original / "conseq.csv").write_text("iva")
            candidate_hash = sha(folder / "conseq.csv")
            iva_hash = sha(original / "conseq.csv")
            evidence = {"fastq_sha256": ["a" * 64, "b" * 64]}
            control = {"provenance": evidence, "iva": {
                "image_id": IVA_IMAGE_SHA256, "metrics": {
                    "outputs": {"conseq.csv": {"sha256": iva_hash}}}}}
            (original / "baseline.json").write_text(json.dumps(control))
            record = {"sample": "S1", "provenance": evidence,
                      "iva": {"image_id": IVA_IMAGE_SHA256, "metrics": {
                          "outputs": {"conseq.csv": {"sha256": iva_hash}}}},
                      "ivanka": {"image_id": "c" * 64,
                          "artifact_dir": str(folder), "metrics": {
                              "outputs": {"conseq.csv": {"sha256": candidate_hash}}}}}
            audit.verify_pair(record, results, cache, "run", "c" * 64)
            (folder / "conseq.csv").write_text("changed")
            with self.assertRaisesRegex(ValueError, "modified"):
                audit.verify_pair(record, results, cache, "run", "c" * 64)
            (folder / "conseq.csv").write_text("candidate")
            outside = base / "outside.csv"
            outside.write_text("candidate")
            (folder / "conseq.csv").unlink()
            (folder / "conseq.csv").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "modified"):
                audit.verify_pair(record, results, cache, "run", "c" * 64)
            (folder / "conseq.csv").unlink()
            (folder / "conseq.csv").write_text("candidate")
            (original / "conseq.csv").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "modified"):
                audit.verify_pair(record, results, cache, "run", "c" * 64)
            (original / "conseq.csv").write_text("iva")
            record["provenance"] = {"fastq_sha256": ["wrong"]}
            with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                audit.verify_pair(record, results, cache, "run", "c" * 64)
            record["provenance"] = evidence
            record["ivanka"]["artifact_dir"] = str(base)
            with self.assertRaisesRegex(ValueError, "escaped"):
                audit.verify_pair(record, results, cache, "run", "c" * 64)

    def test_incomplete_physical_run_fails_before_claiming_success(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            manifest = base / "manifest.tsv"
            manifest.write_text("sample\nS1\n")
            state = base / "state"
            state.mkdir()
            with patch.object(audit, "sha", return_value=audit.MANIFEST_SHA256):
                with self.assertRaisesRegex(ValueError, "Frozen cohort"):
                    audit.verify(base, state, manifest, base / "cache", "run")
            manifest.write_text("sample\n" + "".join("S" + str(i) + "\n" for i in range(198)))
            with patch.object(audit, "sha", return_value=audit.MANIFEST_SHA256):
                with self.assertRaisesRegex(ValueError, "Physical runner did not finish"):
                    audit.verify(base, state, manifest, base / "cache", "run")


    def test_prior_attestation_pins_both_immutable_logs_and_recorded_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary_path = root / "summary-run.json"
            results_path = root / "results.jsonl"
            summary = {"score_psi": {"psi1": 3},
                       "time_psi": {"psi1": 5}}
            summary_path.write_text(json.dumps(summary))
            results_path.write_text("original-records")
            image = "c" * 64
            prior = {
                "attestation": "read_only_artifact_integrity_and_recorded_psi",
                "pass": True, "invocation": "run",
                "verified_samples": audit.SAMPLE_COUNT,
                "original_iva_image_id": audit.IVA_IMAGE_SHA256,
                "candidate_image_id": image,
                "manifest_sha256": audit.MANIFEST_SHA256,
                "reference_panel_sha256": audit.PANEL_SHA256,
                "results_sha256": sha(results_path),
                "summary_sha256": sha(summary_path),
                **summary,
            }
            attestation = root / "prior.json"
            attestation.write_text(json.dumps(prior))
            def verify():
                audit.validate_prior_attestation(attestation, root,
                                                 summary_path, summary, "run", image)
            verify()
            results_path.write_text("tampered-records")
            with self.assertRaisesRegex(ValueError, "does not pin"):
                verify()
            results_path.write_text("original-records")
            prior["score_psi"] = {"psi1": -1}
            attestation.write_text(json.dumps(prior))
            with self.assertRaisesRegex(ValueError, "does not pin"):
                verify()
            prior["score_psi"] = summary["score_psi"]
            prior["pass"] = False
            attestation.write_text(json.dumps(prior))
            with self.assertRaisesRegex(ValueError, "does not pin"):
                verify()


if __name__ == "__main__":
    unittest.main()
