"""Deterministic tests for the gated COPY-only overlay launch path."""
import hashlib
import io
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fail_closed_guard import (build, copy_overlay, copy_overlay_helper,
                               heartbeat, lease, store, watchdog,
                               watchdog_contract)
from fail_closed_guard.errors import GuardExceeded, OrphanLease

BASE = "a" * 64
COMMIT = "b" * 24
GRAPHROOT = "/workspace/ivanka-exploratory-podman-20261121/store"
PID = 4243
CONTROLLER = 4242
BASELINE_ID = "1" * 64
NEW_ID = "2" * 64
IMAGE_ID = "3" * 64
BASE_LAYER = "4" * 64
NEW_LAYER = "5" * 64
PAYLOAD = b"binary-only ivanka"
LABELS = {
    "org.ottojung.ivanka.source-commit": COMMIT,
    "org.ottojung.ivanka.artifact-sha256": hashlib.sha256(PAYLOAD).hexdigest(),
    "org.ottojung.micall.frozen-image-id": BASE,
    "org.ottojung.ivanka.overlay-mode": "copy-only",
}


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
        self.sealed = self.root / "sealed"
        self.sealed.mkdir(mode=0o700)
        (self.sealed / "Containerfile").write_bytes(
            copy_overlay.CONTAINERFILE.format(base=BASE).encode())
        (self.sealed / "ivanka").write_bytes(PAYLOAD)
        os.chmod(self.sealed / "Containerfile", 0o400)
        os.chmod(self.sealed / "ivanka", 0o755)
        os.chmod(self.sealed, 0o500)

    def commit(self, *, pid=None, stable=None, graphroot=GRAPHROOT):
        lease.append(self.root, {"schema": lease.SCHEMA, "lease": self.ident,
                                 "owner": self.ident, "state": "active",
                                 "mode": "copy_overlay",
                                 "pid": pid or os.getpid(),
                                 "pgid": pid or os.getpid(),
                                 "fingerprint": list(stable or self.stable),
                                 "graphroot": str(graphroot),
                                 "at_utc": 1000.0})

    def gate(self, payload=b"G", *, committed=True, deadline=1010.0,
             mono_deadline=1010.0, now=1000.0, mono_now=1000.0):
        journal = self.root / lease.JOURNAL_NAME
        if journal.exists():
            journal.unlink()
        if committed:
            self.commit()
        return copy_overlay_helper.gate(
            io.BytesIO(payload), self.root, self.ident, graphroot=GRAPHROOT,
            deadline=deadline, deadline_mono=mono_deadline,
            clock=lambda: now, monotonic=lambda: mono_now,
            select_fn=lambda readers, _, __, timeout: (readers if timeout > 0
                                                       else [], [], []),
            snapshot=lambda: self.table, sealed_context=self.sealed,
            base=BASE, artifact_sha256=hashlib.sha256(PAYLOAD).hexdigest(),
            artifact_mode=0o755)

    def test_eof_deadline_and_missing_bind_never_exec(self):
        self.assertFalse(self.gate(payload=b""))
        self.assertFalse(self.gate(deadline=1000.0))
        self.assertFalse(self.gate(mono_deadline=1000.0))
        self.assertFalse(self.gate(now=1010.0))
        self.assertFalse(self.gate(mono_now=1010.0))
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

    def test_mutation_before_exec_never_allows_exec(self):
        for mutate in (lambda: (self.sealed / "ivanka").write_bytes(b"bad"),
                       lambda: os.chmod(self.sealed / "Containerfile", 0o600),
                       lambda: (os.chmod(self.sealed, 0o700),
                                (self.sealed / "extra").write_bytes(b"x"),
                                os.chmod(self.sealed, 0o500))):
            with self.subTest():
                (self.sealed / "ivanka").write_bytes(PAYLOAD)
                os.chmod(self.sealed / "Containerfile", 0o400)
                for item in self.sealed.iterdir():
                    if item.name not in ("Containerfile", "ivanka"):
                        item.unlink()
                mutate()
                self.assertFalse(self.gate())


class CopyOverlayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.conf = self.root / "storage.conf"
        self.conf.write_text(
            '[storage]\ndriver = "overlay"\ngraphroot = "%s"\nrunroot = "%s/run"\n'
            % (GRAPHROOT, GRAPHROOT))
        self.conf_sha = hashlib.sha256(self.conf.read_bytes()).hexdigest()
        self.context = self.root / "context"
        self.context.mkdir()
        (self.context / "ivanka").write_bytes(PAYLOAD)
        os.chmod(self.context / "ivanka", 0o755)
        (self.context / "Containerfile").write_text(
            copy_overlay.CONTAINERFILE.format(base=BASE))
        self.plan = {"schema": copy_overlay.SCHEMA, "base_image": BASE,
                     "source_commit": COMMIT, "context": str(self.context),
                     "storage_conf": str(self.conf),
                     "storage_conf_sha256": self.conf_sha,
                     "graphroot": GRAPHROOT, "base_layers": [BASE_LAYER],
                     "artifact_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                     "artifact_mode": 0o755, "source": "ivanka",
                     "destination": "/usr/local/bin/ivanka",
                     "tag": "ivanka-copy-" + "c" * 16}
        self.ident = "copy-" + copy_overlay.plan_digest(self.plan)[:16]
        self.env = {"CONTAINERS_STORAGE_CONF": str(self.conf),
                    "TMPDIR": "/host/tmp", "TMP": "/host/tmp",
                    "UNRELATED_SECRET": "must-not-leak"}
        self.commands = []
        self.removed = []
        self.stopped = []
        self.new_external = []
        self.bad_image = False
        self.bad_layers = False
        self.image_labels = dict(LABELS)
        patches = [
            patch.object(copy_overlay, "PX_ROOT", str(self.root)),
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
                entries = [(BASELINE_ID, BASE[:12] + "-working-container",
                            "Storage")]
                entries.extend(self.new_external)
                return "".join("%s|%s|%s\n" % item for item in entries)
            return ""
        if argv[1] == "inspect":
            image = "f" * 64 if self.bad_image else BASE
            layers = ([BASE_LAYER] if self.bad_layers
                      else [BASE_LAYER, NEW_LAYER])
            return "%s|%s|%s\n" % (
                image, BASE[:12] + "-working-container", json.dumps(layers))
        if argv[1] == "image":
            layers = ([BASE_LAYER] if self.bad_layers
                      else [BASE_LAYER, NEW_LAYER])
            return "%s|%s|%s\n" % (IMAGE_ID, json.dumps(self.image_labels),
                                    json.dumps(layers))
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
        self.new_external.append((NEW_ID, BASE[:12] + "-working-container",
                                  "Storage"))

    def write_iid(self, argv):
        index = argv.index("--iidfile")
        Path(argv[index + 1]).write_text(IMAGE_ID + "\n")

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

    def reset_lease(self):
        for name in (lease.JOURNAL_NAME, watchdog.EVIDENCE_NAME):
            (self.root / name).unlink(missing_ok=True)

    def run_build(self, *, table=None, handle=None, usage=None, wall=None,
                  rss_limit=None, start_owned=True, spawn_hook=None):
        table = table or self.table()
        self.permission = []

        def spawn(argv, env_value, pass_fds):
            if start_owned:
                self.own_external()
            self.write_iid(argv)
            if spawn_hook is not None:
                spawn_hook()
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
        from fail_closed_guard.copy_overlay import shared_lock
        with shared_lock(self.root):
            with self.assertRaises(OSError):
                with shared_lock(self.root):
                    pass
        with shared_lock(self.root):
            pass

    def test_plan_rejects_weak_pins_and_extra_content(self):
        validated = copy_overlay.validate_plan(
            self.plan, expected_base=BASE, expected_commit=COMMIT,
            expected_graphroot=GRAPHROOT, root=self.root)
        self.assertEqual(validated["base_layers"], [BASE_LAYER])
        seal_dir = self.root / "seal-test"
        seal_dir.mkdir()
        sealed_copy = dict(validated)
        copy_overlay.seal_context(seal_dir, sealed_copy)
        self.assertIn("--iidfile", sealed_copy["argv"])
        (self.context / "extra").write_bytes(b"x")
        with self.assertRaises(GuardExceeded):
            copy_overlay.validate_plan(
                self.plan, expected_base=BASE, expected_commit=COMMIT,
                expected_graphroot=GRAPHROOT, root=self.root)
        (self.context / "extra").unlink()
        self.plan["storage_conf_sha256"] = "0" * 64
        with self.assertRaises(GuardExceeded):
            copy_overlay.validate_plan(
                self.plan, expected_base=BASE, expected_commit=COMMIT,
                expected_graphroot=GRAPHROOT, root=self.root)
        self.plan["storage_conf_sha256"] = self.conf_sha
        self.plan["base_layers"] = ["not-a-layer"]
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
        self.assertEqual(lease.latest(lease.events(self.root))[
            self.ident]["state"], "active")
        self.assertEqual(self.evidence()[-1]["reason"], "binding_unavailable")

    def test_success_has_labels_layers_and_clean_environment(self):
        self.ping()
        state = self.run_build()
        self.assertEqual(state["status"], "completed")
        self.assertEqual(self.stopped, [PID])
        self.assertEqual(self.removed, [NEW_ID])
        self.assertEqual(state["image_receipt"]["labels"], LABELS)
        self.assertTrue(state["image_receipt"]["one_layer_overlay"])
        proof = state["teardown"]["orphan_cleanup"]["removed"][0]["inspect"]
        self.assertEqual(proof["image"], BASE)
        self.assertEqual(proof["layers"], [BASE_LAYER, NEW_LAYER])
        self.assertEqual(len(self.permission), 1)
        self.assertEqual(self.permission[0][1], b"G")
        self.assertNotIn("UNRELATED_SECRET", self.spawn_env)
        self.assertEqual(Path(self.spawn_env["TMPDIR"]).parent, self.root)
        receipt = next(self.root.glob("copy-*/result.json"))
        self.assertEqual(json.loads(receipt.read_text())["status"], "completed")

    def test_default_run_path_without_live_build(self):
        self.ping()
        seen = {}
        real_write = os.write

        def fake_spawn(root, argv, env_value, pass_fds, log):
            self.own_external()
            self.write_iid(argv)
            seen["argv"] = argv
            return Handle(PID)

        def safe_write(fd, payload):
            if payload == b"G":
                seen["permission"] = payload
                return len(payload)
            return real_write(fd, payload)

        tables = iter([self.table(), self.table(), self.table(),
                       self.table(), {}, {}, {}])
        signals = []

        def record_signal(pgid, _signal):
            signals.append(pgid)

        with patch.object(copy_overlay, "default_spawn", side_effect=fake_spawn), \
             patch.object(copy_overlay.os, "write", side_effect=safe_write), \
             patch("os.killpg", side_effect=record_signal):
            state = copy_overlay.run(
                self.root, self.plan, expected_base=BASE,
                expected_commit=COMMIT, graphroot=GRAPHROOT, env=self.env,
                reserve_bytes=1024, snapshot=lambda: next(tables, {}),
                command=self.command, usage=lambda path: Free(100 * 1024**3),
                wall=time.time, monotonic=lambda: 0.0, sleep=lambda _: None)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(seen["permission"], b"G")
        sealed = Path(seen["argv"][seen["argv"].index("--context") + 1])
        self.assertEqual(stat.S_IMODE(sealed.stat().st_mode), 0o500)
        self.assertEqual(self.removed, [NEW_ID])
        self.assertEqual(signals, [PID])

    def test_full_ids_and_base_derived_owner_are_required(self):
        self.ping()
        original = self.command

        def short_external(argv, env, timeout=15):
            if "--external" in argv:
                return "deadbeef|short-working-container|Storage\n"
            return original(argv, env, timeout)

        self.command = short_external
        try:
            with self.assertRaises(GuardExceeded) as caught:
                self.run_build(start_owned=False)
        finally:
            self.command = original
        self.assertEqual(caught.exception.reason, "orphan_unrecognized")
        self.reset_lease()
        self.bad_image = True
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(start_owned=True)
        self.assertEqual(caught.exception.reason, "orphan_unowned")
        self.assertEqual(self.removed, [])
        self.bad_image = False
        self.reset_lease()
        def foreign_at_spawn():
            self.new_external.append((NEW_ID, self.ident
                                      + "-working-container", "Storage"))

        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(start_owned=False, spawn_hook=foreign_at_spawn)
        self.assertEqual(caught.exception.reason, "orphan_baseline_changed")
        self.new_external.clear()

    def test_pid_reuse_refuses_signal(self):
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
        self.assertFalse(watchdog.group_still_owned(bound, reused))

    def test_deadline_disk_rss_and_image_receipt_fail_closed(self):
        self.assertLess(watchdog.RSS_LIMIT, watchdog.RSS_UPPER_BOUND)
        self.ping()
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(usage=lambda path: Free(0), start_owned=False)
        self.assertEqual(caught.exception.reason, "reserve_shortfall")
        self.reset_lease()
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(usage=lambda path: Free(
                copy_overlay.MIN_FREE_BYTES + 1024 - 1), start_owned=False)
        self.assertEqual(caught.exception.reason, "reserve_shortfall")
        self.reset_lease()
        heavy = self.table()
        heavy[PID]["rss"] = 4_100_000_000
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(table=heavy, rss_limit=8_000_000_000,
                           start_owned=False)
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        self.assertEqual(self.stopped[-1], PID)
        self.reset_lease()
        self.image_labels = dict(LABELS, **{
            "org.ottojung.ivanka.source-commit": "0" * 24})
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(start_owned=False)
        self.assertEqual(caught.exception.reason, "image_receipt_invalid")
        self.image_labels = dict(LABELS)
        self.reset_lease()
        self.bad_layers = True
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(start_owned=False)
        self.assertEqual(caught.exception.reason, "image_receipt_invalid")
        self.bad_layers = False

    def test_stop_owner_and_nonzero_exit(self):
        self.ping()
        (self.root / "STOP").write_text("other-owner\n")
        with self.assertRaises(GuardExceeded) as caught:
            self.run_build(start_owned=False)
        self.assertEqual(caught.exception.reason, "stop_owner_unauthorized")
        (self.root / "STOP").write_text("hold\n")
        state = self.run_build(handle=Handle(PID, results=(7,)))
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["exit_code"], 7)
        self.assertEqual(state["reason"], "build_exit_nonzero")
        self.assertIn("image_receipt", state)

    def test_watchdog_default_group_teardown_is_verified_and_exact(self):
        self.ping()
        self.own_external()
        lease.acquire(self.root, "orphaned", "copy_overlay", owner="orphaned")
        lease.bind_group(
            self.root, "orphaned", PID, PID, [200, 99], owner="orphaned",
            graphroot=GRAPHROOT, helper=True, baseline_ids=[BASELINE_ID],
            base_image=BASE, base_layers=[BASE_LAYER])
        tables = iter([self.table(), {}, {}, {}])
        signals = []

        def killpg(pgid, _signal):
            signals.append(pgid)

        with patch("os.killpg", side_effect=killpg):
            with self.assertRaises(GuardExceeded) as caught:
                watchdog.check_once(
                    self.root, "orphaned", storage_conf=self.conf,
                    graphroot=GRAPHROOT, env=self.env,
                    heartbeat_path=self.root / "none",
                    monotonic=lambda: 0.0, wall_clock=time.time,
                    snapshot=lambda: next(tables, {}),
                    measure=lambda: 100 * 1024**3, wall_seconds=2400)
        self.assertEqual(caught.exception.reason, "heartbeat_missing")
        self.assertEqual(signals, [PID])
        event = self.evidence()[-1]
        self.assertEqual(event["action"], "teardown")
        self.assertEqual(event["process_group"], PID)
        self.assertEqual(event["teardown"]["orphan_cleanup"]["removed"][0]["id"],
                         NEW_ID)
        self.assertEqual(self.removed, [NEW_ID])

    def test_supported_mode_contract_still_refuses_generic_build(self):
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
