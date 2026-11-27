"""Fail-closed tests for reversible zstd scratch storage."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks import compressed_tables as codec


class ScratchCodecTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.body = b"".join(b"read-%d chr1 1 60 6M\n" % n
                             for n in range(4000))
        self.path = self.root / "scratch" / "temp.sam"
        self.path.parent.mkdir()
        self.path.write_bytes(self.body)

    def test_prepare_install_and_logical_bytes(self):
        frame, proof = codec.prepare_scratch(self.path)
        self.assertEqual(proof["format"], codec.SCRATCH_FORMAT)
        self.assertEqual((proof["original_sha256"], proof["original_size"]),
                         (hashlib.sha256(self.body).hexdigest(), len(self.body)))
        self.assertTrue(self.path.is_file())
        self.assertFalse(frame.name.endswith(codec.ZST_SUFFIX))
        codec.install_scratch(self.path, frame, proof)
        self.assertFalse(self.path.exists())
        self.assertTrue(self.path.with_name(
            self.path.name + codec.ZST_SUFFIX).is_file())
        self.assertEqual(codec.logical_digest(
            self.path, format=codec.SCRATCH_FORMAT),
            (proof["original_sha256"], proof["original_size"]))
        restored = b"".join(codec.logical_bytes(
            self.path, format=codec.SCRATCH_FORMAT))
        self.assertEqual(restored, self.body)

    def test_proof_is_not_reused_by_table_reader(self):
        codec.compress_scratch(self.path)
        with self.assertRaises(codec.InvalidProof):
            codec.logical_digest(self.path)

    def test_tampered_frame_fails_closed(self):
        codec.compress_scratch(self.path)
        stored = self.path.with_name(self.path.name + codec.ZST_SUFFIX)
        stored.write_bytes(stored.read_bytes()[:-4])
        with self.assertRaises(codec.InvalidProof):
            codec.logical_digest(self.path, format=codec.SCRATCH_FORMAT)

    def test_tampered_proof_fails_closed(self):
        codec.compress_scratch(self.path)
        meta = self.path.with_name(self.path.name + codec.META_SUFFIX)
        proof = json.loads(meta.read_text())
        proof["original_sha256"] = "0" * 64
        meta.write_text(json.dumps(proof) + "\n")
        with self.assertRaises(codec.InvalidProof):
            codec.logical_digest(self.path, format=codec.SCRATCH_FORMAT)

    def test_symlink_refused(self):
        target = self.root / "outside.sam"
        target.write_bytes(self.body)
        self.path.unlink()
        self.path.symlink_to(target)
        with self.assertRaises(codec.TableError):
            codec.prepare_scratch(self.path)

    def test_existing_variant_refused(self):
        frame, proof = codec.prepare_scratch(self.path)
        codec.install_scratch(self.path, frame, proof)
        write = self.path.with_name(self.path.name + codec.ZST_SUFFIX)
        self.assertTrue(write.is_file())
        with self.assertRaises(codec.TableError):
            codec.prepare_scratch(self.path)


if __name__ == "__main__":
    unittest.main()
