"""Orphaned Buildah storage is reclaimed only after a failed PX build."""
import unittest
from unittest.mock import patch

from assembler_bench.exploratory_runtime.cleanup import (
    ROOT,
    clean_stopped_build,
)

ENV = {"CONTAINERS_STORAGE_CONF": str(ROOT / "storage.conf")}


class TestGuardedBuildahCleanup(unittest.TestCase):
    def test_cleans_only_signed_external_storage_containers(self):
        calls = []

        def stub(argv, env):
            calls.append(tuple(argv))
            action = tuple(argv[1:3])
            if argv[1] == "info":
                return "/workspace/ivanka-exploratory-podman-20261121/store"
            if action == ("ps", "-a") and "--external" not in argv:
                return ""
            if action == ("ps", "-a") and "{{.ID}}|{{.Names}}|{{.Status}}" in argv:
                return "11b70fcd8942|debian-working-container|Storage"
            if action == ("ps", "-a"):
                return ""
            if argv[1] == "rm":
                self.assertEqual(argv, ["podman", "rm", "-f", "11b70fcd8942"])
                return "11b70fcd8942"
            if argv[1] == "unshare":
                return "123456\t/workspace/ivanka-exploratory-podman-20261121"
            self.fail("unexpected PX cleanup command " + repr(argv))

        with patch("assembler_bench.exploratory_runtime.cleanup.command",
                   side_effect=stub):
            result = clean_stopped_build(ROOT, ENV)
        self.assertEqual(result["dedicated_store_bytes_after_cleanup"], 123456)
        self.assertEqual(len(result["removed_external_build_containers"]), 1)
        self.assertEqual(sum(x[1] == "rm" for x in calls), 1)

    def test_wrong_store_never_attempts_removal(self):
        with (
            patch("assembler_bench.exploratory_runtime.cleanup.command",
                  return_value="/workspace/wrong-store"),
            self.assertRaisesRegex(ValueError, "graphroot"),
        ):
            clean_stopped_build(ROOT, ENV)
        with self.assertRaisesRegex(ValueError, "dedicated"):
            clean_stopped_build("/workspace/not-exploratory", ENV)

    def test_unrecognized_external_container_fails_closed(self):
        def stub(argv, env):
            if argv[1] == "info":
                return "/workspace/ivanka-exploratory-podman-20261121/store"
            if argv[1] == "ps" and "--external" in argv:
                return "11b70fcd8942|a-live-service|Storage"
            if argv[1] == "ps":
                return ""
            self.fail("cleanup must not run on unrecognized container")

        with (
            patch("assembler_bench.exploratory_runtime.cleanup.command",
                  side_effect=stub),
            self.assertRaisesRegex(RuntimeError, "unrecognized"),
        ):
            clean_stopped_build(ROOT, ENV)
