"""Red-green tests for concrete P1 pilot readiness hardening items.

Source-only: temp files and injected callables; no build, OCI, Podman, arm,
lease, STOP or live benchmark is touched.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expanded import p1_bounded_pilot_runner as r
from expanded import p1_watchdog_readiness as w

MERGED_HEAD = "07231fa1a06b2cdd7d43d9896935f5050b7df4f5"
BINARY_SHA = "8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786"
IMAGE = "a" * 64


class ImageContractEnvTests(unittest.TestCase):
    def test_default_inspect_uses_supplied_pinned_env(self):
        sentinel = {"CONTAINERS_STORAGE_CONF": "/pinned/storage.conf"}
        with mock.patch.object(r.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="ok\n")
            rc, out = r._default_inspect("image", "{{.Id}}", env=sentinel)
        self.assertEqual((rc, out), (0, "ok"))
        self.assertIs(run.call_args.kwargs.get("env"), sentinel)

    def test_verify_image_contract_rejects_ambient_or_wrong_store(self):
        def inspect(image, fmt):
            return 0, "{}"
        for env in ({"CONTAINERS_STORAGE_CONF": "/ambient/storage.conf"}, {}):
            with self.assertRaises(ValueError):
                r.verify_image_contract(IMAGE, r.SOURCE_COMMIT, env=env,
                                        inspect=inspect)

    def test_integration_base_is_merged_head(self):
        self.assertEqual(r.INTEGRATION_BASE, MERGED_HEAD)


class SlotBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "slot.json"
        self.record = {
            "schema": "ivanka.p1.operator-slot.v1",
            "slot": "exact-token",
            "expires_utc": 2_000_000_000,
            "source_commit": r.SOURCE_COMMIT,
            "image": IMAGE,
            "cases_sha256": "b" * 64,
            "owner": "p1-pilot:owner",
        }
        self.record["evidence_root"] = "/workspace/evidence"
        self.bindings = {k: self.record[k] for k in
                         ("source_commit", "image", "cases_sha256", "owner",
                          "evidence_root")}

    def write(self, **overrides):
        record = dict(self.record)
        record.update(overrides)
        self.path.write_text(json.dumps(record))

    def test_valid_binding_accepted(self):
        self.write()
        got = r.verify_operator_slot("exact-token", path=self.path,
                                     wall=lambda: 1_900_000_000, **self.bindings)
        self.assertEqual(got["slot"], "exact-token")

    def test_each_binding_mismatch_rejected(self):
        for field in self.bindings:
            self.write(**{field: "WRONG"})
            with self.assertRaises(ValueError, msg=field):
                r.verify_operator_slot("exact-token", path=self.path,
                                       wall=lambda: 1_900_000_000, **self.bindings)

    def test_expired_slot_rejected(self):
        self.write()
        with self.assertRaises(ValueError):
            r.verify_operator_slot("exact-token", path=self.path,
                                   wall=lambda: 2_100_000_000, **self.bindings)


class BinaryStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stage = Path(self.tmp.name) / "stage"
        self.stage.mkdir()
        self.binary = self.stage / "combined-950fe331"
        self.binary.write_bytes(b"\x7fELF" + b"0" * 32)
        self.binary.chmod(0o755)

    def expected(self):
        return r.sha256(self.binary)

    def test_stage_verified(self):
        proof = r.verify_binary_stage(self.stage, expected_sha=self.expected())
        self.assertTrue(proof["verified"])

    def test_stage_rejects_bad_hash(self):
        good_sha = self.expected()
        self.binary.write_bytes(b"\x7fELF" + b"x" * 32)
        with self.assertRaises(ValueError):
            r.verify_binary_stage(self.stage, expected_sha=good_sha)

    def test_stage_rejects_bad_mode_or_elf(self):
        good_sha = self.expected()
        self.binary.chmod(0o644)
        with self.assertRaises(ValueError):
            r.verify_binary_stage(self.stage, expected_sha=good_sha)
        self.binary.chmod(0o755)
        self.binary.write_bytes(b"NOTELF" + b"0" * 32)
        with self.assertRaises(ValueError):
            r.verify_binary_stage(self.stage, expected_sha=good_sha)

    def test_stage_rejects_extra_files(self):
        (self.stage / "extra").write_text("x")
        with self.assertRaises(ValueError):
            r.verify_binary_stage(self.stage, expected_sha=self.expected())

    def test_exact_layer_entries_verified(self):
        fake_sha = "e" * 64
        got = r.verify_binary_layer_entries(
            {"/usr/local/bin/ivanka": fake_sha}, expected_sha=fake_sha)
        self.assertTrue(got["verified"])

    def test_layer_entries_reject_extra_missing_or_wrong_hash(self):
        fake_sha = "e" * 64
        for entries in ({}, {"/usr/local/bin/ivanka": "0" * 64},
                        {"/usr/local/bin/ivanka": fake_sha, "/src/main.rs": "0" * 64}):
            with self.assertRaises(ValueError):
                r.verify_binary_layer_entries(entries, expected_sha=fake_sha)


class LiveFingerprintTests(unittest.TestCase):
    def test_default_expected_has_no_stale_code_path(self):
        exp = w.default_expected()
        self.assertNotIn("WATCHDOG_CODE", exp)
        self.assertEqual(exp["watchdog_service_head"],
                         "091f56275ae823cb3291b81dbdf016fcf16c3ea0")
        self.assertNotEqual(exp["watchdog_service_head"],
                            "f861f25b6e62e1266a498340e7d3cf9a09a9087f")

    def test_probe_alive_checks_live_fingerprint(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        table = {1503395: {"starttime": 447346729, "pid_ns": 4026532737,
                           "cmdline_sha": "c" * 64}}
        (root / ".watchdog-alive.json").write_text(json.dumps({
            "schema": "ivanka.watchdog-alive.v1", "at_utc": 1_900_000_000,
            "pid": 1503395, "fingerprint": [447346729, 4026532737],
            "cmdline_sha": "c" * 64,
            "graphroot": "/workspace/ivanka-exploratory-podman-20261121/store",
        }))
        graphroot = "/workspace/ivanka-exploratory-podman-20261121/store"
        good = w.probe_alive(root=root, graphroot=graphroot,
                             snapshot=lambda: table, wall=lambda: 1_900_000_001)
        self.assertTrue(good["ready"], good)
        bad_table = {1503395: dict(table[1503395], cmdline_sha="d" * 64)}
        bad = w.probe_alive(root=root, graphroot=graphroot,
                            snapshot=lambda: bad_table, wall=lambda: 1_900_000_001)
        self.assertFalse(bad["ready"])
        self.assertEqual(bad["reason"], "watchdog_identity_mismatch")


if __name__ == "__main__":
    unittest.main()


class GlobalSlotConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.auth = Path(self.tmp.name) / "operator-auth"
        self.auth.mkdir()
        self.root_a = Path(self.tmp.name) / "evidence-a"
        self.root_b = Path(self.tmp.name) / "evidence-b"
        self.root_a.mkdir()
        self.root_b.mkdir()
        self.slot = "exact-slot"

    def claim(self, out, **kw):
        return r.claim_slot(out, self.slot, owner="owner",
                            cases_sha256="c" * 64, auth_root=self.auth,
                            wall=lambda: 1_900_000_000, **kw)

    def test_replay_refused_across_alternate_output_roots(self):
        self.claim(self.root_a)
        with self.assertRaises(ValueError):
            self.claim(self.root_b)

    def test_evidence_root_binding_rejected(self):
        # A distinct slot bound to root A cannot be consumed from root B.
        with self.assertRaises(ValueError):
            self.claim(self.root_b, evidence_root=str(self.root_a))

    def test_same_root_replay_refused(self):
        self.claim(self.root_a)
        with self.assertRaises(ValueError):
            self.claim(self.root_a)

    def test_ledger_persists_globally(self):
        marker = self.claim(self.root_a)
        self.assertTrue((self.auth / "slot-consumption.jsonl").is_file())
        self.assertIn("slot_sha256", json.loads(marker.read_text()))


class LayerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.graphroot = self.base / "store"
        self.layer_id = "f" * 64
        diff = self.graphroot / "overlay" / self.layer_id / "diff" / "usr" / "local" / "bin"
        diff.mkdir(parents=True)
        self.binary = diff / "ivanka"
        self.binary.write_bytes(b"\x7fELF" + b"0" * 32)
        self.sha = r.sha256(self.binary)
        layers_dir = self.graphroot / "overlay-layers"
        layers_dir.mkdir(parents=True)
        (layers_dir / "layers.json").write_text(json.dumps([{
            "id": self.layer_id,
            "diff-digest": "sha256:" + self.layer_id,
        }]))
        self.env = {"CONTAINERS_STORAGE_CONF": "/pinned/storage.conf"}

    def inspect(self, image, fmt):
        if "{{json .RootFS.Layers}}" not in fmt:
            return 0, "ignored"
        layers = ["a" * 64, "b" * 64, self.layer_id] if image == "candidate" else ["a" * 64, "b" * 64]
        return 0, json.dumps(layers)

    def test_real_added_layer_evidence_verified(self):
        entries = r.acquire_added_layer_evidence(
            "candidate", env=self.env, inspect=self.inspect,
            graphroot=self.graphroot)
        proof = r.verify_image_layer_contract(
            "candidate", env=self.env, inspect=self.inspect,
            graphroot=self.graphroot, expected_sha=self.sha)
        self.assertTrue(proof["verified"])
        self.assertEqual(entries["entries"]["/usr/local/bin/ivanka"], self.sha)

    def test_added_layer_evidence_rejects_extra_file(self):
        (self.binary.parent / "extra").write_text("x")
        with self.assertRaises(ValueError):
            r.verify_image_layer_contract(
                "candidate", env=self.env, inspect=self.inspect,
                graphroot=self.graphroot, expected_sha=self.sha)

    def test_added_layer_evidence_rejects_wrong_parent(self):
        def bad_inspect(image, fmt):
            if "{{json .RootFS.Layers}}" not in fmt:
                return 0, "ignored"
            layers = ["a" * 64] if image == "candidate" else ["z" * 64]
            return 0, json.dumps(layers)
        with self.assertRaises(ValueError):
            r.verify_image_layer_contract(
                "candidate", env=self.env, inspect=bad_inspect,
                graphroot=self.graphroot)


class AmbientEnvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def synthetic_conf(self):
        conf = Path(self.tmp.name) / "storage.conf"
        conf.write_text("[storage]\ngraphroot = '/tmp/p1-fixture-store'\n")
        return conf, r.sha256(conf)

    def test_ambient_container_selectors_are_stripped(self):
        conf, digest = self.synthetic_conf()
        with mock.patch.dict(os.environ, {
                "CONTAINERS_CONF": "/ambient/containers.conf",
                "CONTAINERS_STORAGE_CONF": "/ambient/storage.conf",
                "CONTAINERS_IMAGEROOT": "/ambient/images",
                "CONTAINERS_STORAGE_DRIVER": "vfs"}, clear=False):
            env = r.pinned_podman_env(conf, expected_sha=digest)
        self.assertEqual(env["CONTAINERS_STORAGE_CONF"], str(conf.resolve()))
        self.assertNotIn("CONTAINERS_CONF", env)
        self.assertNotIn("CONTAINERS_IMAGEROOT", env)
        self.assertNotIn("CONTAINERS_STORAGE_DRIVER", env)

    def test_missing_and_symlink_conf_refused(self):
        conf, digest = self.synthetic_conf()
        missing = Path(self.tmp.name) / "absent.conf"
        with self.assertRaises(ValueError):
            r.pinned_podman_env(missing, expected_sha=digest)
        link = Path(self.tmp.name) / "linked.conf"
        link.symlink_to(conf)
        with self.assertRaises(ValueError):
            r.pinned_podman_env(link, expected_sha=digest)

    def test_wrong_hash_refused(self):
        conf, _digest = self.synthetic_conf()
        with self.assertRaises(ValueError):
            r.pinned_podman_env(conf, expected_sha="0" * 64)

    def test_wrong_store_conf_pin_fails_closed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        bad = Path(tmp.name) / "storage.conf"
        bad.write_text("[storage]\ngraphroot = '/tmp/x'\n")
        with self.assertRaises(ValueError):
            r.pinned_podman_env(bad)


class LiveWatchdogCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".watchdog-alive.json").write_text(json.dumps({
            "schema": "ivanka.watchdog-alive.v1", "at_utc": 1_900_000_000,
            "pid": 1503395, "fingerprint": [447346729, 4026532737],
            "cmdline_sha": "c" * 64,
            "graphroot": "/workspace/ivanka-exploratory-podman-20261121/store"}))
        self.table = {1503395: {"starttime": 447346729, "pid_ns": 4026532737,
                                "cmdline_sha": "c" * 64}}

    def test_live_ready_passes_with_fresh_snapshot(self):
        got = r.require_live_watchdog_ready(
            self.root / ".watchdog-alive.json",
            "/workspace/ivanka-exploratory-podman-20261121/store",
            wall=lambda: 1_900_000_001, snapshot=lambda: self.table)
        self.assertTrue(got["ready"])

    def test_missing_live_pid_fails_closed(self):
        with self.assertRaises(ValueError):
            r.require_live_watchdog_ready(
                self.root / ".watchdog-alive.json",
                "/workspace/ivanka-exploratory-podman-20261121/store",
                wall=lambda: 1_900_000_001, snapshot=dict)

    def test_slot_bindings_bind_evidence_root_and_image(self):
        manifest = {"candidate_source_commit": r.SOURCE_COMMIT,
                    "candidate_image": "i" * 64, "owner": "owner",
                    "paths": {"evidence_root": "/workspace/evidence"}}
        b = r.slot_bindings(manifest, "c" * 64)
        self.assertEqual(b["evidence_root"], "/workspace/evidence")
        self.assertEqual(b["image"], "i" * 64)
        for key in ("source_commit", "image", "cases_sha256", "owner", "evidence_root"):
            self.assertIn(key, b)


class ProspectiveGuardPinTests(unittest.TestCase):
    def test_reviewed_guard_head_pinned_source_only(self):
        proof = r.verify_guard_source_pins()
        self.assertEqual(proof["head"], "091f56275ae823cb3291b81dbdf016fcf16c3ea0")
        self.assertTrue(proof["prospective"])
        self.assertFalse(proof["deployed"])
        self.assertEqual(len(proof["digests"]), 5)

    def test_mismatched_guard_source_refused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        for name, (relative, _digest) in r.REVIEWED_GUARD_DIGESTS.items():
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        with self.assertRaises(ValueError):
            r.verify_guard_source_pins(base)


class CopyOverlayAdmissionPinTests(unittest.TestCase):
    def test_merged_pr535_admission_pinned_source_only(self):
        proof = r.verify_copy_overlay_admission_pins()
        self.assertEqual(proof["merge"], r.COPY_OVERLAY_ADMISSION_MERGE)
        self.assertEqual(proof["pr_head"], r.COPY_OVERLAY_ADMISSION_PR_HEAD)
        self.assertTrue(proof["prospective"])
        self.assertFalse(proof["deployed"])
        self.assertFalse(proof["build_executed"])
        self.assertEqual(len(proof["digests"]), 4)
        self.assertEqual(proof["digests"]["watchdog_cli"],
                         "e00b83adfbf8356f2f92ce92ecd2226854a182d21a21e24ca87d35ed205b5369")

    def test_mismatched_admission_source_refused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        for name, (relative, _digest) in r.COPY_OVERLAY_ADMISSION_DIGESTS.items():
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        with self.assertRaises(ValueError):
            r.verify_copy_overlay_admission_pins(base)


class PortableArtifactPlanTests(unittest.TestCase):
    @staticmethod
    def _elf(interp, *, needed=(), runpath=None, glibc=b""):
        phoff, phentsize, phnum = 64, 56, 3
        interp_offset = phoff + phnum * phentsize
        interp_payload = interp.encode() + b"\0"
        strtab_offset = interp_offset + len(interp_payload)
        strings = bytearray(b"\0")
        offsets = {}
        for name in needed:
            offsets[name] = len(strings)
            strings.extend(name.encode() + b"\0")
        if runpath is not None:
            runpath_offset = len(strings)
            strings.extend(runpath.encode() + b"\0")
        else:
            runpath_offset = None
        entries = [(1, offsets[name]) for name in needed]
        entries.append((5, strtab_offset))  # DT_STRTAB (vaddr == file offset)
        entries.append((10, len(strings)))  # DT_STRSZ
        if runpath_offset is not None:
            entries.append((29, runpath_offset))  # DT_RUNPATH
        dynamic = b"".join(
            tag.to_bytes(8, "little", signed=True) + value.to_bytes(8, "little")
            for tag, value in entries)
        total = strtab_offset + len(strings) + len(dynamic) + len(glibc)
        header = bytearray(64)
        header[0:4] = b"\x7fELF"
        header[4], header[5] = 2, 1
        header[32:40] = phoff.to_bytes(8, "little")
        header[54:56] = phentsize.to_bytes(2, "little")
        header[56:58] = phnum.to_bytes(2, "little")

        def ph(kind, offset, vaddr, size):
            row = bytearray(phentsize)
            row[0:4] = kind.to_bytes(4, "little")
            row[8:16] = offset.to_bytes(8, "little")
            row[16:24] = vaddr.to_bytes(8, "little")
            row[32:40] = size.to_bytes(8, "little")
            return bytes(row)

        return bytes(header
                     + ph(1, 0, 0, total)              # PT_LOAD maps vaddr==offset
                     + ph(3, interp_offset, interp_offset, len(interp_payload))
                     + ph(2, strtab_offset + len(strings),
                          strtab_offset + len(strings), len(dynamic))
                     + interp_payload + strings + dynamic + glibc)

    def _write(self, data):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(lambda: tmp.name and Path(tmp.name).unlink(missing_ok=True))
        tmp.write(data)
        tmp.close()
        return tmp.name

    def test_plan_is_pinned_pending_and_covers_both_candidates(self):
        proof = r.verify_portable_plan()
        self.assertEqual(proof["schema"], "ivanka.p1.portable-artifact-plan.v1")
        self.assertEqual(proof["candidates"], 2)
        self.assertFalse(proof["produced"])
        self.assertFalse(proof["build_executed"])
        doc = r.load_portable_plan()
        native = [row["native_binary_sha256"] for row in doc["candidates"]]
        self.assertEqual(native, [
            "8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786",
            "ec5eb83546fb4fb212514a3ff54a8fea39e5b016e06ac70f46e2e22a1a931563"])
        self.assertTrue(all("/gnu/store/" in row["native_interp"]
                            for row in doc["candidates"]))

    def test_guix_interpreter_refused_no_silent_substitution(self):
        path = self._write(self._elf(
            "/gnu/store/m31vlvwm79m89fk3xk0z4h7snk61y510-glibc-2.41/lib/ld-linux-x86-64.so.2"))
        with self.assertRaises(ValueError):
            r.verify_portable_binary(path)

    def test_portable_interp_without_exact_pin_refused(self):
        path = self._write(self._elf(r.PORTABLE_INTERP,
                                     needed=r.PORTABLE_NEEDED))
        with self.assertRaises(ValueError):
            r.verify_portable_binary(path)

    def test_guix_runpath_and_future_glibc_refused(self):
        guix = self._write(self._elf(
            r.PORTABLE_INTERP, needed=r.PORTABLE_NEEDED,
            runpath="/gnu/store/m31vlvwm79m89fk3xk0z4h7snk61y510-glibc-2.41/lib"))
        with self.assertRaises(ValueError):
            r.verify_portable_binary(guix)
        future = self._write(self._elf(
            r.PORTABLE_INTERP, needed=r.PORTABLE_NEEDED,
            glibc=b"GLIBC_2.36\0"))
        with self.assertRaises(ValueError):
            r.verify_portable_binary(future)


class SeparatePcrCandidateTests(unittest.TestCase):
    def test_existing_950fe331_pin_untouched(self):
        path = Path(r.__file__).with_name("p1_pilot_image_manifest.json")
        self.assertEqual(r.sha256(path),
                         "1e2ac3fa6c688c3dc7bc45e04a59981d2dabbb4dddf7fb3e84c7aad0bf9dd9cb")
        doc = json.loads(path.read_text())
        self.assertEqual(doc["candidate_source_commit"], r.SOURCE_COMMIT)

    def test_pcr_candidate_staged_separately(self):
        path = Path(r.__file__).with_name("p1_pcr_image_manifest.json")
        doc = json.loads(path.read_text())
        self.assertEqual(doc["candidate_source_commit"],
                         "19386765b40a4d57dce15c0984a731486b69121e")
        self.assertEqual(doc["binary"]["sha256"],
                         "ec5eb83546fb4fb212514a3ff54a8fea39e5b016e06ac70f46e2e22a1a931563")
        self.assertFalse(doc["build"]["executed"])
        self.assertIsNone(doc["supersedes_or_overwrites"])
        src = Path(r.__file__).with_name(
            "Containerfile.p1-pcr-19386765-binary-only").read_text()
        self.assertIn("COPY new-candidate /usr/local/bin/ivanka", src)
        self.assertNotIn("\nRUN ", src)

    def test_no_truth_or_receipt_leakage_in_staged_recipes(self):
        forbidden = ("hidden-truth/", "results.jsonl", "conseq.csv",
                     "reference_panel", "panel_path", "truth.fasta")
        for name in ("p1_pilot_image_manifest.json", "p1_pcr_image_manifest.json",
                     "Containerfile.p1-pilot-950fe331-binary-only",
                     "Containerfile.p1-pcr-19386765-binary-only"):
            text = Path(r.__file__).with_name(name).read_text()
            for token in forbidden:
                self.assertNotIn(token, text, (name, token))
