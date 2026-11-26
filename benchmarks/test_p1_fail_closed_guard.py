"""Regression tests for the real worker lock and fail-closed RSS guard."""

from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest import mock

import p1_fail_closed_guard as guard
import p1_matched_timing as timing


def record(pid: int, rss: int | None, starttime: int = 100, namespace: int = 7) -> dict:
    return {
        "pid": pid, "ppid": 1, "starttime": starttime, "pid_ns": namespace,
        "cmdline_sha": "sha", "rss": rss,
    }


class WrongLockTests(unittest.TestCase):
    def test_decoy_lock_path_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="p1-decoy-lock-") as folder:
            decoy = pathlib.Path(folder) / ".global-worker.lock"
            decoy.write_text("decoy")
            with self.assertRaises(timing.Refusal) as caught:
                timing.verify_stop_boundary(
                    "token", lock_path=decoy, stop_path=decoy, journal=decoy,
                    containers=[],
                )
            self.assertIn("wrong worker lock", str(caught.exception))

    def test_real_lock_path_has_no_environment_override(self) -> None:
        self.assertEqual(
            timing.GLOBAL_LOCK,
            pathlib.Path("/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock"),
        )
        source = pathlib.Path(timing.__file__).read_text()
        self.assertNotIn("P1_RUNTIME_LOCK_PATH", source)
        self.assertNotIn("p1-runtime-shared.lock", source)
        self.assertIn("fcntl.flock", source)
        self.assertIn("LOCK_NB", source)

    def test_flock_contention_fails_closed(self) -> None:
        with mock.patch.object(timing.os, "open", return_value=9):
            with mock.patch.object(timing.os, "close"):
                with mock.patch.object(timing.fcntl, "flock", side_effect=BlockingIOError):
                    with mock.patch.object(timing, "verify_stop_boundary", return_value={}):
                        with self.assertRaises(timing.Refusal):
                            with timing.shared_worker_lock("token", pathlib.Path("/tmp/out")):
                                self.fail("body must not run while lock is held")

    def test_stop_boundary_requires_matching_token(self) -> None:
        with tempfile.TemporaryDirectory(prefix="p1-stop-") as folder:
            root = pathlib.Path(folder)
            stop = root / "STOP"
            stop.write_text("PX owner window for p1-runtime-owner")
            journal = root / ".worker-lease.jsonl"
            journal.write_text("")
            with self.assertRaises(timing.Refusal):
                timing.verify_stop_boundary(
                    "a-different-owner", lock_path=timing.GLOBAL_LOCK,
                    stop_path=stop, journal=journal, containers=[],
                )


class LostIdentityTests(unittest.TestCase):
    def test_locate_requires_exactly_one_process(self) -> None:
        table = {1: record(1, 1000), 2: record(2, 1000)}
        with self.assertRaises(guard.GuardExceeded) as caught:
            guard.locate((100, 7, "sha"), table)
        self.assertEqual(caught.exception.reason, "identity_lost")
        with self.assertRaises(guard.GuardExceeded):
            guard.locate((999, 7, "sha"), table)

    def test_inspect_returning_another_cid_is_identity_lost(self) -> None:
        cid = "a" * 64
        with mock.patch.object(guard, "command", return_value=f"{'b' * 64} 4242"):
            with self.assertRaises(guard.GuardExceeded) as caught:
                guard.bind_container(cid, snapshot={})
        self.assertEqual(caught.exception.reason, "identity_lost")

    def test_invalid_cid_is_binding_unavailable(self) -> None:
        with self.assertRaises(guard.GuardExceeded) as caught:
            guard.bind_container("not-a-cid", snapshot={})
        self.assertEqual(caught.exception.reason, "binding_unavailable")


class NullRssTests(unittest.TestCase):
    def test_null_rss_never_becomes_zero(self) -> None:
        table = {11: record(11, None)}
        with self.assertRaises(guard.GuardExceeded) as caught:
            guard.rss_bytes(table, {11})
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_watch_with_no_usable_sample_is_failure_not_success(self) -> None:
        bound = {"cid": "c" * 64, "pid": 11, "fingerprint": (100, 7, "sha")}
        calls = {"n": 0}

        def unavailable(_: dict) -> int:
            calls["n"] += 1
            raise guard.GuardExceeded("measurement_unavailable")

        with self.assertRaises(guard.GuardExceeded) as caught:
            guard.watch(
                bound, limit=guard.RSS_LIMIT, deadline=100.0,
                running=lambda: calls["n"] < 1,
                observe_fn=unavailable, sleep_fn=lambda _: None,
                clock=lambda: 0.0,
            )
        self.assertEqual(caught.exception.reason, "measurement_unavailable")

    def test_watch_peak_stays_none_when_process_exits_before_a_sample(self) -> None:
        bound = {"cid": "c" * 64, "pid": 11, "fingerprint": (100, 7, "sha")}
        peak = guard.watch(
            bound, limit=guard.RSS_LIMIT, deadline=100.0,
            running=lambda: False, observe_fn=lambda _: 123,
            sleep_fn=lambda _: None, clock=lambda: 0.0,
        )
        self.assertIsNone(peak)

    def test_rss_limit_and_wall_deadline(self) -> None:
        bound = {"cid": "c" * 64, "pid": 11, "fingerprint": (100, 7, "sha")}
        with self.assertRaises(guard.GuardExceeded) as caught:
            guard.watch(
                bound, limit=100, deadline=100.0, running=lambda: True,
                observe_fn=lambda _: 101, sleep_fn=lambda _: None,
                clock=lambda: 0.0,
            )
        self.assertEqual(caught.exception.reason, "observed_rss_limit")
        with self.assertRaises(guard.GuardExceeded) as caught:
            guard.watch(
                bound, limit=guard.RSS_LIMIT, deadline=100.0, running=lambda: True,
                observe_fn=lambda _: 1, sleep_fn=lambda _: None,
                clock=lambda: 101.0,
            )
        self.assertEqual(caught.exception.reason, "wall_limit")


class ExactCidTeardownTests(unittest.TestCase):
    def test_teardown_uses_exact_cid_not_name(self) -> None:
        cid = "d" * 64
        seen = []

        def listed() -> list[str]:
            seen.append("list")
            return [cid] if len(seen) == 1 else []

        with mock.patch.object(guard.subprocess, "run", return_value=mock.Mock()) as runner:
            proof = guard.stop_cid(cid, listed=listed)
        self.assertTrue(proof["container_removed"])
        self.assertFalse(proof["kernel_enforcement"])
        self.assertEqual(runner.call_args[0][0], ["podman", "rm", "-f", cid])


if __name__ == "__main__":
    unittest.main()
