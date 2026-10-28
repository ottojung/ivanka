import importlib.util
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("bowtie2_benchmark",Path(__file__).parent/"bowtie2_perf_wrapper.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Bowtie2WrapperTests(unittest.TestCase):
    def test_rewrites_only_thread_count_and_preserves_order(self):
        args=["--wrapper","micall-0","-x","references","-1","reads1","-2","reads2","-p","1"]
        self.assertEqual(m.rewritten(args,8),args[:-1]+["8","--reorder"])
    def test_leaves_other_commands_untouched(self):
        self.assertEqual(m.rewritten(["--version"],8),["--version"])
        self.assertEqual(m.rewritten(["-p","4","--reorder"],8),["-p","4","--reorder"])
    def test_single_thread_preserves_original_argument_structure(self):
        self.assertEqual(m.rewritten(["-p","1"],1),["-p","1"])
