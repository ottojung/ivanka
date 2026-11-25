"""Storage admission is conservative and requires source-pinned scope."""
import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_policy import checked
from assembler_bench.exploratory_space import (
    PROJECT_ROOT,
    PROJECT_TMP,
    ROOTLESS_STORE,
    admit,
    allocated,
    allocated_optional,
    disk_measure_command,
    initial,
    px_temp_dir,
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
        expected = ["podman", "unshare", "du", "-sxB1", "--",
                    str(ROOTLESS_STORE)]
        self.assertEqual(disk_measure_command(ROOTLESS_STORE), expected)
        # Buildah's transient mount under project/tmp is not readable by host
        # du, and must not count a second virtual copy of frozen MiCall.
        for target in (PROJECT_ROOT, PROJECT_TMP):
            self.assertEqual(disk_measure_command(target),
                             ["podman", "unshare", "du", "-sxB1", "--",
                              str(target)])
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
        with (
            self.assertRaises(subprocess.CalledProcessError),
            patch("assembler_bench.exploratory_space.Path.is_dir",
                  return_value=True),
            patch("assembler_bench.exploratory_space.subprocess.run",
                  side_effect=subprocess.CalledProcessError(
                      1, ["podman", "unshare"], stderr="permission denied")),
        ):
            allocated(ROOTLESS_STORE)

    def test_unreadable_project_mounts_never_fall_back_to_host_du(self):
        for target in (PROJECT_ROOT, PROJECT_TMP):
            with (self.subTest(target=target),
                  self.assertRaises(subprocess.CalledProcessError),
                  patch("assembler_bench.exploratory_space.Path.is_dir",
                        return_value=True),
                  patch("assembler_bench.exploratory_space.subprocess.run",
                        side_effect=subprocess.CalledProcessError(
                            1, ["podman", "unshare", "du"],
                            stderr="permission denied")) as run):
                allocated(target)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][0:2],
                                 ["podman", "unshare"])

    def test_live_buildah_temporary_enoent_retries_complete_scan(self):
        stderr = ("du: fts_read failed: " + str(ROOTLESS_STORE)
                  + "/store/overlay/tempdirs/temp-dir-409150334/0-addition:"
                  + " No such file or directory\n")
        transient = subprocess.CalledProcessError(
            1, ["podman", "unshare", "du"], stderr=stderr)
        result = subprocess.CompletedProcess(
            ["podman", "unshare", "du"], 0, "234567\t/store\n", "")
        with (patch("assembler_bench.exploratory_space.Path.is_dir",
                    return_value=True),
              patch("assembler_bench.exploratory_space.subprocess.run",
                    side_effect=[transient, result]) as run,
              patch("assembler_bench.exploratory_space.time.sleep") as sleep):
            self.assertEqual(allocated(ROOTLESS_STORE), 234567)
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(0.1)

    def test_dpkg_overlay_rename_race_retries_full_disk_scan(self):
        layer = "0ac33a4f8c53afab54ce1b47fec6d325359d10d0d76f59af43411d7109722abc"
        prefix = str(ROOTLESS_STORE) + "/store/overlay/" + layer + "/diff/"
        stderr = "".join(
            "du: cannot access '" + prefix + suffix
            + "': No such file or directory\n"
            for suffix in ("usr/include/openmpi/opal/version.h.dpkg-new",
                           "usr/include/openmpi.dpkg-new")
        )
        transient = subprocess.CalledProcessError(
            1, ["podman", "unshare", "du"], stderr=stderr)
        complete = subprocess.CompletedProcess(
            ["podman", "unshare", "du"], 0, "5788692480\t/store\n", "")
        with (patch("assembler_bench.exploratory_space.Path.is_dir",
                    return_value=True),
              patch("assembler_bench.exploratory_space.subprocess.run",
                    side_effect=[transient, complete]) as run,
              patch("assembler_bench.exploratory_space.time.sleep") as sleep):
            self.assertEqual(allocated(ROOTLESS_STORE), 5788692480)
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(0.1)

    def test_dpkg_rename_race_must_stay_private_and_exact(self):
        layer = "a" * 64
        root = str(ROOTLESS_STORE) + "/store/overlay/" + layer + "/diff/"
        for stderr in (
            "du: cannot access '" + root + "foo.dpkg-old': No such file or directory\n",
            "du: cannot access '" + root + "foo.dpkg-new': Permission denied\n",
            "du: cannot access '/tmp/foo.dpkg-new': No such file or directory\n",
            "du: cannot access '" + root + "foo.dpkg-new': No such file or directory\n"
            "du: cannot access '/tmp/bar': Permission denied\n",
        ):
            with (self.subTest(stderr=stderr),
                  self.assertRaises(subprocess.CalledProcessError),
                  patch("assembler_bench.exploratory_space.Path.is_dir",
                        return_value=True),
                  patch("assembler_bench.exploratory_space.subprocess.run",
                        side_effect=subprocess.CalledProcessError(
                            1, ["podman", "unshare", "du"], stderr=stderr)) as run):
                allocated(ROOTLESS_STORE)
                self.assertEqual(run.call_count, 1)

    def test_dpkg_rename_race_exhausts_three_checks_then_fails(self):
        layer = "c" * 64
        stderr = ("du: cannot access '" + str(ROOTLESS_STORE)
                  + "/store/overlay/" + layer + "/diff/version.h.dpkg-new':"
                  " No such file or directory\n")
        with (self.assertRaises(subprocess.CalledProcessError),
              patch("assembler_bench.exploratory_space.Path.is_dir",
                    return_value=True),
              patch("assembler_bench.exploratory_space.subprocess.run",
                    side_effect=subprocess.CalledProcessError(
                        1, ["podman", "unshare", "du"], stderr=stderr)) as run):
            allocated(ROOTLESS_STORE)
            self.assertEqual(run.call_count, 3)

    def test_disappearing_podman_overlay_on_auto_remove_retries(self):
        stderr = ("du: fts_read failed: " + str(ROOTLESS_STORE)
                  + "/store/overlay: No such file or directory\n")
        transient = subprocess.CalledProcessError(
            1, ["podman", "unshare", "du"], stderr=stderr)
        valid = subprocess.CompletedProcess(
            ["podman", "unshare", "du"], 0, "234567\t/store\n", "")
        with (patch("assembler_bench.exploratory_space.Path.is_dir",
                    return_value=True),
              patch("assembler_bench.exploratory_space.subprocess.run",
                    side_effect=[transient, valid]) as run,
              patch("assembler_bench.exploratory_space.time.sleep") as sleep):
            self.assertEqual(allocated(ROOTLESS_STORE), 234567)
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(0.1)

    def test_repeated_live_temp_races_fail_closed(self):
        stderr = ("du: fts_read failed: " + str(ROOTLESS_STORE)
                  + "/store/overlay/tempdirs/temp-dir-40/0-addition:"
                  + " No such file or directory\n")
        with (self.assertRaises(subprocess.CalledProcessError),
              patch("assembler_bench.exploratory_space.Path.is_dir",
                    return_value=True),
              patch("assembler_bench.exploratory_space.subprocess.run",
                    side_effect=subprocess.CalledProcessError(
                        1, ["podman", "unshare", "du"], stderr=stderr)) as run):
            allocated(ROOTLESS_STORE)
            self.assertEqual(run.call_count, 3)

    def test_unrelated_enoent_does_not_get_retried(self):
        stderr = ("du: fts_read failed: /workspace/unrelated/tmp:"
                  " No such file or directory\n")
        with (self.assertRaises(subprocess.CalledProcessError),
              patch("assembler_bench.exploratory_space.Path.is_dir",
                    return_value=True),
              patch("assembler_bench.exploratory_space.subprocess.run",
                    side_effect=subprocess.CalledProcessError(
                        1, ["podman", "unshare", "du"], stderr=stderr)) as run):
            allocated(ROOTLESS_STORE)
            self.assertEqual(run.call_count, 1)

    def test_small_pilot_admitted(self):
        self.assertEqual(self.check(1024)["admitted_reservation_bytes"], 1024)

    def test_temporary_files_are_counted_once_in_the_incremental_budget(self):
        temp = px_temp_dir(self.exp)
        temp.mkdir()
        sizes = {temp.resolve(): 10_000, self.exp.resolve(): 30_000}
        with patch("assembler_bench.exploratory_space.allocated",
                   side_effect=lambda p: sizes.get(Path(p).resolve(), 0)):
            result = self.check(1024)
        self.assertEqual(result["temp_bytes"], 10_000)
        self.assertEqual(result["retained_bytes"], 20_000)
        self.assertEqual(result["incremental_bytes"], 30_000)

    def test_large_incremental_usage_is_admitted_without_a_ceiling(self):
        temp = px_temp_dir(self.exp)
        temp.mkdir()
        huge = 200 * 1024**3
        sizes = {temp.resolve(): huge, self.exp.resolve(): huge}
        with patch("assembler_bench.exploratory_space.allocated",
                   side_effect=lambda p: sizes.get(Path(p).resolve(), 0)):
            result = self.check(1024)
        self.assertEqual(result["temp_bytes"], huge)
        self.assertEqual(result["retained_bytes"], 0)
        self.assertEqual(result["incremental_bytes"], huge)
        self.assertEqual(result["admitted_reservation_bytes"], 1024)

    def test_missing_temporary_directory_counts_as_zero(self):
        self.assertEqual(allocated_optional(px_temp_dir(self.exp)), 0)

    def test_large_arm_reservation_is_admitted_without_a_ceiling(self):
        # 21 GiB was the old ceiling; only the 32 GiB shared reserve still binds.
        result = self.check(21 * 1024**3)
        self.assertEqual(result["admitted_reservation_bytes"], 21 * 1024**3)

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
