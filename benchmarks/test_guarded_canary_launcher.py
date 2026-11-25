"""Focused regression tests for the guarded-canary launcher liveness repair.

The first three tests reproduce the exact prelaunch failure modes from the
2026-11-24 23:39Z operator finding (loose ``.fa`` match, overwrite refusal,
unbounded retry storm) and prove the repaired path is bounded and fail-closed.
No container, live service, sealed root or candidate image is involved.
"""
import json
import pathlib
import tempfile
import unittest

from assembler_bench import guarded_canary_launcher as launcher


def legacy_loose_fa_match(token):
    """Verbatim shape of the old buggy check: '.fa' as a substring."""
    return ".fa" in str(token).lower()


class GuardianLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="guarded-canary-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.reads = self.root / "reads"
        self.reads.mkdir()
        self.attempt = self.root / "attempt"
        self.attempt.mkdir()
        self.timer = self.root / "ivanka-timer.py"
        self.timer.write_text("# timer\n")
        self.store = self.root / "store"
        self.store.mkdir()
        self.runroot = self.root / "runroot"
        self.runroot.mkdir()
        self.argv = launcher.build_command(
            image="sha256:" + "a" * 64,
            reads_dir=self.reads,
            attempt_dir=self.attempt,
            timer=self.timer,
            cidfile=self.attempt / "cid",
            storage_root=self.store,
            runroot=self.runroot,
            name="podman-name-test",
        )

    def _allowlists(self, argv=None):
        argv = self.argv if argv is None else argv
        mounts = [argv[index + 1] for index, token in enumerate(argv[:-1]) if token == "-v"]
        return (frozenset(token for token in argv if token not in mounts),
                frozenset(mount.rsplit(":", 2)[0] for mount in mounts))

    # --- failure mode 1: loose '.fa' vs '.fastq.gz' -------------------------
    def test_fastq_reads_allowed_fasta_reference_rejected(self):
        # Reproduce the prelaunch refusal: the old check rejected paired reads.
        self.assertTrue(legacy_loose_fa_match("/reads/R1.fastq.gz"))
        self.assertTrue(legacy_loose_fa_match("/reads/R2.fastq.gz"))
        # The repaired validator admits the exact FASTQ contract.
        allowed, sources = self._allowlists()
        self.assertTrue(launcher.assert_reference_blind(
            self.argv, allowed_values=allowed, expected_sources=sources))
        self.assertIn("/reads/R1.fastq.gz", self.argv)

        # A genuine FASTA reference (or truth component) still fails closed,
        # even when smuggled into an otherwise allowlisted argv.
        for leak in ("/reads/haplotypes.fa", "/reads/reference.fasta",
                     "/reads/hidden-truth/haplotypes.fasta"):
            argv = list(self.argv)
            argv[argv.index("/reads/R1.fastq.gz")] = leak
            allowed, sources = self._allowlists(argv)
            with self.assertRaises(launcher.ReferenceLeak):
                launcher.assert_reference_blind(
                    argv, allowed_values=allowed, expected_sources=sources)

    def test_unexpected_mount_or_argv_fails_closed(self):
        allowed, sources = self._allowlists()
        extra = list(self.argv)
        extra.extend(("-v", f"{self.root}:/truth:ro"))
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.assert_reference_blind(
                extra, allowed_values=allowed, expected_sources=sources)
        altered = list(self.argv)
        altered[altered.index("--all_projects")] = "--all_projects-extra"
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.assert_reference_blind(
                altered, allowed_values=allowed, expected_sources=sources)

    # --- failure mode 2: overwrite refusal / prelaunch evidence -------------
    def test_unique_attempt_namespace_preserves_prior_evidence(self):
        prior = launcher.new_attempt(self.root, "coverage_hole-s002",
                                     stamp="20261124T233900000000Z", pid=42,
                                     token="abcdef123456")
        (prior / "case.json").write_text("prelaunch evidence must survive\n")
        retry = launcher.new_attempt(self.root, "coverage_hole-s002",
                                     stamp="20261124T233900000000Z", pid=42,
                                     token="abcdef123456")
        self.assertNotEqual(prior, retry)
        self.assertEqual((prior / "case.json").read_text(),
                         "prelaunch evidence must survive\n")
        self.assertTrue((prior / "case.json").is_file())
        self.assertTrue(retry.is_dir())

    def test_bad_cycles_setup_exclusive_and_exact(self):
        path = launcher.setup_bad_cycles(self.attempt)
        self.assertEqual(path.read_bytes(), launcher.BAD_CYCLES_HEADER)
        self.assertTrue(launcher.verify_bad_cycles(path))
        with self.assertRaises(FileExistsError):
            launcher.setup_bad_cycles(self.attempt)
        path.write_bytes(b"tampered\n")
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.verify_bad_cycles(path)

    # --- failure mode 3: retry storm ---------------------------------------
    def test_retry_budget_is_bounded_and_audited(self):
        calls = []

        def always_fails():
            calls.append(1)
            raise RuntimeError("prelaunch failure")

        with launcher.AppendOnlyLog(self.attempt / "launch.jsonl") as log:
            with self.assertRaises(launcher.RetryExhausted):
                launcher.run_bounded(always_fails, launcher.RetryBudget(
                    max_attempts=2), log, attempt_id="attempt-1")
            self.assertEqual(len(calls), 2)
            records = log.records()
            self.assertEqual([r["event"] for r in records],
                             ["start", "failure", "start", "failure"])
            calls.clear()
            with self.assertRaises(launcher.RetryExhausted):
                launcher.run_bounded(always_fails, launcher.RetryBudget(),
                                     log, attempt_id="attempt-2")
            self.assertEqual(len(calls), 1)  # default: no retries at all
        for budget in (launcher.RetryBudget(max_attempts=0),
                       launcher.RetryBudget(max_attempts=999),
                       launcher.RetryBudget(delay_seconds=60)):
            with self.assertRaises(launcher.UnsafeCommand):
                budget.validate()

    def test_guard_bounds_are_capped(self):
        launcher.GuardBounds().validate()
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.GuardBounds(wall_seconds=99999).validate()
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.GuardBounds(rss_limit_bytes=8_000_000_000).validate()

    def test_append_only_log_preserves_earlier_records(self):
        path = self.attempt / "durable.jsonl"
        with launcher.AppendOnlyLog(path) as log:
            log.append({"event": "prelaunch"})
        with launcher.AppendOnlyLog(path) as log:
            log.append({"event": "failure"})
        with launcher.AppendOnlyLog(path) as log:
            self.assertEqual([r["event"] for r in log.records()],
                             ["prelaunch", "failure"])

    # --- receipt handling ---------------------------------------------------
    def test_receipt_binds_attempt_and_fails_on_tamper(self):
        launcher.setup_bad_cycles(self.attempt)
        receipt = launcher.write_receipt(
            self.attempt, case="coverage_hole-s002", attempt_id="attempt-9",
            argv=self.argv)
        self.assertEqual(receipt["qualification_claim"], "NONE")
        self.assertEqual(launcher.verify_receipt(
            self.attempt, case="coverage_hole-s002", attempt_id="attempt-9",
            argv=self.argv)["schema"], launcher.SCHEMA_RECEIPT)
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.verify_receipt(
                self.attempt, case="other-case", attempt_id="attempt-9",
                argv=self.argv)
        (self.attempt / "bad_cycles.csv").write_bytes(b"tile,cycle\nx,y\n")
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.verify_receipt(
                self.attempt, case="coverage_hole-s002", attempt_id="attempt-9",
                argv=self.argv)

    # --- independent-review hardening (PR484 NO-GO defects) ----------------
    def test_new_attempt_rejects_path_escape_and_unsafe_pid(self):
        for bad_pid in ("../../../../tmp/PR484_ESCAPE", "42/x", True, -1, 4_194_304, 1.5):
            with self.assertRaises(launcher.UnsafeCommand):
                launcher.new_attempt(self.root, "coverage_hole-s002", pid=bad_pid,
                                     token="abcdef123456")
        for bad_case in ("../escape", "case/../escape", ""):
            with self.assertRaises(launcher.UnsafeCommand):
                launcher.new_attempt(self.root, bad_case, pid=42, token="abcdef123456")
        self.assertTrue(launcher.new_attempt(
            self.root, "coverage_hole-s002", pid=42, token="abcdef123456").is_dir())

    def test_validator_enforces_numeric_bounds_not_only_format(self):
        for position, bad in ((13, "--cpus=999999999"),
                              (14, "--memory=99999999999999"),
                              (16, "999999"), (16, "abc"), (16, "-1")):
            argv = list(self.argv)
            argv[position] = bad
            allowed, sources = self._allowlists(argv)
            with self.assertRaises(launcher.UnsafeCommand):
                launcher.assert_reference_blind(
                    argv, allowed_values=allowed, expected_sources=sources)

    def test_receipt_rejects_status_claim_extra_fields_and_overwrite(self):
        launcher.setup_bad_cycles(self.attempt)
        original = launcher.write_receipt(
            self.attempt, case="coverage_hole-s002", attempt_id="attempt-9",
            argv=self.argv)
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.write_receipt(
                self.attempt, case="coverage_hole-s002", attempt_id="attempt-9",
                argv=self.argv)
        path = self.attempt / "receipt.json"
        for field, value in (("status", "success"),
                             ("qualification_claim", "QUALIFIED"),
                             ("unexpected_field", "x")):
            path.write_text(json.dumps(dict(original, **{field: value})))
            with self.assertRaises(launcher.UnsafeCommand):
                launcher.verify_receipt(
                    self.attempt, case="coverage_hole-s002", attempt_id="attempt-9",
                    argv=self.argv)
        path.write_text(json.dumps(original))
        self.assertEqual(launcher.verify_receipt(
            self.attempt, case="coverage_hole-s002", attempt_id="attempt-9",
            argv=self.argv)["status"], "attempted")


if __name__ == "__main__":
    unittest.main()
