"""Fail-closed lossless table storage and transparent reader compatibility."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import compressed_tables as ct

BACKENDS = ("module", "cli")
HEADER = ["contig", "coverage", "concordance"]
ROWS = [["sampleA", "10", "0.5"], ["sampleB", "20", "0.9"]]


def write_table(folder, name="genome_coverage.csv", header=HEADER, rows=ROWS):
    path = folder / name
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def meta_for(path):
    return Path(str(path) + ct.META_SUFFIX)


def digest_of(path):
    return (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size)


class CompressedTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.path = write_table(self.folder)
        self.expected = digest_of(self.path)

    def use_backend(self, name):
        return patch.dict(os.environ, {"IVANKA_ZSTD_BACKEND": name})

    def backend_ready(self, name):
        if name == "cli":
            try:
                ct._cli_path()
            except ct.TableError:
                return False
        return True

    def test_roundtrip_preserves_logical_bytes_and_digest(self):
        for backend in BACKENDS:
            if not self.backend_ready(backend):
                continue
            with self.subTest(backend=backend), self.use_backend(backend):
                folder = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, folder, True)
                path = write_table(folder)
                expected = digest_of(path)
                compressed = ct.compress_table(path)
                self.assertEqual(compressed.name,
                                 "genome_coverage.csv" + ct.ZST_SUFFIX)
                proof = ct.load_meta(meta_for(path))
                self.assertEqual(proof["original_sha256"], expected[0])
                self.assertEqual(proof["original_size"], expected[1])
                self.assertEqual(proof["level"], 3)
                self.assertEqual(proof["threads"], 1)
                self.assertTrue(proof["checksum"])
                self.assertEqual(ct.logical_digest(path), expected)
                with ct.open_table(path, newline="") as handle:
                    self.assertEqual(list(csv.reader(handle)),
                                     [HEADER] + ROWS)

    def test_plain_tables_and_missing_tables(self):
        self.assertEqual(ct.logical_digest(self.path), self.expected)
        with ct.open_table(self.path, newline="") as handle:
            self.assertEqual(list(csv.reader(handle)), [HEADER] + ROWS)
        with self.assertRaises(FileNotFoundError):
            ct.open_table(self.folder / "absent.csv")
        self.assertIsNone(ct.find_table(self.folder / "absent.csv"))

    def test_conflicting_variants_fail_closed(self):
        ct.compress_table(self.path, keep_plain=True)
        self.assertEqual(ct.logical_digest(self.path), self.expected)
        self.path.write_text("contig,coverage\nother,999\n")
        with self.assertRaises(ct.ConflictingVariants):
            ct.logical_digest(self.path)
        with self.assertRaises(ct.ConflictingVariants):
            ct.open_table(self.path)

    def test_unsupported_codec_fails_closed(self):
        ct.compress_table(self.path)
        meta = meta_for(self.path)
        proof = json.loads(meta.read_text())
        proof["codec"] = "brotli"
        meta.write_text(json.dumps(proof))
        with self.assertRaises(ct.UnsupportedCodec):
            ct.logical_digest(self.path)

    def test_missing_proof_fails_closed(self):
        ct.compress_table(self.path)
        meta_for(self.path).unlink()
        with self.assertRaises(ct.MissingProof):
            ct.logical_digest(self.path)
        with self.assertRaises(ct.MissingProof):
            ct.open_table(self.path)

    def test_truncated_frame_fails_closed(self):
        for backend in BACKENDS:
            if not self.backend_ready(backend):
                continue
            with self.subTest(backend=backend), self.use_backend(backend):
                folder = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, folder, True)
                path = write_table(folder)
                compressed = ct.compress_table(path)
                compressed.write_bytes(compressed.read_bytes()[:-3])
                meta = meta_for(path)
                proof = json.loads(meta.read_text())
                proof["compressed_sha256"] = hashlib.sha256(
                    compressed.read_bytes()).hexdigest()
                proof["compressed_size"] = compressed.stat().st_size
                meta.write_text(json.dumps(proof))
                with self.assertRaises(ct.TruncatedTable):
                    ct.logical_digest(path)
                with ct.open_table(path) as handle:
                    with self.assertRaises(ct.TruncatedTable):
                        handle.read()

    def test_tampered_compressed_bytes_fail_closed(self):
        ct.compress_table(self.path)
        compressed = self.folder / ("genome_coverage.csv" + ct.ZST_SUFFIX)
        data = bytearray(compressed.read_bytes())
        data[5] ^= 0xFF
        compressed.write_bytes(bytes(data))
        with self.assertRaises(ct.InvalidProof):
            ct.logical_digest(self.path)

    def test_invalid_proof_fails_closed(self):
        ct.compress_table(self.path)
        meta = meta_for(self.path)
        proof = json.loads(meta.read_text())
        proof["original_sha256"] = "0" * 64
        meta.write_text(json.dumps(proof))
        with self.assertRaises(ct.InvalidProof):
            ct.logical_digest(self.path)

    def test_noncompressible_tables_are_refused(self):
        consensus = self.folder / "conseq.csv"
        consensus.write_text("consensus\nACGT\n")
        with self.assertRaises(ValueError):
            ct.compress_table(consensus)
        self.assertFalse((self.folder / ("conseq.csv" + ct.ZST_SUFFIX)).exists())
        self.assertTrue(consensus.is_file())

    def test_recompression_is_idempotent(self):
        compressed = ct.compress_table(self.path)
        before = compressed.stat().st_mtime_ns
        self.assertEqual(ct.compress_table(self.path), compressed)
        self.assertEqual(compressed.stat().st_mtime_ns, before)
        self.assertFalse(self.path.exists())

    def test_interrupted_proof_install_is_recovered(self):
        compressed = ct.compress_table(self.path, keep_plain=True)
        meta_for(self.path).unlink()
        self.assertEqual(ct.compress_table(self.path), compressed)
        self.assertTrue(meta_for(self.path).is_file())
        self.assertEqual(ct.logical_digest(self.path), self.expected)

    def test_interrupted_plain_removal_is_completed(self):
        ct.compress_table(self.path, keep_plain=True)
        self.assertTrue(self.path.is_file())
        ct.compress_table(self.path)
        self.assertFalse(self.path.exists())
        self.assertEqual(ct.logical_digest(self.path), self.expected)

    def test_crash_leftovers_are_ignored(self):
        ct.compress_table(self.path)
        (self.folder / ("genome_coverage.csv" + ct.ZST_SUFFIX + ".tmp.1")) \
            .write_text("partial")
        self.assertEqual(ct.logical_digest(self.path), self.expected)
        with ct.open_table(self.path, newline="") as handle:
            self.assertEqual(len(list(csv.reader(handle))), 3)

    def test_decompression_is_chunk_bounded(self):
        original = self.path.read_bytes()
        ct.compress_table(self.path)
        compressed = self.folder / ("genome_coverage.csv" + ct.ZST_SUFFIX)
        with patch.object(ct, "CHUNK", 7):
            chunks = list(ct._decompress_chunks(compressed))
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 7 for chunk in chunks))
        self.assertEqual(b"".join(chunks), original)

    def test_diagnostic_metrics_read_compressed_tables(self):
        from diagnostic_metrics import extract
        write_table(self.folder, "nuc.csv", ["seed", "refseq.nuc.pos", "clip"],
                    [["a", "10", "2"], ["a", "11", "0"]])
        plain = extract(self.folder)
        self.assertIsNotNone(plain["values"]["average_read_depth"])
        for name in ("genome_coverage.csv", "nuc.csv"):
            ct.compress_table(self.folder / name)
        self.assertEqual(extract(self.folder), plain)

    def test_project_references_read_compressed_consensus(self):
        from project_references import final_max_sequences
        consensus = self.folder / "conseq.csv"
        with consensus.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["consensus-percent-cutoff", "sequence"])
            writer.writerow(["MAX", "ACGT"])
            writer.writerow(["90", "TTTT"])
        self.assertEqual(final_max_sequences(self.folder), ["ACGT"])
        with patch.object(ct, "COMPRESSIBLE_TABLES",
                          ct.COMPRESSIBLE_TABLES | {"conseq.csv"}):
            ct.compress_table(consensus)
        self.assertEqual(final_max_sequences(self.folder), ["ACGT"])


if __name__ == "__main__":
    unittest.main()
