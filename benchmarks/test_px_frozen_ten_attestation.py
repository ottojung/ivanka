"""Fail-closed checks for the ten frozen-8458f9e5 PX attestation verifier."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.verify_px_frozen_ten_attestation import (
    _scoped,
    sha256_bytes,
    verify,
    verify_native,
)


def _manifest(tools):
    return {"frozen_upstream_master": "8458f9e5d34c39a6694b1fb6a40e055d7ce89553",
            "frozen_seven_manifest_sha256": "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f",
            "tools": tools}


class TestFrozenTenAttestation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_raw_digest_keeps_trailing_newline(self):
        self.assertEqual(sha256_bytes(b"abc\n"),
                         hashlib.sha256(b"abc\n").hexdigest())
        self.assertNotEqual(sha256_bytes(b"abc\n"),
                            hashlib.sha256(b"abc").hexdigest())

    def test_native_digest_match_and_mismatch(self):
        (self.root / "tool").write_bytes(b"native-binary\n")
        expected = hashlib.sha256(b"native-binary\n").hexdigest()
        manifest = _manifest({"skesa": {"native_artifact": "tool",
                                        "native_sha256": expected}})
        result = verify_native(manifest, self.root)
        self.assertTrue(result[0]["ok"])
        manifest["tools"]["skesa"]["native_sha256"] = "0" * 64
        self.assertFalse(verify_native(manifest, self.root)[0]["ok"])

    def test_missing_or_unreadable_artifact_fails_closed(self):
        manifest = _manifest({"skesa": {"native_artifact": "absent",
                                        "native_sha256": "0" * 64}})
        result = verify_native(manifest, self.root)
        self.assertFalse(result[0]["ok"])
        self.assertIn("FileNotFoundError", result[0]["reason"])

    def test_symlink_and_escape_rejected(self):
        (self.root / "tool").write_bytes(b"real\n")
        (self.root / "link").symlink_to(self.root / "tool")
        with self.assertRaises(ValueError):
            _scoped(self.root, "link")
        with self.assertRaises(ValueError):
            _scoped(self.root, "../tool")

    def test_manifest_must_cover_exactly_ten_tools(self):
        with self.assertRaisesRegex(ValueError, "exactly ten"):
            verify(_manifest({"skesa": {}}), self.root, self.root)

    def test_bad_adapter_parent_fails_closed(self):
        manifest = _manifest({"skesa": {
            "adapter_commit": "a" * 40,
            "adapter_commands_sha256": "0" * 64,
            "adapter_denovo_sha256": "0" * 64,
        }})
        from assembler_bench.verify_px_frozen_ten_attestation import verify_adapters
        with patch("assembler_bench.verify_px_frozen_ten_attestation._git",
                   return_value=b"eeca0381808a6e9ba5ef791c80238a0e2940abb0\n"):
            result = verify_adapters(manifest, self.root)
        self.assertFalse(result[0]["ok"])
        self.assertIn("parent", result[0]["reason"])

    def test_real_manifest_is_complete(self):
        path = (Path(__file__).parent / "assembler_bench" /
                "px_frozen_ten_attestation.json")
        data = json.loads(path.read_text())
        self.assertEqual(len(data["tools"]), 10)
        for tool, row in data["tools"].items():
            self.assertEqual(len(row["adapter_commit"]), 40, tool)
            self.assertEqual(row["adapter_parent"],
                             data["frozen_upstream_master"], tool)
            self.assertEqual(len(row["native_sha256"]), 64, tool)


if __name__ == "__main__":
    unittest.main()
