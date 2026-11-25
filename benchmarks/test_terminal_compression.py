"""Automatic, fail-closed lossless compression at terminal scratch retirement."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import retained_artifacts
from retained_artifacts import (
    RetentionGateError, compress_retained_tables, content_sha256,
    seal_terminal_evidence, terminal_retire)

TABLE = "genome_coverage.csv"


def digest(data):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def compressible_text(rows=20000):
    return "ref,coverage\n" + "".join(
        "position-%06d,12\n" % i for i in range(rows))


class TerminalCompressionTests(unittest.TestCase):
    def _arm(self, folder, text, *, in_scratch=True):
        arm = Path(folder) / "arm"
        destination = arm / "scratch" if in_scratch else arm
        destination.mkdir(parents=True, exist_ok=True)
        (destination / TABLE).write_text(text)
        (arm / "podman.stderr.log").write_text("failure log")
        return arm

    def _evidence(self, arm, text=None, *, sha=None, hashes=None):
        hashes = hashes or {"input.fastq.gz": "a" * 64}
        sha = sha if sha is not None else digest(text)
        evidence, _ = seal_terminal_evidence(
            arm, {"metrics": {"outputs": {TABLE: {"sha256": sha}}}}, hashes)
        return evidence, hashes

    def test_seal_and_teardown_precede_compression(self):
        """(a) Evidence is sealed and scratch gone before any codec runs."""
        text = compressible_text()
        with TemporaryDirectory() as d:
            arm = self._arm(d, text)
            evidence, hashes = self._evidence(arm, text)
            probe = []

            def dead():
                probe.append(True)
                return True

            original = retained_artifacts.compress_retained_tables
            observations = []

            def observing(*args, **kwargs):
                seal = arm / "terminal_evidence.json"
                side = Path(str(seal) + ".sha256")
                observations.append({
                    "sealed": side.read_text().strip() == digest(seal.read_bytes()),
                    "scratch_gone": not (arm / "scratch").exists(),
                    "dead_calls": len(probe),
                })
                return original(*args, **kwargs)

            with patch.object(retained_artifacts, "compress_retained_tables",
                              observing):
                report = terminal_retire(arm, evidence_path=evidence,
                                         container_dead=dead,
                                         source_hashes=hashes)
            self.assertEqual(len(observations), 1)
            self.assertTrue(observations[0]["sealed"])
            self.assertTrue(observations[0]["scratch_gone"])
            self.assertGreaterEqual(observations[0]["dead_calls"], 1)
            self.assertIn(TABLE, report["compression"]["compressed"])
            self.assertTrue((arm / (TABLE + ".zst")).is_file())
            self.assertTrue((arm / (TABLE + ".zst.meta.json")).is_file())

    def test_no_compression_while_alive_or_unsealed(self):
        """(b) Liveness and seal failures leave the plain table alone."""
        text = compressible_text(rows=100)
        with TemporaryDirectory() as d:
            arm = self._arm(d, text, in_scratch=False)
            evidence, hashes = self._evidence(arm, text)
            with self.assertRaisesRegex(RetentionGateError, "dead container"):
                compress_retained_tables(
                    arm, evidence=json.loads(evidence.read_text()),
                    container_dead=False, root=arm)
            unsealed = {"metrics": json.loads(evidence.read_text())["metrics"]}
            with self.assertRaisesRegex(RetentionGateError, "sealed"):
                compress_retained_tables(arm, evidence=unsealed,
                                         container_dead=True, root=arm)
            self.assertEqual((arm / TABLE).read_text(), text)
            self.assertFalse((arm / (TABLE + ".zst")).exists())
            self.assertFalse((arm / (TABLE + ".zst.meta.json")).exists())
            with self.assertRaises(RetentionGateError):
                terminal_retire(arm, evidence_path=evidence,
                                container_dead=False, source_hashes=hashes)
            self.assertFalse((arm / (TABLE + ".zst")).exists())

    def test_shrink_only_retention_and_no_gain(self):
        """(c) A real shrink is kept; an allocated no-gain keeps the original."""
        with self.subTest(case="shrink"), TemporaryDirectory() as d:
            text = compressible_text()
            arm = self._arm(d, text)
            evidence, hashes = self._evidence(arm, text)
            report = terminal_retire(arm, evidence_path=evidence,
                                     container_dead=True, source_hashes=hashes)
            self.assertIn(TABLE, report["compression"]["compressed"])
            self.assertGreater(report["compression"]["bytes_saved"], 0)
            self.assertFalse((arm / TABLE).exists())
            compressed = arm / (TABLE + ".zst")
            self.assertEqual(content_sha256(compressed), digest(text))
            self.assertEqual(report["verified_outputs"], 1)
        with self.subTest(case="no_gain"), TemporaryDirectory() as d:
            arm = self._arm(d, "x", in_scratch=False)
            # Random bytes are incompressible: the codec pair cannot be
            # smaller than the original in allocated blocks.
            payload = os.urandom(256 * 1024)
            (arm / TABLE).write_bytes(payload)
            evidence, _ = self._evidence(arm, sha=digest(payload))
            report = compress_retained_tables(
                arm, evidence=json.loads(evidence.read_text()),
                container_dead=True, root=arm)
            self.assertEqual(report["compressed"], [])
            self.assertEqual(len(report["no_gain"]), 1)
            self.assertEqual(report["no_gain"][0]["name"], TABLE)
            self.assertGreaterEqual(report["no_gain"][0]["compressed_bytes"],
                                    report["no_gain"][0]["plain_bytes"])
            self.assertEqual((arm / TABLE).read_bytes(), payload)
            self.assertFalse((arm / (TABLE + ".zst")).exists())
            self.assertFalse((arm / (TABLE + ".zst.meta.json")).exists())

    def test_receipt_bound_hash_and_corrupt_sidecar_fail_closed(self):
        """(d) Shared reader re-verifies the sealed digest; proof drift is fatal."""
        from compressed_tables import compress_table
        text = compressible_text(rows=500)
        with self.subTest(case="drift"), TemporaryDirectory() as d:
            arm = self._arm(d, text, in_scratch=False)
            evidence, _ = self._evidence(arm, sha="0" * 64)
            with self.assertRaisesRegex(RetentionGateError, "digest drift"):
                compress_retained_tables(
                    arm, evidence=json.loads(evidence.read_text()),
                    container_dead=True, root=arm)
            self.assertEqual((arm / TABLE).read_text(), text)
            self.assertFalse((arm / (TABLE + ".zst")).exists())
        with self.subTest(case="corrupt_sidecar"), TemporaryDirectory() as d:
            arm = self._arm(d, text, in_scratch=False)
            evidence, _ = self._evidence(arm, text)
            compress_table(arm / TABLE, keep_plain=True)
            proof_path = arm / (TABLE + ".zst.meta.json")
            proof = json.loads(proof_path.read_text())
            proof["original_sha256"] = "1" * 64
            proof_path.write_text(json.dumps(proof, sort_keys=True) + "\n")
            with self.assertRaisesRegex(RetentionGateError, "proof failed"):
                compress_retained_tables(
                    arm, evidence=json.loads(evidence.read_text()),
                    container_dead=True, root=arm)
            self.assertEqual((arm / TABLE).read_text(), text)
            self.assertTrue((arm / (TABLE + ".zst")).is_file())

    def test_idempotent_replay_keeps_seal_and_tables(self):
        """(e) A second terminal pass changes nothing and keeps the seal bytes."""
        text = compressible_text()
        with TemporaryDirectory() as d:
            arm = self._arm(d, text)
            evidence, hashes = self._evidence(arm, text)
            first = terminal_retire(arm, evidence_path=evidence,
                                    container_dead=True, source_hashes=hashes)
            self.assertIn(TABLE, first["compression"]["compressed"])
            compressed = arm / (TABLE + ".zst")
            proof = arm / (TABLE + ".zst.meta.json")
            before = (compressed.read_bytes(), proof.read_bytes(),
                      (arm / "terminal_evidence.json").read_bytes(),
                      (arm / "terminal_evidence.json.sha256").read_bytes())
            second = terminal_retire(arm, evidence_path=evidence,
                                     container_dead=True, source_hashes=hashes)
            self.assertFalse(second["retired"])
            self.assertIn(TABLE, second["compression"]["already_compressed"])
            self.assertEqual(second["compression"]["compressed"], [])
            self.assertEqual(second["compression"]["bytes_saved"], 0)
            after = (compressed.read_bytes(), proof.read_bytes(),
                     (arm / "terminal_evidence.json").read_bytes(),
                     (arm / "terminal_evidence.json.sha256").read_bytes())
            self.assertEqual(before, after)

    def test_symlink_escape_is_refused(self):
        """(f) Neither plain nor compressed variants may escape the arm."""
        text = compressible_text(rows=100)
        with self.subTest(case="plain_symlink"), TemporaryDirectory() as d:
            arm = self._arm(d, text, in_scratch=False)
            outside = Path(d) / "outside.csv"
            outside.write_text(text)
            (arm / TABLE).unlink()
            (arm / TABLE).symlink_to(outside)
            evidence, _ = self._evidence(arm, text)
            with self.assertRaisesRegex(RetentionGateError, "symlink|escaped arm directory"):
                compress_retained_tables(
                    arm, evidence=json.loads(evidence.read_text()),
                    container_dead=True, root=arm)
            self.assertEqual(outside.read_text(), text)
            self.assertFalse((arm / (TABLE + ".zst")).exists())
        with self.subTest(case="compressed_symlink"), TemporaryDirectory() as d:
            arm = self._arm(d, text, in_scratch=False)
            outside = Path(d) / "outside.csv.zst"
            outside.write_bytes(b"not a table")
            (arm / (TABLE + ".zst")).symlink_to(outside)
            evidence, _ = self._evidence(arm, text)
            with self.assertRaisesRegex(RetentionGateError, "symlink|escaped arm directory"):
                compress_retained_tables(
                    arm, evidence=json.loads(evidence.read_text()),
                    container_dead=True, root=arm)
            self.assertEqual(outside.read_bytes(), b"not a table")
            self.assertEqual((arm / TABLE).read_text(), text)


if __name__ == "__main__":
    unittest.main()
