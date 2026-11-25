"""Startup, kill and restart regressions for the fail-closed guard."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_policy import checked
from assembler_bench.exploratory_runtime import launch, monitor
from fail_closed_guard import binding, heartbeat, lease
from fail_closed_guard.errors import GuardExceeded, OrphanLease
from fail_closed_guard.watch import watch_bound

CID = "a" * 64
REG = Path(__file__).parent / "assembler_bench/exploratory_candidates.json"


def rec(pid, ppid, rss, ns=7, start=100, cmd="micall"):
    return {"pid": pid, "ppid": ppid, "rss": rss, "pid_ns": ns,
            "starttime": start, "cmdline_sha": cmd, "cgroup": "0::/"}


class Proc:
    """Launcher handle whose exit can be scheduled during a startup wait."""

    def __init__(self, exit_after=None, exit_when=None):
        self.calls = 0
        self.exit_after = exit_after
        self.exit_when = exit_when

    def poll(self):
        self.calls += 1
        if self.exit_when is not None and self.exit_when():
            return 0
        if self.exit_after is not None and self.calls > self.exit_after:
            return 0
        return None


class Clock:
    """Monotonic clock driven by injected sleeps; no real time is consumed."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class StartupBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cidfile = Path(self.tmp.name) / "pilot.cid"
        self.config = {"rss_bytes": 1000, "wall_seconds": 30, "registry": {},
                       "baseline": {}, "root": ".", "image_store": ".",
                       "workspace": "."}

    def bind(self, proc, clock, *, config=None, on_bind=None, snapshots=None,
             inspect=None):
        writes = []

        def write_after(n):
            def sleeper(seconds):
                clock.sleep(seconds)
                writes.append(len(clock.sleeps))
                if len(writes) == n:
                    self.cidfile.write_text(CID)
            return sleeper

        proc = proc or Proc(exit_when=lambda: self.cidfile.exists())
        with patch.object(binding, "inspect_pid", side_effect=inspect,
                          return_value=9 if inspect is None else None), \
                patch.object(monitor.proc, "snapshot",
                             side_effect=snapshots or (lambda: {9: rec(9, 0, 1)})):
            return monitor.watch_pilot(
                proc, config or self.config, cidfile=self.cidfile, env={},
                interval=0.25, clock=clock, sleep=write_after(3),
                measure=lambda *a: {"incremental_bytes": 0},
                stop=lambda cid: {"cid": cid, "container_removed": True},
                on_bind=on_bind), clock

    def test_cold_start_waits_for_async_cidfile_inside_wall_budget(self):
        clock = Clock()
        bound, clock = self.bind(None, clock)
        self.assertEqual(bound["cid"], CID)
        self.assertEqual(len(clock.sleeps), 3)
        self.assertTrue(all(0 < value <= 0.25 for value in clock.sleeps))
        self.assertLess(clock(), self.config["wall_seconds"])

    def test_startup_wait_observes_disk_and_counts_against_deadline(self):
        clock = Clock()
        disk_calls = []
        config = dict(self.config, wall_seconds=1)

        def measure(*args):
            disk_calls.append(clock())
            return {"incremental_bytes": 0}

        with patch.object(binding, "inspect_pid", return_value=9), \
                patch.object(monitor.proc, "snapshot", return_value={9: rec(9, 0, 1)}):
            with self.assertRaises(GuardExceeded) as caught:
                monitor.watch_pilot(
                    Proc(), config, cidfile=self.cidfile, env={}, interval=0.25,
                    clock=clock, sleep=clock.sleep, measure=measure,
                    stop=lambda cid: {"cid": cid})
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(len(disk_calls), len(clock.sleeps))
        self.assertLessEqual(clock(), 1)
        self.assertFalse(self.cidfile.exists())

    def test_launcher_exit_during_wait_fails_closed_without_full_wait(self):
        clock = Clock()
        with self.assertRaises(GuardExceeded) as caught:
            self.bind(Proc(exit_after=1), clock,
                      config=dict(self.config, wall_seconds=30))
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(len(clock.sleeps), 1)

    def test_missing_identity_is_terminal_not_retried(self):
        clock = Clock()
        self.cidfile.write_text(CID)

        def no_identity(*args, **kwargs):
            raise GuardExceeded("identity_lost")

        with self.assertRaises(GuardExceeded) as caught:
            self.bind(None, clock, inspect=no_identity)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(clock.sleeps, [])

    def test_unsafe_or_invalid_cidfile_is_not_retried(self):
        for content in ("not-a-cid", "z" * 64):
            with self.subTest(content=content):
                self.cidfile.write_text(content)
                fresh = Clock()
                with self.assertRaises(GuardExceeded) as caught:
                    self.bind(Proc(), fresh)
                self.assertEqual(caught.exception.reason, "binding_unavailable")
                self.assertEqual(fresh.sleeps, [])

    def test_real_async_writer_binds_without_podman(self):
        """Real cidfile creation in another thread, real sleeps, fake inspect."""

        def writer():
            time.sleep(0.06)
            self.cidfile.write_text(CID)

        thread = threading.Thread(target=writer)
        thread.start()
        with patch.object(binding, "inspect_pid", return_value=9), \
                patch.object(monitor.proc, "snapshot", return_value={9: rec(9, 0, 1)}):
            try:
                result = monitor.watch_pilot(
                    Proc(exit_when=lambda: self.cidfile.exists()), self.config,
                    cidfile=self.cidfile, env={}, interval=0.01,
                    measure=lambda *a: {"incremental_bytes": 0},
                    stop=lambda cid: {"cid": cid, "container_removed": True})
            finally:
                thread.join(timeout=5)
        self.assertEqual(result["cid"], CID)
        self.assertTrue(result["teardown"]["container_removed"])


