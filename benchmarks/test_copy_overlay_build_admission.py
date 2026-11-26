"""Deterministic tests for the bounded COPY-only overlay build path."""
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fail_closed_guard import (build, copy_overlay, heartbeat, lease, orphans,
                               store, watchdog, watchdog_contract)
from fail_closed_guard.errors import GuardExceeded, OrphanLease

BASE = "a" * 64
COMMIT = "b" * 24
GRAPHROOT = "/workspace/ivanka-exploratory-podman-20261121/store"
PID = 4243
CONTROLLER = 4242
ORPHAN = "1234567890abcdef"


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
        (self.context / "tool").write_bytes(b"binary-only payload")
        self.digest = hashlib.sha256(b"binary-only payload").hexdigest()
        lines = ["FROM " + BASE,
                 "COPY tool /opt/ivanka/bin/tool"]
        (self.context / "Containerfile").write_text("\n".join(lines) + "\n")
        self.plan = {"schema": copy_overlay.SCHEMA, "base_image": BASE,
                     "source_commit": COMMIT, "context": str(self.context),
                     "copies": [{"source": "tool",
                                 "destination": "/opt/ivanka/bin/tool",
                                 "sha256": self.digest}],
                     "tag": "ivanka-copy-" + "c" * 16}
        self.env = {"CONTAINERS_STORAGE_CONF": str(self.conf)}
        self.commands = []
        self.removed = []
        self.stopped = []
        self.cleaned = []
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
                if self.removed:
                    return ""
                return "%s|tool-working-container|Storage\n" % ORPHAN
            return ""
        if argv[1] == "rm":
            self.removed.append(argv[-1])
            return ""
        raise AssertionError("unexpected command %r" % (argv,))

    def table(self, starttime=200, pgid=PID, controller=True):
        table = {PID: record(PID, starttime, pgid=pgid)}
        table[4244] = record(4244, 201, pgid=pgid, rss=300)
        if controller:
            table[CONTROLLER] = record(CONTROLLER, 100, pgid=CONTROLLER,
                                       ns=7, cmd="watchdog")
        return table

    def ping(self, table=None, wall=None):
        target = heartbeat.alive_path(self.root)
        table = table or self.table()
        heartbeat.ping(self.root, pid=CONTROLLER, table=table, target=target,
                       storage_conf=self.conf, graphroot=GRAPHROOT,
                       env=self.env, wall=wall or time.time)
        return target

    def validated(self):
        return copy_overlay.validate_plan(
            self.plan, expected_base=BASE, expected_commit=COMMIT,
            root=self.root)

    def stop_group(self, pgid):
        self.stopped.append(pgid)
        return {"process_group": pgid, "stopped": True,
                "method": "exact_pgid", "kernel_enforcement": False}

    def cleanup(self):
        proof = orphans.clean_pinned_storage(self.env, GRAPHROOT,
                                             command_fn=self.command)
        self.cleaned.append(proof)
        return proof

    def run_build(self, *, snapshot=None, handle=None, usage=None, wall=None,
            rss_limit=None, alive=None):
        table = snapshot or self.table()
        snap = lambda: table
        moment = wall or time.time
        return copy_overlay.run(
            self.root, self.plan, storage_conf=self.conf, graphroot=GRAPHROOT,
            expected_base=BASE, expected_commit=COMMIT, reserve_bytes=1024,
            env=self.env, lock=object(), alive=alive or self.ping(table, moment),
            snapshot=snap, command=self.command,
            usage=usage or (lambda path: Free(100 * 1024**3)),
            spawn=lambda argv, env: handle or Handle(PID),
            stop=self.stop_group, cleanup=self.cleanup,
            wall=moment, monotonic=lambda: 0.0,
            sleep=lambda _: None, rss_limit=rss_limit or watchdog.RSS_LIMIT)

    def evidence(self):
        return watchdog.read_evidence(self.root)

    def test_plan_validation_rejects_run_add_remote_and_digest_mismatch(self):
        validated = self.validated()
        self.assertIn("--network=none", validated["argv"])
        self.assertNotIn("RUN", (self.context / "Containerfile").read_text())
        containerfile = self.context / "Containerfile"
        for text in ("FROM " + BASE + "\nRUN echo x\n",
                     "FROM " + BASE + "\nADD tool /opt/ivanka/bin/tool\n",
                     "FROM https://example.invalid/base\n"):
            with self.subTest(text=text):
                containerfile.write_text(text)
                with self.assertRaises(GuardExceeded) as caught:
                    self.validated()
                self.assertEqual(caught.exception.reason, "invalid_plan")
        containerfile.write_text("FROM " + BASE + "\nCOPY tool /opt/ivanka/bin/tool\n")
        self.plan["copies"][0]["sha256"] = "0" * 64
        with self.assertRaises(GuardExceeded):
            self.validated()

    def test_no_bypass_when_watchdog_armed_is_zero(self):
        self.ping()
        with patch.dict(os.environ, {"WATCHDOG_ARMED": "0"}):
            with self.assertRaises(GuardExceeded) as caught:
                self.run_build(alive=self.root / "missing-alive.json")
        self.assertEqual(caught.exception.reason, "watchdog_unavailable")
        self.assertEqual(self.stopped, [])
        watchdog_contract.require_supported_mode("copy_overlay")

    def test_success_requires_fresh_group_and_orphan_proof(self):
        state = self.run_build()
        self.assertEqual(state["status"], "completed")
        self.assertEqual(self.stopped, [PID])
        self.assertEqual(self.removed, [ORPHAN])
        self.assertEqual(state["teardown"]["orphan_cleanup"]["removed"][0]["id"],
                         ORPHAN)
        self.assertTrue(state["teardown"]["orphan_cleanup"]["fresh_absence_check"])
        self.assertEqual(lease.latest(lease.events(self.root))[
            state["lease"]]["state"], "released")
        self.assertEqual(self.evidence(), [])

    def test_pre_spawn_crash_leaves_pending_lease_and_blocks_admission(self):
        lease.acquire(self.root, "crashed", "copy_overlay", owner="crashed")
        report = lease.reconcile(self.root, self.env,
                                 snapshot=lambda: self.table())
        self.assertEqual(report["blocked"][0]["reason"], "ambiguous_lease")
        with self.assertRaises(OrphanLease):
            lease.require_clear(self.root, self.env,
                                watchdog_path=self.ping(), graphroot=GRAPHROOT,
                                snapshot=lambda: self.table(), wall=time.time,
                                command=self.command)
        with self.assertRaises(GuardExceeded) as caught:
            watchdog.check_once(
                self.root, "crashed", storage_conf=self.conf,
                graphroot=GRAPHROOT, env=self.env, heartbeat_path=self.root / "none",
                monotonic=lambda: 0.0, wall_clock=lambda: 1000.0,
                snapshot=lambda: self.table(), measure=lambda: FREE_BYTES,
                wall_seconds=2400)
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.evidence()[-1]["action"], "none")
        self.assertEqual(self.stopped, [])

    def test_post_spawn_crash_stops_exact_group_and_records_orphan_evidence(self):
        lease.acquire(self.root, "crashed", "copy_overlay", owner="crashed")
        lease.bind_group(self.root, "crashed", PID, PID,
                         [200, 99, "podman"], owner="crashed",
                         plan_sha256="d" * 64, graphroot=GRAPHROOT)
        with patch("os.kill", side_effect=AssertionError("bare PID")), \
             patch("os.killpg", side_effect=AssertionError("bare PGID")):
            with self.assertRaises(GuardExceeded) as caught:
                watchdog.check_once(
                    self.root, "crashed", storage_conf=self.conf,
                    graphroot=GRAPHROOT, env=self.env,
                    heartbeat_path=self.root / "none",
                    monotonic=lambda: 0.0, wall_clock=lambda: 1000.0,
                    snapshot=lambda: self.table(), measure=lambda: FREE_BYTES,
                    wall_seconds=2400, stop=self.stop_group,
                    group_cleanup=self.cleanup)
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(self.stopped, [PID])
        event = self.evidence()[-1]
        self.assertEqual(event["action"], "teardown")
        self.assertEqual(event["process_group"], PID)
        self.assertEqual(event["teardown"]["orphan_cleanup"]["removed"][0]["id"],
                         ORPHAN)
        self.assertFalse(event["kernel_enforcement"])

    def test_pid_reuse_and_ambiguity_fail_closed(self):
        lease.acquire(self.root, "reused", "copy_overlay", owner="reused")
        lease.bind_group(self.root, "reused", PID, PID,
                         [200, 99, "podman"], owner="reused",
                         plan_sha256="d" * 64, graphroot=GRAPHROOT)
        reused = self.table(starttime=999)
        with self.assertRaises(GuardExceeded) as caught:
            watchdog.verify_group_bound(
                watchdog.bound_from_lease(self.root, "reused", self.env), reused)
        self.assertEqual(caught.exception.reason, "identity_lost")
        report = lease.reconcile(self.root, self.env, snapshot=lambda: reused)
        self.assertEqual(report["blocked"][0]["reason"], "identity_lost")
        ambiguous = self.table()
        ambiguous[9000] = record(9000, 200, pgid=9000)
        report = lease.reconcile(self.root, self.env, snapshot=lambda: ambiguous)
        self.assertEqual(report["blocked"][0]["reason"], "ambiguous_identity")

    def test_deadline_disk_and_rss_are_policy_ceilings(self):
        self.assertLess(watchdog.RSS_LIMIT, watchdog.RSS_UPPER_BOUND)
        for free, reason in ((0, "reserve_shortfall"),):
            metering = lambda path, amount=free: Free(amount)
            with self.subTest(reason=reason):
                with self.assertRaises(GuardExceeded) as caught:
                    self.run_build(usage=metering)
                self.assertEqual(caught.exception.reason, reason)
                # The reserve gate runs before spawn: no process exists to stop.
                self.assertEqual(self.stopped, [])
        heavy = self.table()
        heavy[PID]["rss"] = 4_100_000_000
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(snapshot=heavy, rss_limit=8_000_000_000)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual(self.stopped[-1], PID)
        jumped = [False]

        def wall():
            return time.time() + 5000 if jumped[0] else time.time()

        handle = Handle(PID, results=(None, None),
                        on_poll=lambda: jumped.__setitem__(0, True))
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(wall=wall, handle=handle)
        self.assertEqual(caught.exception.reason, "wall_limit")

    def test_orphan_cleanup_refuses_unknown_and_regular_containers(self):
        def external(argv, env, timeout=15):
            if "--external" in argv:
                return "deadbeefdead|mystery-working-container|Bogus\n"
            return ""
        with patch.object(orphans, "command", side_effect=external):
            with self.assertRaises(GuardExceeded) as caught:
                orphans.clean_pinned_storage(self.env, GRAPHROOT,
                                             command_fn=external)
        self.assertEqual(caught.exception.reason, "orphan_unrecognized")

        def regular(argv, env, timeout=15):
            if "--external" in argv:
                return ""
            return "f" * 64 + "\n"
        with self.assertRaises(GuardExceeded) as caught:
            orphans.clean_pinned_storage(self.env, GRAPHROOT,
                                         command_fn=regular)
        self.assertEqual(caught.exception.reason,
                         "orphan_regular_container_present")
        proof = orphans.clean_pinned_storage(self.env, GRAPHROOT,
                                             command_fn=self.command)
        self.assertEqual(proof["removed"][0]["id"], ORPHAN)
        self.assertTrue(proof["fresh_absence_check"])

    def test_group_stop_proves_absence_before_success(self):
        calls = []

        def fake_killpg(pgid, _signal):
            calls.append(pgid)
            raise ProcessLookupError()

        with patch("os.killpg", side_effect=fake_killpg), \
             patch("os.kill", side_effect=AssertionError("bare PID")):
            proof = build.stop_group_by_id(
                PID, snapshot=lambda: {}, sleep=lambda _: None,
                clock=lambda: 0.0)
        self.assertEqual(proof["process_group"], PID)
        self.assertTrue(proof["stopped"])
        self.assertEqual(calls[0], PID)
        with self.assertRaises(Exception):
            build.stop_group_by_id(
                0, snapshot=lambda: {}, sleep=lambda _: None,
                clock=lambda: 0.0)


FREE_BYTES = 100 * 1024**3


if __name__ == "__main__":
    unittest.main()
