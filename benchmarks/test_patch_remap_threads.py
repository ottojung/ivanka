"""Test fail-closed patching of MiCall's Bowtie2 subprocess arguments."""
import unittest
from patch_remap_threads import patch_remap_source


class RemapThreadPatchTests(unittest.TestCase):
    def test_patches_only_target_assignment(self):
        src = '''
def unrelated():
    bowtie_args = ["-p", "1"]

def map_to_reference():
    bowtie_args = [
        "--quiet",
        "-p", "1",
    ]
    return bowtie_args
'''
        patched = patch_remap_source(src, 2)
        self.assertEqual(patched.count('"--quiet"'), 1)
        self.assertIn('"-p", "1"', patched)  # unrelated assignment preserved
        self.assertIn('"2", \'--reorder\'', patched)
        self.assertEqual(patch_remap_source(src, 4).count("'--reorder'"), 1)

    def test_unsupported_or_duplicate_options_fail_closed(self):
        src = "def map_to_reference():\n    bowtie_args=['-p','1']\n"
        with self.assertRaisesRegex(ValueError, "single-thread"):
            patch_remap_source(patch_remap_source(src, 2), 4)
        with self.assertRaisesRegex(ValueError, "exactly one Bowtie2"):
            patch_remap_source("def map_to_reference():\n    bowtie_args=['-p','1','-p','1']\n", 2)
        with self.assertRaisesRegex(ValueError, "one Bowtie2 arguments"):
            patch_remap_source("def map_to_reference():\n    pass\n", 2)

    def test_rejects_unexpected_function_structure(self):
        with self.assertRaisesRegex(ValueError, "exactly one MiCall"):
            patch_remap_source("def dummy(): pass\n", 2)
        with self.assertRaisesRegex(ValueError, "exactly one MiCall"):
            patch_remap_source("def map_to_reference(): pass\ndef map_to_reference(): pass\n", 2)

    def test_rejects_bad_thread_counts(self):
        src="def map_to_reference():\n    bowtie_args=['-p','1']\n"
        for count in (0, 1, 33, 500):
            with self.assertRaisesRegex(ValueError, "2..32"):
                patch_remap_source(src, count)

    def test_no_modification_to_other_source_lines(self):
        src="marker='-p 1'\n\ndef map_to_reference():\n    bowtie_args = ['-p', '1']\n    return bowtie_args\n"
        result=patch_remap_source(src,3)
        self.assertTrue(result.startswith("marker='-p 1'\n"))
        self.assertIn("['-p', '3', '--reorder']",result)
        self.assertEqual(result.replace("'3', '--reorder'","'1'"),src)


if __name__ == "__main__":
    unittest.main()
