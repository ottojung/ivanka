"""No invisible wall/RSS/disk failures may escape supervisor."""
import os
import signal
import unittest
from unittest.mock import patch

from assembler_bench.exploratory_runtime.monitor import GuardExceeded, watch, watch_build


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
                       "image_store": ".", "workspace": "."}
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

    def test_large_incremental_usage_is_not_a_disk_limit(self):
        watched = watch(Dummy(), self.params, measure=lambda *a: {
            "incremental_bytes": 200 * 1024**3}, rss=lambda pid: 0,
            clock=self.clock, sleep=lambda s: None)
        self.assertEqual(watched, 0)

    def test_actual_reserve_breach_is_not_unknown_telemetry(self):
        def reserve_exceeded(*args):
            raise ValueError("exploration would breach the workspace reserve")

        with self.assertRaisesRegex(GuardExceeded, "disk_limit"):
            watch(Dummy(), self.params, measure=reserve_exceeded,
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

    def test_build_exited_during_snapshot_null_record_is_not_killed(self):
        class Exited:
            pid = 424242
            returncode = 0

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

        # Snapshot read raced with exit: pid present but identity unreadable.
        null_record = {"pid": 424242, "ppid": None, "starttime": None,
                       "pid_ns": None, "cmdline_sha": None,
                       "rss": None, "cgroup": None}
        snapshot = lambda: {424242: null_record}
        with patch("assembler_bench.exploratory_runtime.monitor.build.os.killpg",
                   side_effect=ProcessLookupError):
            result = watch_build(Exited(), self.params, snapshot=snapshot,
                                 measure=self.measure,
                                 clock=lambda: 0, sleep=lambda s: None)
        self.assertIsNone(result["peak_rss"])
        self.assertIsNone(result["cid"])
        self.assertEqual(result["teardown"],
                         {"process_group": 424242, "stopped": True})
        self.assertEqual(result["enforcement"], "userspace_observed")
        self.assertFalse(result["kernel_enforcement"])

    def test_build_live_unreadable_snapshot_fails_closed(self):
        class Running:
            pid = 434343

            def poll(self):
                return None

            def wait(self, timeout=None):
                return -15

        null_record = {"pid": 434343, "ppid": None, "starttime": None,
                       "pid_ns": None, "cmdline_sha": None,
                       "rss": None, "cgroup": None}
        snapshot = lambda: {434343: null_record}
        with patch("assembler_bench.exploratory_runtime.monitor.build.os.killpg",
                   side_effect=ProcessLookupError):
            with self.assertRaisesRegex(GuardExceeded, "measurement_unavailable") as caught:
                watch_build(Running(), self.params, snapshot=snapshot,
                            measure=self.measure,
                            clock=lambda: 0, sleep=lambda s: None)
        self.assertEqual(caught.exception.teardown,
                         {"process_group": 434343, "stopped": True})
