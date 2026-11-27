"""Proven-zombie RSS regression: zero for a reaped group member only.

Reproduces the guarded COPY-only build failure at
``fail_closed_guard/watchdog.py:249 verify_group_bound -> tree.rss_bytes``
where the sole bound group member was a /proc zombie (state Z, VmRSS absent)
and the conservative rule turned its unreadable RSS into
``measurement_unavailable``. A zombie holds no resident pages, so a state
positively read as Z may contribute zero; every live, unreadable or ambiguous
observation still fails closed. No guard check is bypassed or substituted.
"""
import tempfile
import unittest
from pathlib import Path

from fail_closed_guard import proc, tree, watchdog
from fail_closed_guard.errors import GuardExceeded


def record(pid, ppid, rss, state=None, pgid=None, ns=7, start=100):
    """Minimal snapshot record; ``state=None`` is an unreadable stat field."""
    return {"pid": pid, "ppid": ppid, "pgid": pgid if pgid is not None else pid,
            "starttime": start, "pid_ns": ns, "cmdline_sha": "x",
            "rss": rss, "cgroup": "0::/", "state": state,
            "structural_unavailable": False}


def proc_entry(root, pid, state, ppid, *, pgid=None, vmrss_kb=None):
    """Write one /proc-like entry with a real stat field 3 and optional VmRSS."""
    entry = Path(root, str(pid))
    (entry / "ns").mkdir(parents=True)
    if pgid is None:
        pgid = pid
    # After the comm ")": field 3 state, 4 ppid, 5 pgrp, ..., 22 starttime.
    fields = [state, str(ppid), str(pgid)] + ["0"] * 16 + ["55"]
    (entry / "stat").write_text(f"{pid} (x) {' '.join(fields)}\n")
    (entry / "ns" / "pid").write_text("")
    (entry / "cmdline").write_bytes(b"x")
    (entry / "cgroup").write_text("0::/\n")
    status = "Name:\tx\n"
    if vmrss_kb is not None:
        status += f"VmRSS:\t{vmrss_kb} kB\n"
    (entry / "status").write_text(status)
    return entry


class ProcStateTests(unittest.TestCase):
    def test_snapshot_preserves_zombie_state_without_vmRSS(self):
        with tempfile.TemporaryDirectory() as folder:
            entry = proc_entry(folder, 123, "Z", 1)
            table = proc.snapshot(folder)
            record = table[123]
            namespace_id = (entry / "ns" / "pid").stat().st_ino
        self.assertEqual(record["state"], "Z")
        self.assertIsNone(record["rss"])
        self.assertEqual(record["ppid"], 1)
        self.assertEqual(record["pgid"], 123)
        self.assertEqual(record["starttime"], 55)
        self.assertEqual(record["pid_ns"], namespace_id)
        self.assertFalse(record["structural_unavailable"])

    def test_snapshot_preserves_live_state_too(self):
        with tempfile.TemporaryDirectory() as folder:
            proc_entry(folder, 124, "S", 1, vmrss_kb=7)
            record = proc.snapshot(folder)[124]
        self.assertEqual(record["state"], "S")
        self.assertEqual(record["rss"], 7 * 1024)

    def test_unparsable_stat_leaves_state_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            entry = Path(folder, "125")
            (entry / "ns").mkdir(parents=True)
            (entry / "stat").write_text("125 (x) Z\n")  # no ppid/pgid/starttime
            (entry / "ns" / "pid").write_text("")
            record = proc.snapshot(folder)[125]
        self.assertIsNone(record["state"])
        self.assertTrue(record["structural_unavailable"])


class TreeZombieTests(unittest.TestCase):
    def test_proven_zombie_contributes_zero_rss(self):
        table = {100: record(100, 0, None, state="Z"),
                 101: record(101, 100, 1_500_000_000, state="S")}
        self.assertEqual(tree.rss_bytes(table, {100, 101}), 1_500_000_000)
        # The reported case: the whole bound group was a single zombie.
        self.assertEqual(tree.rss_bytes(table, {100}), 0)

    def test_live_unreadable_member_still_fails_closed(self):
        for label, rec in (
                ("live", record(100, 0, None, state="S")),
                ("unknown state", record(100, 0, None)),
                ("ambiguous state", record(100, 0, None, state="X")),
                ("zombie-shaped but no state", dict(record(100, 0, None),
                                                    structural_unavailable=True))):
            with self.subTest(label=label):
                with self.assertRaises(GuardExceeded) as caught:
                    tree.rss_bytes({100: rec}, {100})
                self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_null_rss_from_real_proc_reader_fails_closed_when_live(self):
        with tempfile.TemporaryDirectory() as folder:
            proc_entry(folder, 126, "S", 1)  # no VmRSS
            table = proc.snapshot(folder)
            with self.assertRaises(GuardExceeded) as caught:
                tree.rss_bytes(table, {126})
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_positive_rss_is_never_discarded_as_zombie_zero(self):
        rec = record(100, 0, 4_000_000_000, state="Z")
        self.assertEqual(tree.rss_bytes({100: rec}, {100}), 4_000_000_000)


class VerifyGroupBoundTests(unittest.TestCase):
    """Exercise the exact guarded-build path that failed closed on a zombie."""

    def bound(self, table, leader):
        rec = table[leader]
        return {"state": "bound_group", "pid": leader, "pgid": rec["pgid"],
                "fingerprint": [rec["starttime"], rec["pid_ns"]],
                "stable": True, "graphroot": "0::/"}

    def test_zombie_leader_plus_live_child_verifies(self):
        with tempfile.TemporaryDirectory() as folder:
            proc_entry(folder, 200, "Z", 1)  # zombie init, no VmRSS
            proc_entry(folder, 201, "S", 200, vmrss_kb=2048)
            table = proc.snapshot(folder)
            proof = watchdog.verify_group_bound(self.bound(table, 200), table)
        self.assertEqual(proof["pid"], 200)
        self.assertEqual(proof["pgid"], 200)
        self.assertEqual(proof["members"], 2)
        self.assertEqual(proof["rss"], 2048 * 1024)

    def test_all_zombie_group_verifies_with_zero_rss(self):
        with tempfile.TemporaryDirectory() as folder:
            proc_entry(folder, 300, "Z", 1)
            table = proc.snapshot(folder)
            proof = watchdog.verify_group_bound(self.bound(table, 300), table)
        self.assertEqual(proof["members"], 1)
        self.assertEqual(proof["rss"], 0)

    def test_live_unreadable_group_member_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            proc_entry(folder, 400, "Z", 1)  # zombie init
            proc_entry(folder, 401, "S", 400)  # live child, no VmRSS
            table = proc.snapshot(folder)
            with self.assertRaises(GuardExceeded) as caught:
                watchdog.verify_group_bound(self.bound(table, 400), table)
        self.assertEqual(caught.exception.reason, "measurement_unavailable")


if __name__ == "__main__":
    unittest.main()
