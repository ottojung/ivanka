"""Negative controls for accepting only authenticated Podman post-run cleanup errors."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from container_completion import (
    authenticated_postrun_cleanup, cleanup_lock_after_micall_done,
    verified_internal_seconds, startup_database_lock, TIMING_ORIGIN,
)

CONTAINER_ID = "a" * 64
CLEANUP_LINE = (
    'time="2026-11-01T08:57:24Z" level=error msg="Removing container '
    f'{CONTAINER_ID}: retrieving container {CONTAINER_ID} '
    f'configuration from DB to remove: retrieving container {CONTAINER_ID} '
    'config from DB: database is locked"'
)


class CompletionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stderr = self.root / "podman.stderr.log"
        self.timing = self.root / "micall_internal_timing.json"
        self.write_evidence()

    def write_evidence(self, *, done=True, diagnostic=CLEANUP_LINE,
                       seconds=12.25, exit_code=0, origin=TIMING_ORIGIN):
        self.stderr.write_text(
            ("2026-11-01 [INFO]micall.process_run(): Done.\n" if done else "")
            + diagnostic + "\n")
        self.timing.write_text(json.dumps(
            {"exit_code": exit_code, "seconds": seconds, "timing_origin": origin}))

    def test_exact_completed_auto_removal_lock_is_accepted_with_real_time(self):
        self.assertTrue(cleanup_lock_after_micall_done(self.stderr))
        self.assertEqual(authenticated_postrun_cleanup(127, self.root, 13), 12.25)

    def test_other_exit_codes_are_never_recovered(self):
        for code in (0, 1, 124, 125, 126):
            self.assertIsNone(authenticated_postrun_cleanup(code, self.root, 13))

    def test_missing_completion_is_not_recovered(self):
        self.write_evidence(done=False)
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 13))

    def test_wrong_cleanup_error_is_not_recovered(self):
        self.write_evidence(diagnostic='time="now" level=error msg="exec missing"')
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 13))
        self.write_evidence(diagnostic=CLEANUP_LINE.replace(
            "database is locked", "no such container"))
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 13))

    def test_mismatched_container_id_is_not_recovered(self):
        self.write_evidence(diagnostic=CLEANUP_LINE.replace(
            f"retrieving container {CONTAINER_ID} config from DB",
            f"retrieving container {'b' * 64} config from DB"))
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 13))

    def test_invalid_timer_origin_exit_and_wall_are_not_recovered(self):
        self.write_evidence(exit_code=1)
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 13))
        self.write_evidence(origin="outer_podman_wall")
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 13))
        self.write_evidence(seconds=14)
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 12))
        self.write_evidence(seconds=True)
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 13))
        self.timing.unlink()
        self.assertIsNone(authenticated_postrun_cleanup(127, self.root, 13))

    def test_startup_lock_requires_no_micall_completion(self):
        self.write_evidence(done=False,
            diagnostic="Error: beginning transaction: database is locked")
        self.assertTrue(startup_database_lock(self.stderr))
        self.write_evidence(done=True,
            diagnostic="Error: beginning transaction: database is locked")
        self.assertFalse(startup_database_lock(self.stderr))
        self.write_evidence(done=False,
            diagnostic="Error: beginning container create transaction: database is locked")
        self.assertTrue(startup_database_lock(self.stderr))
        self.write_evidence(done=False,
            diagnostic="Error: failed to find image")
        self.assertFalse(startup_database_lock(self.stderr))

    def test_clean_timer_uses_identical_validation(self):
        self.assertEqual(verified_internal_seconds(self.timing, 13), 12.25)
        self.write_evidence(seconds=0)
        with self.assertRaises(ValueError):
            verified_internal_seconds(self.timing, 13)


if __name__ == "__main__":
    unittest.main()
