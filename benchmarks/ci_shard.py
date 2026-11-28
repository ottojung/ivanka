"""Deterministic sharding of the exact unittest discovery suite.

Loads the same suite as:
    python -m unittest discover -s benchmarks -p 'test_*.py' -v

using TestLoader.discover with the original discovery root and sys.path, so
load_tests, skips, import errors and inherited duplicate test IDs are
preserved. The suite is flattened and partitioned by whole test modules (the
module prefix of test.id()). Before any test runs, the full discovered
Counter(test.id()) is compared with the aggregate of all shards; a new
discrepancy, an empty shard, or a discovery error fails closed.
"""

from __future__ import annotations

import argparse
import collections
import unittest


START_DIR = "benchmarks"
PATTERN = "test_*.py"


def flatten(suite):
    """Yield test instances in the suite's original order."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def discover_tests():
    """Discover with the original root/pattern and return a flat test list."""
    loader = unittest.TestLoader()
    suite = loader.discover(START_DIR, pattern=PATTERN)
    if loader.errors:
        raise RuntimeError("test discovery errors: " + "; ".join(loader.errors))
    tests = list(flatten(suite))
    broken = [t.id() for t in tests if type(t).__name__ == "_FailedTest"]
    if broken:
        raise RuntimeError("discovery produced failed imports: " + ", ".join(broken))
    return tests


def module_group(test):
    """Module prefix of a test id, e.g. ``memory_guard.test_guard``."""
    module = type(test).__module__
    if test.id().startswith(module + "."):
        return module
    # Unusual dynamic test ids: strip the class and method components.
    return ".".join(test.id().split(".")[:-2])


def partition(tests, total):
    """Assign whole module groups round-robin, keeping per-module suite order."""
    if total < 1:
        raise ValueError("total must be >= 1")
    groups = sorted({module_group(t) for t in tests})
    assignment = {group: index % total for index, group in enumerate(groups)}
    shards = [[] for _ in range(total)]
    for test in tests:
        shards[assignment[module_group(test)]].append(test)
    return shards


def verify(tests, shards):
    """Fail on any new difference from unsharded discovery or an empty shard."""
    original = collections.Counter(t.id() for t in tests)
    aggregate = collections.Counter(t.id() for shard in shards for t in shard)
    if aggregate != original:
        raise RuntimeError(
            "shard aggregate differs from discovery: "
            f"missing={dict(original - aggregate)} extra={dict(aggregate - original)}"
        )
    if sum(len(shard) for shard in shards) != len(tests):
        raise RuntimeError("shard instance count differs from discovery")
    if any(not shard for shard in shards):
        raise RuntimeError("empty shard")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total", type=int, default=4)
    parser.add_argument("--index", type=int)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    tests = discover_tests()
    shards = partition(tests, args.total)
    verify(tests, shards)

    if args.self_test:
        print(
            f"discovery OK: {len(tests)} test instances, "
            f"{len(set(t.id() for t in tests))} unique ids, "
            f"{len(shards)} non-empty shards"
        )
        return 0

    if args.index is None or not 0 <= args.index < args.total:
        raise SystemExit(f"--index must be in [0, {args.total})")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite(shards[args.index])
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
