"""Regressions for the five operator-flagged cache auto-retire safety defects."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from assembler_bench import terminal_cache_retire as tcr


def terminal_status(agent_id, **overrides):
    status = {
        "id": agent_id,
        "state": "clearexit",
        "alive": False,
        "exit_code": 0,
        "finished_at": 2_000_000_000.0,
    }
    status.update(overrides)
    return status


class TerminalCacheRetireTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.state = self.base / "state"
        self.proc = self.base / "proc"
        (self.state / tcr.BUILD_CACHE_DIR).mkdir(parents=True)
        self.proc.mkdir()
        self.cleanups = []

    def register(self, agent_id, payload=b"compiler output"):
        directory = self.state / tcr.BUILD_CACHE_DIR / agent_id
        target = directory / tcr.MANAGED_CACHE_LEAF
        target.mkdir(parents=True)
        (target / ".rustc_info.json").write_bytes(json.dumps({}).encode())
        (target / "debug").mkdir()
        (target / "debug" / "artifact.o").write_bytes(payload)
        st = target.lstat()
        marker = {
            "schema": tcr.MANAGED_CACHE_SCHEMA,
            "agent_id": agent_id,
            "path": str(target),
            "nonce": "nonce-" + agent_id,
            "created_at": 1_700_000_000_000,
            "dev": st.st_dev,
            "ino": st.st_ino,
        }
        (directory / tcr.MANAGED_CACHE_MARKER).write_text(json.dumps(marker))
        return target, marker

    def quiet_snapshot(self, proc_root=None, running_agent_ids=(), log_reader=None):
        return tcr.take_reference_snapshot(str(self.proc), running_agent_ids,
                                           log_reader)

    def clean_snapshot(self):
        return tcr.ReferenceSnapshot((), ())

    def plan(self, status_reader=None, proc_root=None):
        if status_reader is None:
            status_reader = lambda aid: terminal_status(aid)
        return tcr.plan_retirements(
            str(self.state), str(self.proc), (), None,
            status_reader=status_reader)

    def apply(self, candidates, **kwargs):
        def recorder():
            self.cleanups.append("registered-cache-clean")
        kwargs.setdefault("status_reader", lambda aid: terminal_status(aid))
        kwargs.setdefault("snapshot_reader",
                          lambda proc_root, running, logs: self.clean_snapshot())
        return tcr.apply_retirements(candidates, str(self.state), str(self.proc),
                                     (), None, cleanup=recorder, **kwargs)

    # --- Defect 1: cached snapshots reused at deletion time -----------------
    def test_fresh_reference_snapshot_at_apply_blocks_candidate(self):
        target, _ = self.register("AAAAAAAA1111-terminal")
        candidates, blocked = self.plan()
        self.assertEqual([c["path"] for c in candidates], [str(target)])
        self.assertEqual(blocked, [])
        # A process now references the path after the planning snapshot.
        appearing = tcr.ReferenceSnapshot((str(target),), ())
        applied, refused = self.apply(
            candidates,
            snapshot_reader=lambda proc_root, running, logs: appearing)
        self.assertEqual(applied, [])
        self.assertEqual(refused, [(str(target), "live or unreadable reference")])
        self.assertEqual(self.cleanups, [])

    def test_owner_status_is_reread_at_apply(self):
        target, _ = self.register("AAAAAAAA1111-terminal")
        calls = {"n": 0}

        def changing(aid):
            calls["n"] += 1
            if calls["n"] == 1:
                return terminal_status(aid)
            # The owner restarted between scan and apply.
            return terminal_status(aid, state="running", alive=True,
                                   finished_at=None)

        # Use one reader across both phases so the second read is the apply one.
        candidates, _ = self.plan(status_reader=changing)
        applied, refused = self.apply(candidates, status_reader=changing)
        self.assertEqual(applied, [])
        self.assertEqual(refused[0][0], str(target))
        self.assertIn("restarted", refused[0][1])
        self.assertEqual(self.cleanups, [])

    def test_nul_separated_cmdline_reference_is_detected(self):
        target, _ = self.register("AAAAAAAA3333-terminal")
        pid = self.proc / "5150"
        pid.mkdir()
        for key in ("cwd", "root", "exe"):
            (pid / key).symlink_to(str(self.base))
        (pid / "fd").mkdir()
        (pid / "environ").write_bytes(b"")
        (pid / "mountinfo").write_bytes(b"")
        (pid / "cmdline").write_bytes(
            ("/usr/bin/cargo\x00" + str(target) + "\x00").encode())
        snapshot = self.quiet_snapshot()
        self.assertEqual(snapshot.unreadable, ())
        self.assertTrue(snapshot.blocks(str(target)))

    def test_unparseable_reference_fails_closed(self):
        target, _ = self.register("AAAAAAAA4444-terminal")
        snapshot = tcr.ReferenceSnapshot(("/bad\x00reference",), ())
        self.assertTrue(snapshot.blocks(str(target)))

    def test_unreadable_running_agent_list_fails_closed(self):
        target, _ = self.register("AAAAAAAA5555-terminal")
        failed = SimpleNamespace(returncode=1, stdout="", stderr="list failed")
        with mock.patch.object(tcr.subprocess, "run", return_value=failed):
            candidates, blocked = tcr.plan_retirements(
                str(self.state), str(self.proc), None)
        self.assertEqual(candidates, [])
        self.assertTrue(any("running-agent list unreadable" in reason
                            for _, reason in blocked))

    # --- Defect 2: ownership inferred via an 8-character substring ----------
    def test_ownership_requires_exact_registration_not_path_substring(self):
        target, _ = self.register("AAAAAAAA1111-terminal")
        # Shares the first 8 characters of the registered agent id and looks
        # exactly like a compiler target, but has no registration marker.
        sibling = self.state / tcr.BUILD_CACHE_DIR / "AAAAAAAA2222-other"
        stray = sibling / tcr.MANAGED_CACHE_LEAF
        stray.mkdir(parents=True)
        (stray / ".rustc_info.json").write_text("{}")
        candidates, blocked = self.plan()
        self.assertEqual([c["path"] for c in candidates], [str(target)])
        self.assertTrue(all(path != str(stray) for path, _ in blocked))

    def test_marker_identity_mismatch_is_rejected(self):
        target, marker = self.register("BBBBBBBB1111-terminal")
        marker_path = target.parent / tcr.MANAGED_CACHE_MARKER
        # A marker bound to a different inode or agent cannot claim this path.
        for field, value in (("ino", marker["ino"] + 1),
                             ("agent_id", "BBBBBBBB9999-other")):
            forged = dict(marker, **{field: value})
            marker_path.write_text(json.dumps(forged))
            candidates, _ = self.plan()
            self.assertEqual(candidates, [], f"forged field accepted: {field}")
        marker_path.write_text(json.dumps(marker))
        candidates, _ = self.plan()
        self.assertEqual([c["path"] for c in candidates], [str(target)])

    def test_marker_changed_between_scan_and_apply_is_refused(self):
        target, marker = self.register("BBBBBBBB2222-terminal")
        marker_path = target.parent / tcr.MANAGED_CACHE_MARKER
        candidates, _ = self.plan()
        # A re-registration with a new nonce must invalidate the scan-time claim.
        marker_path.write_text(json.dumps(dict(marker, nonce="re-registered")))
        applied, refused = self.apply(candidates)
        self.assertEqual(applied, [])
        self.assertEqual(refused,
                         [(str(target), "registration changed since scan")])
        self.assertEqual(self.cleanups, [])

    # --- Defect 3: unreadable proc/log references silently ignored ----------
    def test_unreadable_log_reference_fails_closed(self):
        target, _ = self.register("CCCCCCCC1111-terminal")
        candidates, _ = self.plan()
        def unreadable_log(agent_id):
            raise PermissionError("log unreadable")
        snapshot = tcr.take_reference_snapshot(
            str(self.proc), ("live-agent",), unreadable_log)
        self.assertTrue(snapshot.unreadable)
        self.assertTrue(snapshot.blocks(str(target)))
        applied, refused = self.apply(
            candidates, snapshot_reader=lambda p, r, l: snapshot)
        self.assertEqual(applied, [])
        self.assertEqual(refused, [(str(target), "live or unreadable reference")])

    def test_unreadable_proc_reference_fails_closed(self):
        target, _ = self.register("CCCCCCCC2222-terminal")
        candidates, _ = self.plan()
        pid = self.proc / "4242"
        pid.mkdir()
        # A dangling fd symlink: readlink raises, so absence cannot be proven.
        (pid / "fd").mkdir()
        (pid / "fd" / "9").symlink_to(self.base / "vanished")
        snapshot = self.quiet_snapshot()
        self.assertTrue(snapshot.unreadable)
        self.assertTrue(snapshot.blocks(str(target)))
        ok, reason = tcr.predelete_reverify(
            candidates[0], lambda aid: terminal_status(aid),
            tcr.read_registration, snapshot)
        self.assertFalse(ok)
        self.assertEqual(reason, "live or unreadable reference")

    # --- Defect 4: lstat sampled after scan, not the original inode ---------
    def test_inode_swap_since_scan_is_refused(self):
        target, marker = self.register("DDDDDDDD1111-terminal")
        candidates, _ = self.plan()
        original_ino = candidates[0]["identity"]["ino"]
        # Rename the old directory aside so its inode stays allocated; a fresh
        # directory at the same path must then get a different inode.
        target.rename(target.parent / "old-target")
        target.mkdir()
        (target / ".rustc_info.json").write_text("{}")
        (target / "debug").mkdir()
        (target / "debug" / "artifact.o").write_bytes(b"fresh inode")
        self.assertNotEqual(target.lstat().st_ino, original_ino)
        applied, refused = self.apply(candidates)
        self.assertEqual(applied, [])
        self.assertEqual(refused,
                         [(str(target), "directory inode changed since scan")])
        self.assertEqual(self.cleanups, [])

    def test_tree_mutation_same_inode_is_refused(self):
        target, _ = self.register("DDDDDDDD2222-terminal", payload=b"small")
        candidates, _ = self.plan()
        # Same directory inode, but new files appear after the scan.
        (target / "debug" / "late.o").write_bytes(b"x" * 4096)
        applied, refused = self.apply(candidates)
        self.assertEqual(applied, [])
        self.assertEqual(refused, [(str(target), "cache tree changed since scan")])
        self.assertEqual(self.cleanups, [])

    # --- Defect 5: no ownership lock / restart guard ------------------------
    def test_exclusive_ownership_lock_blocks_apply(self):
        target, _ = self.register("EEEEEEEE1111-terminal")
        candidates, _ = self.plan()
        with tcr.ownership_lock(str(self.state), "EEEEEEEE1111-terminal"):
            applied, refused = self.apply(candidates)
        self.assertEqual(applied, [])
        self.assertEqual(len(refused), 1)
        self.assertIn("ownership lock busy", refused[0][1])
        self.assertEqual(self.cleanups, [])

    def test_restarted_owner_is_refused_under_lock(self):
        target, _ = self.register("EEEEEEEE2222-terminal")
        candidates, _ = self.plan()
        # Even if the reference snapshot is clean, a restarted owner blocks it.
        restarted = terminal_status("EEEEEEEE2222-terminal", state="running",
                                    alive=True, finished_at=None)
        applied, refused = self.apply(
            candidates, status_reader=lambda aid: restarted)
        self.assertEqual(applied, [])
        self.assertEqual(len(refused), 1)
        self.assertIn("restarted", refused[0][1])
        self.assertEqual(self.cleanups, [])

    # --- Guards: dry-run-only and delegation --------------------------------
    def test_happy_path_delegates_to_registered_cleanup(self):
        target, _ = self.register("FFFFFFFF1111-terminal")
        candidates, _ = self.plan()
        applied, refused = self.apply(candidates)
        self.assertEqual(applied, [str(target)])
        self.assertEqual(refused, [])
        self.assertEqual(self.cleanups, ["registered-cache-clean"])

    def test_apply_gate_requires_explicit_operator_approval(self):
        target, _ = self.register("FFFFFFFF2222-terminal")
        self.assertEqual(tcr.main(["--state-root", str(self.state),
                                   "--proc-root", str(self.proc)]), 0)
        self.assertEqual(tcr.main(["--state-root", str(self.state),
                                   "--proc-root", str(self.proc), "--apply"]), 2)
        self.assertEqual(self.cleanups, [])

    def test_owner_terminal_strict(self):
        self.assertTrue(tcr.owner_terminal(terminal_status("x")))
        self.assertFalse(tcr.owner_terminal(terminal_status("x", alive=True)))
        self.assertFalse(tcr.owner_terminal(terminal_status("x", exit_code=1)))
        self.assertFalse(tcr.owner_terminal(terminal_status("x", state="failed")))
        self.assertFalse(tcr.owner_terminal(
            terminal_status("x", finished_at=None)))
        self.assertFalse(tcr.owner_terminal(
            terminal_status("x", steers_pending=1)))


if __name__ == "__main__":
    unittest.main()
