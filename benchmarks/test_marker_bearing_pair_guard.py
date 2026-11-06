import json
import unittest
from marker_bearing_pair_guard import assess_safe_restorations

S48B = '/workspace/ivanka-lab/snv-full-micall-ab-20261105/outputs/pinned-wrapper-main-vs-snv-cap1000/73090AMIDI-MidHCV_S48/baseline'
S48E = '/workspace/ivanka-lab/snv-full-micall-ab-20261105/outputs/pinned-wrapper-main-vs-snv-cap1000/73090AMIDI-MidHCV_S48/experimental'
S12B = '/workspace/ivanka-lab/snv-full-micall-ab-20261105/outputs/pinned-wrapper-main-vs-snv-cap1000/73111AMIDI-MidHCV_S12/baseline'
S12E = '/workspace/ivanka-lab/snv-full-micall-ab-20261105/outputs/pinned-wrapper-main-vs-snv-cap1000/73111AMIDI-MidHCV_S12/experimental'

class T(unittest.TestCase):
    def test_s48_moved_pairs_not_safely_restorable(self):
        r = assess_safe_restorations(S48B, S48E)
        self.assertGreater(r['moved_pairs'], 2000)
        self.assertEqual(r['restoration_applied'], False)
        self.assertEqual(r['original_pairs_duplicated'], 0)
        # Most moved pairs land on changed/new contig contexts; no transplant.
        self.assertEqual(r['restorable_to_identical_baseline_reference'] + r['unsafe_sequence_changed_or_missing_baseline_reference'], r['moved_pairs'])

    def test_s12_reports_moves(self):
        r = assess_safe_restorations(S12B, S12E)
        self.assertEqual(r['restoration_applied'], False)
        self.assertEqual(r['original_pairs_duplicated'], 0)

if __name__ == '__main__':
    unittest.main()
