"""Deterministic crash-race tests for the shared independent watchdog."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fail_closed_guard import binding, heartbeat, lease, teardown, watchdog
from fail_closed_guard.errors import GuardExceeded, OrphanLease

CID = "a" * 64
CID_B = "c" * 64
OTHER = "b" * 64
GRAPHROOT = "/workspace/ivanka-exploratory-podman-20261121/store"
WORKER = "watchdog-worker"
FREE = 40_000_000_000


def rec(pid, ppid, rss, ns=7, start=100, cmd="ctrl"):
    return {"pid": pid, "ppid": ppid, "rss": rss, "pid_ns": ns,
            "starttime": start, "cmdline_sha": cmd, "cgroup": "0::/"}


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.conf = self.root / "storage.conf"
        self.conf.write_text(
            "[storage]\ndriver = overlay\ngraphroot = %s\nrunroot = %s/run\n"
            % (GRAPHROOT, GRAPHROOT))
        self.env = {"CONTAINERS_STORAGE_CONF": str(self.conf),
                    "CONTAINERS_CONF": "/host/other.conf"}
        self.clock = Clock()
        self.wall_now = 0.0
        self.podman_calls = []
        self.stopped = []
        command_patch = patch.object(binding, "command", side_effect=self.fake_command)
        command_patch.start()
        self.addCleanup(command_patch.stop)

    def wall(self):
        return self.wall_now + self.clock.now

    def fake_command(self, argv, env, timeout=15):
        self.podman_calls.append(list(argv))
        if argv[1] == "info":
            return GRAPHROOT + "\n"
        if argv[1] == "inspect":
            return "%s 100\n" % CID
        if argv[1] == "ps":
            raise AssertionError("CID must never be inferred from a listing")
        raise AssertionError("unexpected command %r" % (argv,))

    def make_stop(self):
        def stop(cid):
            self.stopped.append(cid)
            return {"cid": cid, "container_removed": True,
                    "method": "exact_cid_inspect", "kernel_enforcement": False}
        return stop

    def issue(self, worker=WORKER, cid=CID, *, journal_cid=True,
              write_cidfile=True, start=None, mode="pilot"):
        cidfile = self.root / (worker + ".cid")
        if write_cidfile and cid is not None:
            cidfile.write_text(cid)
        self.wall_now = start if start is not None else 1000.0
        lease.append(self.root, {
            "schema": lease.SCHEMA, "lease": worker, "state": "active",
            "mode": mode, "cid": cid if journal_cid else None,
            "cidfile": str(cidfile),
            "pid": 100 if journal_cid else None,
            "fingerprint": [50, 99] if journal_cid else None,
            "at_utc": self.wall_now})
        return worker

    def beat(self, worker=WORKER, cid=CID, *, at_monotonic=None,
             target=None, cmd="ctrl"):
        table = {4242: rec(4242, 1, 1000, start=100, cmd=cmd),
                 100: rec(100, 4242, 2000, ns=99, start=50, cmd="micall"),
                 101: rec(101, 100, 500, ns=99, start=51, cmd="child")}
        moment = self.clock.now if at_monotonic is None else at_monotonic
        return heartbeat.emit(
            self.root, worker, pid=4242, table=table, cid=cid,
            monotonic=lambda: moment, wall=self.wall,
            target=target or heartbeat.path(self.root, worker))

    def table(self, controller=True, bound_cmd="micall", bound_start=50,
              child_rss=500):
        table = {}
        if controller:
            table[4242] = rec(4242, 1, 1000, start=100)
        table[100] = rec(100, 4242, 2000, ns=99, start=bound_start, cmd=bound_cmd)
        table[101] = rec(101, 100, child_rss, ns=99, start=51, cmd="child")
        table[777] = rec(777, 1, 10, ns=1234, start=9, cmd="unrelated")
        return table

    def check(self, worker=WORKER, *, snapshots=None, wall_seconds=2400,
              max_age=10000, measure=None, stop=None, rss_limit=None):
        snaps = snapshots if snapshots is not None else [self.table()]
        return watchdog.check_once(
            self.root, worker, storage_conf=self.conf, graphroot=GRAPHROOT,
            env=self.env, heartbeat_path=heartbeat.path(self.root, worker),
            monotonic=self.clock, wall_clock=self.wall,
            snapshot=lambda: snaps[0], measure=(lambda: FREE if measure is None
                                                else measure()),
            stop=self.make_stop() if stop is None else stop,
            wall_seconds=wall_seconds, max_age=max_age,
            rss_limit=watchdog.RSS_LIMIT if rss_limit is None else rss_limit)

    def supervise(self, *, ticks=1, stop_path=None, snapshots=None):
        snaps = snapshots if snapshots is not None else [self.table()]
        return watchdog.supervise(
            self.root, storage_conf=self.conf, graphroot=GRAPHROOT, env=self.env,
            stop_path=stop_path, ticks=ticks, sleep=lambda _: None,
            monotonic=self.clock, wall_clock=self.wall,
            snapshot=lambda: snaps[0], measure=lambda: FREE,
            stop=self.make_stop())

    def evidence(self):
        return watchdog.read_evidence(self.root)

    def test_active_leases_are_discovered_dynamically(self):
        self.assertEqual(watchdog.discover_workers(self.root), [])
        self.issue("alpha")
        self.issue("beta", cid=CID_B)
        self.assertEqual(watchdog.discover_workers(self.root), ["alpha", "beta"])
        lease.release(self.root, "alpha", cid=CID, proof={"container_removed": True})
        self.assertEqual(watchdog.discover_workers(self.root), ["beta"])

    def test_missing_controller_tears_down_exact_cid(self):
        self.issue()
        with patch("os.kill", side_effect=AssertionError("bare PID signal")), \
             patch("os.killpg", side_effect=AssertionError("bare PGID signal")):
            with self.assertRaises(GuardExceeded) as caught:
                self.check()
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.stopped, [CID])
        event = self.evidence()[-1]
        self.assertEqual(event["action"], "teardown")
        self.assertEqual(event["cid_source"], "journal")
        self.assertEqual(caught.exception.evidence, event)

    def test_cidfile_appearing_after_owner_death_is_owned(self):
        self.issue(journal_cid=False, write_cidfile=False)
        (self.root / (WORKER + ".cid")).write_text(CID)
        with self.assertRaises(GuardExceeded) as caught:
            self.check()
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.stopped, [CID])
        event = self.evidence()[-1]
        self.assertEqual(event["cid_source"], "cidfile")
        self.assertEqual(event["lease_state"], "bound")

    def test_pending_without_trusted_cid_does_not_tear_down(self):
        self.issue(journal_cid=False, write_cidfile=False)
        with self.assertRaises(GuardExceeded):
            self.check()
        self.assertEqual(self.stopped, [])
        event = self.evidence()[-1]
        self.assertEqual(event["action"], "none")
        self.assertIsNone(event["cid"])

    def test_exact_cid_never_inferred_from_podman_listing(self):
        self.issue()
        self.beat()
        result = self.check()
        self.assertEqual(result["result"], "observing")
        self.assertTrue(all(argv[1] != "ps" for argv in self.podman_calls))

    def test_pid_reuse_fails_closed_with_identity_evidence(self):
        self.issue()
        self.beat()
        with self.assertRaises(GuardExceeded) as caught:
            self.check(snapshots=[self.table(bound_start=999)])
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.stopped, [CID])
        self.assertFalse(caught.exception.identity_observation["observed"]["identity_matches"])

    def test_monitor_exec_keeps_binding_and_records_cmdline_change(self):
        self.issue()
        bound = watchdog.bound_from_lease(self.root, WORKER, self.env)
        bound["cmdline_sha"] = "micall"
        observed = watchdog.verify_bound(bound, self.env,
                                         self.table(bound_cmd="execed-micall"))
        self.assertEqual(observed["rss"], 2500)
        self.assertTrue(observed["identity"]["observed"]["identity_matches"])
        self.assertTrue(observed["identity"]["observed"]["cmdline_changed"])

    def test_unreadable_child_record_fails_closed(self):
        self.issue()
        self.beat()
        with self.assertRaises(GuardExceeded) as caught:
            self.check(snapshots=[self.table(child_rss=None)])
        self.assertEqual(caught.exception.reason, "measurement_unavailable")
        self.assertEqual(self.stopped, [CID])

    def test_wall_deadline_comes_from_durable_lease_start(self):
        self.issue(start=1000.0)
        self.beat()
        self.check(wall_seconds=2400)
        self.assertEqual(self.evidence(), [])
        # A restarted observer uses the same durable start, not a fresh budget.
        self.clock.advance(2000)
        self.check(wall_seconds=2400)
        self.clock.advance(500)
        with self.assertRaises(GuardExceeded) as caught:
            self.check(wall_seconds=2400)
        self.assertEqual(caught.exception.reason, "wall_limit")
        self.assertEqual(caught.exception.evidence["durable_start"], 1000.0)
        self.assertEqual(self.stopped, [CID])

    def test_invalid_future_and_nonfinite_heartbeat_ages_fail(self):
        self.issue()
        for moment in (self.clock.now + 10, float("nan"), float("inf")):
            with self.subTest(moment=moment):
                self.stopped.clear()
                self.beat(at_monotonic=moment)
                with self.assertRaises(GuardExceeded) as caught:
                    self.check(max_age=10000)
                self.assertEqual(caught.exception.reason, "heartbeat_unreadable")
                self.assertEqual(self.stopped, [CID])
        target = heartbeat.path(self.root, WORKER)
        raw = json.loads(target.read_text())
        del raw["at_monotonic"]
        target.write_text(json.dumps(raw) + "\n")
        with self.assertRaises(GuardExceeded) as caught:
            self.check()
        self.assertEqual(caught.exception.reason, "heartbeat_unreadable")

    def test_stop_boundary_does_not_disable_live_arm_monitoring(self):
        self.issue()
        stop = self.root / "STOP"
        stop.write_text("")
        result = self.supervise(stop_path=stop)
        self.assertEqual(result["result"], "observing")
        self.assertEqual(self.stopped, [CID])
        lease.release(self.root, WORKER, cid=CID, proof={"container_removed": True})
        result = self.supervise(stop_path=stop)
        self.assertEqual(result["result"], "boundary")

    def test_unavailable_watchdog_blocks_admission(self):
        with self.assertRaises(OrphanLease) as caught:
            lease.require_clear(self.root, self.env,
                                watchdog_path=heartbeat.alive_path(self.root))
        self.assertEqual(caught.exception.report["blocked"][0]["reason"],
                         "watchdog_unavailable")
        heartbeat.ping(self.root, wall=self.wall)
        result = lease.require_clear(
            self.root, self.env, watchdog_path=heartbeat.alive_path(self.root),
            wall=self.wall)
        self.assertEqual(result["blocked"], [])

    def test_successive_lease_lifecycle_is_supervised_per_lease(self):
        self.issue("alpha")
        self.beat("alpha")
        self.check("alpha")
        self.assertEqual(self.stopped, [])
        lease.release(self.root, "alpha", cid=CID, proof={"container_removed": True})
        self.issue("beta", cid=CID_B)
        result = self.supervise(ticks=1)
        self.assertEqual(result["workers"], ["beta"])
        self.assertEqual(self.stopped, [CID_B])
        events = self.evidence()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["worker"], "beta")
        self.assertEqual(events[0]["cid"], CID_B)

    def test_disk_reserve_and_rss_budget(self):
        self.assertLess(watchdog.RSS_LIMIT, watchdog.RSS_UPPER_BOUND)
        for free, reason in ((FREE, "observing"),
                             (watchdog.DEFAULT_MIN_FREE
                              + watchdog.DEFAULT_RESERVE - 1, "disk_limit"),
                             (None, "measurement_unavailable")):
            measured = (lambda value=free: value)
            with self.subTest(reason=reason):
                self.issue()
                self.beat()
                self.stopped.clear()
                if reason == "observing":
                    self.assertEqual(
                        self.check(measure=measured)["result"], "observing")
                else:
                    with self.assertRaises(GuardExceeded) as caught:
                        self.check(measure=measured)
                    self.assertEqual(caught.exception.reason, reason)
                    self.assertEqual(self.stopped, [CID])
        self.issue()
        self.beat()
        with self.assertRaises(GuardExceeded) as caught:
            self.check(snapshots=[self.table(child_rss=4_100_000_000)])
        self.assertEqual(caught.exception.reason, "observed_rss_limit")

    def test_verified_cid_teardown_leaves_unrelated_containers_alone(self):
        self.podman_calls.clear()
        rm = []
        responses = iter([CID + " 100\n",
                          subprocess.CalledProcessError(
                              1, ["podman", "inspect"], stderr="no such object"),
                          subprocess.CalledProcessError(
                              1, ["podman", "inspect"], stderr="no such object")])

        def command(argv, env, timeout=15):
            self.podman_calls.append(list(argv))
            value = next(responses)
            if isinstance(value, Exception):
                raise value
            return value

        def fake_run(argv, **kwargs):
            rm.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        with patch.object(teardown, "command", side_effect=command), \
             patch("fail_closed_guard.teardown.subprocess.run",
                   side_effect=fake_run):
            proof = teardown.stop_verified_cid(self.env, CID)
        self.assertEqual(rm, [["podman", "rm", "-f", CID]])
        self.assertTrue(proof["container_removed"])
        self.assertFalse(proof["kernel_enforcement"])
        self.assertNotIn("ps", [argv[1] for argv in self.podman_calls])

    def test_evidence_is_append_only_and_never_a_success_receipt(self):
        self.issue()
        with self.assertRaises(GuardExceeded):
            self.check()
        first = self.evidence()
        self.issue("beta", cid=CID_B)
        with self.assertRaises(GuardExceeded):
            self.check("beta")
        second = self.evidence()
        self.assertEqual(len(second), len(first) + 1)
        self.assertEqual(second[0], first[0])
        self.assertNotIn("success", second[-1]["result"])
        self.assertEqual(os.stat(watchdog.evidence_path(self.root)).st_mode
                         & 0o777, 0o600)
        journal = watchdog.evidence_path(self.root)
        lines = journal.read_text().splitlines()
        lines[-1] = "{not json}"
        journal.write_text("\n".join(lines) + "\n")
        with self.assertRaises(GuardExceeded) as caught:
            self.evidence()
        self.assertEqual(caught.exception.reason, "journal_unreadable")

    def test_wrong_store_namespace_never_touches_container(self):
        self.issue()
        self.conf.write_text("[storage]\ndriver = overlay\ngraphroot = /other\n")
        with self.assertRaises(GuardExceeded) as caught:
            self.check()
        self.assertEqual(caught.exception.reason, "store_namespace_mismatch")
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence()[-1]["action"], "none")

    def test_release_race_skips_teardown(self):
        self.issue()
        bound = watchdog.bound_from_lease(self.root, WORKER, self.env)
        released = {"state": "released", "cid": CID}
        with patch.object(watchdog, "bound_from_lease",
                          side_effect=[bound, released]):
            with self.assertRaises(GuardExceeded) as caught:
                self.check()
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence()[-1]["action"], "release_raced")


    def test_bind_does_not_reset_durable_start(self):
        lease.append(self.root, {"schema": lease.SCHEMA, "lease": "clocked",
                                 "state": "active", "mode": "pilot", "cid": None,
                                 "cidfile": None, "pid": None,
                                 "fingerprint": None, "at_utc": 123.0})
        lease.bind_cid(self.root, "clocked", CID, pid=100,
                       fingerprint=[50, 99])
        latest = lease.latest(lease.events(self.root))["clocked"]
        self.assertEqual(latest["at_utc"], 123.0)
        lease.bind(self.root, "clocked-build", 77, [1, 2, 3])
        self.assertEqual(lease.acquisition_start(self.root, "clocked-build"),
                         lease.latest(lease.events(self.root))["clocked-build"]["at_utc"])

    def test_readiness_requires_verified_store_and_own_identity(self):
        with self.assertRaises(GuardExceeded) as caught:
            heartbeat.advertise(self.root, storage_conf=self.conf,
                                graphroot="/wrong", wall=self.wall)
        self.assertEqual(caught.exception.reason, "store_namespace_mismatch")
        self.assertFalse(heartbeat.alive_path(self.root).exists())
        with patch.object(binding, "command",
                          side_effect=OSError("podman unavailable")):
            with self.assertRaises(GuardExceeded) as caught:
                heartbeat.advertise(self.root, storage_conf=self.conf,
                                    graphroot=GRAPHROOT, wall=self.wall)
        self.assertEqual(caught.exception.reason, "inspection_unavailable")
        self.assertFalse(heartbeat.alive_path(self.root).exists())

    def test_readiness_rejects_future_stale_and_pid_reused(self):
        table = {4242: rec(4242, 1, 1000, start=100)}
        heartbeat.ping(self.root, pid=4242, table=table, wall=self.wall)
        source = heartbeat.alive_path(self.root)
        event = json.loads(source.read_text())
        event["at_utc"] = self.wall() + 10
        source.write_text(json.dumps(event) + "\n")
        with self.assertRaises(GuardExceeded):
            heartbeat.read_alive(self.root, wall=self.wall)
        event["at_utc"] = self.wall() - 1000
        source.write_text(json.dumps(event) + "\n")
        with self.assertRaises(GuardExceeded):
            heartbeat.read_alive(self.root, wall=self.wall)
        event["at_utc"] = self.wall()
        source.write_text(json.dumps(event) + "\n")
        self.assertTrue(heartbeat.read_alive(self.root, wall=self.wall))
        with self.assertRaises(GuardExceeded):
            heartbeat.read_alive(
                self.root, wall=self.wall,
                snapshot=lambda: {4242: rec(4242, 1, 1000, start=999)})

    def test_inspection_failure_fails_closed_with_exact_teardown(self):
        self.issue()
        self.beat()

        def command(argv, env, timeout=15):
            if argv[1] == "info":
                return GRAPHROOT + "\n"
            raise OSError("podman inspect unavailable")

        with patch.object(binding, "command", side_effect=command):
            with self.assertRaises(GuardExceeded) as caught:
                self.check()
        self.assertEqual(caught.exception.reason, "inspection_unavailable")
        self.assertEqual(self.stopped, [CID])
        self.assertEqual(self.evidence()[-1]["reason"], "inspection_unavailable")

    def test_policy_ceilings_cannot_be_relaxed_by_caller(self):
        self.issue()
        self.beat()
        with self.assertRaises(GuardExceeded) as caught:
            self.check(snapshots=[self.table(child_rss=4_100_000_000)],
                       rss_limit=8_000_000_000)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.clock.advance(2500)
        with self.assertRaises(GuardExceeded) as caught:
            self.check(wall_seconds=9999, max_age=100000)
        self.assertEqual(caught.exception.reason, "wall_limit")

    def test_build_leases_are_explicitly_blocked(self):
        lease.acquire(self.root, "builder", "build")
        lease.bind(self.root, "builder", 77, [1, 2, 3])
        with self.assertRaises(GuardExceeded) as caught:
            self.check("builder")
        self.assertEqual(caught.exception.reason, "unsupported_lease")
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.evidence()[-1]["action"], "none")

    def test_watchdog_death_never_turns_into_success(self):
        self.issue()
        with patch.object(watchdog, "append_evidence",
                          side_effect=OSError("watchdog killed")):
            with self.assertRaises(OSError):
                self.check()
        self.assertFalse(watchdog.evidence_path(self.root).exists())
        self.assertNotIn("success", watchdog.SCHEMA)

    def test_blocked_admission_records_independent_evidence(self):
        with self.assertRaises(OrphanLease):
            lease.require_clear(self.root, self.env,
                                watchdog_path=heartbeat.alive_path(self.root))
        event = self.evidence()[-1]
        self.assertEqual(event["reason"], "watchdog_unavailable")
        self.assertEqual(event["result"], "fail_closed")
        self.assertEqual(event["action"], "none")


class S6ServiceTests(unittest.TestCase):
    def test_service_is_inert_and_scoped(self):
        script = Path(__file__).parent.parent / "scripts/px_watchdog_s6_service.sh"
        text = script.read_text()
        self.assertEqual(subprocess.run(["sh", "-n", str(script)]).returncode, 0)
        self.assertTrue(os.access(script, os.X_OK))
        self.assertIn("WATCHDOG_ARMED", text)
        self.assertIn("--stop", text)
        self.assertIn(".watchdog.lock", text)
        self.assertIn("watchdog_cli", text)
        self.assertNotIn("WATCHDOG_WORKER", text)
        self.assertNotIn("--supervise", text)
        self.assertNotIn("kill ", text)
        self.assertNotIn("cgroup", text)


if __name__ == "__main__":
    unittest.main()
