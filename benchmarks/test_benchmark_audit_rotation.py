"""Lossless rotation of the image-cleaner audit, including interrupted writes."""
import gzip
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/rotate_benchmark_audit_log.py"
SPEC = importlib.util.spec_from_file_location("audit_rotation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AuditRotationTests(unittest.TestCase):
    def test_lossless_rotation_and_new_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            log = p / "active"
            body = b'{"removed":0}\n' * 100
            log.write_bytes(body)
            MODULE.rotate(log, p / "archive", 1)
            self.assertFalse(log.exists())
            final = next((p / "archive").glob("*.gz"))
            self.assertEqual(gzip.decompress(final.read_bytes()), body)
            self.assertEqual(final.with_suffix(".sha256").read_text().strip(),
                             hashlib.sha256(body).hexdigest())
            log.write_bytes(b"new")
            MODULE.rotate(log, p / "archive", 100)
            self.assertEqual(log.read_bytes(), b"new")

    def test_resume_pending_and_refuse_corrupt_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            pending = p / "retention-1.jsonl.pending"
            pending.write_bytes(b"original")
            pending.with_suffix(".gz").write_bytes(gzip.compress(b"wrong"))
            with self.assertRaisesRegex(ValueError, "disagrees"):
                MODULE.rotate(p / "active", p)
            self.assertEqual(pending.read_bytes(), b"original")
            pending.with_suffix(".gz").unlink()
            MODULE.rotate(p / "active", p)
            self.assertFalse(pending.exists())
            self.assertEqual(gzip.decompress(pending.with_suffix(".gz").read_bytes()),
                             b"original")
