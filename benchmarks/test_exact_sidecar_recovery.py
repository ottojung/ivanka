"""Interrupted sidecars are archived, not substituted into MiCall outputs."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from assembler_bench.exact_recovery import recover_partial

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class ExactSidecarRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.meta=root/"provenance.json"
        self.csv=root/"exact_coverage.csv"

    def test_empty_transaction_is_unchanged(self):
        self.assertIsNone(recover_partial(self.meta,self.csv,digest))

    def test_complete_transaction_is_unchanged(self):
        self.meta.write_text('{"valid":true}')
        self.csv.write_text("position,exact_coverage\n")
        self.assertIsNone(recover_partial(self.meta,self.csv,digest))
        self.assertTrue(self.meta.exists())
        self.assertTrue(self.csv.exists())

    def test_lone_csv_is_preserved_for_recomputation(self):
        content="position,exact_coverage\n1,10\n"
        self.csv.write_text(content)
        old=digest(self.csv)
        target=recover_partial(self.meta,self.csv,digest)
        self.assertFalse(self.csv.exists())
        self.assertEqual(target.read_text(),content)
        self.assertIn(old,target.name)

    def test_lone_metadata_is_preserved_for_recomputation(self):
        content='{"source":"sha256"}\n'
        self.meta.write_text(content)
        target=recover_partial(self.meta,self.csv,digest)
        self.assertFalse(self.meta.exists())
        self.assertEqual(target.read_text(),content)

    def test_archive_collision_fails_without_destroying_original(self):
        self.csv.write_text("original")
        original_hash=digest(self.csv)
        target=self.csv.parent/f"interrupted-{original_hash}-exact_coverage.csv"
        target.write_text("prior-interruption")
        with self.assertRaisesRegex(ValueError,"cannot overwrite"):
            recover_partial(self.meta,self.csv,digest)
        self.assertEqual(self.csv.read_text(),"original")
        self.assertEqual(target.read_text(),"prior-interruption")

if __name__=="__main__":
    unittest.main()
