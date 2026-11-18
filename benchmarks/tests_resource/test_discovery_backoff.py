"""Discovery failures must not increase scan frequency under load."""
from unittest import TestCase
from unittest.mock import patch

from benchmarks.resource_telemetry import watch


class DiscoveryBackoffTests(TestCase):
    def test_failed_discoveries_are_rate_limited(self):
        times = iter([10., 11., 12., 13., 14., 15.])
        calls = []

        def clock():
            try:
                return next(times)
            except StopIteration:
                raise KeyboardInterrupt()

        def fail():
            calls.append(True)
            raise RuntimeError("transient podman 125")

        with patch.object(watch.time, "monotonic", side_effect=clock), \
             patch.object(watch.time, "sleep"), \
             patch.object(watch, "running", side_effect=fail), \
             patch.object(watch.logging, "warning") as warning:
            with self.assertRaises(KeyboardInterrupt):
                watch.watch("/unused")
        self.assertEqual(len(calls), 2)
        self.assertEqual(warning.call_count, 2)
