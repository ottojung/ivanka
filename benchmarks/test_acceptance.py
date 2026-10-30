import unittest

from acceptance import accept_sample


class AcceptanceTests(unittest.TestCase):
    def test_ordinary_score_passes_at_95_percent(self):
        iva={"hxb2_score": 1000}
        ivanka={"hxb2_score": 950, "stitched_count": 1}
        self.assertEqual(accept_sample("ordinary", iva, ivanka), (True, []))
        ivanka["hxb2_score"]=949
        self.assertFalse(accept_sample("ordinary", iva, ivanka)[0])

    def test_negative_baseline_has_no_nonsensical_percentage(self):
        iva={"hxb2_score": -359}
        ivanka={"hxb2_score": -350, "stitched_count": 1}
        self.assertTrue(accept_sample("FRAGMENTED", iva, ivanka)[0])
        ivanka["hxb2_score"]=-500
        self.assertFalse(accept_sample("FRAGMENTED", iva, ivanka)[0])

    def test_structural_cases_require_independent_alignment(self):
        iva={"hxb2_score": 100}
        ivanka={"hxb2_score": 100, "stitched_count": 1}
        self.assertTrue(accept_sample("deletion", iva, ivanka)[0])
        self.assertTrue(accept_sample("deletion", iva, ivanka, {"pass": False})[0])
        self.assertTrue(accept_sample("deletion", iva, ivanka, {"pass": True})[0])
        self.assertTrue(accept_sample("fragmented", iva, ivanka)[0])

    def test_any_one_contig_may_pass_with_many_poor_contigs(self):
        iva={"hxb2_score": 1000}
        ivanka={"per_contig_scores": [12, -850, 957, 100],
              "hxb2_score": 957, "stitched_count": 4}
        self.assertTrue(accept_sample("mixed", iva, ivanka, {"pass": False})[0])
        ivanka["hxb2_score"] = 949
        self.assertFalse(accept_sample("mixed", iva, ivanka, {"pass": True})[0])

    def test_no_contigs_is_never_pass(self):
        self.assertFalse(accept_sample("SAMPLE",{"hxb2_score":0},{"hxb2_score":0,"stitched_count":0})[0])


if __name__ == "__main__":
    unittest.main()
