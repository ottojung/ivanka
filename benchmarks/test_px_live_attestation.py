"""Hermetic adversarial proofs for fail-closed pre/post cutover attestation.

No live services, s6 directories, /proc entries, sockets, leases or locks are
touched. Every path is a temporary fixture and git/digest helpers are patched
to deterministic in-memory values.
"""
import json
import tempfile
import unittest
from pathlib import Path

from assembler_bench import px_live_attestation as live
from benchmarks.fail_closed_guard import heartbeat, lease

SCHEMA = lease.SCHEMA
WATCHDOG = 139
SUPERVISOR = 777
START, NS = 11, 22


def _status(pid):
    blob = bytearray(35)
    blob[24:32] = int(pid).to_bytes(8, "big")
    blob[32:35] = b"\x00\x00\x04"
    return bytes(blob)


def _line(var, root, head):
    return 'test "$(git -C "$%s" rev-parse HEAD)" = %s || exit 1' % (var, head)


class AttestationHarness(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        self.registry = self.project / "registry.json"
        self.s6 = self.base / "s6"
        self.proc = self.base / "proc"
        self.head = live.OLD_HEAD
        self.heads = {}
        self.locked = False
        self.now = 1000.0
        self.mods = self.base / "mods"
        self._fixture_roots = {}
        self._missing_roots = set()
        orig_is_dir = Path.is_dir

        def _is_dir(path_obj):
            s = str(path_obj)
            if s in self._missing_roots:
                return False
            if s in self._fixture_roots:
                return self._fixture_roots[s].is_dir()
            return orig_is_dir(path_obj)

        self._orig_is_dir = orig_is_dir
        Path.is_dir = _is_dir
        self.addCleanup(self._restore_is_dir)

    def _restore_is_dir(self):
        Path.is_dir = self._orig_is_dir

    def code_root(self, root):
        root = str(root)
        if root not in self._fixture_roots:
            path = self.base / Path(root).name
            (path / ".git").mkdir(parents=True, exist_ok=True)
            self._fixture_roots[root] = path
        return self._fixture_roots[root]

    def modules(self, root, table):
        self.code_root(root)
        for name, digest in table.items():
            path = self.mods / Path(root).name / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(digest)

    def reader_opts(self):
        return {
            "module_reader": lambda base, name: (
                (self.mods / Path(base).name / name).read_text()
                if (self.mods / Path(base).name / name).is_file() else None),
            "head_reader": lambda base: self.heads.get(str(base), self.head),
            "git_present": lambda _base: True,
        }

    def s6_status(self, service, pid):
        directory = self.s6 / service / "supervise"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "status").write_bytes(_status(pid))

    def proc_entry(self, pid, cmdline, env):
        entry = self.proc / str(pid)
        entry.mkdir(parents=True, exist_ok=True)
        (entry / "cmdline").write_bytes(cmdline.encode().replace(b" ", b"\0") + b"\0")
        (entry / "environ").write_bytes(b"".join(
            ("%s=%s\0" % (key, value)).encode() for key, value in env.items()))
        if not (entry / "cwd").is_symlink():
            (entry / "cwd").symlink_to(self.project)

    def scripts(self, phase, root=None, head=None):
        expected = live.PHASES[phase]
        wd_exp = expected["watchdog"]
        ctl_exp = expected["control"]
        wd_root = root or wd_exp["root"]
        wd_head = head or wd_exp["head"]
        wd = "\n".join([
            "export WATCHDOG_CODE=" + wd_root,
            _line("WATCHDOG_CODE", wd_root, wd_head),
            'git -C "$WATCHDOG_CODE" diff --quiet HEAD || exit 1',
            "export WATCHDOG_ROOT=" + str(self.project),
            "export WATCHDOG_STORAGE_CONF=" + str(self.project / "storage.conf"),
            "export WATCHDOG_GRAPHROOT=" + str(live.GRAPHROOT),
            "export WATCHDOG_STOP=" + str(self.project / "STOP"),
            "export WATCHDOG_ARMED=1",
            "# -m fail_closed_guard.watchdog_cli",
            'exec env PYTHONPATH="$CODE:$CODE/benchmarks" python3 -m fail_closed_guard.watchdog_cli',
        ]) + "\n"
        sup = "\n".join([
            "export PX_CODE=" + ctl_exp["root"],
            _line("PX_CODE", ctl_exp["root"], ctl_exp["head"]),
            'git -C "$PX_CODE" diff --quiet HEAD || exit 1',
            "export PX_ROOT=" + str(self.project),
            "export PX_REGISTRY=" + str(self.registry),
            "export WATCHDOG_ARMED=1",
            'exec /bin/sh "$PX_CODE/scripts/px_cohort_s6_service.sh"',
        ]) + "\n"
        paths = {
            "persistent_watchdog": self.base / "persist-watchdog",
            "runtime_watchdog": self.base / "runtime-watchdog",
            "persistent_supervisor": self.base / "persist-supervisor",
            "runtime_supervisor": self.base / "runtime-supervisor",
        }
        for path in paths.values():
            path.write_text(wd if "watchdog" in path.name else sup)
        return paths

    def build(self, phase, *, supervisor="absent", active=None, stop=False,
              lock=None, alive_fingerprint=None, events=None):
        expected = live.PHASES[phase]
        wd_exp = expected["watchdog"]
        ctl_exp = expected["control"]
        self.code_root(wd_exp["root"])
        self.modules(wd_exp["root"], wd_exp["modules"])
        self.code_root(ctl_exp["root"])
        self.modules(ctl_exp["root"], ctl_exp["modules"])
        self.head = wd_exp["head"]
        self.heads = {wd_exp["root"]: wd_exp["head"],
                      ctl_exp["root"]: ctl_exp["head"]}
        paths = self.scripts(phase)
        self.s6_status("ivanka-watchdog", WATCHDOG)
        self.s6_status("px-cohort-supervisor", SUPERVISOR if supervisor == "running" else 0)
        common_env = {
            "PYTHONPATH": wd_exp["root"] + ":" + wd_exp["root"] + "/benchmarks",
        }
        wd_env = dict(common_env, WATCHDOG_CODE=wd_exp["root"],
                      WATCHDOG_ROOT=str(self.project),
                      WATCHDOG_GRAPHROOT=str(live.GRAPHROOT))
        sup_env = {"PYTHONPATH": ctl_exp["root"] + ":" + ctl_exp["root"] + "/benchmarks",
                   "PX_CODE": ctl_exp["root"], "PX_ROOT": str(self.project),
                   "PX_REGISTRY": str(self.registry)}
        self.proc_entry(WATCHDOG,
                        "python3 -m fail_closed_guard.watchdog_cli --root %s --graphroot %s"
                        % (self.project, live.GRAPHROOT), wd_env)
        if supervisor == "running":
            self.proc_entry(SUPERVISOR,
                            "python3 -m assembler_bench.px_execution --registry %s "
                            "--root %s --supervise --armed"
                            % (self.registry, self.project), sup_env)
        finger = alive_fingerprint or [START, NS]
        (self.project / ".watchdog-alive.json").write_text(json.dumps({
            "schema": heartbeat.ALIVE_SCHEMA, "at_utc": 1000.0,
            "graphroot": str(live.GRAPHROOT), "pid": WATCHDOG,
            "fingerprint": finger,
        }))
        journal = self.project / lease.JOURNAL_NAME
        rows = list(events or [])
        journal.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        (self.project / ".global-worker.lock").write_text("")
        if stop:
            (self.project / "STOP").write_text("operator stop\n")
        table = {
            WATCHDOG: {"pid": WATCHDOG, "starttime": START, "pid_ns": NS,
                       "cmdline_sha": "a", "rss": 1},
        }
        if supervisor == "running":
            table[SUPERVISOR] = {"pid": SUPERVISOR, "starttime": 33, "pid_ns": 44,
                                 "cmdline_sha": "b", "rss": 1}
        return dict(paths, project_root=self.project, s6_root=self.s6,
                    proc_root=self.proc, global_lock=self.project / ".global-worker.lock",
                    worker_journal=journal, registry=self.registry,
                    snapshot=lambda: table,
                    lock_probe=lambda _path: self.locked, now=lambda: self.now,
                    **self.reader_opts())

    def attest(self, phase, **kwargs):
        opts = self.build(phase, **kwargs)
        return live.attest(phase=phase, **opts)

    def event(self, lease_id, state, owner="owner-a"):
        return {"schema": SCHEMA, "lease": lease_id, "owner": owner,
                "state": state, "cid": "c1", "at_utc": self.now}


