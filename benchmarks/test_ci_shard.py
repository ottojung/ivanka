"""Guards for the exact-discovery, Counter-preserving CI shard partition."""

import collections
import unittest
from unittest import mock

from benchmarks import ci_shard


class AlphaTests(unittest.TestCase):
    def test_first(self):
        pass

    def test_second(self):
        pass


class BetaTests(unittest.TestCase):
    def test_third(self):
        pass


class GammaTests(unittest.TestCase):
    def test_extra(self):
        pass


# Distinct simulated modules so partition tests exercise module grouping.
AlphaTests.__module__ = "alpha_mod"
BetaTests.__module__ = "beta_mod"
GammaTests.__module__ = "gamma_mod"


class CIShardTests(unittest.TestCase):
    def test_discover_uses_original_root_and_pattern(self):
        suite = unittest.TestSuite()
        with mock.patch.object(unittest, "TestLoader") as loader_cls:
            loader = loader_cls.return_value
            loader.discover.return_value = suite
            loader.errors = []
            self.assertEqual(ci_shard.discover_tests(), [])
            loader.discover.assert_called_once_with(
                ci_shard.START_DIR, pattern=ci_shard.PATTERN
            )

    def test_discovery_errors_fail_closed(self):
        with mock.patch.object(unittest, "TestLoader") as loader_cls:
            loader = loader_cls.return_value
            loader.discover.return_value = unittest.TestSuite()
            loader.errors = ["boom"]
            with self.assertRaises(RuntimeError):
                ci_shard.discover_tests()

    def test_flatten_preserves_nested_suite_order(self):
        suite = unittest.TestSuite([
            unittest.TestSuite([
                AlphaTests("test_first"), AlphaTests("test_second"),
            ]),
            BetaTests("test_third"),
        ])
        self.assertEqual(
            [t.id() for t in ci_shard.flatten(suite)],
            [
                AlphaTests("test_first").id(),
                AlphaTests("test_second").id(),
                BetaTests("test_third").id(),
            ],
        )

    def test_nested_module_group_uses_full_module_name(self):
        class NestedTests(unittest.TestCase):
            def test_nested(self):
                pass

        NestedTests.__module__ = "memory_guard.test_guard"
        test = NestedTests("test_nested")
        self.assertEqual(ci_shard.module_group(test), "memory_guard.test_guard")
        self.assertTrue(test.id().startswith("memory_guard.test_guard."))

    def test_partition_keeps_multiset_and_per_module_order(self):
        tests = [
            AlphaTests("test_first"),
            BetaTests("test_third"),
            AlphaTests("test_second"),
            AlphaTests("test_first"),  # deliberate inherited duplicate
        ]
        shards = ci_shard.partition(tests, 2)
        aggregate = [t for shard in shards for t in shard]
        self.assertEqual(
            collections.Counter(t.id() for t in aggregate),
            collections.Counter(t.id() for t in tests),
        )
        for shard in shards:
            for group in {ci_shard.module_group(t) for t in shard}:
                self.assertEqual(
                    [t.id() for t in shard if ci_shard.module_group(t) == group],
                    [t.id() for t in tests if ci_shard.module_group(t) == group],
                )
        ci_shard.verify(tests, shards)

    def test_partition_is_deterministic(self):
        tests = [AlphaTests("test_first"), BetaTests("test_third")]
        first = ci_shard.partition(tests, 4)
        second = ci_shard.partition(list(tests), 4)
        self.assertEqual(
            [[t.id() for t in shard] for shard in first],
            [[t.id() for t in shard] for shard in second],
        )

    def test_verify_rejects_extra_duplicate(self):
        tests = [AlphaTests("test_first"), BetaTests("test_third")]
        shards = ci_shard.partition(tests, 2)
        shards[0].append(GammaTests("test_extra"))
        with self.assertRaises(RuntimeError) as raised:
            ci_shard.verify(tests, shards)
        self.assertIn("differs from discovery", str(raised.exception))

    def test_verify_rejects_empty_shard(self):
        tests = [AlphaTests("test_first")]
        shards = ci_shard.partition(tests, 2)
        with self.assertRaises(RuntimeError):
            ci_shard.verify(tests, shards)

    def test_verify_rejects_missing_test(self):
        tests = [AlphaTests("test_first"), BetaTests("test_third")]
        shards = ci_shard.partition(tests, 2)
        shards[1] = []
        shards[0].append(BetaTests("test_third"))
        with self.assertRaises(RuntimeError):
            ci_shard.verify(tests, shards)

    def test_invalid_total(self):
        with self.assertRaises(ValueError):
            ci_shard.partition([AlphaTests("test_first")], 0)

    def test_main_runs_only_selected_shard(self):
        tests = [AlphaTests("test_first"), BetaTests("test_third")]
        argv = ["ci_shard", "--total", "2", "--index", "1"]
        with mock.patch.object(ci_shard, "discover_tests", return_value=tests), \
             mock.patch("sys.argv", argv):
            self.assertEqual(ci_shard.main(), 0)


if __name__ == "__main__":
    unittest.main()