class FailClosedTeardownTests(unittest.TestCase):
    def watch(self, *, limit=100, wall=1, stop=None, snapshots=None,
              measure=None, sleep=None, clock=None, rss_fn=None):
        table = {100: rec(100, 0, 50), 101: rec(101, 100, 20, start=101)}
        snaps = snapshots or [table]
        stopped = []
        used = [0]

        def take():
            used[0] += 1
            return snaps[min(used[0] - 1, len(snaps) - 1)]

        def live():
            return used[0] < len(snaps)

        def terminate(cid):
            stopped.append(cid)
            return {"cid": cid, "container_removed": True}

        clock = clock or Clock()
        result = watch_bound(
            {"cid": CID, "fingerprint": None}, limit=limit, wall_seconds=wall,
            running=live if snapshots else (lambda: True), snapshot=take,
            measure=measure or (lambda: {"incremental_bytes": 0}),
            stop=stop or terminate, clock=clock,
            sleep=sleep or clock.sleep, interval=0.25,
            rss_fn=rss_fn or (lambda t, b: sum(item["rss"] for item in t.values())))
        return result, stopped

    def test_wall_limit_tears_down_and_keeps_peak(self):
        clock = Clock()
        with self.assertRaises(GuardExceeded) as caught:
            self.watch(wall=1, clock=clock)
        exc = caught.exception
        self.assertEqual(exc.reason, "wall_limit")
        self.assertEqual(exc.peak_rss, 70)
        self.assertEqual(exc.teardown["cid"], CID)
        self.assertEqual(exc.guard_result["peak_rss"], 70)

    def test_disk_exception_during_watch_tears_down(self):
        calls = [0]

        def measure():
            calls[0] += 1
            if calls[0] == 2:
                raise FileNotFoundError("overlay path disappeared")
            return {"incremental_bytes": 0}

        with self.assertRaises(GuardExceeded) as caught:
            self.watch(measure=measure)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")
        self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)
        self.assertEqual(caught.exception.teardown["cid"], CID)

    def test_harness_timeout_tears_down_and_is_not_a_success(self):
        def timeout(_seconds):
            raise subprocess.TimeoutExpired(["watch"], 1)

        with self.assertRaises(GuardExceeded) as caught:
            self.watch(sleep=timeout)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")
        self.assertIsInstance(caught.exception.__cause__, subprocess.TimeoutExpired)
        self.assertEqual(caught.exception.teardown["cid"], CID)

    def test_disappearing_descendant_retains_peak_then_proves_teardown(self):
        full = {100: rec(100, 0, 50), 101: rec(101, 100, 30, start=101)}
        gone = {100: rec(100, 0, 50)}
        result, stopped = self.watch(wall=100, snapshots=[full, gone],
                                     rss_fn=lambda table, b: sum(
                                         item["rss"] for item in table.values()))
        self.assertEqual(result["peak_rss"], 80)
        self.assertEqual(stopped, [CID])
        self.assertTrue(result["teardown"]["container_removed"])


class LauncherRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        self.cidfile = self.root / "pilot.cid"
        self.cidfile.write_text(CID)
        self.policy = copy.deepcopy(checked(REG))
        self.policy["policy"]["dedicated_podman_storage_conf"] = str(
            self.root / "storage.conf")
        self.policy["policy"]["dedicated_image_store_root"] = str(self.store)
        (self.root / "storage.conf").write_text(
            '[storage]\ndriver = "overlay"\ngraphroot = "' + str(self.store / "store")
            + '"\nrunroot = "' + str(self.store / "run") + '"\n')
        base = {"schema": "ivanka.exploratory.storage-baseline.v1",
                "root": str(self.root), "image_store": str(self.store),
                "workspace": str(self.root), "base_store_bytes": 0,
                "frozen_manifest_sha256":
                    self.policy["policy"]["frozen_seven_manifest_sha256"],
                "active_job": None}
        self.baseline = self.root / "baseline.json"
        self.baseline.write_text(json.dumps(base))
        self.policy["storage_baseline_sha256"] = hashlib.sha256(
            self.baseline.read_bytes()).hexdigest()
        for target, value in (
                ("assembler_bench.exploratory_runtime.setup.checked", self.policy),
                ("assembler_bench.exploratory_runtime.setup.eligible", True),
                ("assembler_bench.exploratory_space.available", 100 * 1024**3)):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

        def finish(proc):
            proc.returncode = 0
            return 0

        patcher = patch("assembler_bench.exploratory_runtime.launch.group", finish)
        patcher.start()
        self.addCleanup(patcher.stop)

    def operate(self):
        heartbeat.ping(self.root)
        return launch.operate(REG, self.baseline, "skesa", "pilot",
                              [sys.executable, "-c", "print('hello')"], 1024**3)

    def test_bound_cid_survives_vanished_cidfile_and_releases_lease(self):
        proof = {"cid": CID, "container_removed": True, "kernel_enforcement": False}

        def watch(proc, cfg, on_bind=None, **kwargs):
            proc.returncode = 0
            on_bind({"cid": CID, "pid": 9, "fingerprint": [100, 7, "sha"]})
            # Emulate --rm: the cidfile is gone before cleanup runs.
            self.cidfile.unlink()
            return {"peak_rss": 42, "cid": CID, "teardown": proof,
                    "enforcement": "userspace_observed", "kernel_enforcement": False}

        with patch.object(launch, "bind_pilot", return_value=(
                [sys.executable], self.cidfile)), \
                patch.object(launch, "watch", side_effect=watch), \
                patch.object(launch, "prove_pilot_absent",
                             return_value={"pilot_container_id": CID,
                                           "container_removed": True,
                                           "fresh_absence_check": True}) as prove, \
                patch.object(launch, "stop_pilot",
                             side_effect=AssertionError("duplicate cid cleanup")), \
                patch.object(launch.job_temp, "clean_job_temp",
                             return_value={"removed": True}) as clean:
            state = self.operate()

        self.assertEqual(state["status"], "finished")
        self.assertNotIn("pilot_cleanup_error", state)
        self.assertEqual(state["bound_cid"], CID)
        prove.assert_called_once()
        self.assertEqual(prove.call_args[0][2], CID)
        self.assertEqual(prove.call_args[0][3], proof)
        clean.assert_called_once()
        events = lease.events(self.root)
        latest = lease.latest(events)
        self.assertEqual(latest[next(iter(latest))]["cid"], CID)
        self.assertEqual(latest[next(iter(latest))]["state"], "released")
        self.assertFalse(self.cidfile.exists())

    def test_killed_guard_keeps_peak_and_teardown_before_release(self):
        proof = {"cid": CID, "container_removed": True}
        failure = GuardExceeded("wall_limit")
        failure.peak_rss = 137
        failure.guard_result = {"peak_rss": 137, "cid": CID, "teardown": proof,
                                "enforcement": "userspace_observed"}
        failure.teardown = proof

        def watch(proc, cfg, on_bind=None, **kwargs):
            on_bind({"cid": CID, "pid": 9, "fingerprint": [100, 7, "sha"]})
            self.cidfile.unlink()
            raise failure

        with patch.object(launch, "bind_pilot", return_value=(
                [sys.executable], self.cidfile)), \
                patch.object(launch, "watch", side_effect=watch), \
                patch.object(launch, "prove_pilot_absent",
                             return_value={"pilot_container_id": CID,
                                           "container_removed": True,
                                           "fresh_absence_check": True}), \
                patch.object(launch, "stop_pilot",
                             side_effect=AssertionError("duplicate cid cleanup")), \
                patch.object(launch.job_temp, "clean_job_temp",
                             return_value={"removed": True}):
            state = self.operate()

        self.assertEqual(state["status"], "killed")
        self.assertEqual(state["reason"], "wall_limit")
        self.assertEqual(state["peak_rss"], 137)
        self.assertEqual(state["guard_result"]["teardown"], proof)
        self.assertNotIn("pilot_cleanup_error", state)
        latest = lease.latest(lease.events(self.root))
        event = latest[next(iter(latest))]
        self.assertEqual(event["state"], "released")
        self.assertEqual(event["cid"], CID)

    def test_crashed_launcher_orphan_recovers_from_journal_cid(self):
        lease.acquire(self.root, "crashed", "pilot", cidfile=self.cidfile)
        lease.bind_cid(self.root, "crashed", CID, cidfile=self.cidfile)
        # --rm can delete the cidfile while the journal CID survives.
        self.cidfile.unlink()
        self.env = {"CONTAINERS_STORAGE_CONF": str(self.root / "storage.conf")}
        with patch.object(binding, "command", return_value=CID + "\n"):
            report = lease.reconcile(self.root, self.env)
            with self.assertRaises(OrphanLease):
                lease.require_clear(self.root, self.env)
        self.assertEqual(report["blocked"][0]["reason"], "orphan_container_alive")
        self.assertEqual(report["blocked"][0]["cid"], CID)
        with patch.object(binding, "command", return_value=""):
            cleared = lease.require_clear(self.root, self.env)
        self.assertEqual(cleared["blocked"], [])
        self.assertEqual(cleared["closed"][0]["cid"], CID)
        latest = lease.latest(lease.events(self.root))
        self.assertEqual(latest["crashed"]["state"], "reconciled")


class DiskAccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {"rss_bytes": 1000, "wall_seconds": 100, "registry": {},
                       "baseline": {}, "root": ".", "image_store": ".",
                       "workspace": "."}

    def measure(self, config, margin, measure):
        from assembler_bench.exploratory_runtime.monitor import _disk
        return _disk(config, margin, measure)

    def test_transient_enoent_is_retried_without_inventing_zero_bytes(self):
        calls = [0]

        def measure(*args):
            calls[0] += 1
            if calls[0] < 3:
                raise FileNotFoundError("layer path temporarily absent")
            return {"incremental_bytes": 500}

        # Startup binding and the watcher both observe disk through _disk; a
        # transient absence must not be cached as a zero-byte admission.
        self.assertEqual(self.measure(self.config, 1024**3, measure),
                         {"incremental_bytes": 500})
        self.assertEqual(calls[0], 3)

    def test_persistent_enoent_fails_closed(self):
        def measure(*args):
            raise FileNotFoundError("store unavailable")

        with self.assertRaises(GuardExceeded) as caught:
            self.measure(self.config, 1024**3, measure)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_large_incremental_usage_has_no_project_ceiling(self):
        def measure(*args):
            return {"incremental_bytes": 200 * 1024**3}

        self.assertEqual(self.measure(self.config, 1024**3, measure),
                         {"incremental_bytes": 200 * 1024**3})

    def test_reserve_breach_fails_closed_with_disk_limit(self):
        def measure(*args):
            raise ValueError("exploration would breach the workspace reserve")

        with self.assertRaises(GuardExceeded) as caught:
            self.measure(self.config, 1024**3, measure)
        self.assertEqual(caught.exception.reason, "disk_limit")


if __name__ == "__main__":
    unittest.main()
