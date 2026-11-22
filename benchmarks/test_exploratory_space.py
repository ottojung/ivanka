"""Storage admission is conservative and requires source-pinned scope."""
import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_policy import checked
from assembler_bench.exploratory_space import (
    ROOTLESS_STORE, admit, allocated, disk_measure_command, initial,
)

PATH = Path(__file__).parent / "assembler_bench/exploratory_candidates.json"


class TestExploratorySpace(unittest.TestCase):
    def setUp(self):
        self.r = copy.deepcopy(checked(PATH))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "images"
        self.work = self.root / "workspace"
        self.exp = self.root / "experiment"
        for p in (self.store, self.work, self.exp):
            p.mkdir()
        self.r["policy"]["dedicated_image_store_root"] = str(self.store.resolve())
        self.large = 100 * 1024**3
        with patch("assembler_bench.exploratory_space.available", return_value=self.large):
            self.base = initial(self.exp, self.store, self.work, self.r)

    def check(self, reserve, free=None):
        with patch("assembler_bench.exploratory_space.available",
                   return_value=self.large if free is None else free):
            return admit(self.r, self.base, self.exp, self.store, self.work, reserve)

    def test_rootless_overlay_uses_podman_userns_not_partial_host_du(self):
        expected = ["podman", "unshare", "du", "-sB1", "--",
                    str(ROOTLESS_STORE)]
        self.assertEqual(disk_measure_command(ROOTLESS_STORE), expected)
        self.assertEqual(disk_measure_command(self.store.resolve()),
                         ["du", "-sB1", "--", str(self.store.resolve())])
        result = subprocess.CompletedProcess(expected, 0,
                                             "123456\t/store\n", "")
        with patch("assembler_bench.exploratory_space.Path.is_dir",
                   return_value=True), patch(
                    "assembler_bench.exploratory_space.subprocess.run",
                    return_value=result) as run:
            self.assertEqual(allocated(ROOTLESS_STORE), 123456)
            self.assertEqual(run.call_args.args[0], expected)
            self.assertTrue(run.call_args.kwargs["check"])

    def test_rootless_accounting_fails_closed_when_userns_cannot_read(self):
        with patch("assembler_bench.exploratory_space.Path.is_dir",
                   return_value=True), patch(
                    "assembler_bench.exploratory_space.subprocess.run",
                    side_effect=subprocess.CalledProcessError(
                        1, ["podman", "unshare"], stderr="permission denied")):
            with self.assertRaises(subprocess.CalledProcessError):
                allocated(ROOTLESS_STORE)

    def test_small_pilot_admitted(self):
        self.assertEqual(self.check(1024)["admitted_reservation_bytes"], 1024)

    def test_stop_when_reserve_breached(self):
        with self.assertRaisesRegex(ValueError, "disk budget"):
            self.check(9 * 1024**3)

    def test_stop_when_free_space_too_low(self):
        with self.assertRaisesRegex(ValueError, "reserve"):
            self.check(3 * 1024**3, free=34 * 1024**3)

    def test_stop_when_another_worker_active(self):
        self.base["active_job"] = "pilot-skesa"
        with self.assertRaises(ValueError):
            self.check(1024)

    def test_prevent_relocated_storage_and_nonempty_start(self):
        old = self.base["image_store"]
        self.base["image_store"] = str(self.work)
        with self.assertRaises(ValueError):
            self.check(1024)
        self.base["image_store"] = old
        (self.exp / "unexpected").touch()
        with self.assertRaises(ValueError):
            initial(self.exp, self.store, self.work, self.r)


if __name__ == "__main__":
    unittest.main()
