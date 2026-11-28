"""Red-green tests for concrete P1 pilot readiness hardening items.

Source-only: temp files and injected callables; no build, OCI, Podman, arm,
lease, STOP or live benchmark is touched.
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from assembler_bench import px_guard_source as guard_source
from expanded import p1_bounded_pilot_runner as r
from expanded import p1_watchdog_readiness as w
from p1_portable_fixtures import build as build_postbuild_fixture

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
                         "1e5104082c4366f30c93fd759e3f46307a142e63")
        self.assertEqual(w.PREVIOUS_WATCHDOG_SERVICE_HEAD,
                         "165a86b38c0bc29b4f8e0281a39ca59b909a6563")
        self.assertEqual(w.LEGACY_WATCHDOG_SERVICE_HEAD,
                         "091f56275ae823cb3291b81dbdf016fcf16c3ea0")
        self.assertNotEqual(exp["watchdog_service_head"],
                            w.PREVIOUS_WATCHDOG_SERVICE_HEAD)

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
        self.assertEqual(proof["head"], "1e5104082c4366f30c93fd759e3f46307a142e63")
        self.assertEqual(r.PREVIOUS_REVIEWED_GUARD_HEAD,
                         "165a86b38c0bc29b4f8e0281a39ca59b909a6563")
        self.assertEqual(r.LEGACY_REVIEWED_GUARD_HEAD,
                         "091f56275ae823cb3291b81dbdf016fcf16c3ea0")
        self.assertNotEqual(proof["head"], r.PREVIOUS_REVIEWED_GUARD_HEAD)
        self.assertTrue(proof["prospective"])
        self.assertFalse(proof["deployed"])
        self.assertEqual(len(proof["digests"]), 5)

    def test_p1_harness_source_pin_tracks_reviewed_bytes(self):
        path = (Path(__file__).resolve().parent
                / "fail_closed_guard" / "p1_harness.py")
        expected = r.sha256(path)
        self.assertEqual(r.REVIEWED_GUARD_DIGESTS["p1_harness"][1], expected)
        self.assertEqual(r.verify_guard_source_pins()["digests"]["p1_harness"],
                         expected)

    def test_new_reviewed_digests_and_unchanged_cli(self):
        identity = json.loads((Path(__file__).resolve().parent / "fixtures"
                               / "px_guard_pins" / "px_guard_identity.json")
                              .read_text())
        # The fixture is the staged deployment identity; the runner's reviewed
        # source head remains the prospective P1 source pin.
        self.assertEqual(identity["source_commit"],
                         guard_source.DEPLOYED_HEAD)
        self.assertEqual(r.REVIEWED_GUARD_HEAD,
                         "1e5104082c4366f30c93fd759e3f46307a142e63")
        sources = identity["sources"]
        for name, (relative, digest) in r.REVIEWED_GUARD_DIGESTS.items():
            key = "benchmarks/" + relative
            if key in sources:
                self.assertEqual(sources[key], digest, name)
        cli = r.COPY_OVERLAY_ADMISSION_DIGESTS["watchdog_cli"][1]
        self.assertEqual(cli, w.WATCHDOG_CLI_SHA256)
        self.assertEqual(cli,
                         "e00b83adfbf8356f2f92ce92ecd2226854a182d21a21e24ca87d35ed205b5369")
        self.assertEqual(sources["benchmarks/fail_closed_guard/watchdog_cli.py"], cli)

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

    def test_plan_pins_produced_portable_bytes_not_built_images(self):
        proof = r.verify_portable_plan()
        self.assertEqual(proof["schema"], "ivanka.p1.portable-artifact-plan.v1")
        self.assertEqual(proof["candidates"], 2)
        self.assertEqual(proof["produced"], 2)
        self.assertFalse(proof["build_executed"])
        doc = r.load_portable_plan()
        self.assertEqual(doc["status"], "PORTABLE_BYTES_PRODUCED_NOT_IMAGE_BUILT")
        self.assertEqual(doc["materialization_receipt"]["sha256"],
                         "e4cb0b07dc466a3656ab06816b2d457aa958088cb883e5b4bbb549a4061c1d51")
        self.assertEqual(doc["materialization_receipt"]["independent_elf_evidence_sha256"],
                         "f67550650d08d3fc7cb11516dbe224a2a9a6675b5b7f35c4037428618bf9c2ef")
        native = [row["native_binary_sha256"] for row in doc["candidates"]]
        self.assertEqual(native, [
            "8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786",
            "ec5eb83546fb4fb212514a3ff54a8fea39e5b016e06ac70f46e2e22a1a931563"])
        portable = [row["portable_binary_sha256"] for row in doc["candidates"]]
        self.assertEqual(portable, [
            "a3c3181be82a87bb823917e74d9e265b1afc0bd981c65d92b6db7cb2ea66a0bf",
            "de62b9f59f323090e7f2ba03890f33a2bb11c6dc1487a4cb22cca7a93efd8c16"])
        self.assertTrue(all("/gnu/store/" in row["native_interp"]
                            for row in doc["candidates"]))
        self.assertTrue(all(row["portable_image"] is None
                            and row["image_built"] is False
                            and row["image_identity_verified"] is False
                            and row["copy_only_build"]["executed"] is False
                            for row in doc["candidates"]))

    def test_actual_portable_bytes_match_pins_and_dynamic_contract(self):
        doc = r.load_portable_plan()
        for row in doc["candidates"]:
            path = Path(row["portable_binary_path"])
            if not path.exists():
                self.skipTest(f"portable artifact not mounted: {path}")
            self.assertEqual(r.sha256(path), row["portable_binary_sha256"])
            info = r.inspect_elf_portability(path)
            self.assertEqual(info["interp"], r.PORTABLE_INTERP)
            self.assertFalse(info["guix_store_runpath"])
            self.assertEqual(info["needed"], list(r.PORTABLE_NEEDED))
            self.assertLessEqual(max(info["glibc_minor_versions"]), 34)
            proof = r.verify_portable_binary(
                path, source_commit=row["source_commit"])
            self.assertTrue(proof["portable"])

    def test_guix_interpreter_refused_no_silent_substitution(self):
        path = self._write(self._elf(
            "/gnu/store/m31vlvwm79m89fk3xk0z4h7snk61y510-glibc-2.41/lib/ld-linux-x86-64.so.2",
            needed=r.PORTABLE_NEEDED))
        with self.assertRaises(ValueError):
            r.verify_portable_binary(path)

    def test_native_pinned_binary_is_not_treated_as_portable(self):
        doc = r.load_portable_plan()
        row = doc["candidates"][0]
        native = Path(row["native_binary_path"])
        if not native.exists():
            self.skipTest(f"native artifact not mounted: {native}")
        with self.assertRaisesRegex(ValueError, "no silent substitution"):
            r.verify_portable_binary(native, source_commit=row["source_commit"])

    def test_portable_interp_without_exact_pin_refused(self):
        path = self._write(self._elf(r.PORTABLE_INTERP,
                                     needed=r.PORTABLE_NEEDED))
        with self.assertRaisesRegex(ValueError, "not produced/pinned"):
            r.verify_portable_binary(path, source_commit=r.SOURCE_COMMIT)

    def test_guix_runpath_and_future_glibc_refused(self):
        guix = self._write(self._elf(
            r.PORTABLE_INTERP, needed=r.PORTABLE_NEEDED,
            runpath="/gnu/store/m31vlvwm79m89fk3xk0z4h7snk61y510-glibc-2.41/lib"))
        with self.assertRaises(ValueError):
            r.verify_portable_binary(guix, source_commit=r.SOURCE_COMMIT)
        future = self._write(self._elf(
            r.PORTABLE_INTERP, needed=r.PORTABLE_NEEDED,
            glibc=b"GLIBC_2.36\0"))
        with self.assertRaises(ValueError):
            r.verify_portable_binary(future, source_commit=r.SOURCE_COMMIT)

    def test_post_build_image_identity_gate_fails_closed(self):
        row = r.load_portable_plan()["candidates"][0]
        with self.assertRaisesRegex(ValueError, "not verified post-build"):
            r.require_portable_image_identity_verified(
                row["source_commit"], "0" * 64)

    def _row(self):
        plan = r.load_portable_plan()
        return next(c for c in plan["candidates"]
                    if c["source_commit"] == r.SOURCE_COMMIT)

    def _fixture(self, root, *, row=None, image="1" * 64, mutate_result=None,
                 mutate_receipt=None, **kwargs):
        row = row or self._row()
        return build_postbuild_fixture(
            root, source_commit=row["source_commit"], role=row["role"],
            portable_sha=row["portable_binary_sha256"],
            native_sha=row["native_binary_sha256"],
            portable_binary_path=row["portable_binary_path"],
            prebuild_plan_sha=r.PORTABLE_PLAN_SHA256, image=image,
            base_image=r.PARENT_IMAGE,
            expected_labels=r.expected_portable_labels(row),
            mutate_result=mutate_result, mutate_receipt=mutate_receipt,
            **kwargs)

    def _prepare_args(self, root, info, *, image="1" * 64, receipt_sha=None):
        root = Path(root)
        out = root / "evidence"
        return mock.Mock(
            data=root / "data", frozen_results=root / "frozen.jsonl",
            timer=root / "timer.py", out=out, image=image,
            commit=r.SOURCE_COMMIT, storage_conf=root / "storage.conf",
            lock=r.DEFAULT_LOCK, stop=r.DEFAULT_STOP,
            lease_root=r.DEFAULT_LEASE_ROOT, disk_path=root,
            watchdog_path=root / "alive.json", owner="test-owner",
            cases=None, check=True, armed=False, slot=r.PENDING_SLOT,
            portable_postbuild_receipt=(info["receipt_path"] if info else None),
            portable_postbuild_receipt_sha256=(
                receipt_sha if receipt_sha is not None
                else (info["receipt_sha"] if info else None)))

    def _prepare_patches(self, args, graphroot="/px"):
        return (
            mock.patch.object(r, "verify_pins", return_value=True),
            mock.patch.object(r, "pinned_podman_env",
                              return_value={"CONTAINERS_STORAGE_CONF": "/pinned"}),
            mock.patch.object(r, "verify_px_store_binding",
                              return_value={"storage_conf": str(args.storage_conf),
                                            "storage_conf_sha256": "f" * 64,
                                            "graphroot": graphroot}),
            mock.patch.object(r, "verify_shared_px_boundary",
                              return_value={"shared": True}),
            mock.patch.object(r, "verify_image_contract",
                              return_value={"labels": {}, "parent": r.PARENT_IMAGE}),
            mock.patch.object(r, "verify_image_layer_contract",
                              return_value={"verified": True, "entries": {}}),
            mock.patch.object(r, "_disk_free", return_value=33 * 1024 ** 3),
        )

    def _with_patches(self, patches, fn):
        stack = __import__('contextlib').ExitStack()
        with stack:
            for patch in patches:
                stack.enter_context(patch)
            return fn()

    def test_prepare_requires_and_accepts_verified_portable_postbuild_receipt(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        info = self._fixture(tmp.name)
        args = self._prepare_args(tmp.name, info)
        run = lambda: r.prepare(args, disk_usage_fn=lambda p: 33 * 1024 ** 3,
                                copy_overlay_root=tmp.name)
        manifest = self._with_patches(self._prepare_patches(args), run)
        self.assertEqual(manifest["candidate_image"], "1" * 64)
        self.assertEqual(manifest["candidate_source_commit"], r.SOURCE_COMMIT)
        self.assertTrue(manifest["portable_postbuild_receipt"]["image_identity_verified"])
        self.assertTrue(manifest["portable_postbuild_receipt"]
                        ["copy_overlay_result"]["released"])

        args_missing = self._prepare_args(tmp.name, None)
        with self.assertRaisesRegex(ValueError, "portable postbuild receipt required"):
            r.prepare(args_missing, disk_usage_fn=lambda p: 33 * 1024 ** 3,
                      copy_overlay_root=tmp.name)
        with self.assertRaisesRegex(ValueError, "portable postbuild receipt required"):
            r.run(args_missing, disk_usage_fn=lambda p: 33 * 1024 ** 3,
                  copy_overlay_root=tmp.name)

    def test_postbuild_receipt_requires_sha_pin(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        info = self._fixture(tmp.name)
        args = self._prepare_args(tmp.name, info, receipt_sha=None)
        args.portable_postbuild_receipt_sha256 = None
        run = lambda: r.prepare(args, disk_usage_fn=lambda p: 33 * 1024 ** 3,
                                copy_overlay_root=tmp.name)
        with self.assertRaisesRegex(ValueError, "SHA pin required"):
            self._with_patches(self._prepare_patches(args), run)
        args_wrong = self._prepare_args(tmp.name, info, receipt_sha="0" * 64)
        with self.assertRaisesRegex(ValueError, "receipt pin mismatch"):
            self._with_patches(self._prepare_patches(args_wrong),
                               lambda: r.prepare(args_wrong,
                                                 disk_usage_fn=lambda p: 33 * 1024 ** 3,
                                                 copy_overlay_root=tmp.name))

    def test_prepare_rejects_tampered_portable_postbuild_evidence(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cases = [
            (dict(mutate_receipt=lambda rec: rec.__setitem__("prebuild_plan_sha256", "0" * 64)), "not bound to prebuild plan"),
            (dict(mutate_receipt=lambda rec: rec.__setitem__("image_digest", "2" * 64)), "image digest mismatch"),
            (dict(mutate_receipt=lambda rec: rec["copy_overlay_result"].__setitem__("sha256", "0" * 64)), "result pin mismatch"),
            (dict(mutate_result=lambda res: res["image_receipt"].__setitem__("one_layer_overlay", False)), "one-layer evidence"),
            (dict(mutate_result=lambda res: res["image_receipt"]["labels"].__setitem__(
                "org.ottojung.ivanka.binary-sha256", "f" * 64)), "label mismatch"),
            (dict(mutate_result=lambda res: res.__setitem__("status", "failed")), "not completed cleanly"),
            (dict(mutate_result=lambda res: res.__setitem__("exit_code", 1)), "exit code nonzero"),
            (dict(mutate_result=lambda res: res.__setitem__("plan_sha256", "f" * 64)), "plan sha mismatch"),
            (dict(omit_result=True), "result missing"),
            (dict(omit_bind=True), "lifecycle not unique"),
            (dict(duplicate_bind=True), "lifecycle not unique"),
            (dict(replay_acquire=True), "lifecycle not unique"),
            (dict(omit_release=True), "lifecycle not unique"),
            (dict(foreign_owner_release=True), "lease owner changed"),
            (dict(foreign_proof=True), "release proof mismatch"),
            (dict(wrong_release_proof=True), "release proof mismatch"),
            (dict(wrong_teardown=True), "release proof mismatch"),
            (dict(wrong_bind_plan=True), "bind evidence mismatch"),
            (dict(wrong_bind_graphroot=True), "bind evidence mismatch"),
            (dict(wrong_bind_storage_conf=True), "bind evidence mismatch"),
            (dict(fail_closed=True), "fail-closed evidence"),
        ]
        for index, (kwargs, pattern) in enumerate(cases):
            sub = Path(tmp.name) / f"case-{index}"
            info = self._fixture(sub, **kwargs)
            args = self._prepare_args(str(sub), info)
            run = lambda a=args, s=str(sub): r.prepare(
                a, disk_usage_fn=lambda p: 33 * 1024 ** 3, copy_overlay_root=s)
            with self.assertRaisesRegex(ValueError, pattern):
                self._with_patches(self._prepare_patches(args), run)


class PortablePostbuildSeamTests(unittest.TestCase):
    """Positive low-level seam: real image + layer verification, no mocks of it."""

    def test_prepare_independently_verifies_portable_image_and_binary_layer(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        binary = root / "portable-binary"
        binary.write_bytes(b"portable seam fixture binary")
        binary_sha = r.sha256(binary)

        plan = json.loads(json.dumps(r.load_portable_plan()))
        row = dict(plan["candidates"][1])
        pcr_commit = "19386765b40a4d57dce15c0984a731486b69121e"
        role = row["role"]
        row.update({"source_commit": pcr_commit,
                    "portable_binary_sha256": binary_sha})
        plan["candidates"][1] = row
        plan_path = root / "portable-plan.json"
        plan_path.write_text(json.dumps(plan, sort_keys=True))
        plan_pin = r.sha256(plan_path)

        image = "1" * 64
        base_layers = ["sha256:" + "b" * 64]
        added = "sha256:" + "c" * 64
        info = build_postbuild_fixture(
            root, source_commit=pcr_commit, role=role,
            portable_sha=binary_sha, native_sha=row["native_binary_sha256"],
            portable_binary_path=row["portable_binary_path"],
            prebuild_plan_sha=plan_pin, image=image,
            base_image=r.PARENT_IMAGE,
            expected_labels=r.expected_portable_labels(row),
            base_layers=base_layers, added_digest=added)

        graphroot = root / "graphroot"
        layer_id = "d" * 64
        index_dir = graphroot / "overlay-layers"
        index_dir.mkdir(parents=True)
        (index_dir / "layers.json").write_text(json.dumps([
            {"id": layer_id, "diff-digest": added,
             "compressed-diff-digest": added}]))
        target = graphroot / "overlay" / layer_id / "diff" / "usr" / "local" / "bin"
        target.mkdir(parents=True)
        shutil.copyfile(binary, target / "ivanka")

        expected_labels = r.expected_portable_labels(row)
        layers = base_layers + [added]

        def inspect(value, fmt):
            if fmt == "{{.Id}}":
                return 0, value
            if fmt == "{{json .Config.Labels}}":
                return 0, json.dumps(expected_labels)
            if fmt == "{{json .RootFS.Layers}}":
                return 0, json.dumps(base_layers if value == r.PARENT_IMAGE else layers)
            raise AssertionError(fmt)

        args = mock.Mock(
            data=root / "data", frozen_results=root / "frozen.jsonl",
            timer=root / "timer.py", out=root / "evidence", image=image,
            commit=pcr_commit, storage_conf=root / "storage.conf",
            lock=r.DEFAULT_LOCK, stop=r.DEFAULT_STOP,
            lease_root=r.DEFAULT_LEASE_ROOT, disk_path=root,
            watchdog_path=root / "alive.json", owner="test-owner",
            cases=None, check=True, armed=False, slot=r.PENDING_SLOT,
            portable_postbuild_receipt=info["receipt_path"],
            portable_postbuild_receipt_sha256=info["receipt_sha"])

        with mock.patch.object(r, "PORTABLE_PLAN", plan_path),              mock.patch.object(r, "PORTABLE_PLAN_SHA256", plan_pin),              mock.patch.object(r, "verify_pins", return_value=True),              mock.patch.object(r, "verify_guard_source_pins", return_value={}),              mock.patch.object(r, "verify_copy_overlay_admission_pins", return_value={}),              mock.patch.object(r, "verify_shared_px_boundary", return_value={"shared": True}),              mock.patch.object(r, "verify_px_store_binding",
                               return_value={"storage_conf": str(args.storage_conf),
                                             "storage_conf_sha256": "f" * 64,
                                             "graphroot": str(graphroot)}),              mock.patch.object(r, "pinned_podman_env",
                               return_value={"CONTAINERS_STORAGE_CONF":
                                             r.SHARED_PX_BOUNDARY["storage_conf"]}):
            manifest = r.prepare(args, image_inspect=inspect,
                                 disk_usage_fn=lambda p: 33 * 1024 ** 3,
                                 copy_overlay_root=root)

        self.assertEqual(manifest["candidate_image"], image)
        self.assertEqual(manifest["candidate_source_commit"], pcr_commit)
        self.assertEqual(manifest["candidate_portable_role"], role)
        self.assertEqual(manifest["candidate_image_contract"]["labels"],
                         expected_labels)
        self.assertEqual(manifest["added_layer_evidence"]["entries"],
                         {"/usr/local/bin/ivanka": binary_sha})
        # The native image manifest would reject this PCR source and binary.
        with self.assertRaisesRegex(ValueError, "source commit differs"):
            r.verify_image_contract(
                image, pcr_commit,
                env={"CONTAINERS_STORAGE_CONF": r.SHARED_PX_BOUNDARY["storage_conf"]},
                inspect=inspect, image_manifest=r.load_image_manifest()[0])


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
