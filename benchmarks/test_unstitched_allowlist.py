"""Exact-source tests for the proposed unstitched diagnostic allowlist.

Runs against the reviewed codec with the benchmark venv (no pytest needed):

  IVANKA_ZSTD_BACKEND=module <bench-ci-venv>/bin/python \
      benchmarks/test_unstitched_allowlist.py

No live sealed data is converted; every table here is a synthetic fixture.
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compressed_tables import (  # noqa: E402
    COMPRESSIBLE_TABLES, FORMAT, META_SUFFIX, ZST_SUFFIX,
    compress_table, load_meta, logical_digest, open_table,
)


PROPOSED = frozenset({
    "unstitched_amino.csv", "unstitched_amino_details.csv",
    "unstitched_cascade.csv", "unstitched_clipping.csv",
    "unstitched_concordance.csv", "unstitched_concordance_detailed.csv",
    "unstitched_concordance_seed.csv", "unstitched_coverage_scores.csv",
    "unstitched_coverage_summary.csv", "unstitched_failed.csv",
    "unstitched_failed_align.csv", "unstitched_insertions.csv",
    "unstitched_minimap_hits.csv", "unstitched_nuc.csv",
    "unstitched_nuc_details.csv", "unstitched_nuc_mutations.csv",
    "unstitched_remap_counts.csv", "unstitched_unique_aligned_fragments.csv",
})

PROTECTED = frozenset({
    "conseq.csv", "conseq_all.csv", "contigs.csv", "stitched_contigs.csv",
    "unstitched_contigs.csv", "unstitched_conseq.csv",
    "unstitched_conseq_all.csv", "unstitched_conseq_region.csv",
    "unstitched_remap_conseq.csv", "receipt.json", "terminal_evidence.json",
})


class AllowlistTests(unittest.TestCase):
    def test_proposed_names_allowed(self):
        self.assertTrue(PROPOSED <= COMPRESSIBLE_TABLES)

    def test_protected_names_refused(self):
        self.assertFalse(PROTECTED & COMPRESSIBLE_TABLES)

    def test_lossless_roundtrip_and_proof(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            for name in sorted(PROPOSED):
                with self.subTest(name=name):
                    original = ("pos,depth\n" + "".join(
                        "chr%d,%d\n" % (i, i * 7) for i in range(512))).encode()
                    plain = folder / name
                    if plain.exists():
                        plain.unlink()
                    for suffix in (ZST_SUFFIX, META_SUFFIX):
                        p = folder / (name + suffix)
                        if p.exists():
                            p.unlink()
                    plain.write_bytes(original)
                    before = logical_digest(plain)
                    self.assertEqual(before[1], len(original))

                    compressed = compress_table(plain)
                    self.assertEqual(compressed, folder / (name + ZST_SUFFIX))
                    self.assertFalse(plain.exists())
                    proof = load_meta(folder / (name + META_SUFFIX))
                    self.assertEqual(proof["format"], FORMAT)
                    self.assertEqual(proof["codec"], "zstd")
                    self.assertIs(proof["checksum"], True)
                    self.assertEqual(proof["threads"], 1)
                    self.assertEqual(proof["original_sha256"],
                                     hashlib.sha256(original).hexdigest())
                    self.assertEqual(logical_digest(plain), before)
                    with open_table(plain) as stream:
                        self.assertEqual(stream.read().encode(), original)

    def test_recompression_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            name = "unstitched_nuc.csv"
            plain = folder / name
            plain.write_bytes(b"a,b\n1,2\n" * 100)
            compress_table(plain)
            first = (folder / (name + ZST_SUFFIX)).read_bytes()
            compress_table(plain)
            self.assertEqual((folder / (name + ZST_SUFFIX)).read_bytes(), first)
            self.assertEqual(logical_digest(plain)[1], 800)

    def test_non_allowlisted_name_still_refused(self):
        with tempfile.TemporaryDirectory() as td:
            plain = Path(td) / "unstitched_contigs.csv"
            plain.write_bytes(b"x\n")
            with self.assertRaises(ValueError):
                compress_table(plain)


if __name__ == "__main__":
    unittest.main(verbosity=2)