class PreCutoverTests(AttestationHarness):
    def test_ready_at_idle_boundary(self):
        result = self.attest("pre_cutover")
        self.assertTrue(result["ready"], result["blockers"])
        self.assertFalse(result["blockers"])
        self.assertEqual(result["checks"]["leases"]["active"], [])

    def test_foreign_head_in_scripts_is_blocker(self):
        self.attest("pre_cutover", events=[])
        paths = self.build("pre_cutover")
        for key in ("persistent_watchdog", "runtime_watchdog",
                    "persistent_supervisor", "runtime_supervisor"):
            path = paths[key]
            path.write_text(path.read_text().replace(live.OLD_HEAD, "0" * 40))
        from assembler_bench.px_live_attestation import attest
        blocked = attest(phase="pre_cutover", project_root=self.project,
                         s6_root=self.s6, proc_root=self.proc,
                         persistent_watchdog=paths["persistent_watchdog"],
                         runtime_watchdog=paths["runtime_watchdog"],
                         persistent_supervisor=paths["persistent_supervisor"],
                         runtime_supervisor=paths["runtime_supervisor"],
                         snapshot=lambda: {WATCHDOG: {"starttime": START, "pid_ns": NS}},
                         lock_probe=lambda _p: False, now=lambda: self.now,
                         **self.reader_opts())
        self.assertFalse(blocked["ready"])
        self.assertTrue(any("script_pin" in b or "foreign_script" in b
                            for b in blocked["blockers"]), blocked["blockers"])

    def test_runtime_persist_mismatch_is_blocker(self):
        self.attest("pre_cutover")
        opts = self.build("pre_cutover")
        opts["runtime_watchdog"].write_text(opts["runtime_watchdog"].read_text() + "#x\n")
        blocked = live.attest(phase="pre_cutover", **opts)
        self.assertIn("runtime_persist_mismatch:watchdog", blocked["blockers"])

    def test_wrong_code_root_is_blocker(self):
        opts = self.build("pre_cutover")
        entry = self.proc / str(WATCHDOG) / "environ"
        entry.write_bytes(("WATCHDOG_CODE=%s\0PYTHONPATH=%s:%s/benchmarks\0"
                           % (live.NEW_ROOT, live.OLD_ROOT, live.OLD_ROOT)).encode())
        blocked = live.attest(phase="pre_cutover", **opts)
        self.assertIn("wrong_code_root:watchdog", blocked["blockers"])

    def test_missing_code_root_is_blocker(self):
        opts = self.build("pre_cutover")
        self._missing_roots.add(str(live.OLD_ROOT))
        blocked = live.attest(phase="pre_cutover", **opts)
        self.assertIn("code_root_missing:watchdog", blocked["blockers"])
        self.assertFalse(blocked["ready"])

    def test_module_byte_drift_is_blocker(self):
        opts = self.build("pre_cutover")
        (self.mods / Path(live.OLD_ROOT).name /
         "benchmarks/fail_closed_guard/watchdog.py").write_text("0" * 64)
        blocked = live.attest(phase="pre_cutover", **opts)
        self.assertIn("module_bytes_mismatch:watchdog", blocked["blockers"])

    def test_alive_identity_mismatch_is_blocker(self):
        blocked = self.attest("pre_cutover", alive_fingerprint=[99, 99])
        self.assertFalse(blocked["ready"])
        self.assertTrue(any("watchdog" in b for b in blocked["blockers"]))

    def test_stale_alive_is_blocker(self):
        self.now = 5000.0
        blocked = self.attest("pre_cutover")
        self.assertIn("watchdog_readiness_failed", blocked["blockers"])

    def test_foreign_release_does_not_hide_active_lease(self):
        events = [self.event("L", "active"), self.event("L", "released", owner="foreign")]
        blocked = self.attest("pre_cutover", events=events)
        self.assertIn("active_lease", blocked["blockers"])

    def test_foreign_reconciled_does_not_hide_active_lease(self):
        events = [self.event("L", "active"), self.event("L", "reconciled", owner="foreign")]
        blocked = self.attest("pre_cutover", events=events)
        self.assertIn("active_lease", blocked["blockers"])

    def test_own_release_clears_lease(self):
        ok = self.attest("pre_cutover", events=[
            self.event("L", "active"), self.event("L", "released")])
        self.assertTrue(ok["ready"], ok["blockers"])

    def test_stop_sentinel_is_blocker(self):
        blocked = self.attest("pre_cutover", stop=True)
        self.assertIn("foreign_stop", blocked["blockers"])

    def test_locked_global_lock_is_blocker(self):
        self.locked = True
        blocked = self.attest("pre_cutover")
        self.assertIn("global_lock_busy", blocked["blockers"])

    def test_running_supervisor_violates_idle_boundary(self):
        blocked = self.attest("pre_cutover", supervisor="running")
        self.assertTrue(any("supervisor_not_idle" in b for b in blocked["blockers"]))

    def test_unreadable_journal_is_blocker(self):
        opts = self.build("pre_cutover")
        opts["worker_journal"].write_text("not json\n")
        blocked = live.attest(phase="pre_cutover", **opts)
        self.assertIn("lease_journal_unreadable", blocked["blockers"])

    def test_s6_watchdog_down_is_blocker(self):
        opts = self.build("pre_cutover")
        self.s6_status("ivanka-watchdog", 0)
        blocked = live.attest(phase="pre_cutover", **opts)
        self.assertIn("s6_service_down:watchdog", blocked["blockers"])

    def test_foreign_graphroot_is_blocker(self):
        opts = self.build("pre_cutover")
        path = opts["persistent_watchdog"]
        path.write_text(path.read_text().replace(
            str(live.GRAPHROOT), "/foreign/store"))
        blocked = live.attest(phase="pre_cutover", **opts)
        self.assertIn("foreign_graphroot", blocked["blockers"])


