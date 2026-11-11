import ast
import unittest
from patch_pinned_ivanka_contig_budget import patch_source

SOURCE = '''from pathlib import Path
import os
def cached(value):
    return lambda fn: fn
@cached("denovo[ivanka]")
def run_subprocess(fastq1, fastq2, merged_contigs_csv):
    command = ["ivanka", "--reads1", str(fastq1),
               "--reads2", str(fastq2), "--output", str(merged_contigs_csv)]
    return command
'''


class BudgetPatchTests(unittest.TestCase):
    def test_command_appended_not_replaced(self):
        result = patch_source(SOURCE)
        ast.parse(result)
        self.assertIn('    import os\n    limit =', result)
        self.assertIn('command.extend(["--max-contigs", str(limit)])', result)
        self.assertIn("raise ValueError", result)
        self.assertIn('["ivanka", "--reads1"', result)

    def test_refuse_repeat_patch(self):
        with self.assertRaises(ValueError):
            patch_source(patch_source(SOURCE))

    def test_refuse_unpinned_caller(self):
        with self.assertRaises(ValueError):
            patch_source(SOURCE.replace("denovo[ivanka]", "denovo[iva]"))

    def test_refuse_different_assembly_command(self):
        with self.assertRaises(ValueError):
            patch_source(SOURCE.replace('"--output"', '"--extra", "--output"'))

    def test_refuse_missing_boundary(self):
        with self.assertRaises(ValueError):
            patch_source(SOURCE.replace("def run_subprocess", "def other"))
