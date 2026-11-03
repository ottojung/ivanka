"""Operational Podman graph-root identity verification without Podman."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from podman_store_guard import verify_expected_store


class StoreGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.seen = []

    def fake(self, command, **kwargs):
        self.seen.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, f"btrfs\t{self.root}\n", "")

    def test_optional_check_does_not_call_podman(self):
        self.assertIsNone(verify_expected_store(None, None, self.fake))
        self.assertFalse(self.seen)

    def test_correct_btrfs_store_and_exact_command(self):
        result = verify_expected_store("btrfs", str(self.root), self.fake)
        self.assertEqual(result, {
            "driver": "btrfs", "graph_root": str(self.root)})
        command, args = self.seen[0]
        self.assertEqual(command[:2], ["podman", "info"])
        self.assertEqual(args["timeout"], 90)
        self.assertTrue(args["check"])
        self.assertTrue(args["capture_output"])

    def test_driver_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_expected_store("overlay", str(self.root), self.fake)

    def test_root_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_expected_store("btrfs", other, self.fake)

    def test_incomplete_or_relative_expectation_rejected(self):
        for driver, root in ((None, str(self.root)),
                             ("btrfs", None), ("btrfs", "relative")):
            with self.subTest(driver=driver, root=root):
                with self.assertRaises(ValueError):
                    verify_expected_store(driver, root, self.fake)
        self.assertEqual(self.seen, [])

    def test_missing_graph_root_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "graph root unavailable"):
            verify_expected_store("btrfs", str(self.root / "does-not-exist"), self.fake)
        self.assertEqual(self.seen, [])

    def test_ambiguous_output_rejected(self):
        def ambiguous(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "btrfs\n", "")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            verify_expected_store("btrfs", str(self.root), ambiguous)

    def test_podman_unavailable_fails_closed(self):
        def missing(cmd, **kwargs):
            raise FileNotFoundError("podman")
        with self.assertRaisesRegex(ValueError, "Cannot authenticate"):
            verify_expected_store("btrfs", str(self.root), missing)


if __name__ == "__main__":
    unittest.main()