class PostCutoverTests(AttestationHarness):
    def test_ready_when_running_expected_service(self):
        result = self.attest("post_cutover", supervisor="running",
                             events=[self.event("L", "active")])
        self.assertTrue(result["ready"], result["blockers"])
        self.assertTrue(result["attests_live_process_identity"])
        self.assertEqual(result["checks"]["leases"]["active"], ["L"])

    def test_supervisor_down_is_blocker(self):
        blocked = self.attest("post_cutover", supervisor="absent")
        self.assertIn("s6_service_down:supervisor", blocked["blockers"])

    def test_old_script_pins_are_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        for path in (opts["persistent_watchdog"], opts["runtime_watchdog"]):
            text = path.read_text().replace(live.guard_source.DEPLOYED_HEAD, live.OLD_HEAD)
            path.write_text(text.replace(live.NEW_ROOT, live.OLD_ROOT))
        for path in (opts["persistent_supervisor"], opts["runtime_supervisor"]):
            text = path.read_text().replace(live.CONTROL_HEAD, live.OLD_HEAD)
            path.write_text(text.replace(live.CONTROL_ROOT, live.OLD_ROOT))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertTrue(any("script_pin" in b for b in blocked["blockers"]))

    def test_stop_sentinel_is_blocker(self):
        blocked = self.attest("post_cutover", supervisor="running", stop=True)
        self.assertIn("foreign_stop", blocked["blockers"])

    def test_split_roots_are_both_bound(self):
        result = self.attest("post_cutover", supervisor="running")
        self.assertTrue(result["ready"], result["blockers"])
        self.assertNotEqual(live.CONTROL_ROOT, live.NEW_ROOT)
        self.assertEqual(result["checks"]["expected_watchdog_root"], live.NEW_ROOT)
        self.assertEqual(result["checks"]["expected_control_root"], live.CONTROL_ROOT)

    def test_wrong_control_root_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        for key in ("persistent_supervisor", "runtime_supervisor"):
            opts[key].write_text(opts[key].read_text().replace(
                live.CONTROL_ROOT, live.NEW_ROOT))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertTrue(any(("script_pin_mismatch" in b
                             or "foreign_script_pin" in b)
                            and "persistent_supervisor" in b
                            for b in blocked["blockers"]), blocked["blockers"])

    def test_wrong_control_head_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        opts["head_reader"] = lambda base: (
            live.OLD_HEAD if str(base) == live.CONTROL_ROOT else self.heads.get(
                str(base), self.head))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("code_head_mismatch:supervisor", blocked["blockers"])

    def test_mixed_roots_are_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        for key in ("persistent_watchdog", "runtime_watchdog"):
            opts[key].write_text(opts[key].read_text().replace(
                live.NEW_ROOT, live.CONTROL_ROOT))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertTrue(any("watchdog" in b and (
            "script_pin_mismatch" in b or "foreign_script_pin" in b)
            for b in blocked["blockers"]), blocked["blockers"])

    def test_control_module_drift_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        original = opts["module_reader"]

        def drift(base, name):
            if name == "benchmarks/assembler_bench/px_supervisor.py":
                return "drift"
            return original(base, name)

        opts["module_reader"] = drift
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("module_bytes_mismatch:supervisor", blocked["blockers"])


