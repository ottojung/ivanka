import unittest

from acceptance import accept_sample


class AcceptanceTests(unittest.TestCase):
    def test_ordinary_score_passes_at_95_percent(self):
        iva={"hxb2_score": 1000}
        riva={"hxb2_score": 950, "stitched_count": 1}
        self.assertEqual(accept_sample("ordinary", iva, riva), (True, []))
        riva["hxb2_score"]=949
        self.assertFalse(accept_sample("ordinary", iva, riva)[0])

    def test_negative_baseline_has_no_nonsensical_percentage(self):
        iva={"hxb2_score": -359}
        riva={"hxb2_score": -350, "stitched_count": 1}
        self.assertTrue(accept_sample("FRAGMENTED", iva, riva)[0])
        riva["hxb2_score"]=-500
        self.assertFalse(accept_sample("FRAGMENTED", iva, riva)[0])

    def test_structural_cases_require_independent_alignment(self):
        iva={"hxb2_score": 100}
        riva={"hxb2_score": 100, "stitched_count": 1}
        self.assertFalse(accept_sample("deletion", iva, riva)[0])
        self.assertFalse(accept_sample("deletion", iva, riva, {"pass": False})[0])
        self.assertTrue(accept_sample("deletion", iva, riva, {"pass": True})[0])

    def test_no_contigs_is_never_pass(self):
        self.assertFalse(accept_sample("SAMPLE",{"hxb2_score":0},{"hxb2_score":0,"stitched_count":0})[0])


if __name__ == "__main__":
    unittest.main()
