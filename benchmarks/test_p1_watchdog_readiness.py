"""Deterministic source-only tests for the s6 watchdog readiness probe.

No live service, ALIVE record, PX lock/journal, STOP, lease or Podman is
touched. The s6 layout and watchdog code are simulated in a temp directory.
"""
import tempfile
import unittest
from pathlib import Path

from expanded import p1_watchdog_readiness as w


class WatchdogReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scan = self.root / "service"
        self.services = self.root / "legacy-services"
        self.scan.mkdir()
        self.services.mkdir()
        self.svc = self.services / w.SERVICE_NAME
        self.svc.mkdir()
        self.code = self.root / "code"
        cli = self.code / w.WATCHDOG_CLI_REL
        cli.parent.mkdir(parents=True)
        cli.write_text("#!/usr/bin/env python3\n# reviewed watchdog CLI\n")
        self.cli_sha = w._sha256(cli)
        self.px_root = self.root / "px-worker"
        self.px_root.mkdir()
        (self.px_root / ".global-worker.lock").write_text("")
        (self.px_root / ".worker-lease.jsonl").write_text("")
        self.expected = {
            "WATCHDOG_ROOT": str(self.px_root),
            "WATCHDOG_CODE": str(self.code),
            "WATCHDOG_STORAGE_CONF": "/workspace/ivanka-exploratory-ten-20261121/storage.conf",
            "WATCHDOG_GRAPHROOT": "/workspace/ivanka-exploratory-podman-20261121/store",
            "watchdog_cli_sha256": self.cli_sha,
            "armed": True,
        }

    def install(self, *, armed="1", graphroot=None, executable=True,
                symlink=True, head_pin=True):
        exports = [
            "export PATH=/usr/bin:/bin",
            "export WATCHDOG_ROOT=%s" % self.expected["WATCHDOG_ROOT"],
            "export WATCHDOG_CODE=%s" % self.expected["WATCHDOG_CODE"],
            "export WATCHDOG_STORAGE_CONF=%s" % self.expected["WATCHDOG_STORAGE_CONF"],
            "export WATCHDOG_GRAPHROOT=%s" % (
                graphroot or self.expected["WATCHDOG_GRAPHROOT"]),
            "export WATCHDOG_ARMED=%s" % armed,
        ]
        if head_pin:
            exports.append('test "$(git -C "$WATCHDOG_CODE" rev-parse HEAD)" = %s || exit 1' % w.WATCHDOG_SERVICE_HEAD)
        run = self.svc / "run"
        run.write_text("#!/bin/sh\n" + "\n".join(exports)
                       + "\nexec python3 -m %s --root x\n" % w.WATCHDOG_MODULE)
        mode = 0o755 if executable else 0o644
        run.chmod(mode)
        supervise = self.svc / "supervise"
        supervise.mkdir(exist_ok=True)
        (supervise / "status").write_bytes(b"x" * 35)
        if symlink:
            (self.scan / w.SERVICE_NAME).symlink_to(self.svc)

    def layout(self):
        return w.probe_service_layout(scan_dir=self.scan,
                                      services_dir=self.services,
                                      expected=self.expected)

    def test_parse_exports_handles_quotes_and_comments(self):
        got = w.parse_exports(
            'export WATCHDOG_ROOT="/px" # note\nexport WATCHDOG_ARMED=1\n')
        self.assertEqual(got["WATCHDOG_ROOT"], "/px")
        self.assertEqual(got["WATCHDOG_ARMED"], "1")

    def test_deployed_armed_service_layout_is_ready(self):
        self.install()
        result = self.layout()
        self.assertTrue(result["ready"], result)
        self.assertTrue(all(result["checks"].values()), result)
        self.assertTrue(result["checks"]["armed"])

    def test_missing_activation_symlink_fails_closed(self):
        self.install(symlink=False)
        self.assertFalse(self.layout()["ready"])
        self.assertIn("symlink", self.layout()["detail"]["reason"])

    def test_wrong_graphroot_pin_fails_closed(self):
        self.install(graphroot="/workspace/foreign/store")
        result = self.layout()
        self.assertFalse(result["ready"])
        self.assertIn("WATCHDOG_GRAPHROOT", result["detail"]["pin_mismatches"])

    def test_unarmed_service_is_not_ready(self):
        self.install(armed="0")
        result = self.layout()
        self.assertFalse(result["ready"])
        self.assertFalse(result["checks"]["armed"])

    def test_non_executable_run_fails_closed(self):
        self.install(executable=False)
        self.assertFalse(self.layout()["ready"])

    def test_wrong_watchdog_cli_hash_fails_closed(self):
        self.expected["watchdog_cli_sha256"] = "0" * 64
        self.install()
        result = self.layout()
        self.assertFalse(result["ready"])
        self.assertFalse(result["checks"]["code_cli_pinned"])

    def test_service_outside_s6_dir_fails_closed(self):
        self.install()
        other = self.root / "elsewhere" / w.SERVICE_NAME
        other.parent.mkdir()
        other.mkdir()
        link = self.scan / w.SERVICE_NAME
        link.unlink()
        link.symlink_to(other)
        self.assertFalse(self.layout()["ready"])

    def test_absent_alive_record_fails_closed(self):
        alive = w.probe_alive(root=self.px_root, graphroot=self.expected["WATCHDOG_GRAPHROOT"])
        self.assertFalse(alive["ready"])
        self.assertEqual(alive["reason"], "watchdog_unavailable")

    def test_combined_probe_not_ready_without_alive_record(self):
        self.install()
        verdict = w.probe(scan_dir=self.scan, services_dir=self.services,
                          expected=self.expected)
        self.assertTrue(verdict["service_layout"]["ready"])
        self.assertFalse(verdict["alive"]["ready"])
        self.assertFalse(verdict["ready"])
        self.assertFalse(verdict["kernel_enforcement"])

    def test_default_pins_bind_to_shared_px_boundary(self):
        exp = w.default_expected()
        self.assertEqual(exp["WATCHDOG_ROOT"], "/workspace/ivanka-exploratory-ten-20261121")
        self.assertEqual(exp["WATCHDOG_GRAPHROOT"],
                         "/workspace/ivanka-exploratory-podman-20261121/store")
        self.assertTrue(exp["armed"])

    def test_deployment_plan_is_source_only(self):
        plan = w.deployment_plan()
        self.assertEqual(plan["scan_dir"], "/run/service")
        self.assertEqual(plan["service_dir"],
                         "/run/s6/legacy-services/" + w.SERVICE_NAME)
        self.assertIn("WATCHDOG_ARMED", plan["run_script"]["exports"])
        self.assertIn("0 until operator authorization",
                      plan["run_script"]["exports"]["WATCHDOG_ARMED"])
        self.assertFalse(plan.get("armed", False))