class SupervisorArgvBindingTests(AttestationHarness):
    def _supervisor_cmd(self, root, registry):
        return ("python3 -m assembler_bench.px_execution --registry %s "
                "--root %s --supervise --armed" % (registry, root))

    def _supervisor_env(self, root, registry):
        return {
            "PYTHONPATH": "%s:%s/benchmarks" % (root, root),
            "PX_CODE": root, "PX_ROOT": str(root), "PX_REGISTRY": str(registry),
        }

    def test_wrong_supervisor_root_argv_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        self.proc_entry(SUPERVISOR,
                        self._supervisor_cmd("/foreign/root", self.registry),
                        self._supervisor_env(live.CONTROL_ROOT, self.registry))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("option_value_mismatch:supervisor:--root", blocked["blockers"])

    def test_wrong_supervisor_registry_argv_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        self.proc_entry(SUPERVISOR,
                        self._supervisor_cmd(self.project, "/foreign/registry.json"),
                        self._supervisor_env(live.CONTROL_ROOT, self.registry))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("option_value_mismatch:supervisor:--registry", blocked["blockers"])

    def test_duplicate_supervisor_root_option_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        cmd = self._supervisor_cmd(self.project, self.registry).replace(
            "--root " + str(self.project),
            "--root " + str(self.project) + " --root /foreign/root")
        self.proc_entry(SUPERVISOR, cmd,
                        self._supervisor_env(live.CONTROL_ROOT, self.registry))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("option_count_mismatch:supervisor:--root", blocked["blockers"])

    def test_duplicate_supervise_flag_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        self.proc_entry(SUPERVISOR,
                        self._supervisor_cmd(self.project, self.registry)
                        + " --supervise",
                        self._supervisor_env(live.CONTROL_ROOT, self.registry))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("flag_count_mismatch:supervisor:--supervise", blocked["blockers"])

    def test_extra_unknown_supervisor_token_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        self.proc_entry(SUPERVISOR,
                        self._supervisor_cmd(self.project, self.registry)
                        + " --unknown-flag",
                        self._supervisor_env(live.CONTROL_ROOT, self.registry))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertFalse(blocked["ready"], blocked["blockers"])
        self.assertTrue(any("unexpected_argv_token:supervisor" in b
                            for b in blocked["blockers"]), blocked["blockers"])

    def test_wrong_px_root_env_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        env = self._supervisor_env(live.CONTROL_ROOT, self.registry)
        env["PX_ROOT"] = "/foreign/root"
        self.proc_entry(SUPERVISOR,
                        self._supervisor_cmd(self.project, self.registry), env)
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("env_mismatch:supervisor:PX_ROOT", blocked["blockers"])

    def test_wrong_px_registry_env_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        env = self._supervisor_env(live.CONTROL_ROOT, self.registry)
        env["PX_REGISTRY"] = "/foreign/registry.json"
        self.proc_entry(SUPERVISOR,
                        self._supervisor_cmd(self.project, self.registry), env)
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("env_mismatch:supervisor:PX_REGISTRY", blocked["blockers"])

    def test_foreign_registry_script_pin_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        for key in ("persistent_supervisor", "runtime_supervisor"):
            opts[key].write_text(opts[key].read_text().replace(
                str(self.registry), "/foreign/registry.json"))
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertTrue(any("foreign_registry_pin" in b for b in blocked["blockers"]),
                        blocked["blockers"])

    def test_wrong_watchdog_root_argv_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        self.proc_entry(WATCHDOG,
                        "python3 -m fail_closed_guard.watchdog_cli --root /foreign/root "
                        "--graphroot " + str(live.GRAPHROOT),
                        {"PYTHONPATH": "%s:%s/benchmarks" % (live.NEW_ROOT, live.NEW_ROOT),
                         "WATCHDOG_CODE": live.NEW_ROOT,
                         "WATCHDOG_ROOT": str(self.project),
                         "WATCHDOG_GRAPHROOT": str(live.GRAPHROOT)})
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertIn("option_value_mismatch:watchdog:--root", blocked["blockers"])

    def test_noncanonical_worker_journal_is_refused(self):
        opts = self.build("post_cutover", supervisor="running")
        opts["worker_journal"] = self.project / "other.jsonl"
        with self.assertRaisesRegex(ValueError, "canonical lease journal"):
            live.attest(phase="post_cutover", **opts)


