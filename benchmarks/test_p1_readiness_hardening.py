"""Red-green tests for concrete P1 pilot readiness hardening items.

Source-only: temp files and injected callables; no build, OCI, Podman, arm,
lease, STOP or live benchmark is touched.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expanded import p1_bounded_pilot_runner as r
from expanded import p1_watchdog_readiness as w

MERGED_HEAD = "3fb720c7fd74e08b77d453441c10fdfed3eb305f"
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
        self.bindings = {k: self.record[k] for k in
                         ("source_commit", "image", "cases_sha256", "owner")}

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
    def test_default_expected_includes_watchdog_code(self):
        exp = w.default_expected()
        self.assertEqual(exp["WATCHDOG_CODE"], "/workspace/ivanka-oci-transfer-20261126")

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
