"""Adversarial proofs for PR535+537 guard source-byte verification.

Source-only: temp dirs only, no live services, no mutation of real roots.
Distinguishes staged-byte/manifest verification from live process attestation.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_guard_source as guard_source

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks" / "fixtures" / "px_guard_pins"
CANONICAL_MANIFEST = ROOT / "benchmarks/assembler_bench" / guard_source.IDENTITY_NAME
CANONICAL_CONTROL = ROOT / "benchmarks/assembler_bench" / guard_source.CONTROL_IDENTITY_NAME


def _copy_fixture(destination):
    for source in FIXTURE.rglob("*"):
        if source.is_file():
            target = destination / source.relative_to(FIXTURE)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    return destination


def _init_git(destination, head=None):
    subprocess.run(["git", "init", "-q", str(destination)], check=True)
    subprocess.run(["git", "-C", str(destination), "config", "user.email", "t@e"], check=True)
    subprocess.run(["git", "-C", str(destination), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(destination), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(destination), "commit", "-q", "-m", "fixture"], check=True)
    if head is not None:
        # create a commit at a specific fake head? no - easier set HEAD by amend? avoid.
        pass
    return subprocess.run(["git", "-C", str(destination), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


class GuardSourceIdentityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.deployed = _copy_fixture(self.root / "deployed")
        self.control = _copy_fixture(self.root / "control")
        self.identity_root = self.root / "identity"
        (self.identity_root / "benchmarks/assembler_bench").mkdir(parents=True)
        shutil.copyfile(CANONICAL_CONTROL,
                        self.identity_root / "benchmarks/assembler_bench" / guard_source.CONTROL_IDENTITY_NAME)
        # Control checkout must carry the reviewed control-source files.
        control_id = json.loads(CANONICAL_CONTROL.read_bytes())
        for name in list(control_id["sources"]) + ["benchmarks/assembler_bench/px_guard_source.py"]:
            src = ROOT / name
            dst = self.control / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        _init_git(self.control)

    def verify(self, deployed=None, control=None):
        return guard_source.verify(root=deployed or self.deployed,
                                   control_root=control or self.control)

    def test_canonical_manifests_match(self):
        self.assertEqual((self.deployed / guard_source.IDENTITY_NAME).read_bytes(),
                         CANONICAL_MANIFEST.read_bytes())
        self.assertEqual(guard_source.digest(CANONICAL_MANIFEST), guard_source.IDENTITY_SHA256)
        self.assertEqual(guard_source.digest(CANONICAL_CONTROL), guard_source.CONTROL_IDENTITY_SHA256)

    def test_deployment_digest_chain_covers_runtime_modules(self):
        manifest = json.loads(CANONICAL_MANIFEST.read_bytes())
        self.assertEqual(manifest["schema"], guard_source.IDENTITY_SCHEMA)
        self.assertEqual(manifest["source_commit"], guard_source.DEPLOYED_HEAD)
        self.assertEqual(manifest["sources"], dict(guard_source.EXPECTED))
        self.assertEqual(len(guard_source.EXPECTED), 19)

    def test_no_self_referential_commit_pin(self):
        self.assertFalse(hasattr(guard_source, "CONTROL_HEAD"))
        self.assertEqual(guard_source.DEPLOYED_HEAD,
                         "165a86b38c0bc29b4f8e0281a39ca59b909a6563")

    def test_staged_git_checkout_head_is_checked(self):
        _init_git(self.deployed)
        with self.assertRaisesRegex(ValueError, "deployed checkout HEAD drift"):
            guard_source.verify_deployment(self.deployed)

    def test_staged_git_checkout_exact_head_passes(self):
        head = _init_git(self.deployed)
        manifest_path = self.deployed / guard_source.IDENTITY_NAME
        manifest = json.loads(manifest_path.read_bytes())
        manifest["source_commit"] = head
        blob = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        manifest_path.write_bytes(blob)
        sha = __import__("hashlib").sha256(blob).hexdigest()
        with patch.object(guard_source, "DEPLOYED_HEAD", head),              patch.object(guard_source, "IDENTITY_SHA256", sha):
            result = guard_source.verify_deployment(self.deployed)
        self.assertEqual(result["git_state"], "git_head_verified")

    def test_copy_build_without_git_requires_manifest(self):
        # no .git in fixture by default: manifest attestation is required and sufficient for bytes
        result = guard_source.verify_deployment(self.deployed)
        self.assertEqual(result["git_state"], "git_absent_manifest_attested")
        self.assertEqual(result["modules"], dict(guard_source.EXPECTED))

    def test_missing_git_never_skips_manifest(self):
        (self.deployed / guard_source.IDENTITY_NAME).unlink()
        with self.assertRaisesRegex(ValueError, "identity manifest missing"):
            guard_source.verify_deployment(self.deployed)

    def test_manifest_drift_fails_closed(self):
        path = self.deployed / guard_source.IDENTITY_NAME
        blob = json.loads(path.read_bytes())
        blob["source_commit"] = "0" * 40
        path.write_text(json.dumps(blob, sort_keys=True, separators=(",", ":")) + "\n")
        with self.assertRaisesRegex(ValueError, "identity manifest drift"):
            guard_source.verify_deployment(self.deployed)

    def test_deployment_byte_drift_fails_closed(self):
        target = self.deployed / "benchmarks/fail_closed_guard/copy_overlay.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "deployed PX guard source drift"):
            guard_source.verify_deployment(self.deployed)

    def test_control_requires_git_checkout(self):
        shutil.rmtree(self.control / ".git")
        with self.assertRaisesRegex(ValueError, "control checkout git identity missing"):
            guard_source.verify_control(self.control, identity_root=self.identity_root)

    def test_control_head_not_pinned_but_must_be_real(self):
        # arbitrary valid git head is fine (not self-referential hash pin)
        res = guard_source.verify_control(self.control, identity_root=self.identity_root)
        self.assertFalse(res["head_pinned"])
        self.assertRegex(res["head"], r"^[a-f0-9]{40}$")

    def test_control_source_drift_fails_closed(self):
        target = self.control / guard_source.CONTROL_RETRY_SOURCE
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "control PX source drift"):
            guard_source.verify_control(self.control, identity_root=self.identity_root)

    def test_control_guard_module_drift_fails_closed(self):
        target = self.control / "benchmarks/fail_closed_guard/watchdog.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "control PX guard source drift"):
            guard_source.verify_control(self.control, identity_root=self.identity_root)

    def test_both_identities_verified(self):
        with patch.object(guard_source, "root", return_value=self.identity_root):
            found = guard_source.verify(root=self.deployed, control_root=self.control)
        self.assertEqual(found, dict(guard_source.EXPECTED))

    def test_verify_is_not_live_attestation(self):
        # verify() checks bytes/manifests only; no /proc/s6 binding.
        self.assertEqual(guard_source.verify_deployment(self.deployed)["kind"],
                         "staged_deployment_bytes")


class NormalSchedulingPreservedTests(unittest.TestCase):
    def test_guard_rebinding_does_not_change_normal_scheduling(self):
        self.assertEqual(sched.MAX_INFRA_ATTEMPTS, 2)
        self.assertEqual(sched.RECEIPT_SCHEMA, "ivanka.px.case.receipt.v1")
        from assembler_bench import px_retry_authorization as authz
        self.assertEqual(authz.EXTRA_ATTEMPT, sched.MAX_INFRA_ATTEMPTS + 1)


if __name__ == "__main__":
    unittest.main()
