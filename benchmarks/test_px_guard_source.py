"""Adversarial proofs for the combined PR535+537 guard source identity.

These tests are source-only: they copy reviewed fixture bytes into temporary
directories and never arm, stop, restart or mutate a live service. They prove
that the deployment checkout and the control checkout are both verified and
that a missing git directory can never silently skip identity verification.
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
CANONICAL_MANIFEST = (ROOT / "benchmarks" / "assembler_bench"
                      / guard_source.IDENTITY_NAME)
CANONICAL_RETRY = ROOT / guard_source.CONTROL_RETRY_SOURCE


def _copy_fixture(destination):
    """Copy the reviewed fixture tree, including the identity manifest."""
    for source in FIXTURE.rglob("*"):
        if source.is_file():
            target = destination / source.relative_to(FIXTURE)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    return destination


def _git_repo(destination):
    """Create a real git checkout holding byte-identical guard modules."""
    target = destination / guard_source.CONTROL_RETRY_SOURCE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CANONICAL_RETRY, target)
    subprocess.run(["git", "init", "-q", str(destination)], check=True)
    subprocess.run(["git", "-C", str(destination), "config",
                    "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(destination), "config",
                    "user.name", "guard test"], check=True)
    (destination / "README").write_text("control checkout fixture\n")
    subprocess.run(["git", "-C", str(destination), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(destination), "commit", "-q",
                    "-m", "fixture"], check=True)


class GuardSourceIdentityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.deployed = _copy_fixture(self.root / "deployed")
        self.control = _copy_fixture(self.root / "control")
        _git_repo(self.control)

    def test_reviewed_manifest_matches_the_canonical_source_artifact(self):
        self.assertEqual((self.deployed / guard_source.IDENTITY_NAME).read_bytes(),
                         CANONICAL_MANIFEST.read_bytes())
        self.assertEqual(guard_source.digest(CANONICAL_MANIFEST),
                         guard_source.IDENTITY_SHA256)

    def test_exact_digest_chain_covers_every_runtime_module(self):
        manifest = json.loads((self.deployed / guard_source.IDENTITY_NAME).read_bytes())
        self.assertEqual(manifest["schema"], guard_source.IDENTITY_SCHEMA)
        self.assertEqual(manifest["source_commit"], guard_source.DEPLOYED_HEAD)
        self.assertEqual(manifest["sources"], dict(guard_source.EXPECTED))
        self.assertEqual(len(guard_source.EXPECTED), 19)
        for name in guard_source.WATCHDOG + guard_source.NATURAL_EXIT \
                + guard_source.MEMORY_GUARD + (guard_source.RESERVE_SOURCE,):
            self.assertIn(name, guard_source.EXPECTED)

    def test_no_self_referential_commit_pin(self):
        self.assertNotEqual(guard_source.DEPLOYED_HEAD,
                            "07231fa1a06b2cdd7d43d9896935f5050b7df4f5")
        self.assertFalse(hasattr(guard_source, "CONTROL_HEAD"))
        self.assertEqual(guard_source.digest(CANONICAL_RETRY),
                         guard_source.CONTROL_RETRY_SHA256)

    def test_fixture_verification_returns_reviewed_digest_map(self):
        self.assertEqual(guard_source.verify(root=self.deployed),
                         dict(guard_source.EXPECTED))

    def test_missing_git_never_skips_deployment_identity(self):
        # Before the fix a COPY-built tree with no .git skipped the HEAD check
        # and passed on bytes alone. Correct bytes with no reviewed manifest
        # must now fail closed.
        (self.deployed / guard_source.IDENTITY_NAME).unlink()
        with self.assertRaisesRegex(ValueError, "identity manifest missing"):
            guard_source.verify(root=self.deployed)

    def test_manifest_bytes_are_pinned(self):
        path = self.deployed / guard_source.IDENTITY_NAME
        blob = json.loads(path.read_bytes())
        blob["source_commit"] = "0" * 40
        path.write_text(json.dumps(blob, sort_keys=True,
                                   separators=(",", ":")) + "\n")
        with self.assertRaisesRegex(ValueError, "identity manifest drift"):
            guard_source.verify(root=self.deployed)

    def test_manifest_digest_chain_is_pinned(self):
        path = self.deployed / guard_source.IDENTITY_NAME
        blob = json.loads(path.read_bytes())
        blob["sources"]["benchmarks/fail_closed_guard/watchdog.py"] = "0" * 64
        path.write_text(json.dumps(blob, sort_keys=True,
                                   separators=(",", ":")) + "\n")
        with self.assertRaisesRegex(ValueError, "identity manifest drift"):
            guard_source.verify(root=self.deployed)

    def test_deployment_byte_drift_fails_closed(self):
        target = self.deployed / "benchmarks/fail_closed_guard/copy_overlay.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "deployed PX guard source drift"):
            guard_source.verify(root=self.deployed)

    def test_both_service_identities_are_verified(self):
        found = guard_source.verify(root=self.deployed,
                                    control_root=self.control)
        self.assertEqual(found, dict(guard_source.EXPECTED))

    def test_control_git_missing_fails_closed(self):
        shutil.rmtree(self.control / ".git")
        with self.assertRaisesRegex(ValueError, "control checkout git identity missing"):
            guard_source.verify(root=self.deployed, control_root=self.control)

    def test_control_retry_source_drift_fails_closed(self):
        target = self.control / guard_source.CONTROL_RETRY_SOURCE
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "control PX retry source drift"):
            guard_source.verify(root=self.deployed, control_root=self.control)

    def test_control_modules_must_be_byte_identical(self):
        target = self.control / "benchmarks/fail_closed_guard/watchdog.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        with self.assertRaisesRegex(ValueError, "control PX guard source drift"):
            guard_source.verify(root=self.deployed, control_root=self.control)

    def test_production_mode_uses_both_pinned_roots(self):
        with patch.object(guard_source, "CONTROL_ROOT", self.control), \
                patch.object(guard_source, "DEPLOYED_ROOT", self.deployed):
            self.assertEqual(guard_source.verify(), dict(guard_source.EXPECTED))

    def test_production_mode_fails_closed_when_control_git_absent(self):
        shutil.rmtree(self.control / ".git")
        with patch.object(guard_source, "CONTROL_ROOT", self.control), \
                patch.object(guard_source, "DEPLOYED_ROOT", self.deployed):
            with self.assertRaisesRegex(ValueError, "control checkout git identity missing"):
                guard_source.verify()


class NormalSchedulingPreservedTests(unittest.TestCase):
    def test_guard_rebinding_does_not_change_normal_scheduling(self):
        """The guard pins are evidence only; PX plan identity is untouched."""
        self.assertEqual(sched.MAX_INFRA_ATTEMPTS, 2)
        self.assertEqual(sched.RECEIPT_SCHEMA, "ivanka.px.case.receipt.v1")
        self.assertTrue(callable(sched.build_plan))
        self.assertTrue(callable(sched.resume))
        # Authorizing one arm never mutates the scheduler's normal two-attempt
        # budget or its canonical receipt identity.
        from assembler_bench import px_retry_authorization as authz
        self.assertEqual(authz.EXTRA_ATTEMPT, sched.MAX_INFRA_ATTEMPTS + 1)
        self.assertEqual(authz.GUARD_COMMIT,
                         "165a86b38c0bc29b4f8e0281a39ca59b909a6563")


if __name__ == "__main__":
    unittest.main()
