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
        self.assertIn("_IvankaPath(with_prefix(self.remap_csv))", updated)
        self.assertIn("_IvankaPath(with_prefix(self.remap_conseq_csv))", updated)
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

    def test_string_prefix_paths_execute_in_the_patched_stage(self):
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import ModuleType
        from unittest.mock import patch
        script = ("class Sample:\n"
                  "    def stage(self):\n"
                  "        with_prefix = lambda path: path\n"
                  "        logger = type('Log', (), {'info': lambda *args: None})()\n"
                  + LOG_MARKER + "\n"
                  + "        " + INPUT_MARKER + ":\n"
                  + "            self.text = remap_csv.read()\n")
        module = ModuleType("micall.core.ivanka_conserved_remap")
        module.project_remap = lambda original, reference, output: (original, {})
        package = ModuleType("micall")
        package.__path__ = []
        core = ModuleType("micall.core")
        core.__path__ = []
        ns = {}
        exec(patched_source(script), ns)
        with TemporaryDirectory() as d, patch.dict(sys.modules, {
                "micall": package, "micall.core": core,
                "micall.core.ivanka_conserved_remap": module}):
            remap = Path(d) / "remap.csv"
            remap.write_text("unchanged original remap")
            sample = ns["Sample"]()
            sample.remap_csv = str(remap)
            sample.remap_conseq_csv = str(Path(d) / "remap_conseq.csv")
            sample.stage()
            self.assertEqual(sample.text, "unchanged original remap")

    def test_compiles_pinned_shape(self):
        source = (
            "class Sample:\n"
            "    def stage(self):\n"
            + LOG_MARKER + "\n"
            + "        " + INPUT_MARKER + ":\n"
            + "            pass\n"
        )
        compile(patched_source(source), "<test>", "exec")


if __name__ == "__main__":
    unittest.main()
