import unittest
from unittest.mock import patch
from .signals import enforce


class SignalTests(unittest.TestCase):
    @patch("benchmarks.memory_guard.signals.os.kill")
    @patch("benchmarks.memory_guard.signals.time.monotonic", side_effect=[10, 11, 13])
    def test_escalation_once(self, clock, kill):
        events = []
        def report(*args):
            events.append(args[-1])
        pending = {}
        for _ in range(3):
            enforce(12, {12, 13}, "micall analyze sample /reads/R1", 3800000000,
                    pending, report)
        self.assertEqual(events, ["SIGTERM", "SIGKILL"])
        self.assertEqual(kill.call_count, 4)
