"""Tests for the fail-closed experimental MiCall remap overlay."""
import unittest

from patch_micall_conserved_remap import patched_source, LOG_MARKER, INPUT_MARKER


STUB = (
    "def stage(self):\n"
    "    def with_prefix(path):\n"
    "        return path\n"
    "    logger = type('Logger', (), {'info': print})()\n"
    + LOG_MARKER + "\n"
    + "        " + INPUT_MARKER + ", open('output.csv', 'w') as output:\n"
    + "            pass\n"
)


class RemapOverlayTests(unittest.TestCase):
    def test_inserts_before_sam2aln_without_other_stage_changes(self):
        source = (
            "class Sample:\n"
            "    def stage(self):\n"
            + LOG_MARKER + "\n"
            + "        " + INPUT_MARKER + ":\n"
            + "            pass\n"
        )
        updated = patched_source(source)
        self.assertIn("ivanka_conserved_remap import project_remap", updated)
        self.assertIn("with open(_ivanka_remap_path) as remap_csv", updated)
        self.assertNotIn(INPUT_MARKER, updated)
        self.assertEqual(updated.count("Running sam2aln"), 1)
        self.assertEqual(updated.count("from micall.core.ivanka_conserved_remap"), 1)
        with self.assertRaisesRegex(ValueError, "already"):
            patched_source(updated)

    def test_missing_or_duplicated_boundary_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "changed"):
            patched_source("def other():\n    pass\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            patched_source(STUB + "\n" + STUB)
        reversed_order = (
            "class Sample:\n"
            "    def stage(self):\n"
            + "        " + INPUT_MARKER + ":\n"
            + "            pass\n"
            + LOG_MARKER + "\n"
        )
        with self.assertRaisesRegex(ValueError, "order"):
            patched_source(reversed_order)

    def test_compiles_pinned_shape(self):
        source = (
            "class Sample:\n"
            "    def stage(self):\n"
            + LOG_MARKER + "\n"
            + "        " + INPUT_MARKER + ":\n"
            + "            pass\n"
        )
        compile(patched_source(source), "<test>", "exec")

    def test_actual_micall_string_path_at_patched_boundary(self):
        """MiCall with_prefix() returns str; the overlay must accept it."""
        import sys
        import tempfile
        import types
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            remap = Path(directory) / "remap.csv"
            reference = Path(directory) / "remap_conseq.csv"
            remap.write_text("unchanged\n")
            reference.write_text("region,sequence\n")
            fake = types.ModuleType("micall.core.ivanka_conserved_remap")
            fake.project_remap = lambda original, refs, output: (
                original, {"reassigned_pairs": 0})
            micall = types.ModuleType("micall")
            micall.__path__ = []
            core = types.ModuleType("micall.core")
            core.__path__ = []
            source = (
                "class Sample:\n"
                + f"    remap_csv = {str(remap)!r}\n"
                + f"    remap_conseq_csv = {str(reference)!r}\n"
                + "    def stage(self):\n"
                + "        def with_prefix(value): return value\n"
                + "        logger = type('Logger', (), {'info': lambda *args: None})()\n"
                + LOG_MARKER + "\n"
                + "        " + INPUT_MARKER + ":\n"
                + "            return remap_csv.read()\n"
            )
            namespace = {}
            with patch.dict(sys.modules, {
                "micall": micall,
                "micall.core": core,
                "micall.core.ivanka_conserved_remap": fake,
            }):
                exec(patched_source(source), namespace)
                self.assertEqual(namespace["Sample"]().stage(), "unchanged\n")


if __name__ == "__main__":
    unittest.main()
