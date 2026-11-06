import unittest
from pathlib import Path
from marker_bearing_pair_guard import assess_safe_restorations

S48B = '/workspace/ivanka-lab/snv-full-micall-ab-20261105/outputs/pinned-wrapper-main-vs-snv-cap1000/73090AMIDI-MidHCV_S48/baseline'
S48E = '/workspace/ivanka-lab/snv-full-micall-ab-20261105/outputs/pinned-wrapper-main-vs-snv-cap1000/73090AMIDI-MidHCV_S48/experimental'
S12B = '/workspace/ivanka-lab/snv-full-micall-ab-20261105/outputs/pinned-wrapper-main-vs-snv-cap1000/73111AMIDI-MidHCV_S12/baseline'
S12E = '/workspace/ivanka-lab/snv-full-micall-ab-20261105/outputs/pinned-wrapper-main-vs-snv-cap1000/73111AMIDI-MidHCV_S12/experimental'

class T(unittest.TestCase):
    @unittest.skipUnless(Path(S48B).is_dir() and Path(S48E).is_dir(),
                         'Private S48 original-data artifacts not in public CI')
    def test_s48_original_pair_exact_sequence_match_recovery_is_diagnostic(self):
        r = assess_safe_restorations(S48B, S48E)
        self.assertEqual(r['moved_pairs'], 2471)
        self.assertGreaterEqual(r['restorable_to_identical_baseline_reference'],2400)
        self.assertEqual(r['restoration_applied'], False)
        self.assertEqual(r['original_pairs_duplicated'], 0)
        # Restoration is only an offline hypothetical; original source untouched.
        self.assertEqual(r['restorable_to_identical_baseline_reference'] + r['unsafe_sequence_changed_or_missing_baseline_reference'], r['moved_pairs'])

    @unittest.skipUnless(Path(S12B).is_dir() and Path(S12E).is_dir(),
                         'Private S12 original-data artifacts not in public CI')
    def test_s12_original_pair_exact_sequence_match_diagnostic(self):
        r = assess_safe_restorations(S12B, S12E)
        self.assertEqual(r['restoration_applied'], False)
        self.assertEqual(r['original_pairs_duplicated'], 0)
        self.assertEqual(r['moved_pairs'],27)

if __name__ == '__main__':
    unittest.main()
