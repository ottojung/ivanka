"""Fail-closed tests for the prospective P1 whole-container RSS guard."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from p1_guard import (GuardError, bind_container, check_disk, locate, members,
                      recover_lease, release_stop, rss_bytes, watch)

CID = "a" * 64


def rec(pid, ppid, start, ns, rss, cmd="x"):
    return {"pid": pid, "ppid": ppid, "starttime": start, "pid_ns": ns,
            "cmdline_sha": cmd, "rss": rss}


def fake_binding():
    return {"cid": CID, "pid": 100, "starttime": 5, "pid_ns": 7,
            "fingerprint": (5, 7), "cmdline_sha": "c0"}


def fake_stop(calls, fail=False):
    def stop(cid):
        calls.append(cid)
        if fail:
            raise RuntimeError("podman rm failed")
        return {"cid": cid, "container_removed": True,
                "fresh_absence_check": True}
    return stop


class P1GuardTests(unittest.TestCase):
    def test_happy_whole_container_tree_excludes_launcher(self):
        table = {1: rec(1, 0, 1, 99, 40_000_000),          # podman launcher, other ns
                 100: rec(100, 1, 5, 7, 1_000_000),       # container init
                 101: rec(101, 100, 6, 7, 2_000_000),     # child in container
                 102: rec(102, 100, 7, 7, 0)}             # zero-RSS task
        calls = []
        ticks = iter([0, 1, 2])
        clocks = iter([0, 1, 2, 3])
        res = watch(fake_binding(), limit=4_000_000, wall_seconds=30,
                    running=lambda: next(ticks, None) is not None,
                    snap=lambda: table, measure=lambda: True,
                    stop=fake_stop(calls), clock=lambda: next(clocks),
                    sleep=lambda _: None)
        self.assertEqual(res["peak_rss_bytes"], 3_000_000)
        self.assertEqual(res["rss_sample_scope"], "whole_container_process_tree")
        self.assertFalse(res["kernel_enforcement"])
        self.assertEqual(calls, [CID])
        self.assertTrue(res["teardown"]["fresh_absence_check"])

    def test_unreadable_rss_is_null_and_fails_closed(self):
        table = {100: rec(100, 1, 5, 7, 1_000_000),
                 101: rec(101, 100, 6, 7, None)}
        calls = []
        with self.assertRaises(GuardError) as ctx:
            watch(fake_binding(), limit=4_000_000, wall_seconds=30,
                  running=lambda: True, snap=lambda: table,
                  measure=lambda: True, stop=fake_stop(calls),
                  clock=lambda: 0, sleep=lambda _: None)
        self.assertEqual(ctx.exception.reason, "measurement_unavailable")
        self.assertIsNone(ctx.exception.result["peak_rss_bytes"])
        self.assertEqual(calls, [CID])

    def test_missing_container_fails_before_sampling(self):
        with self.assertRaises(GuardError) as ctx:
            bind_container(CID, lambda cid: None, snap={})
        self.assertEqual(ctx.exception.reason, "identity_lost")

    def test_missing_bound_process_during_watch_tears_down(self):
        calls = []
        state = {"n": 0}
        def snap():
            state["n"] += 1
            return {100: rec(100, 1, 5, 7, 1_000_000)} if state["n"] == 1 else {}
        with self.assertRaises(GuardError) as ctx:
            watch(fake_binding(), limit=4_000_000, wall_seconds=30,
                  running=lambda: True, snap=snap, measure=lambda: True,
                  stop=fake_stop(calls), clock=lambda: 0, sleep=lambda _: None)
        self.assertEqual(ctx.exception.reason, "identity_lost")
        self.assertEqual(calls, [CID])

    def test_launcher_death_is_measurement_unavailable_with_teardown(self):
        calls = []
        table = {100: rec(100, 1, 5, 7, 1_000_000)}
        def measure():
            raise RuntimeError("launcher SIGKILL")
        with self.assertRaises(GuardError) as ctx:
            watch(fake_binding(), limit=4_000_000, wall_seconds=30,
                  running=lambda: True, snap=lambda: table, measure=measure,
                  stop=fake_stop(calls), clock=lambda: 0, sleep=lambda _: None)
        self.assertEqual(ctx.exception.reason, "measurement_unavailable")
        self.assertEqual(ctx.exception.result["peak_rss_bytes"], 1_000_000)
        self.assertEqual(calls, [CID])

    def test_disk_reserve_fail_closed(self):
        class Usage:
            def __init__(self, free):
                self.free = free
        self.assertEqual(check_disk("/tmp", 100, lambda p: Usage(101)), 101)
        with self.assertRaises(GuardError) as ctx:
            check_disk("/tmp", 100, lambda p: Usage(99))
        self.assertEqual(ctx.exception.reason, "reserve_shortfall")
        def broken(_):
            raise OSError("unreadable")
        with self.assertRaises(GuardError) as ctx:
            check_disk("/tmp", 100, broken)
        self.assertEqual(ctx.exception.reason, "measurement_unavailable")

    def test_pid_reuse_fails_closed(self):
        old = {100: rec(100, 1, 5, 7, 1_000_000)}
        new = {100: rec(100, 1, 999, 7, 1_000_000)}   # same PID, new task
        self.assertEqual(locate(fake_binding(), old), 100)
        with self.assertRaises(GuardError) as ctx:
            locate(fake_binding(), new)
        self.assertEqual(ctx.exception.reason, "identity_lost")

    def test_cmdline_exec_transition_keeps_stable_identity(self):
        b = bind_container(CID, lambda cid: {"id": CID, "pid": 100},
                           snap={100: rec(100, 1, 5, 7, 10, cmd="python")})
        changed = {100: rec(100, 1, 5, 7, 10, cmd="micall")}
        self.assertEqual(locate(b, changed), 100)
        self.assertEqual(members(changed, 100, b), {100})

    def test_rss_limit_tears_down_exact_cid(self):
        calls = []
        table = {100: rec(100, 1, 5, 7, 5_000_000)}
        with self.assertRaises(GuardError) as ctx:
            watch(fake_binding(), limit=4_000_000, wall_seconds=30,
                  running=lambda: True, snap=lambda: table, measure=lambda: True,
                  stop=fake_stop(calls), clock=lambda: 0, sleep=lambda _: None)
        self.assertEqual(ctx.exception.reason, "observed_rss_limit")
        self.assertEqual(calls, [CID])

    def test_stop_not_retired_without_teardown_proof(self):
        with tempfile.TemporaryDirectory() as d:
            stop = Path(d) / "STOP"
            stop.write_text("hold\n")
            lease = Path(d) / "lease.jsonl"
            with self.assertRaises(GuardError) as ctx:
                release_stop(stop, {"container_removed": True}, lease, "owner")
            self.assertEqual(ctx.exception.reason, "teardown_unverified")
            self.assertTrue(stop.is_file())
            proof = {"container_removed": True, "fresh_absence_check": True, "cid": CID}
            release_stop(stop, proof, lease, "owner")
            self.assertFalse(stop.is_file())

    def test_lease_reconciliation_fails_closed_after_controller_death(self):
        with tempfile.TemporaryDirectory() as d:
            lease = Path(d) / "lease.jsonl"
            from p1_guard import append_lease
            append_lease(lease, {"event": "acquired", "owner": "dead-controller", "cid": CID})
            self.assertEqual(len(recover_lease(lease)), 1)
            append_lease(lease, {"event": "released", "owner": "owner", "cid": CID})
            self.assertEqual(recover_lease(lease), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
