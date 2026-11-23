import unittest
from patch_denovo_mapping_k_experiment import adjust

SOURCE = "from math import floor\nMAX_DENOVO_ALIGNMENTS = 12\nDENOVO_BOWTIE_THREADS = 4\n"


class MappingKExperimentTests(unittest.TestCase):
    def test_only_limit_is_changed(self):
        self.assertEqual(adjust(SOURCE,2),SOURCE.replace(" = 12"," = 2"))
    def test_other_mapping_options_untouched(self):
        self.assertIn("DENOVO_BOWTIE_THREADS = 4",adjust(SOURCE,1))
    def test_reject_unpinned_source(self):
        with self.assertRaises(ValueError):
            adjust(SOURCE.replace(" = 12", " = 13"),2)
    def test_refuse_second_patch(self):
        with self.assertRaises(ValueError):
            adjust(adjust(SOURCE,2),2)
    def test_invalid_limit(self):
        for limit in (0,-1,13):
            with self.assertRaises(ValueError):
                adjust(SOURCE,limit)
