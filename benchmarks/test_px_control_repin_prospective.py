"""Hermetic proof of the prospective PX control-source repin.

Source-only: temporary checkouts only. The live OLD control root is never read,
patched or retired; verification here uses the reviewed fixture bytes.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import px_guard_source as gs

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "assembler_bench" / gs.CONTROL_IDENTITY_NAME
GUARD_FIXTURE = ROOT / "benchmarks" / "fixtures" / "px_guard_pins"
CONTROL_FIXTURE = ROOT / "benchmarks" / "fixtures" / "px_control_pins"
SUPERVISOR = "benchmarks/assembler_bench/px_supervisor.py"
EXPECTED_SUPERVISOR_SHA = "cc55d4000d296d69484ba83ecf475491e2fbe7840f59e89a407819a55f56d177"


def _overlay(destination, source_root):
    for source in source_root.rglob("*"):
        if source.is_file():
            target = destination / source.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


class ProspectiveControlRepinTests(unittest.TestCase):
    def _checkout(self, root):
        _overlay(root, GUARD_FIXTURE)
        identity = json.loads(MANIFEST.read_bytes())
        for name in identity["sources"]:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        _overlay(root, CONTROL_FIXTURE)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "t@e"],
                       check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "t"],
                       check=True)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "fixture"],
                       check=True)
        return identity

    def test_manifest_pins_exact_reviewed_source_bytes(self):
        identity = json.loads(MANIFEST.read_bytes())
        self.assertEqual(gs.digest(MANIFEST), gs.CONTROL_IDENTITY_SHA256)
        for name, digest in identity["sources"].items():
            self.assertEqual(gs.digest(ROOT / name), digest, name)
        self.assertEqual(identity["sources"][SUPERVISOR],
                         EXPECTED_SUPERVISOR_SHA)
        gs_canon = MANIFEST.parent / "px_guard_source.py"
        canon = gs_canon.read_text().replace(
            f'CONTROL_GUARD_SOURCE_SHA256 = "{gs.CONTROL_GUARD_SOURCE_SHA256}"',
            'CONTROL_GUARD_SOURCE_SHA256 = "' + "0" * 64 + '"')
        import hashlib
        self.assertEqual(hashlib.sha256(canon.encode()).hexdigest(),
                         gs.CONTROL_GUARD_SOURCE_SHA256)

    def test_verify_control_on_prospective_root_without_live_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            control = temp / "prospective-control"
            identity = self._checkout(control)
            # No host control checkout may be consulted by this proof.
            with patch.object(gs, "CONTROL_ROOT", temp / "absent-live-root"):
                result = gs.verify_control(control, identity_root=ROOT)
            self.assertEqual(result["identity_sha256"],
                             gs.CONTROL_IDENTITY_SHA256)
            self.assertFalse(result["head_pinned"])
            self.assertEqual(result["sources"][SUPERVISOR],
                             EXPECTED_SUPERVISOR_SHA)
            self.assertEqual(set(result["sources"]),
                             set(identity["sources"]) | set(gs.EXPECTED) | {
                                 "benchmarks/assembler_bench/px_guard_source.py"})

    def test_prospective_source_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            control = temp / "prospective-control"
            self._checkout(control)
            (control / SUPERVISOR).write_bytes(
                (control / SUPERVISOR).read_bytes() + b"\n# drift\n")
            with patch.object(gs, "CONTROL_ROOT", temp / "absent-live-root"):
                with self.assertRaisesRegex(ValueError,
                                            "control PX source drift"):
                    gs.verify_control(control, identity_root=ROOT)


if __name__ == "__main__":
    unittest.main()
