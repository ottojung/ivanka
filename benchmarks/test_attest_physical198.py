"""Negative controls for read-only physical 198-sample attestation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import attest_physical198 as audit
from milestone198 import IVA_IMAGE_SHA256
from podman_full_micall import sha


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


if __name__ == "__main__":
    unittest.main()