if __name__ == "__main__":
    unittest.main()


class ServiceHeadPinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.scan = root / "service"
        self.services = root / "legacy"
        self.scan.mkdir()
        self.services.mkdir()
        self.svc = self.services / w.SERVICE_NAME
        self.svc.mkdir()
        self.code = root / "code"
        cli = self.code / w.WATCHDOG_CLI_REL
        cli.parent.mkdir(parents=True)
        cli.write_text("# reviewed cli\n")
        exp = w.default_expected()
        exp["watchdog_cli_sha256"] = w._sha256(cli)
        exp["WATCHDOG_CODE"] = str(self.code)
        exp["WATCHDOG_ROOT"] = str(root / "px")
        (root / "px").mkdir()
        self.exp = exp

    def install(self, head_pin=True):
        exports = [
            "export WATCHDOG_ROOT=%s" % self.exp["WATCHDOG_ROOT"],
            "export WATCHDOG_CODE=%s" % self.exp["WATCHDOG_CODE"],
            "export WATCHDOG_STORAGE_CONF=%s" % self.exp["WATCHDOG_STORAGE_CONF"],
            "export WATCHDOG_GRAPHROOT=%s" % self.exp["WATCHDOG_GRAPHROOT"],
            "export WATCHDOG_ARMED=1",
            "-m %s" % w.WATCHDOG_MODULE,
        ]
        if head_pin:
            exports.append('test "$(git -C "$WATCHDOG_CODE" rev-parse HEAD)" = %s || exit 1' % w.WATCHDOG_SERVICE_HEAD)
        run = self.svc / "run"
        run.write_text("#!/bin/sh\n" + "\n".join(exports) + "\n")
        run.chmod(0o755)
        (self.svc / "supervise").mkdir(exist_ok=True)
        (self.svc / "supervise" / "status").write_bytes(b"x" * 35)
        (self.scan / w.SERVICE_NAME).symlink_to(self.svc)

    def layout(self, head_pin=True):
        self.install(head_pin=head_pin)
        return w.probe_service_layout(scan_dir=self.scan,
                                      services_dir=self.services,
                                      expected=self.exp)

    def test_head_pinned_layout_ready(self):
        result = self.layout()
        self.assertTrue(result["checks"]["service_head_pinned"])
        self.assertTrue(result["ready"], result)

    def test_integrated_head_and_staged_cli_layout_ready(self):
        """The new s6 service head and exact staged watchdog CLI are accepted."""
        from assembler_bench import px_guard_source as guard_source
        from expanded import p1_bounded_pilot_runner as runner
        head = "b777f34976bb338ba3652239feffe99510326e44"
        self.assertEqual(w.WATCHDOG_SERVICE_HEAD, head)
        self.assertEqual(w.WATCHDOG_SERVICE_HEAD, guard_source.DEPLOYED_HEAD)
        self.assertEqual(w.WATCHDOG_SERVICE_HEAD, runner.REVIEWED_GUARD_HEAD)
        # Hermetic proof of the staged CLI bytes: the deployment identity pins
        # them, and the reviewed source in this checkout carries the same bytes.
        source_cli = Path(__file__).resolve().parents[1] / w.WATCHDOG_CLI_REL
        cli_sha = w._sha256(source_cli)
        self.assertEqual(cli_sha, w.WATCHDOG_CLI_SHA256)
        self.assertEqual(cli_sha, guard_source.DEPLOYED_EXPECTED[
            "benchmarks/fail_closed_guard/watchdog_cli.py"])
        (self.code / w.WATCHDOG_CLI_REL).write_bytes(source_cli.read_bytes())
        self.exp["watchdog_cli_sha256"] = cli_sha
        result = self.layout()
        self.assertTrue(result["checks"]["service_head_pinned"])
        self.assertTrue(result["checks"]["code_cli_pinned"])
        self.assertTrue(result["ready"], result)

    def test_old_service_head_fails_closed_under_new_expectation(self):
        """A live s6 run still pinned to 165a86b3 cannot satisfy readiness."""
        old_pin = "1e5104082c4366f30c93fd759e3f46307a142e63"
        self.assertNotEqual(old_pin, w.WATCHDOG_SERVICE_HEAD)
        self.install()
        run = self.svc / "run"
        run.write_text(run.read_text().replace(w.WATCHDOG_SERVICE_HEAD,
                                               old_pin))
        result = w.probe_service_layout(scan_dir=self.scan,
                                        services_dir=self.services,
                                        expected=self.exp)
        self.assertFalse(result["checks"]["service_head_pinned"])
        self.assertFalse(result["ready"])

    def test_missing_head_pin_fails_closed(self):
        result = self.layout(head_pin=False)
        self.assertFalse(result["checks"]["service_head_pinned"])
        self.assertFalse(result["ready"])
