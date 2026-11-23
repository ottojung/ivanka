"""PX pilot CID provenance and exact-container cleanup tests."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_runtime import pilot


class TestPilotIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = {"CONTAINERS_STORAGE_CONF": str(self.root / "storage.conf")}
        p = patch.object(pilot, "ROOT", self.root)
        p.start()
        self.addCleanup(p.stop)

    def test_inject_exact_cidfile_in_foreground_podman(self):
        cmd, cid = pilot.bind_pilot(
            self.root, "pilot", ["podman", "run", "--rm", "test-image"], "x1")
        self.assertEqual(cmd[:4], ["podman", "run", "--cidfile", str(cid)])
        self.assertEqual(cmd[4:], ["test-image"])
        self.assertNotIn("--rm", cmd)
        self.assertEqual(cid.parent, self.root)

    def test_refuse_untracked_or_supplied_cidfile(self):
        for argv in (["bash", "-c", "podman run image"],
                     ["podman", "run", "--cidfile=/tmp/stolen", "image"]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                pilot.bind_pilot(self.root, "pilot", argv, "x")

    def test_reap_only_issued_container(self):
        cid = "a" * 64
        other = "b" * 64
        path = self.root / "pilot-x.cid"
        path.write_text(cid)
        calls = []
        def command(argv, env):
            calls.append(list(argv))
            if argv[1] == "info":
                return "/isolated/graphroot"
            if argv[1] == "ps":
                if len([x for x in calls if x[1] == "ps"]) == 1:
                    return cid + "\n" + other
                return other
            self.fail("unexpected command")
        with (patch.object(pilot, "STORE", "/isolated/graphroot"),
              patch.object(pilot, "command", side_effect=command),
              patch.object(pilot.subprocess, "run") as run):
            result = pilot.stop_pilot(self.root, self.env, path)
        self.assertTrue(result["container_removed"])
        self.assertEqual(result["pilot_container_id"], cid)
        self.assertEqual(run.call_args.args[0], ["podman", "rm", "-f", cid])
        self.assertNotIn(other, str(run.call_args))

    def test_missing_cid_and_wrong_store_fail_closed(self):
        path = self.root / "pilot-x.cid"
        with (patch.object(pilot, "command", return_value="/isolated/graphroot"),
              self.assertRaisesRegex(ValueError, "graphroot")):
            pilot.stop_pilot(self.root, self.env, path)
        with (patch.object(pilot, "STORE", "/isolated/graphroot"),
              patch.object(pilot, "command", return_value="/isolated/graphroot"),
              self.assertRaisesRegex(RuntimeError, "CID")):
            pilot.stop_pilot(self.root, self.env, path)

    def test_unremoved_container_fails_closed(self):
        path = self.root / "pilot-x.cid"
        path.write_text("c" * 64)
        def command(argv, env):
            return "/isolated/graphroot" if argv[1] == "info" else "c" * 64
        with (patch.object(pilot, "STORE", "/isolated/graphroot"),
              patch.object(pilot, "command", side_effect=command),
              patch.object(pilot.subprocess, "run",
                           return_value=subprocess.CompletedProcess([], 0)),
              self.assertRaisesRegex(RuntimeError, "survived")):
            pilot.stop_pilot(self.root, self.env, path)


if __name__ == "__main__":
    unittest.main()
