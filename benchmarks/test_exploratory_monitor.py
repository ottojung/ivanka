"""No invisible wall/RSS/disk failures may escape supervisor."""
import unittest

from assembler_bench.exploratory_runtime.monitor import GuardExceeded, watch


class Dummy:
    pid = 123
    count = 0

    def poll(self):
        self.count += 1
        return None if self.count < 3 else 0


class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.params = {"wall_seconds": 2400, "rss_bytes": 4_000_000_000,
                       "registry": {}, "baseline": {}, "root": ".",
                       "image_store": ".", "workspace": ".",
                       "budget_bytes": 8 * 1024**3}
        self.measure = lambda *a: {"incremental_bytes": 1024}
        self.clock = lambda: 10

    def test_normal_sampled_monitor(self):
        result = watch(Dummy(), self.params, measure=self.measure,
                       rss=lambda pid: 100, clock=self.clock, sleep=lambda s: None)
        self.assertEqual(result, 100)

    def test_rss_kill(self):
        with self.assertRaisesRegex(GuardExceeded, "observed_rss_limit"):
            watch(Dummy(), self.params, measure=self.measure,
                  rss=lambda pid: 4_000_000_001, clock=self.clock, sleep=lambda s: None)

    def test_disk_kill(self):
        with self.assertRaises(GuardExceeded):
            watch(Dummy(), self.params, measure=lambda *a: {
                "incremental_bytes": 8*1024**3}, rss=lambda pid: 0,
                clock=self.clock, sleep=lambda s: None)

    def test_actual_disk_admission_overflow_is_not_unknown_telemetry(self):
        def budget_exceeded(*args):
            raise ValueError("exploration would breach disk budget or workspace reserve")

        with self.assertRaisesRegex(GuardExceeded, "disk_limit"):
            watch(Dummy(), self.params, measure=budget_exceeded,
                  rss=lambda pid: 0, clock=self.clock, sleep=lambda s: None)

    def test_bad_policy_measurement_still_fails_closed(self):
        def bad_policy(*args):
            raise ValueError("invalid or concurrently active exploration admission")

        with self.assertRaisesRegex(GuardExceeded, "measurement_unavailable"):
            watch(Dummy(), self.params, measure=bad_policy,
                  rss=lambda pid: 0, clock=self.clock, sleep=lambda s: None)

    def test_measurement_failure_kills(self):
        with self.assertRaisesRegex(GuardExceeded, "measurement_unavailable"):
            watch(Dummy(), self.params, measure=lambda *a: 1/0,
                  rss=lambda pid: 0, clock=self.clock, sleep=lambda s: None)

    def test_requires_fast_poll(self):
        with self.assertRaises(ValueError):
            watch(Dummy(), self.params, interval=2)
