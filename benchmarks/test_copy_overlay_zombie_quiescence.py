"""Strict quiescence proof for COPY teardown with real orphan zombies.

The bound helper can exit before the guard's stop callback while a descendant
remains visible as a kernel-verified zombie. This module proves that narrow
case using real Linux processes and /proc snapshots, and that every live,
unreadable, ambiguous or escaped member still fails closed.
"""
import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fail_closed_guard import build, copy_overlay, proc, watchdog

PR_SET_CHILD_SUBREAPER = 36


def _zombie(pid, pgid, *, starttime=201, ns=100, rss=None):
    return {"pid": pid, "ppid": os.getpid(), "pgid": pgid,
            "starttime": starttime, "pid_ns": ns, "cmdline_sha": "zombie",
            "rss": rss, "cgroup": "0::/", "state": "Z",
            "structural_unavailable": False}


def _bound(pid=4243, pgid=4243, finger=None):
    return {"state": "bound_group", "pid": pid, "pgid": pgid,
            "fingerprint": list(finger or [200, 99]), "stable": True}


class QuiescenceProofTests(unittest.TestCase):
    def test_live_group_is_not_quiescent(self):
        bound = _bound()
        table = {4243: {"pid": 4243, "ppid": 1, "pgid": 4243,
                        "starttime": 200, "pid_ns": 99, "cmdline_sha": "live",
                        "rss": 100, "cgroup": "0::/", "state": "S",
                        "structural_unavailable": False}}
        self.assertFalse(watchdog.group_quiesced(bound, table))

    def test_reused_leader_and_ambiguous_group_fail_closed(self):
        bound = _bound()
        reused = {4243: dict(_zombie(4243, 4243), starttime=999, pid_ns=98)}
        self.assertFalse(watchdog.group_quiesced(bound, reused))
        # Leader identity absent but a different process sits in the same PID
        # slot and same PGID: the group owner is ambiguous.
        ambiguous = {4243: dict(_zombie(4243, 4243), starttime=999,
                                pid_ns=98), 4244: _zombie(4244, 4243)}
        self.assertFalse(watchdog.group_quiesced(bound, ambiguous))

    def test_unreadable_unknown_and_positive_rss_zombies_fail_closed(self):
        bound = _bound()
        for zombie in (_zombie(4244, 4243, rss=4096),
                       dict(_zombie(4244, 4243), state="?", rss=None),
                       dict(_zombie(4244, 4243), state=None),
                       dict(_zombie(4244, 4243),
                            structural_unavailable=True)):
            with self.subTest(zombie=zombie):
                self.assertFalse(watchdog.group_quiesced(bound,
                                                         {4244: zombie}))

    def test_escaped_live_descendant_fails_closed(self):
        bound = _bound()
        table = {4244: _zombie(4244, 4243),
                 5000: {"pid": 5000, "ppid": 4243, "pgid": 5000,
                        "starttime": 500, "pid_ns": 99, "cmdline_sha": "live",
                        "rss": 100, "cgroup": "0::/", "state": "R",
                        "structural_unavailable": False}}
        self.assertFalse(watchdog.group_quiesced(bound, table))

    def test_zombie_only_group_is_quiescent_not_reaped(self):
        bound = _bound()
        table = {4244: _zombie(4244, 4243)}
        proof = watchdog.group_quiesced(bound, table)
        self.assertTrue(proof["quiescent"])
        self.assertEqual(proof["quiescent_zombies"], 1)
        self.assertFalse(build._quiescent_proof(
            4243, table, lambda _p, t: watchdog.group_quiesced(bound, t)
        )["reaped"])

    def test_confirmation_snapshot_race_fails_closed(self):
        bound = _bound()
        quiet = {4244: _zombie(4244, 4243)}
        live = {4244: dict(_zombie(4244, 4243), state="R", rss=100)}
        tables = iter([quiet, live])
        with patch("os.killpg", side_effect=AssertionError("no signal")):
            with self.assertRaises(Exception) as caught:
                build.stop_group_by_id(
                    4243, snapshot=lambda: next(tables, {}),
                    sleep=lambda _: None, clock=lambda: 0.0,
                    verify=lambda p, t: watchdog.group_still_owned(bound, t),
                    absent=lambda p, t: watchdog.group_absence_proven(bound, t),
                    quiesced=lambda p, t: watchdog.group_quiesced(bound, t))
        self.assertEqual(str(caught.exception), "identity_lost_before_signal")


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux /proc required")
class RealLinuxQuiescenceTests(unittest.TestCase):
    def setUp(self):
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
        if result != 0:
            self.skipTest("PR_SET_CHILD_SUBREAPER unavailable: %s"
                          % os.strerror(ctypes.get_errno()))
        self.addCleanup(libc.prctl, PR_SET_CHILD_SUBREAPER, 0, 0, 0, 0)
        self.child = None
        self.leader = None

    def tearDown(self):
        if self.leader is not None:
            if self.leader.poll() is None:
                self.leader.kill()
            self.leader.wait(timeout=5)
        if self.child is not None:
            try:
                os.kill(self.child, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(self.child, 0)
            except ChildProcessError:
                pass

    def test_real_orphan_zombie_quiescence_uses_exact_teardown_path(self):
        script = ("import os, sys\n"
                  "pid = os.fork()\n"
                  "if pid == 0: os._exit(0)\n"
                  "sys.stdout.write(str(pid) + '\\n'); sys.stdout.flush()\n"
                  "sys.stdin.buffer.read()\n"
                  "os._exit(0)\n")
        self.leader = subprocess.Popen(
            [sys.executable, "-c", script], start_new_session=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=tempfile.gettempdir())
        self.addCleanup(self.leader.stdout.close)
        self.addCleanup(self.leader.stderr.close)
        self.child = int(self.leader.stdout.readline().decode().strip())
        table = proc.snapshot()
        record = table[self.leader.pid]
        bound = {"state": "bound_group", "pid": self.leader.pid,
                 "pgid": record["pgid"],
                 "fingerprint": [record["starttime"], record["pid_ns"]],
                 "stable": True}
        self.assertEqual(record["pgid"], self.leader.pid)
        self.assertTrue(watchdog.group_still_owned(bound, table))

        # Reap the direct Popen handle; its child is reparented to this
        # subreaper and remains a zombie with the original PID/PGID/identity.
        self.leader.stdin.close()
        self.assertEqual(self.leader.wait(timeout=10), 0)
        deadline = time.monotonic() + 5
        while True:
            table = proc.snapshot()
            zombie = table.get(self.child)
            if zombie is not None and zombie.get("state") == "Z":
                break
            if time.monotonic() >= deadline:
                self.fail("real zombie descendant did not become visible")
            time.sleep(0.02)
        self.assertEqual(zombie["pgid"], bound["pgid"])
        self.assertIsNone(zombie["rss"])
        self.assertFalse(zombie["structural_unavailable"])
        self.assertNotIn(bound["pid"], table)
        self.assertFalse(watchdog.group_still_owned(bound, table))
        self.assertFalse(watchdog.group_absence_proven(bound, table))
        quiescence = watchdog.group_quiesced(bound, table)
        self.assertTrue(quiescence, msg=(
            "bound=%r relevant=%r" % (
                bound, [record for record in table.values()
                        if record.get("pgid") == bound["pgid"]
                        or record.get("pid") == bound["pid"]
                        or record.get("ppid") == bound["pid"]])))
        self.assertTrue(quiescence["quiescent"])

        with patch("os.killpg", side_effect=AssertionError("unverified PGID")):
            proof = copy_overlay._teardown(
                bound, pinned={}, graphroot="/nonexistent",
                snapshot=proc.snapshot, sleep=lambda _: None,
                monotonic=time.monotonic, command=lambda *a, **k: "",
                baseline=[], cleanup=lambda: {"removed": []})
        self.assertTrue(proof["quiesced"])
        self.assertFalse(proof["reaped"])
        self.assertEqual(proof["method"], "verified_quiescent_group")
        self.assertEqual(proof["quiescent_zombies"], 1)
        self.assertEqual(proof["orphan_cleanup"], {"removed": []})
        try:
            os.waitpid(self.child, 0)
        except ChildProcessError:
            # subprocess cleanup may already have reaped the reparented child;
            # either way no zombie is left behind by this regression.
            pass
        self.child = None
        after = proc.snapshot()
        self.assertNotIn(self.child, after)
        self.assertFalse(watchdog.group_quiesced(bound, after))


if __name__ == "__main__":
    unittest.main()
