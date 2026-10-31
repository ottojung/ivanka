"""Regression for concurrent benchmark invocations in PID-reused containers."""
import re
import unittest
from unittest.mock import patch

import bench


class InvocationIdTests(unittest.TestCase):
    def test_same_second_and_pid_have_distinct_invocation_ids(self):
        with patch.object(bench.time, "time", return_value=1700000000), \
             patch.object(bench.os, "getpid", return_value=1):
            ids = [bench.new_invocation_id() for _ in range(100)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.fullmatch(r"1700000000-1-[0-9a-f]{32}", value)
                            for value in ids))
