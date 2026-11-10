"""Fail-closed validation of the experimental shared-MiCall thread override."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from patch_denovo_bowtie_thread_budget import main


class ThreadBudgetTests(unittest.TestCase):
    ORIGINAL = "# immutable header\nMAX_DENOVO_ALIGNMENTS = 12\nDENOVO_BOWTIE_THREADS = 4\nOTHER = 99\n"

    def attempt(self, original, count):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "denovo_multimap.py"
            target.write_text(original)
            with (patch("patch_denovo_bowtie_thread_budget.importlib.util.find_spec",
                        return_value=SimpleNamespace(origin=str(target))),
                  patch.dict(os.environ, {"IVANKA_EXPERIMENT_BOWTIE_THREADS": str(count)})):
                try:
                    main()
                    error = None
                except Exception as exc:
                    error = exc
                return target.read_text(), error

    def test_changes_only_shared_thread_count(self):
        updated, err = self.attempt(self.ORIGINAL, 2)
        self.assertIsNone(err)
        self.assertEqual(updated, self.ORIGINAL.replace("THREADS = 4", "THREADS = 2"))

    def test_one_thread_is_allowed(self):
        updated, err = self.attempt(self.ORIGINAL, 1)
        self.assertIsNone(err)
        self.assertIn("DENOVO_BOWTIE_THREADS = 1", updated)

    def test_invalid_thread_counts_leave_source_unchanged(self):
        for count in (0, -1, 17):
            updated, err = self.attempt(self.ORIGINAL, count)
            self.assertIsInstance(err, ValueError)
            self.assertEqual(updated, self.ORIGINAL)

    def test_unexpected_source_fails_closed(self):
        for original in (
            self.ORIGINAL.replace("THREADS = 4", "THREADS = 8"),
            self.ORIGINAL + "DENOVO_BOWTIE_THREADS = 4\n",
            self.ORIGINAL.replace("DENOVO_BOWTIE_THREADS = 4\n", ""),
        ):
            updated, err = self.attempt(original, 2)
            self.assertIsInstance(err, ValueError)
            self.assertEqual(updated, original)


if __name__ == "__main__":
    unittest.main()
