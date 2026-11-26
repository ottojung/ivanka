"""Regression: a lagging launcher poll must not attest a pilot's natural exit.

A finished arm can have a launcher poll that still reports the process alive
while the bound CID is already removed. A ``/proc`` snapshot in that window
loses the bound PID and the old guard treated the missing PID as completion,
so a success receipt carried ``present=false / identity_lost`` instead of a
real natural-exit attestation. These tests pin the shared-guard contract:
completion is proved by exact-CID absence plus a real launcher result, with
teardown proof, and a live or unknown identity stays fail-closed.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.exploratory_runtime import monitor
from fail_closed_guard import binding, natural_exit
from fail_closed_guard.errors import GuardExceeded

CID = "c" * 64
OTHER_CID = "d" * 64
CONFIG = {"registry": "registry", "baseline": "baseline", "root": "root",
          "image_store": "store", "workspace": "workspace",
          "rss_bytes": 10**9, "wall_seconds": 100}


def record(pid, rss=1000):
    return {"pid": pid, "ppid": 1, "rss": rss, "starttime": 100,
            "pid_ns": 7, "cmdline_sha": "podman-run", "cgroup": "0::/"}


def teardown_proof(cid, removed=False):
    """Idempotent stop of an already-removed container, with inspect proof."""
    return {"cid": cid, "container_removed": removed,
            "fresh_absence_check": True, "method": "exact_cid_inspect",
            "absence_proof": {"observed_absent": True},
            "kernel_enforcement": False}


class LaggingLauncher:
    """Launcher whose ``poll`` lags container exit by ``lag`` calls."""

    def __init__(self, *, lag=2, code=0, pid=4321):
        self.pid = pid
        self.lag = lag
        self.code = code
        self.polls = 0

    def poll(self):
        self.polls += 1
        return None if self.polls <= self.lag else self.code


class NaturalExitUnitTests(unittest.TestCase):
    def test_requires_a_real_launcher_result(self):
        with self.assertRaises(GuardExceeded) as caught:
            natural_exit.attest(CID, {}, None, inspect=lambda cid: None)
        self.assertEqual(caught.exception.reason, "natural_exit_unverified")

    def test_live_cid_is_identity_loss_not_a_natural_exit(self):
        with self.assertRaises(GuardExceeded) as caught:
            natural_exit.attest(CID, {}, 0, inspect=lambda cid: 9)
        self.assertEqual(caught.exception.reason, "identity_lost")

    def test_second_inspection_must_also_prove_absence(self):
        checks = iter([None, 9])
        with self.assertRaises(GuardExceeded) as caught:
            natural_exit.attest(CID, {}, 0, inspect=lambda cid: next(checks))
        self.assertEqual(caught.exception.reason, "natural_exit_unverified")

    def test_unusable_inspection_never_becomes_absence(self):
        def broken(_cid):
            raise GuardExceeded("inspection_unavailable")

        with self.assertRaises(GuardExceeded) as caught:
            natural_exit.attest(CID, {}, 0, inspect=broken)
        self.assertEqual(caught.exception.reason, "inspection_unavailable")

    def test_wrong_cid_diagnostic_does_not_prove_our_cid_absent(self):
        error = subprocess.CalledProcessError(
            125, ["podman", "inspect", OTHER_CID],
            stderr=f'Error: no such object: "{OTHER_CID}"\n')
        with patch.object(binding, "command", side_effect=error):
            with self.assertRaises(GuardExceeded) as caught:
                natural_exit.attest(CID, {}, 0)
        self.assertEqual(caught.exception.reason, "inspection_unavailable")

    def test_valid_attestation_carries_result_and_inspect_method(self):
        proof = natural_exit.attest(CID, {}, 0, inspect=lambda cid: None)
        self.assertEqual(proof["cid"], CID)
        self.assertEqual(proof["returncode"], 0)
        self.assertEqual(proof["method"], "exact_cid_inspect")
        self.assertTrue(proof["absence_proof"]["observed_absent"])
        self.assertFalse(proof["kernel_enforcement"])


class PilotPollLagTests(unittest.TestCase):
    """Full ``watch_pilot`` path: poll lags a removed exact CID."""

    def setUp(self):
        self.calls = []

    def stop(self, cid):
        self.calls.append(cid)
        return teardown_proof(cid)

    def run_pilot(self, *, inspect_live=None, launcher=None, snapshots=None,
                  code=0):
        launcher = launcher or LaggingLauncher(code=code)
        snapshots = snapshots or ([{9: record(9)}] * 2 + [{}])
        tables = iter(snapshots)
        with tempfile.TemporaryDirectory() as folder:
            cidfile = Path(folder) / "pilot.cid"
            cidfile.write_text(CID)
            with patch.object(binding, "inspect_pid", return_value=9), \
                    patch.object(binding, "inspect_pid_if_live",
                                 side_effect=inspect_live or (lambda cid, env: None)):
                return monitor.watch_pilot(
                    launcher, CONFIG, cidfile=cidfile, env={}, interval=0.25,
                    stop=self.stop, snapshot=lambda: next(tables),
                    measure=lambda *_args: {"incremental_bytes": 0},
                    clock=lambda: 0.0, sleep=lambda _seconds: None)

    def test_poll_lag_with_removed_cid_is_a_true_natural_exit(self):
        # PX-R035 shape: exit_code 0, exact CID already removed, and a final
        # /proc snapshot that lost the bound PID before the launcher caught up.
        result = self.run_pilot(launcher=LaggingLauncher(lag=2, code=0))
        self.assertEqual(result["cid"], CID)
        self.assertEqual(result["peak_rss"], 1000)
        self.assertEqual(self.calls, [CID])
        natural = result["natural_exit"]
        self.assertEqual(natural["returncode"], 0)
        self.assertEqual(natural["method"], "exact_cid_inspect")
        self.assertTrue(natural["absence_proof"]["observed_absent"])
        # Completion is attested by the CID, not by a false identity claim.
        observed = result["identity_observation"]["observed"]
        self.assertTrue(observed["present"])
        self.assertTrue(observed["identity_matches"])

    def test_live_cid_after_identity_loss_fails_closed(self):
        with self.assertRaises(GuardExceeded) as caught:
            self.run_pilot(inspect_live=lambda cid, env: 9)
        self.assertEqual(caught.exception.reason, "identity_lost")
        self.assertEqual(self.calls, [CID])
        self.assertNotIn("natural_exit", caught.exception.guard_result)

    def test_unknown_cid_identity_fails_closed(self):
        def broken(_cid, _env):
            raise GuardExceeded("inspection_unavailable")

        with self.assertRaises(GuardExceeded) as caught:
            self.run_pilot(inspect_live=broken)
        self.assertEqual(caught.exception.reason, "inspection_unavailable")
        self.assertEqual(self.calls, [CID])
        self.assertNotIn("natural_exit", caught.exception.guard_result)

    def test_missing_pid_alone_never_attests_without_a_real_result(self):
        with self.assertRaises(GuardExceeded) as caught:
            self.run_pilot(launcher=LaggingLauncher(lag=10**6))
        self.assertEqual(caught.exception.reason, "natural_exit_unverified")
        self.assertEqual(self.calls, [CID])
        self.assertNotIn("natural_exit", caught.exception.guard_result)

    def test_teardown_proof_for_a_different_cid_is_never_a_success(self):
        def bad_stop(cid):
            self.calls.append(cid)
            return {"cid": OTHER_CID, "container_removed": True,
                    "fresh_absence_check": True}

        with tempfile.TemporaryDirectory() as folder:
            cidfile = Path(folder) / "pilot.cid"
            cidfile.write_text(CID)
            with patch.object(binding, "inspect_pid", return_value=9), \
                    patch.object(binding, "inspect_pid_if_live",
                                 return_value=None):
                with self.assertRaises(GuardExceeded) as caught:
                    monitor.watch_pilot(
                        LaggingLauncher(lag=2), CONFIG, cidfile=cidfile, env={},
                        interval=0.25, stop=bad_stop,
                        snapshot=iter([{9: record(9)}] * 2 + [{}]).__next__,
                        measure=lambda *_args: {"incremental_bytes": 0},
                        clock=lambda: 0.0, sleep=lambda _seconds: None)
        self.assertEqual(caught.exception.reason, "teardown_unverified")


if __name__ == "__main__":
    unittest.main()
