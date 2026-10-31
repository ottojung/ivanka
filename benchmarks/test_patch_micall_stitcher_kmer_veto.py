"""Verify fail-closed source patching without relying on a private checkout."""
import importlib.util
import pathlib
import unittest
from patch_micall_stitcher_kmer_veto import patched_source


class PatchMiCallStitcherTests(unittest.TestCase):
    @staticmethod
    def fixture():
        return (
            "\ndef try_combine_1(\n"
            "    contigs,\n"
            "):\n"
            "    for first in contigs:\n"
            "            if result is not None:\n"
            "                combined, additional_score = result\n"
            "                return first, second, combined\n"
            "\ndef stitch_consensus_overlaps(remaining):\n"
            "        log(events.Constructed(most_probable))\n"
            "        yield most_probable.whole\n"
            "        remaining = tuple(remaining)\n"
        )

    def test_source_patcher_is_idempotency_guarded(self):
        patched = patched_source(self.fixture())
        self.assertIn("def preserves_source_kmers(", patched)
        self.assertIn("yield from consumed", patched)
        self.assertIn("if not preserves_source_kmers(", patched)
        with self.assertRaisesRegex(ValueError, "already-modified"):
            patched_source(patched)

    def test_pinned_three_field_result_contract(self):
        original = self.fixture().replace(
            "combined, additional_score = result",
            "combined, _additional_score, _covered_input = result")
        patched = patched_source(original)
        self.assertIn("combined, _additional_score, _covered_input = result", patched)
        self.assertIn("yield from consumed", patched)

    def test_fails_closed_on_unknown_source(self):
        with self.assertRaisesRegex(ValueError, "Unexpected MiCall"):
            patched_source("def not_a_stitcher(): pass\n")

    def test_pinned_micall_source_if_installed(self):
        try:
            spec = importlib.util.find_spec("micall.utils.referenceless_contig_stitcher")
        except (ModuleNotFoundError, ImportError):
            self.skipTest("MiCall not installed")
        if spec is None or spec.origin is None:
            self.skipTest("MiCall not installed")
        source=pathlib.Path(spec.origin).read_text()
        patched = patched_source(source)
        self.assertIn("def preserves_source_kmers(", patched)


if __name__ == "__main__":
    unittest.main()
