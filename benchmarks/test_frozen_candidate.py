"""Candidate substitution may touch only Ivanka's binary, not MiCall."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.frozen_candidate import (
    DESTINATION,
    IVANKA_IMAGE,
    candidate_mount,
    permitted_image_and_mount,
)


class RustOnlyCandidateTests(unittest.TestCase):
    def test_only_one_readonly_rust_binary_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "ivanka"
            p.write_bytes(b"Rust candidate fixture")
            p.chmod(0o755)
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            with patch("assembler_bench.frozen_candidate.SOURCE_ROOT", Path(tmp)):
                image, mount = permitted_image_and_mount(p, digest)
                self.assertEqual(image, IVANKA_IMAGE)
                self.assertEqual(mount[0], "--mount")
                self.assertIn("dst=" + DESTINATION + ",ro", mount[1])
                self.assertNotIn("/micall/", mount[1])
                with self.assertRaisesRegex(ValueError, "SHA256 changed"):
                    candidate_mount(p, "0"*64)

    def test_non_executable_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "ivanka"
            p.write_bytes(b"candidate")
            p.chmod(0o644)
            with patch("assembler_bench.frozen_candidate.SOURCE_ROOT", Path(tmp)):
                with self.assertRaisesRegex(ValueError, "executable"):
                    candidate_mount(p, hashlib.sha256(p.read_bytes()).hexdigest())
                p.chmod(0o755)
                q = Path(tmp) / "linked-ivanka"
                q.symlink_to(p)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    candidate_mount(q, hashlib.sha256(p.read_bytes()).hexdigest())
