import unittest

from .synthetic_admission import GB, choose


class AdmissionTests(unittest.TestCase):
    def test_three_when_genuine_raw_headroom(self):
        self.assertEqual(choose(30*GB, 20*GB, 8*GB), 3)

    def test_two_when_raw_memory_is_tight_but_cache_reclaimable(self):
        self.assertEqual(choose(30*GB, 28*GB, 18*GB), 2)

    def test_two_when_raw_not_sufficient_for_three(self):
        self.assertEqual(choose(30*GB, 22*GB-1, 4*GB), 3)
        self.assertEqual(choose(30*GB, 23*GB, 7*GB), 2)

    def test_fail_closed_if_memory_not_reclaimable(self):
        with self.assertRaises(OSError):
            choose(30*GB, 29*GB, 2*GB)

    def test_reject_unbounded_or_invalid_readings(self):
        for data in ((0, 0, 0), (30*GB, -1, 0),
                     (30*GB, 20*GB, 21*GB)):
            with self.assertRaises(ValueError):
                choose(*data)
