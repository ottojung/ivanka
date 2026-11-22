"""Parent-owned global PX admission guard is exclusive and fail-closed."""
import json
import tempfile
import unittest
from pathlib import Path

from assembler_bench.global_admission import (
    STATE_SCHEMA,
    AdmissionDenied,
    CapExceeded,
    FOUNDER_FREE_FLOOR_BYTES,
    FOUNDER_INCREMENTAL_CAP_BYTES,
    GlobalAdmissionGuard,
    GuardConfig,
)


class TestGlobalAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.free = [100 * 1024 ** 3]
        self.incremental = [0]
        self.config = GuardConfig(
            state_dir=self.root / "state",
            workspace=self.root,
            free_bytes_fn=lambda _path: self.free[0],
            incremental_bytes_fn=lambda: self.incremental[0],
        )
        self.guard = GlobalAdmissionGuard(self.config)

    def state(self):
        if not self.guard.state_path.exists():
            return {"schema": STATE_SCHEMA, "token": None, "programs": {}}
        return json.loads(self.guard.state_path.read_text())

    def test_two_simultaneous_claimants_one_rejected(self):
        first = self.guard.claim("skesa")
        try:
            # A distinct guard instance proves exclusion is file-lock based,
            # not merely an in-memory flag on the first object.
            other = GlobalAdmissionGuard(self.config)
            with self.assertRaisesRegex(AdmissionDenied, "already admitted"):
                other.claim("unicycler")
            self.assertEqual(self.state()["token"]["program"], "skesa")
        finally:
            first.release()
        second = self.guard.claim("unicycler")
        self.assertEqual(second.program, "unicycler")
        second.release()

    def test_disk_below_ceiling_rejected(self):
        self.free[0] = FOUNDER_FREE_FLOOR_BYTES - 1
        with self.assertRaisesRegex(AdmissionDenied, "free-disk floor"):
            self.guard.claim("skesa")
        self.assertIsNone(self.state()["token"])
        # The refusal released the lock, so a healthy claim still succeeds.
        self.free[0] = FOUNDER_FREE_FLOOR_BYTES + 1024 ** 3
        token = self.guard.claim("skesa")
        token.release()

    def test_reservation_must_leave_floor_after_admission(self):
        self.free[0] = FOUNDER_FREE_FLOOR_BYTES + 512 ** 2
        with self.assertRaises(AdmissionDenied):
            self.guard.claim("skesa", reservation_bytes=1024 ** 3)
        self.assertIsNone(self.state()["token"])

    def test_token_released_after_normal_exit_and_after_failure(self):
        with self.guard.claim("skesa") as token:
            self.assertEqual(token.program, "skesa")
            self.assertIsNotNone(self.state()["token"])
        self.assertTrue(token.released)
        self.assertIsNone(self.state()["token"])
        self.assertEqual(self.state()["programs"], {})

        with self.assertRaisesRegex(ValueError, "boom"):
            with self.guard.claim("skesa") as failed:
                raise ValueError("boom")
        self.assertTrue(failed.released)
        self.assertIsNone(self.state()["token"])
        self.assertEqual(self.state()["programs"], {})
        # Both releases left the guard usable.
        again = self.guard.claim("skesa")
        again.release()

    def test_cap_enforcement(self):
        self.config.per_program_max_bytes = 2 * 1024
        with self.assertRaisesRegex(CapExceeded, "disk cap"):
            self.guard.claim("skesa", reservation_bytes=3 * 1024)
        self.assertIsNone(self.state()["token"])

        self.config.per_program_max_bytes = FOUNDER_INCREMENTAL_CAP_BYTES
        self.config.per_program_max_cost_units = 1
        with self.assertRaisesRegex(CapExceeded, "cost cap"):
            self.guard.claim("skesa", cost_units=2)
        self.assertIsNone(self.state()["token"])

        self.incremental[0] = FOUNDER_INCREMENTAL_CAP_BYTES - 512 ** 2
        with self.assertRaisesRegex(AdmissionDenied, "founder ceiling"):
            self.guard.claim("skesa", reservation_bytes=1024 ** 3)
        self.assertIsNone(self.state()["token"])

    def test_fail_closed_on_corrupt_state(self):
        self.guard.state_dir.mkdir(parents=True, exist_ok=True)
        self.guard.state_path.write_text("{not json")
        with self.assertRaisesRegex(AdmissionDenied, "unreadable"):
            self.guard.claim("skesa")
        # The corrupt file is not overwritten by a denied claim.
        self.assertEqual(self.guard.state_path.read_text(), "{not json")

    def test_stale_crashed_token_is_reclaimed(self):
        self.config.pid_alive = lambda _pid: False
        self.guard.state_dir.mkdir(parents=True, exist_ok=True)
        stale = {
            "schema": STATE_SCHEMA,
            "token": {"id": "dead", "program": "ray", "pid": 424242,
                      "reservation_bytes": 1024 ** 3, "cost_units": 1},
            "programs": {"ray": {"workers": 1, "bytes": 1024 ** 3,
                                 "cost_units": 1}},
        }
        self.guard.state_path.write_text(json.dumps(stale))
        token = self.guard.claim("skesa")
        try:
            self.assertEqual(self.state()["token"]["program"], "skesa")
            self.assertEqual(self.state()["programs"], {
                "skesa": {"workers": 1, "bytes": 1024 ** 3, "cost_units": 1}})
        finally:
            token.release()

    def test_founder_constants_match_merged_policy(self):
        self.assertEqual(FOUNDER_FREE_FLOOR_BYTES, 32 * 1024 ** 3)
        self.assertEqual(FOUNDER_INCREMENTAL_CAP_BYTES, 8 * 1024 ** 3)
        self.assertEqual(self.config.max_workers, 1)
        self.assertEqual(self.config.max_wall_seconds, 2400)
        self.assertEqual(self.config.max_rss_bytes, 4_000_000_000)


if __name__ == "__main__":
    unittest.main()
