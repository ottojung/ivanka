"""Deterministic tests for the gated COPY-only overlay launch path."""
import hashlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fail_closed_guard import (build, copy_overlay, copy_overlay_helper,
                               heartbeat, lease, orphans, store, watchdog,
                               watchdog_contract)
from fail_closed_guard.errors import GuardExceeded, OrphanLease

BASE = "a" * 64
COMMIT = "b" * 24
GRAPHROOT = "/workspace/ivanka-exploratory-podman-20261121/store"
PID = 4243
CONTROLLER = 4242
BASELINE_ID = "111111111111"
NEW_ID = "222222222222"
PAYLOAD = b"binary-only ivanka"


def record(pid, starttime, pgid=None, rss=100, ns=99, cmd="podman"):
    return {"pid": pid, "ppid": 1 if pid == PID else PID, "pgid": pgid,
            "starttime": starttime, "pid_ns": ns, "cmdline_sha": cmd,
            "rss": rss, "cgroup": "0::/", "structural_unavailable": False}


class Handle:
    def __init__(self, pid, results=(0,), on_poll=None):
        self.pid = pid
        self.results = list(results)
        self.on_poll = on_poll

    def poll(self):
        if self.on_poll is not None:
            self.on_poll()
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


class Free:
    def __init__(self, free):
        self.free = free


class GateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ident = "gate-job"
        self.stable = (100, 7)
        self.table = {os.getpid(): record(os.getpid(), self.stable[0],
                                           pgid=os.getpid(),
                                           ns=self.stable[1], cmd="helper")}

    def commit(self, *, pid=None, stable=None, graphroot=GRAPHROOT):
        lease.append(self.root, {"schema": lease.SCHEMA, "lease": self.ident,
                                 "owner": self.ident, "state": "active",
                                 "mode": "copy_overlay", "pid": pid or os.getpid(),
                                 "pgid": pid or os.getpid(),
                                 "fingerprint": list(stable or self.stable),
                                 "graphroot": str(graphroot),
                                 "at_utc": 1000.0})

    def gate(self, payload=b"G", *, committed=True, deadline=1010.0,
             now=1000.0):
        journal = self.root / lease.JOURNAL_NAME
        if journal.exists():
            journal.unlink()
        if committed:
            self.commit()
        return copy_overlay_helper.gate(
            io.BytesIO(payload), self.root, self.ident, graphroot=GRAPHROOT,
            deadline=deadline, clock=lambda: now,
            select_fn=lambda readers, _, __, timeout: (readers if timeout > 0
                                                       else [], [], []),
            snapshot=lambda: self.table)

    def test_eof_deadline_and_missing_bind_never_exec(self):
        self.assertFalse(self.gate(payload=b""))
        self.assertFalse(self.gate(deadline=1000.0))
        self.assertFalse(self.gate(committed=False))

    def test_wrong_pid_identity_or_store_never_exec(self):
        self.assertFalse(self.gate(payload=b"X"))
        for changes in ({"pid": os.getpid() + 1},
                        {"stable": (999, 7)},
                        {"graphroot": "/foreign/store"}):
            with self.subTest(changes=changes):
                journal = self.root / lease.JOURNAL_NAME
                if journal.exists():
                    journal.unlink()
                self.commit(**changes)
                self.assertFalse(self.gate(committed=False))

    def test_exact_durable_bind_allows_exec(self):
        self.assertTrue(self.gate())


class CopyOverlayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.conf = self.root / "storage.conf"
        self.conf.write_text(
            '[storage]\ndriver = "overlay"\ngraphroot = "%s"\nrunroot = "%s/run"\n'
            % (GRAPHROOT, GRAPHROOT))
        self.context = self.root / "context"
        self.context.mkdir()
        (self.context / "ivanka").write_bytes(PAYLOAD)
        os.chmod(self.context / "ivanka", 0o755)
        (self.context / "Containerfile").write_text(
            copy_overlay.CONTAINERFILE.format(base=BASE))
        self.digest = hashlib.sha256(PAYLOAD).hexdigest()
        self.plan = {"schema": copy_overlay.SCHEMA, "base_image": BASE,
                     "source_commit": COMMIT, "context": str(self.context),
                     "storage_conf": str(self.conf), "graphroot": GRAPHROOT,
                     "artifact_sha256": self.digest, "artifact_mode": 0o755,
                     "source": "ivanka",
                     "destination": "/usr/local/bin/ivanka",
                     "tag": "ivanka-copy-" + "c" * 16}
        self.ident = "copy-" + copy_overlay.plan_digest(self.plan)[:16]
        self.env = {"CONTAINERS_STORAGE_CONF": str(self.conf),
                    "TMPDIR": "/host/tmp", "TMP": "/host/tmp"}
        self.commands = []
        self.removed = []
        self.stopped = []
        self.new_external = []
        self.permission = []
        patches = [
            patch.object(store.binding, "command", side_effect=self.command),
            patch.object(heartbeat.Emitter, "before_spawn",
                         lambda self: {"schema": heartbeat.SCHEMA}),
            patch.object(heartbeat.Emitter, "refresh",
                         lambda self: {"schema": heartbeat.SCHEMA}),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def command(self, argv, env, timeout=15):
        self.commands.append(list(argv))
        if argv[1] == "info":
            return GRAPHROOT + "\n"
        if argv[1] == "ps":
            if "--external" in argv:
                entries = [(BASELINE_ID, "prior-working-container", "Storage")]
                entries.extend(self.new_external)
                return "".join("%s|%s|%s\n" % item for item in entries)
            return ""
        if argv[1] == "rm":
            self.removed.append(argv[-1])
            self.new_external = [entry for entry in self.new_external
                                 if entry[0] != argv[-1]]
            return ""
        raise AssertionError("unexpected command %r" % (argv,))

    def table(self, starttime=200, pgid=PID, controller=True):
        table = {PID: record(PID, starttime, pgid=pgid)}
        table[4244] = record(4244, 201, pgid=pgid, rss=300)
        if controller:
            table[CONTROLLER] = record(CONTROLLER, 100, pgid=CONTROLLER,
                                       ns=7, cmd="watchdog")
        return table

    def own_external(self):
        self.new_external.append((NEW_ID, self.ident + "-working-container",
                                  "Storage"))

    def ping(self, table=None):
        heartbeat.ping(self.root, pid=CONTROLLER, table=table or self.table(),
                       storage_conf=self.conf, graphroot=GRAPHROOT,
                       env=self.env, wall=time.time)
        return heartbeat.alive_path(self.root)

    def write_permission(self, fd, payload):
        self.permission.append((fd, payload))
        return len(payload)

    def stop_group(self, pgid):
        self.stopped.append(pgid)
        return {"process_group": pgid, "stopped": True,
                "method": "verified_exact_group", "kernel_enforcement": False}

    def cleanup(self):
        return orphans.reclaim_owned(self.env, GRAPHROOT,
                                     self.baseline_snapshot(),
                                     expected_name=self.ident
                                     + "-working-container",
                                     command_fn=self.command)

    def baseline_snapshot(self):
        return orphans.capture_baseline(self.env, GRAPHROOT,
                                        command_fn=self.command)

    def reset_lease(self):
        for name in (lease.JOURNAL_NAME, watchdog.EVIDENCE_NAME):
            (self.root / name).unlink(missing_ok=True)

    def run_build(self, *, table=None, handle=None, usage=None, wall=None,
                  rss_limit=None, start_owned=True):
        table = table or self.table()

        def spawn(argv, env_value, pass_fds):
            if start_owned:
                self.own_external()
            if getattr(self, "on_spawn", None) is not None:
                self.on_spawn()
            self.gate_argv = argv
            self.spawn_env = env_value
            return handle or Handle(PID)

        return copy_overlay.run(
            self.root, self.plan, expected_base=BASE,
            expected_commit=COMMIT, graphroot=GRAPHROOT, env=self.env,
            reserve_bytes=1024, snapshot=lambda: table, command=self.command,
            usage=usage or (lambda path: Free(100 * 1024**3)),
            spawn=spawn, stop=self.stop_group,
            wall=wall or time.time, monotonic=lambda: 0.0,
            sleep=lambda _: None, rss_limit=rss_limit or watchdog.RSS_LIMIT,
            permission=self.write_permission)

    def evidence(self):
        return watchdog.read_evidence(self.root)

    def test_real_shared_lock_is_held(self):
        self.ping()
        self.own_external()
        from fail_closed_guard.copy_overlay import shared_lock
        with shared_lock(self.root):
            with self.assertRaises(OSError):
                with shared_lock(self.root):
                    pass
        # A fresh lock is available again after the context exits.
        with shared_lock(self.root):
            pass

    def test_plan_rejects_extra_nested_symlink_mode_and_digest_errors(self):
        validated = copy_overlay.validate_plan(
            self.plan, expected_base=BASE, expected_commit=COMMIT,
            expected_graphroot=GRAPHROOT, root=self.root)
        self.assertEqual(validated["destination"], "/usr/local/bin/ivanka")
        self.assertEqual(validated["argv"][1:3],
                         ["build", "--network=none"])
        extra = self.context / "extra"
        extra.write_bytes(b"x")
        with self.assertRaises(GuardExceeded):
            copy_overlay.validate_plan(
                self.plan, expected_base=BASE, expected_commit=COMMIT,
                expected_graphroot=GRAPHROOT, root=self.root)
        extra.unlink()
        os.chmod(self.context / "ivanka", 0o644)
        with self.assertRaises(GuardExceeded):
            copy_overlay.validate_plan(
                self.plan, expected_base=BASE, expected_commit=COMMIT,
                expected_graphroot=GRAPHROOT, root=self.root)
        os.chmod(self.context / "ivanka", 0o755)
        self.plan["artifact_sha256"] = "0" * 64
        with self.assertRaises(GuardExceeded):
            copy_overlay.validate_plan(
                self.plan, expected_base=BASE, expected_commit=COMMIT,
                expected_graphroot=GRAPHROOT, root=self.root)

    def test_pre_bind_crash_leaves_no_permission_and_no_build(self):
        self.ping()
        only_controller = {CONTROLLER: record(CONTROLLER, 100,
                                              pgid=CONTROLLER, ns=7,
                                              cmd="watchdog")}
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(table=only_controller, start_owned=False)
        self.assertEqual(caught.exception.reason, "binding_unavailable")
        self.assertEqual(self.permission, [])
        self.assertEqual(self.stopped, [])
        self.assertEqual(self.removed, [])
        self.assertEqual(lease.latest(lease.events(self.root))[
            self.ident]["state"], "active")
        self.assertEqual(self.evidence()[-1]["reason"], "binding_unavailable")

    def test_success_gates_after_bind_with_job_temp_and_real_receipt(self):
        self.ping()
        state = self.run_build()
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["exit_code"], 0)
        self.assertEqual(self.stopped, [PID])
        self.assertEqual(self.removed, [NEW_ID])
        self.assertEqual(state["teardown"]["orphan_cleanup"]["removed"][0]["id"],
                         NEW_ID)
        self.assertEqual(len(self.permission), 1)
        self.assertEqual(self.permission[0][1], b"G")
        self.assertEqual(Path(self.spawn_env["TMPDIR"]).parent, self.root)
        self.assertNotIn("/host/tmp", self.spawn_env.values())
        self.assertIn("--ident", self.gate_argv)
        receipt = next((self.root).glob("copy-*/result.json"))
        self.assertEqual(json.loads(receipt.read_text())["status"], "completed")
        self.assertEqual(lease.latest(lease.events(self.root))[
            self.ident]["state"], "released")

    def test_pid_reuse_refuses_signal_and_records_blocker(self):
        self.ping()
        self.own_external()
        bound = {"state": "bound_group", "pid": PID, "pgid": PID,
                 "fingerprint": [200, 99], "stable": True,
                 "graphroot": GRAPHROOT}
        reused = {9999: record(9999, 999, pgid=9999)}
        with patch("os.killpg", side_effect=AssertionError("bare/reused PGID")):
            with self.assertRaises(Exception):
                build.stop_group_by_id(
                    PID, snapshot=lambda: reused, sleep=lambda _: None,
                    clock=lambda: 0.0,
                    verify=lambda pgid, table: watchdog.group_still_owned(
                        bound, table),
                    absent=lambda pgid, table: watchdog.group_absent(
                        bound, table))
        self.assertEqual(self.stopped, [])
        self.assertFalse(watchdog.group_still_owned(bound, reused))
        self.assertTrue(watchdog.group_absent(bound, reused))

    def test_deadline_disk_and_rss_are_policy_ceilings(self):
        self.assertLess(watchdog.RSS_LIMIT, watchdog.RSS_UPPER_BOUND)
        self.ping()
        self.reset_lease()
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(usage=lambda path: Free(0))
        self.assertEqual(caught.exception.reason, "reserve_shortfall")
        self.assertEqual(self.stopped, [])
        self.reset_lease()
        heavy = self.table()
        heavy[PID]["rss"] = 4_100_000_000
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(table=heavy, rss_limit=8_000_000_000,
                           start_owned=False)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual(self.stopped[-1], PID)
        self.reset_lease()
        jumped = [False]
        handle = Handle(PID, results=(None, None),
                        on_poll=lambda: jumped.__setitem__(0, True))
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(
                handle=handle, start_owned=False,
                wall=lambda: time.time() + 5000 if jumped[0] else time.time())
        self.assertEqual(caught.exception.reason, "wall_limit")

    def test_no_broad_orphan_sweep_and_exact_ownership_proof(self):
        self.ping()

        def foreign_at_spawn():
            self.new_external.append((NEW_ID, "foreign-working-container",
                                      "Storage"))

        self.on_spawn = foreign_at_spawn
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(start_owned=False)
        self.assertEqual(caught.exception.reason, "orphan_unowned")
        self.assertEqual(self.removed, [])
        self.assertEqual(self.evidence()[-1]["result"], "fail_closed")

    def test_supported_mode_contract_accepts_only_bounded_path(self):
        watchdog_contract.require_supported_mode("copy_overlay")
        with self.assertRaises(GuardExceeded):
            watchdog_contract.require_supported_mode("build")
        with self.assertRaises(OrphanLease):
            lease.require_clear(self.root, self.env,
                                watchdog_path=self.root / "absent",
                                graphroot=GRAPHROOT, snapshot=lambda: {},
                                wall=time.time, command=self.command)


if __name__ == "__main__":
    unittest.main()
