"""Fail-closed guard tests: mocked races, real /proc, CID-only teardown."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_runtime import monitor
from fail_closed_guard import binding, build, proc, teardown, tree
from fail_closed_guard.errors import GuardExceeded, TeardownError
from fail_closed_guard.identity import fingerprint
from fail_closed_guard.watch import watch_bound

CID = "a" * 64


def rec(pid, ppid, rss, ns=7, start=100, cmd="micall"):
    return {"pid": pid, "ppid": ppid, "rss": rss, "pid_ns": ns,
            "starttime": start, "cmdline_sha": cmd, "cgroup": "0::/"}


class DummyProc:
    def __init__(self, pid=4242):
        self.pid = pid

    def poll(self):
        return None

    def wait(self, timeout=5):
        return 0


class GuardTests(unittest.TestCase):
    def watch(self, finger, snaps, stop, keep_running=False):
        iterator = iter(snaps)
        used = [0]

        def running():
            return keep_running or used[0] < len(snaps)

        def take():
            used[0] += 1
            return next(iterator)

        return watch_bound({"cid": CID, "fingerprint": finger},
                           limit=4_000_000_000, wall_seconds=100,
                           running=running, snapshot=take,
                           measure=lambda: {}, stop=stop,
                           clock=lambda: 0.0, sleep=lambda _: None)

    def test_pid_reuse_fails_closed_without_stopping_new_process(self):
        stopped = []
        snaps = [{100: rec(100, 0, 1000)},
                 {100: rec(100, 0, 9_000_000_000, start=999)}]

        def stop(cid):
            # Same-CID removal is always safe; no PID is ever signalled, so a
            # reused PID belonging to an unrelated process survives.
            stopped.append(cid)
            return {"cid": cid, "container_removed": True}

        with self.assertRaises(GuardExceeded) as caught:
            self.watch(fingerprint(rec(100, 0, 1000)), snaps, stop,
                       keep_running=True)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(stopped, [CID])
        self.assertEqual(caught.exception.teardown["cid"], CID)

    def test_reparented_descendant_in_same_namespace_is_counted(self):
        snaps = [{100: rec(100, 0, 1_000_000_000),
                  101: rec(101, 100, 1_000_000_000, start=101),
                  102: rec(102, 1, 1_000_000_000, start=102)}]
        total = self.watch(fingerprint(rec(100, 0, 1000)), snaps, lambda _: None)
        self.assertEqual(total["peak_rss"], 3_000_000_000)

    def test_exceeded_limit_stops_only_exact_cid(self):
        stopped = []
        snaps = [{100: rec(100, 0, 3_000_000_000),
                  101: rec(101, 100, 1_500_000_000, start=101),
                  999: rec(999, 0, 9_000_000_000, ns=8, start=5, cmd="other")}]
        with self.assertRaises(GuardExceeded) as caught:
            self.watch(fingerprint(rec(100, 0, 1000)), snaps, stopped.append)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual(stopped, [CID])

    def test_null_observation_fails_closed(self):
        with self.assertRaises(GuardExceeded) as caught:
            tree.rss_bytes({1: rec(1, 0, None)}, {1})
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_null_observation_from_real_proc_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            pid_dir = Path(folder, "123")
            (pid_dir / "ns").mkdir(parents=True)
            fields = ["S", "1"] + ["0"] * 17 + ["55"]
            (pid_dir / "stat").write_text(f"123 (x) {' '.join(fields)}\n")
            (pid_dir / "ns" / "pid").write_text("")
            (pid_dir / "cmdline").write_bytes(b"cmd")
            (pid_dir / "cgroup").write_text("0::/\n")
            (pid_dir / "status").write_text("Name:\tx\n")
            table = proc.snapshot(folder)
            self.assertIsNone(table[123]["rss"])
            self.assertEqual(table[123]["starttime"], 55)

    def test_real_short_non_container_snapshot(self):
        child = subprocess.Popen(["sleep", "0.2"])
        try:
            record = proc.snapshot().get(child.pid)
            self.assertIsNotNone(record)
            self.assertIsInstance(record["rss"], int)
            self.assertEqual(record["pid_ns"],
                             Path("/proc/self/ns/pid").stat().st_ino)
        finally:
            child.wait(timeout=5)

    def test_binding_requires_exact_cid(self):
        table = {555: rec(555, 0, 1000)}
        with patch.object(binding, "inspect_pid", return_value=555):
            bound = binding.bind_container(CID, {}, snapshot=table)
            self.assertEqual(bound["cid"], CID)
            self.assertEqual(bound["pid"], 555)
        with self.assertRaises(GuardExceeded):
            binding.bind_container("z" * 64, {}, snapshot=table)

    def test_teardown_proves_exact_cid_removed(self):
        with patch.object(teardown, "_listed", side_effect=[{CID}, set()]), \
                patch.object(teardown.subprocess, "run") as runner:
            result = teardown.stop_cid({}, CID)
            self.assertTrue(result["container_removed"])
            self.assertEqual(runner.call_args[0][0][-1], CID)
        with patch.object(teardown, "_listed", side_effect=[{CID}, {CID}]), \
                patch.object(teardown.subprocess, "run"):
            with self.assertRaises(TeardownError):
                teardown.stop_cid({}, CID)

    def test_pilot_watch_breach_stops_by_cid_not_pid(self):
        config = {"rss_bytes": 1000, "wall_seconds": 100, "registry": {},
                  "baseline": {}, "root": ".", "image_store": ".",
                  "workspace": "."}
        bound = {"cid": CID, "fingerprint": fingerprint(rec(9, 0, 1))}
        snaps = [{9: rec(9, 0, 5000)}, {9: rec(9, 0, 5000)}]
        stopped = []
        with patch.object(monitor.binding, "bind_container", return_value=bound), \
                patch.object(monitor.binding, "read_cid", return_value=CID), \
                patch.object(monitor.proc, "snapshot", side_effect=snaps):
            with self.assertRaises(GuardExceeded) as caught:
                monitor.watch_pilot(DummyProc(), config, cidfile=Path("x.cid"),
                                    env={}, measure=lambda *a: {"incremental_bytes": 0},
                                    stop=stopped.append, sleep=lambda _: None,
                                    clock=lambda: 0.0)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual(stopped, [CID])

    def test_build_identity_and_process_group_stop(self):
        table = {77: rec(77, 0, 100, start=77, cmd="build"),
                 78: rec(78, 77, 200, start=78, cmd="child")}
        bound = build.bind_launcher(77, snapshot=table)
        self.assertEqual(build.rss(table, bound), 300)
        with patch.object(build.os, "killpg", side_effect=[None, ProcessLookupError()]) as kill:
            proof = build.stop_group(bound, DummyProc())
        self.assertTrue(proof["stopped"])
        self.assertEqual(kill.call_args_list[0][0][0], 77)


if __name__ == "__main__":
    unittest.main()
