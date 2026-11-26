"""Adversarial proofs for the single explicit PX retry authorization."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import exploratory_policy
from assembler_bench import px_cohort_ingest as ingest
from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_guard_source as guard_source
from assembler_bench import px_retry_authorization as authz
from assembler_bench import px_supervisor as sup
from assembler_bench.public_view import (EVIDENCE_SCHEMA, PANEL,
                                         PHYSICAL_MANIFEST, PHYSICAL_SCORE,
                                         merge_evidence)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "benchmarks/assembler_bench/exploratory_candidates.json"
TOOLS = ("skesa", "minia")

# Explicit isolated guard fixture. CI merges the branch into a main that may
# already contain not-yet-deployed guard code (PR #536 changed three pinned
# monitor paths), so tests must not read the checkout as if it were the live
# service. Production verification still reads DEPLOYED_ROOT/DEPLOYED_HEAD.
_REAL_GUARD_VERIFY = guard_source.verify
_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "px_guard_pins"


def _fixture_verify(root=None):
    return _REAL_GUARD_VERIFY(root=_FIXTURE_ROOT)


def setUpModule():
    global _guard_patch
    _guard_patch = patch.object(guard_source, "verify", side_effect=_fixture_verify)
    _guard_patch.start()


def tearDownModule():
    _guard_patch.stop()

# Exact indexed receipts from the exhausted infrastructure run records. The
# first pair are two IDBA-UD du-measurement timeouts; the second pair are a
# Minia measurement timeout followed by a disk-stop failure.
IDBA_ATTEMPT_1 = {
    "adapter_commit": "ea51b5030edf6a6c89c36ffa3d48fac15b2cb1c9",
    "alias": "PX-R001", "attempt": 1, "cohort": "physical",
    "failure_reason": "measurement_unavailable",
    "image_sha256": "36ae5c23a20e86cf1f93ef9e85fe9fee8b89b38c405f133e800aecc86a094a94",
    "input_sha256": {"R1": "680e9daf815205f166731de6b986bce3a67a1f4a83fee5dffce6b0bb7dd41862",
                     "R2": "95717103a1462813a1e05bda79b75e82f165976c62b8fd7d178cb69ca39f468f"},
    "outcome": "failure", "output_sha256": None,
    "peak_ram_method": "container_process_tree_sampled_rss",
    "peak_ram_method_version": "ivanka.px.whole-container-rss.v2",
    "peak_ram_scope": "whole_container_process_tree", "peak_rss_bytes": 308531200,
    "qualifying": False,
    "runner_receipt_sha256": "4b53396224ac2be0d4ea4c6aefb9cd12e96c644062dc595fb1272780ee2d4fbd",
    "schema": "ivanka.px.case.receipt.v1", "seconds": None,
    "source_commit": "a1bafe6b012912cd9a76926ec75a98aee6213af6",
    "terminal": True, "tool_id": "idba-ud"}
IDBA_ATTEMPT_2 = dict(IDBA_ATTEMPT_1, attempt=2, peak_rss_bytes=285433856,
                      runner_receipt_sha256="ce13eaaf5610584566debbf6a7e7d7fad144aa004f6d4cae67411079eef5c3d2")
MINIA_ATTEMPT_1 = {
    "adapter_commit": "ff75f0f2dca4b8b26dd8520638e4981d02484fbe",
    "alias": "PX-R001", "attempt": 1, "cohort": "physical",
    "failure_reason": "measurement_unavailable",
    "image_sha256": "d218919d19ac1e053e15905a222a1f05ae085d6f7e0e0e620817bd06913df08e",
    "input_sha256": {"R1": "680e9daf815205f166731de6b986bce3a67a1f4a83fee5dffce6b0bb7dd41862",
                     "R2": "95717103a1462813a1e05bda79b75e82f165976c62b8fd7d178cb69ca39f468f"},
    "outcome": "failure", "output_sha256": None,
    "peak_ram_method": "container_process_tree_sampled_rss",
    "peak_ram_method_version": "ivanka.px.whole-container-rss.v2",
    "peak_ram_scope": "whole_container_process_tree", "peak_rss_bytes": 288542720,
    "qualifying": False,
    "runner_receipt_sha256": "4a9c96302222c6e79abd9444fa43870b5d795deeb7519e47d65952241d48900e",
    "schema": "ivanka.px.case.receipt.v1", "seconds": None,
    "source_commit": "7b7239c69ecc63534a20fc0d0c2de30f0f67e31c",
    "terminal": True, "tool_id": "minia"}
MINIA_ATTEMPT_2 = dict(MINIA_ATTEMPT_1, attempt=2,
                       failure_reason="disk_stop", peak_rss_bytes=240234496,
                       runner_receipt_sha256="f0236f5bdb6c9cd24218a481c3bc26c168cb05b4c83c94aa8ac679d1610b5c4c")
IDBA_DIGEST = "b23516a0b769e05a73f8948cb6bd9251b7e5d279c8998e5b7b4e32185c8e0b11"
MINIA_DIGEST = "dca34fe9eef928960d220171f9598614fc8b4ff77677018f9e40ed1e60bd2ccc"


def canonical_bytes(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_receipt(root, arm, data):
    path = sched.receipt_path(root, arm)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(data))
    entries = sched._load_index(root)
    entries[sched.receipt_id(arm)] = hashlib.sha256(path.read_bytes()).hexdigest()
    sched._write_index(root, entries)
    return path


def write_preserved(root, arm, data):
    path = sched.attempt_path(root, arm, data["attempt"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(data))
    return path


def arm_of(receipt):
    return {key: receipt[key] for key in (
        "tool_id", "cohort", "alias", "input_sha256", "source_commit",
        "adapter_commit", "image_sha256")}


def no_posthoc(root, arm, case, receipt):
    return None


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.arm = arm_of(IDBA_ATTEMPT_2)
        self.provenance = patch.object(exploratory_policy, "PROVENANCE_ROOT", self.root)
        self.provenance.start()
        self.addCleanup(self.provenance.stop)
        self.first = sched.record_outcome(
            self.root, self.arm, None, "failure", failure_reason="measurement_unavailable")
        self.prior = sched.record_outcome(
            self.root, self.arm, None, "failure", failure_reason="measurement_unavailable")
        self.prior_bytes = sched.receipt_path(self.root, self.arm).read_bytes()
        self.first_bytes = sched.attempt_path(self.root, self.arm, 1).read_bytes()
        self.prior_digest = sched._load_index(self.root)[sched.receipt_id(self.arm)]

    def test_binding_covers_arm_identity_prior_bytes_guard_and_extra_attempt(self):
        path, digest = authz.authorize(self.root, self.arm)
        record = authz.verify(self.root, self.arm)
        self.assertEqual(path, authz.authorization_path(self.root, self.arm))
        self.assertEqual(record["arm"], authz.arm_identity(self.arm))
        self.assertEqual(record["prior_receipt_sha256"], self.prior_digest)
        self.assertEqual(len(self.prior_digest), 64)
        self.assertEqual(record["guard_commit"], authz.GUARD_COMMIT)
        self.assertEqual(record["guard_source_sha256"],
                         guard_source.verify()[guard_source.RESERVE_SOURCE])
        self.assertEqual(record["preserved_attempt_sha256"], {
            "1": hashlib.sha256(self.first_bytes).hexdigest(),
            "2": hashlib.sha256(self.prior_bytes).hexdigest()})
        self.assertEqual(record["extra_attempt"], 3)
        self.assertEqual(record["authorization_sha256"], digest)
        self.assertEqual(hashlib.sha256(canonical_bytes({
            key: value for key, value in record.items()
            if key != "authorization_sha256"})).hexdigest(), digest)
        self.assertEqual(self.prior_bytes, sched.receipt_path(self.root, self.arm).read_bytes())
        self.assertEqual(self.first_bytes, sched.attempt_path(self.root, self.arm, 1).read_bytes())

    def test_repeat_authorization_is_idempotent(self):
        first = authz.authorize(self.root, self.arm)
        second = authz.authorize(self.root, self.arm)
        self.assertEqual(first, second)
        self.assertEqual(len(list(authz.authorization_path(self.root, self.arm).parent.glob("*.json"))), 1)

    def test_successful_and_generic_error_arms_are_never_authorized(self):
        success = dict(self.arm, alias="PX-R002")
        sched.record_outcome(self.root, success, None, "failure",
                             failure_reason="measurement_unavailable")
        output = self.root / "conseq.csv"
        output.write_bytes(b"region,MAX\nHIV1,ACGT\n")
        sched.record_outcome(self.root, success, output, "success", seconds=1.0)
        with self.assertRaisesRegex(ValueError, "only exhausted"):
            authz.authorize(self.root, success)
        generic = dict(self.arm, alias="PX-R003")
        sched.record_outcome(self.root, generic, None, "failure",
                             failure_reason="measurement_unavailable")
        sched.record_outcome(self.root, generic, None, "failure", failure_reason="error")
        with self.assertRaisesRegex(ValueError, "only exhausted"):
            authz.authorize(self.root, generic)

    def test_tampered_receipt_or_authorization_fails_closed(self):
        authz.authorize(self.root, self.arm)
        preserved = sched.attempt_path(self.root, self.arm, 2)
        preserved.write_bytes(canonical_bytes(dict(self.prior, output_sha256="0" * 64)))
        with self.assertRaisesRegex(ValueError, "indexed receipt bytes changed"):
            authz.verify(self.root, self.arm)
        preserved.write_bytes(self.prior_bytes)
        path = authz.authorization_path(self.root, self.arm)
        record = json.loads(path.read_bytes())
        record["guard_commit"] = "0" * 40
        path.write_bytes(canonical_bytes(record))
        with self.assertRaisesRegex(ValueError, "does not bind this arm"):
            authz.verify(self.root, self.arm)

    def test_prior_identity_tampering_fails_closed(self):
        authz.authorize(self.root, self.arm)
        preserved = sched.attempt_path(self.root, self.arm, 2)
        changed = json.loads(preserved.read_bytes())
        changed["alias"] = "PX-R999"
        preserved.write_bytes(canonical_bytes(changed))
        with self.assertRaisesRegex(ValueError, "indexed receipt bytes changed"):
            authz.verify(self.root, self.arm)

    def test_exact_exhausted_run_records_are_bound(self):
        for first, second, digest in ((IDBA_ATTEMPT_1, IDBA_ATTEMPT_2, IDBA_DIGEST),
                                      (MINIA_ATTEMPT_1, MINIA_ATTEMPT_2, MINIA_DIGEST)):
            with self.subTest(tool=second["tool_id"]):
                root = self.root / second["tool_id"]
                arm = arm_of(second)
                write_preserved(root, arm, first)
                write_preserved(root, arm, second)
                write_receipt(root, arm, second)
                self.assertEqual(hashlib.sha256(sched.receipt_path(root, arm).read_bytes()).hexdigest(),
                                 digest)
                path, _ = authz.authorize(root, arm)
                record = json.loads(path.read_bytes())
                self.assertEqual(record["prior_receipt_sha256"], digest)
                self.assertEqual(record["extra_attempt"], 3)
                self.assertEqual(record["guard_commit"], authz.GUARD_COMMIT)
                self.assertEqual(authz.verify(root, arm), record)

    def test_plan_identity_is_unchanged_and_exhausted_arm_is_pending(self):
        registry = self.registry()
        for tool in TOOLS:
            sup.make_handoff(self.root, registry, tool)
        source = self.source()
        plan = sched.build_plan(registry, source, self.root)
        digest = sched._plan_digest(plan)
        pending_arm = plan["pending"][0]
        for _ in range(sched.MAX_INFRA_ATTEMPTS):
            sched.record_outcome(self.root, pending_arm, None, "failure",
                                 failure_reason="measurement_unavailable")
        authz.authorize(self.root, pending_arm)
        rebuilt = sched.build_plan(registry, source, self.root)
        self.assertEqual(sched._plan_digest(rebuilt), digest)
        self.assertIn(sched.receipt_id(pending_arm),
                      {sched.receipt_id(a) for a in sched.resume(rebuilt, self.root)})

    def source(self):
        ids = [f"P{i:03d}" for i in range(1, sched.PHYSICAL_COUNT + 1)]
        canonical = sched.canonical_aliases(ids, "physical")
        synth = [f"S{i:03d}" for i in range(1, sched.SYNTHETIC_COUNT + 1)]
        sc = sched.canonical_aliases(synth, "synthetic")
        r1, r2 = self.root / "r1.fastq.gz", self.root / "r2.fastq.gz"
        r1.write_bytes(b"@r\nACGT\n+\n!!!!\n")
        r2.write_bytes(b"@r\nTGCA\n+\n!!!!\n")
        return sched.CohortSource(
            [sched.CasePair(i, canonical[i], "physical", r1, r2) for i in ids],
            [sched.CasePair(i, sc[i], "synthetic", r1, r2) for i in synth])

    def registry(self):
        data = json.loads(REGISTRY.read_text())
        for tool in TOOLS:
            item = next(x for x in data["candidates"] if x["id"] == tool)
            receipt = self.root / (tool + "-image.json")
            pilot = self.root / (tool + "-pilot.json")
            receipt.write_bytes(canonical_bytes({
                "schema": "ivanka.exploratory.image.receipt.v1", "tool_id": tool,
                "source_commit": item["source_commit"],
                "adapter_commit": data["adapter_branch_commits"][tool],
                "image_sha256": "b" * 64, "qualifying": False,
                "native_binary_sha256": "a" * 64}))
            pilot.write_bytes(canonical_bytes({
                "schema": "ivanka.exploratory.pilot.receipt.v1", "tool_id": tool,
                "source_commit": item["source_commit"],
                "adapter_commit": data["adapter_branch_commits"][tool],
                "image_sha256": "b" * 64, "qualifying": False,
                "physical": {"source_input_sha256": "c" * 64, "status": "success"},
                "synthetic": {"source_input_sha256": "d" * 64, "status": "success"}}))
            item.update({"status": "pilot", "image_sha256": "b" * 64,
                         "image_evidence": {"path": str(receipt),
                                            "sha256": sched.sha256_file(receipt)},
                         "pilot_evidence": {"path": str(pilot),
                                            "sha256": sched.sha256_file(pilot)}})
        path = self.root / "registry.json"
        path.write_bytes(canonical_bytes(data))
        return path


class SupervisorRetryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.px = self.root / "px"
        self.px.mkdir()
        self.r1 = self.root / "r1.fastq.gz"
        self.r2 = self.root / "r2.fastq.gz"
        self.r1.write_bytes(b"@r\nACGT\n+\n!!!!\n")
        self.r2.write_bytes(b"@r\nTGCA\n+\n!!!!\n")
        self.provenance = patch.object(exploratory_policy, "PROVENANCE_ROOT", self.root)
        self.provenance.start()
        self.addCleanup(self.provenance.stop)
        self.admission = patch("assembler_bench.exploratory_space.admit_reserve",
                               return_value={"incremental_bytes": 0,
                                             "free_bytes": 100 * 1024**3,
                                             "admitted_reservation_bytes": 1024**3})
        self.admission.start()
        self.addCleanup(self.admission.stop)
        self.registry = self.make_registry()
        self.source = self.make_source()
        for tool in TOOLS:
            sup.make_handoff(self.px, self.registry, tool)
        baseline = self.root / "baseline.json"
        baseline.write_bytes(canonical_bytes({
            "schema": "ivanka.exploratory.storage-baseline.v1",
            "root": str(self.px), "image_store": str(self.px),
            "workspace": str(self.root), "base_store_bytes": 0,
            "frozen_manifest_sha256":
                "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f",
            "active_job": None}))
        self.baseline = baseline
        self.arm = sched.build_plan(self.registry, self.source, self.px)["pending"][0]

    def make_source(self):
        ids = [f"P{i:03d}" for i in range(1, sched.PHYSICAL_COUNT + 1)]
        canonical = sched.canonical_aliases(ids, "physical")
        synth = [f"S{i:03d}" for i in range(1, sched.SYNTHETIC_COUNT + 1)]
        sc = sched.canonical_aliases(synth, "synthetic")
        return sched.CohortSource(
            [sched.CasePair(i, canonical[i], "physical", self.r1, self.r2) for i in ids],
            [sched.CasePair(i, sc[i], "synthetic", self.r1, self.r2) for i in synth])

    def make_registry(self):
        data = json.loads(REGISTRY.read_text())
        for tool in TOOLS:
            item = next(x for x in data["candidates"] if x["id"] == tool)
            image = self.root / (tool + "-image.json")
            pilot = self.root / (tool + "-pilot.json")
            image.write_bytes(canonical_bytes({
                "schema": "ivanka.exploratory.image.receipt.v1", "tool_id": tool,
                "source_commit": item["source_commit"],
                "adapter_commit": data["adapter_branch_commits"][tool],
                "image_sha256": "b" * 64, "qualifying": False,
                "native_binary_sha256": "a" * 64}))
            pilot.write_bytes(canonical_bytes({
                "schema": "ivanka.exploratory.pilot.receipt.v1", "tool_id": tool,
                "source_commit": item["source_commit"],
                "adapter_commit": data["adapter_branch_commits"][tool],
                "image_sha256": "b" * 64, "qualifying": False,
                "physical": {"source_input_sha256": "c" * 64, "status": "success"},
                "synthetic": {"source_input_sha256": "d" * 64, "status": "success"}}))
            item.update({"status": "pilot", "image_sha256": "b" * 64,
                         "image_evidence": {"path": str(image),
                                            "sha256": sched.sha256_file(image)},
                         "pilot_evidence": {"path": str(pilot),
                                            "sha256": sched.sha256_file(pilot)}})
        path = self.root / "registry.json"
        path.write_bytes(canonical_bytes(data))
        return path

    def supervisor(self, runner):
        return sup.BackgroundSupervisor(self.registry, self.baseline, self.source,
                                        self.px, runner, diagnostics=no_posthoc)

    def start(self, runner):
        # Isolate the single arm under proof from the rest of the live queue.
        with patch.object(sched, "resume", return_value=[self.arm]):
            return self.supervisor(runner).start(armed=True)

    def exhausted(self, reason="measurement_unavailable"):
        sched.record_outcome(self.px, self.arm, None, "failure",
                             failure_reason=reason)
        sched.record_outcome(self.px, self.arm, None, "failure",
                             failure_reason=reason)

    def success_runner(self, calls, seen=None):
        def runner(arm, case):
            calls.append(sched.receipt_id(arm))
            output = self.px / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
            if seen is not None:
                seen.append(sorted(p.name for p in output.iterdir()) if output.is_dir() else [])
            output.mkdir(parents=True, exist_ok=True)
            (output / "conseq.csv").write_bytes(b"region,MAX\nHIV1,ACGT\n")
            return {"outcome": "success", "output_path": output / "conseq.csv",
                    "alias": arm["alias"], "cohort": arm["cohort"],
                    "input_sha256": arm["input_sha256"], "seconds": 1.0,
                    "runner_receipt_sha256": "c" * 64}
        return runner

    def test_third_attempt_requires_authorization(self):
        self.exhausted()
        calls = []
        self.start(self.success_runner(calls))
        self.assertEqual(calls, [])
        self.assertEqual(sched.verify_receipt(self.px, self.arm)["attempt"], 2)
        authz.authorize(self.px, self.arm)
        self.start(self.success_runner(calls))
        self.assertEqual(len(calls), 1)
        receipt = sched.verify_receipt(self.px, self.arm)
        self.assertEqual(receipt["attempt"], 3)
        self.assertEqual(receipt["outcome"], "success")
        for attempt in (1, 2):
            self.assertTrue(sched.attempt_path(self.px, self.arm, attempt).is_file())

    def test_failure_then_stop_archives_output_before_resume_launch(self):
        calls = []

        def failing(arm, case):
            calls.append(sched.receipt_id(arm))
            output = self.px / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "conseq.csv").write_bytes(b"stale-attempt-1\n")
            (self.px / sup.STOP_FILE).write_text("stop\n")
            return {"outcome": "failure", "failure_reason": "disk_stop",
                    "alias": arm["alias"], "cohort": arm["cohort"],
                    "input_sha256": arm["input_sha256"]}

        self.start(failing)
        output = self.px / "outputs" / (self.arm["tool_id"] + "-" + self.arm["alias"])
        self.assertEqual((output / "conseq.csv").read_bytes(), b"stale-attempt-1\n")
        self.assertFalse((self.px / "outputs" / "attempts").exists())
        (self.px / sup.STOP_FILE).unlink()
        seen = []
        self.start(self.success_runner(calls, seen))
        archive = (self.px / "outputs" / "attempts"
                   / (self.arm["tool_id"] + "-" + self.arm["alias"] + ".attempt-001"))
        self.assertEqual((archive / "conseq.csv").read_bytes(), b"stale-attempt-1\n")
        self.assertEqual(seen[0], [])
        self.assertEqual(sched.verify_receipt(self.px, self.arm)["attempt"], 2)
        self.assertEqual(len(calls), 2)

    def test_admission_failure_still_archives_prior_output(self):
        self.exhausted()
        authz.authorize(self.px, self.arm)
        output = self.px / "outputs" / (self.arm["tool_id"] + "-" + self.arm["alias"])
        output.mkdir(parents=True)
        (output / "conseq.csv").write_bytes(b"stale-attempt-2\n")
        with patch.object(sched, "admit_arm", side_effect=ValueError("disk budget")):
            with self.assertRaisesRegex(ValueError, "disk budget"):
                self.start(self.success_runner([]))
        archive = (self.px / "outputs" / "attempts"
                   / (self.arm["tool_id"] + "-" + self.arm["alias"] + ".attempt-002"))
        self.assertEqual((archive / "conseq.csv").read_bytes(), b"stale-attempt-2\n")
        seen = []
        self.start(self.success_runner([], seen))
        self.assertEqual(seen[0], [])
        self.assertEqual(sched.verify_receipt(self.px, self.arm)["attempt"], 3)

    def test_interrupted_archive_state_fails_closed(self):
        self.exhausted()
        authz.authorize(self.px, self.arm)
        output = self.px / "outputs" / (self.arm["tool_id"] + "-" + self.arm["alias"])
        output.mkdir(parents=True)
        archive = self.px / "outputs" / "attempts" / (
            self.arm["tool_id"] + "-" + self.arm["alias"] + ".attempt-002")
        archive.mkdir(parents=True)
        (archive / "conseq.csv").write_bytes(b"preserved\n")
        calls = []
        with self.assertRaisesRegex(ValueError, "already preserved"):
            self.start(self.success_runner(calls))
        self.assertEqual(calls, [])
        self.assertEqual((archive / "conseq.csv").read_bytes(), b"preserved\n")


class GuardPinAndDigestTests(unittest.TestCase):
    def setUp(self):
        AuthorizationTests.setUp(self)

    def test_guard_pin_is_verified_against_deployed_source(self):
        path, _ = authz.authorize(self.root, self.arm)
        record = json.loads(path.read_bytes())
        guard = guard_source.verify()
        self.assertEqual(record["guard_commit"], guard_source.GUARD_COMMIT)
        self.assertEqual(record["guard_commit"],
                         "f861f25b6e62e1266a498340e7d3cf9a09a9087f")
        self.assertEqual(record["reserve_origin_commit"],
                         guard_source.RESERVE_COMMIT)
        self.assertEqual(record["guard_source_sha256"],
                         guard[guard_source.RESERVE_SOURCE])
        self.assertEqual(record["guard_stack_sha256"], guard)
        self.assertIn("benchmarks/fail_closed_guard/watchdog.py",
                      record["guard_stack_sha256"])
        for path in guard_source.NATURAL_EXIT:
            self.assertIn(path, record["guard_stack_sha256"])
        self.assertEqual(len(record["guard_stack_sha256"]), 14)
        with patch.object(guard_source, "EXPECTED",
                          {guard_source.RESERVE_SOURCE: "0" * 64}):
            with self.assertRaisesRegex(ValueError, "guard source drift"):
                authz.authorize(self.root, self.arm)
            with self.assertRaisesRegex(ValueError, "guard source drift"):
                authz.verify(self.root, self.arm)

    def test_watchdog_source_drift_fails_closed(self):
        authz.authorize(self.root, self.arm)
        watchdog = "benchmarks/fail_closed_guard/watchdog.py"
        drifted = dict(guard_source.EXPECTED)
        drifted[watchdog] = "0" * 64
        with patch.object(guard_source, "EXPECTED", drifted):
            with self.assertRaisesRegex(ValueError, "guard source drift"):
                authz.verify(self.root, self.arm)

    def test_natural_exit_monitor_drift_fails_closed(self):
        authz.authorize(self.root, self.arm)
        for path in guard_source.NATURAL_EXIT:
            drifted = dict(guard_source.EXPECTED)
            drifted[path] = "0" * 64
            with patch.object(guard_source, "EXPECTED", drifted):
                with self.assertRaisesRegex(ValueError, "guard source drift"):
                    authz.verify(self.root, self.arm)

    def test_guard_pins_match_deployed_watchdog_tree(self):
        deployed = Path("/workspace/ivanka-guard-pr530-staged-20261126")
        if not deployed.is_dir():
            self.skipTest("deployed watchdog checkout not present")
        guard = _REAL_GUARD_VERIFY(root=deployed)
        self.assertEqual(guard, dict(guard_source.EXPECTED))
        for name, digest in guard.items():
            self.assertEqual(
                hashlib.sha256((deployed / name).read_bytes()).hexdigest(),
                digest, name)

    def test_every_preserved_attempt_digest_is_bound(self):
        authz.authorize(self.root, self.arm)
        record = authz.verify(self.root, self.arm)
        self.assertEqual(set(record["preserved_attempt_sha256"]), {"1", "2"})
        self.assertEqual(record["preserved_attempt_sha256"]["1"],
                         hashlib.sha256(self.first_bytes).hexdigest())
        self.assertEqual(record["preserved_attempt_sha256"]["2"],
                         hashlib.sha256(self.prior_bytes).hexdigest())
        first = sched.attempt_path(self.root, self.arm, 1)
        drifted = json.loads(first.read_bytes())
        drifted["seconds"] = 1.0
        first.write_bytes(canonical_bytes(drifted))
        with self.assertRaisesRegex(ValueError, "does not bind this arm"):
            authz.verify(self.root, self.arm)

    def test_one_shot_consumption_is_durable_and_exclusive(self):
        authz.authorize(self.root, self.arm)
        marker = authz.dispatch_path(self.root, self.arm)
        self.assertFalse(marker.is_file())
        self.assertEqual(authz.claim(self.root, self.arm), marker)
        self.assertIsNone(authz.verify(self.root, self.arm))
        self.assertIsNotNone(authz.verify_spent(self.root, self.arm))
        with self.assertRaisesRegex(ValueError, "already consumed"):
            authz.claim(self.root, self.arm)
        sched.record_outcome(self.root, self.arm, None, "failure",
                             failure_reason="disk_stop")
        self.assertEqual(sched.verify_receipt(self.root, self.arm)["attempt"], 3)
        record = json.loads(marker.read_bytes())
        record["authorization_sha256"] = "0" * 64
        marker.write_bytes(canonical_bytes(record))
        with self.assertRaisesRegex(ValueError, "does not bind authorization"):
            sched.verify_receipt(self.root, self.arm)


class OneShotDispatchTests(unittest.TestCase):
    make_registry = SupervisorRetryTests.make_registry
    make_source = SupervisorRetryTests.make_source
    supervisor = SupervisorRetryTests.supervisor
    start = SupervisorRetryTests.start
    exhausted = SupervisorRetryTests.exhausted
    success_runner = SupervisorRetryTests.success_runner

    def setUp(self):
        SupervisorRetryTests.setUp(self)

    def test_claim_is_durable_before_spawn_and_interrupted_dispatch_stays_spent(self):
        self.exhausted()
        authz.authorize(self.px, self.arm)
        marker = authz.dispatch_path(self.px, self.arm)
        calls = []

        def interrupted(arm, case):
            self.assertTrue(marker.is_file())
            self.assertIsNone(authz.verify(self.px, arm))
            calls.append(sched.receipt_id(arm))
            raise RuntimeError("spawn interrupted")

        with self.assertRaisesRegex(RuntimeError, "spawn interrupted"):
            self.start(interrupted)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(authz.verify(self.px, self.arm))
        self.assertIsNotNone(authz.verify_spent(self.px, self.arm))
        again = []
        self.start(self.success_runner(again))
        self.assertEqual(again, [])
        self.assertEqual(sched.verify_receipt(self.px, self.arm)["attempt"], 2)


class SupersessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.arm = arm_of(IDBA_ATTEMPT_2)
        self.receipt = dict(IDBA_ATTEMPT_2)
        write_preserved(self.root, self.arm, IDBA_ATTEMPT_1)
        write_preserved(self.root, self.arm, IDBA_ATTEMPT_2)
        write_receipt(self.root, self.arm, IDBA_ATTEMPT_2)
        authz.authorize(self.root, self.arm)
        authz.claim(self.root, self.arm)
        self.record = authz.verify_spent(self.root, self.arm)
        base = {key: self.arm[key] for key in (
            "tool_id", "source_commit", "adapter_commit", "image_sha256")}
        self.prior = dict(base, cohort="real", canonical_alias="R001",
                          outcome="failure",
                          failure_reason="measurement_unavailable",
                          score=None, attempt=2,
                          diagnostics={"peak_ram_observed_mib": 263.0,
                                       "soft_clips_count": 12})
        self.success = dict(
            base, cohort="real", canonical_alias="R001",
            outcome="success", score=9000.0, attempt=3,
            retry_authorization_sha256=self.record["authorization_sha256"],
            canonical_manifest_sha256=PHYSICAL_MANIFEST,
            read_sha256=dict(self.arm["input_sha256"]),
            score_origin=PHYSICAL_SCORE, reference_panel_sha256=PANEL,
            binding_receipts=5,
            diagnostics={"peak_ram_observed_mib": 270.0})

    def report(self):
        return {"runs": [{"id": "r", "cohort": "real", "tools": ["idba-ud"],
                          "expected_sample_count": 1,
                          "samples": [{"alias": "R001", "failures": ["idba-ud"],
                                       "score": {"idba-ud": None},
                                       "seconds": {"idba-ud": None},
                                       "outcome": "failure"}]}]}

    def evidence(self, case):
        return {"schema": EVIDENCE_SCHEMA,
                "cohorts": {"real": {"assemblers": ["idba-ud"]}},
                "assemblers": [{"id": "idba-ud", "cases": [case]}]}

    def test_supersession_preserves_history_and_is_idempotent(self):
        cases = [json.loads(json.dumps(self.prior))]
        self.assertTrue(ingest.reconcile_case(
            cases, self.success, self.root, self.receipt))
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["outcome"], "success")
        self.assertEqual(cases[0]["superseded"], [self.prior])
        self.assertEqual(cases[0]["superseded"][0]["diagnostics"],
                         self.prior["diagnostics"])
        self.assertFalse(ingest.reconcile_case(
            cases, self.success, self.root, self.receipt))

    def test_scientific_failure_and_success_are_never_superseded(self):
        for prior in (dict(self.prior, failure_reason="error"),
                      dict(self.prior, outcome="success", score=1.0,
                           failure_reason=None)):
            cases = [prior]
            self.assertFalse(ingest.reconcile_case(
                cases, self.success, self.root, self.receipt))
            self.assertEqual(cases[0], prior)

    def test_unauthorized_or_unconsumed_retry_never_supersedes(self):
        for case in (dict(self.success, retry_authorization_sha256="0" * 64),
                     {key: value for key, value in self.success.items()
                      if key != "retry_authorization_sha256"}):
            cases = [json.loads(json.dumps(self.prior))]
            self.assertFalse(ingest.reconcile_case(
                cases, case, self.root, self.receipt))
        fresh = self.root / "fresh"
        write_preserved(fresh, self.arm, IDBA_ATTEMPT_1)
        write_preserved(fresh, self.arm, IDBA_ATTEMPT_2)
        write_receipt(fresh, self.arm, IDBA_ATTEMPT_2)
        _, digest = authz.authorize(fresh, self.arm)
        cases = [json.loads(json.dumps(self.prior))]
        self.assertFalse(ingest.reconcile_case(
            cases, dict(self.success, retry_authorization_sha256=digest),
            fresh, self.receipt))

    def test_public_view_retires_failure_and_keeps_history(self):
        cases = [json.loads(json.dumps(self.prior))]
        ingest.reconcile_case(cases, self.success, self.root, self.receipt)
        merged, joined = merge_evidence(self.report(), self.evidence(cases[0]))
        sample = merged["runs"][0]["samples"][0]
        self.assertEqual(sample["score"]["idba-ud"], 9000.0)
        self.assertNotIn("idba-ud", sample["failures"])
        self.assertEqual(sample["outcome"], "success")
        row = sample["measurement_evidence"]["idba-ud"]
        self.assertEqual(row["superseded"], [self.prior])
        self.assertEqual(row["attempt"], 3)
        self.assertEqual(joined, [("r", "idba-ud", "R001")])

    def test_public_view_rejects_scientific_supersession(self):
        case = dict(self.success,
                    superseded=[dict(self.prior, failure_reason="error")])
        with self.assertRaisesRegex(ValueError, "only infrastructure failures"):
            merge_evidence(self.report(), self.evidence(case))


class PublicationCoordinationTests(unittest.TestCase):
    def test_failure_order_is_roster_order_and_idempotent(self):
        tools = ["zeta", "alpha", "omega"]
        case = {"cohort": "real", "canonical_alias": "R001",
                "canonical_manifest_sha256": PHYSICAL_MANIFEST,
                "read_sha256": {"R1": "a" * 64, "R2": "b" * 64},
                "binding_receipts": 2, "score_origin": PHYSICAL_SCORE,
                "reference_panel_sha256": PANEL, "outcome": "failure",
                "failure_reason": "error", "score": None}
        evidence = {"schema": EVIDENCE_SCHEMA,
                    "cohorts": {"real": {"assemblers": tools}},
                    "assemblers": [{"id": tool, "cases": [dict(case)]}
                                   for tool in reversed(tools)]}
        report = {"runs": [{"id": "test", "cohort": "real", "tools": tools,
                            "expected_sample_count": 1,
                            "samples": [{"alias": "R001",
                                         "failures": ["omega", "alpha"],
                                         "score": {}, "seconds": {}}]}]}
        merged, _ = merge_evidence(report, evidence)
        self.assertEqual(merged["runs"][0]["samples"][0]["failures"], tools)
        repeated, joined = merge_evidence(merged, evidence)
        self.assertEqual(repeated, merged)
        self.assertEqual(joined, [])


if __name__ == "__main__":
    unittest.main()