class WatchdogArgvBindingTests(AttestationHarness):
    def _watchdog_cmd(self, *, graphroot=None, extra=""):
        return ("python3 -m fail_closed_guard.watchdog_cli --root %s "
                "--graphroot %s%s" % (self.project, graphroot or live.GRAPHROOT,
                                      extra))

    def _watchdog_env(self):
        return {
            "PYTHONPATH": "%s:%s/benchmarks" % (live.NEW_ROOT, live.NEW_ROOT),
            "WATCHDOG_CODE": live.NEW_ROOT,
            "WATCHDOG_ROOT": str(self.project),
            "WATCHDOG_GRAPHROOT": str(live.GRAPHROOT),
        }

    def test_duplicate_watchdog_graphroot_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        self.proc_entry(WATCHDOG,
                        self._watchdog_cmd(extra=" --graphroot /foreign/store"),
                        self._watchdog_env())
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertFalse(blocked["ready"], blocked["blockers"])
        self.assertIn("option_count_mismatch:watchdog:--graphroot",
                      blocked["blockers"])

    def test_foreign_watchdog_graphroot_value_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        self.proc_entry(WATCHDOG, self._watchdog_cmd(graphroot="/foreign/store"),
                        self._watchdog_env())
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertFalse(blocked["ready"], blocked["blockers"])
        self.assertIn("option_value_mismatch:watchdog:--graphroot",
                      blocked["blockers"])

    def test_extra_unknown_watchdog_token_is_blocker(self):
        opts = self.build("post_cutover", supervisor="running")
        self.proc_entry(WATCHDOG,
                        self._watchdog_cmd(extra=" --unknown-option /foreign"),
                        self._watchdog_env())
        blocked = live.attest(phase="post_cutover", **opts)
        self.assertFalse(blocked["ready"], blocked["blockers"])
        self.assertTrue(any("unexpected_argv_token:watchdog" in b
                            for b in blocked["blockers"]), blocked["blockers"])

    def test_legitimate_watchdog_options_remain_ready(self):
        opts = self.build("post_cutover", supervisor="running")
        cmd = ("python3 -m fail_closed_guard.watchdog_cli "
               "--root %s --storage-conf %s --graphroot %s --stop %s "
               "--rss-limit 4000000000"
               % (self.project, self.project / "storage.conf", live.GRAPHROOT,
                  self.project / "STOP"))
        self.proc_entry(WATCHDOG, cmd, self._watchdog_env())
        result = live.attest(phase="post_cutover", **opts)
        self.assertTrue(result["ready"], result["blockers"])
        self.assertTrue(result["attests_live_process_identity"])


if __name__ == "__main__":
    unittest.main()
