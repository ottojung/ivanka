"""Source-only tests for the reference-based MiCall remap execution plan.

No MiCall process, container, truth genome, frozen result or image is touched.
These tests build plans from audited constants and tiny fabricated digests,
then check that invocation, guard, provenance, missingness and row identities
cannot drift toward a de novo arm or a qualification decision.
"""
import importlib.util
import pathlib
import tempfile
import unittest

from assembler_bench import guarded_canary_launcher as launcher
from assembler_bench import remap_runner as runner
from assembler_bench.px_ram_semantics import (
    COMPARABLE_KEY, COMPARABLE_METHOD, COMPARABLE_METHOD_VERSION,
    COMPARABLE_SCOPE, METHOD_KEY, SCOPE_KEY, VERSION_KEY,
)

STAMP = "20261126T223000000000Z"
TOKEN = "abc123"
R1_NAME = "R001_L001_R1_001.fastq.gz"
R2_NAME = "R001_L001_R2_001.fastq.gz"
R1_SHA = "a" * 64
R2_SHA = "b" * 64


def make_read_mount(root):
    """Two original FASTQ basenames, hard-linked, no sample metadata."""
    source = root / "original-sample"
    source.mkdir()
    for name in (R1_NAME, R2_NAME):
        (source / name).write_bytes(b"@read\nACGT\n+\nIIII\n")
    return runner.isolate_reads(
        source_dir=source, r1_name=R1_NAME, r2_name=R2_NAME,
        r1_sha256=launcher.sha256_file(source / R1_NAME),
        r2_sha256=launcher.sha256_file(source / R2_NAME),
        destination_root=root)


class RemapPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="remap-runner-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.reads = make_read_mount(self.root)
        self.attempt = self.root / "attempt"
        self.attempt.mkdir()
        self.timer = self.root / "timer.py"
        self.timer.write_text("# timer\n")
        self.case = runner.Case(
            alias="R001", cohort="real",
            r1_sha256=launcher.sha256_file(self.reads / R1_NAME),
            r2_sha256=launcher.sha256_file(self.reads / R2_NAME),
            reads_dir=str(self.reads), attempt_dir=str(self.attempt),
            timer=str(self.timer), cidfile=str(self.attempt / "cid"),
            storage_root=str(self.root / "store"), runroot=str(self.root / "runroot"),
            name="podman-name-remap-R001-test",
            r1_name=R1_NAME, r2_name=R2_NAME,
        )
        self.manifest = runner.input_manifest([self.case])
        self.plan = runner.plan_case(self.case, self.manifest,
                                     stamp=STAMP, token=TOKEN)

    def test_plan_is_frozen_invocation_minus_only_denovo_token(self):
        argv = self.plan["argv"]
        self.assertNotIn("--denovo", argv)
        for token in ("--keep_scratch", "--bad_cycles_csv",
                      "/results/bad_cycles.csv", "--all_projects",
                      runner.IMAGE_DIGEST):
            self.assertIn(token, argv)
        self.assertEqual(argv[argv.index("--cpus=2")], "--cpus=2")
        self.assertEqual(argv[argv.index("--memory=4000000000")],
                         "--memory=4000000000")
        self.assertEqual(argv[argv.index("--timeout") + 1], "2398")
        mounts = [argv[i + 1] for i, token in enumerate(argv[:-1])
                  if token == "-v"]
        allowed = frozenset(t for t in argv if t not in mounts)
        sources = frozenset(m.rsplit(":", 2)[0] for m in mounts)
        self.assertTrue(launcher.assert_reference_blind(
            argv, allowed_values=allowed, expected_sources=sources,
            denovo=False, reads=(R1_NAME, R2_NAME)))
        self.assertEqual(self.plan["guard"]["wall_seconds"], 2400)
        self.assertEqual(self.plan["guard"]["rss_limit_bytes"], 4_000_000_000)
        self.assertIs(self.plan["guard"]["kernel_enforcement"], False)
        self.assertTrue(self.plan["run_id"].startswith("remap-real-"))
        self.assertFalse(self.plan["executed"])

    def test_read_mount_isolated_and_hash_pinned(self):
        names = sorted(p.name for p in self.reads.iterdir())
        self.assertEqual(names, sorted([R1_NAME, R2_NAME]))
        self.assertTrue(launcher.verify_isolated_reads(
            self.reads, reads=(R1_NAME, R2_NAME),
            sha256s=(self.case.r1_sha256, self.case.r2_sha256)))
        # A historical sample file or a symlink must never reach the mount.
        (self.reads / "unstitched_contigs.csv").write_text("x")
        with self.assertRaises(launcher.UnsafeCommand):
            launcher.verify_isolated_reads(
                self.reads, reads=(R1_NAME, R2_NAME),
                sha256s=(self.case.r1_sha256, self.case.r2_sha256))
        (self.reads / "unstitched_contigs.csv").unlink()

    def test_source_image_and_reference_provenance_are_audited(self):
        source = self.plan["source"]
        self.assertEqual(source["commit"], runner.SOURCE_COMMIT)
        self.assertEqual(source["sample_py_sha256"], runner.SAMPLE_PY_SHA256)
        self.assertEqual(source["projects_json_sha256"],
                         runner.PROJECTS_JSON_SHA256)
        image = self.plan["image"]
        self.assertEqual(image["id"], runner.IMAGE_ID)
        self.assertEqual(image["digest"], runner.IMAGE_DIGEST)
        self.assertEqual(image["reuse"], "frozen-clinical-base")
        self.assertFalse(image["rebuilt"])
        reference = self.plan["reference"]
        self.assertEqual(reference["panel_sha256"], runner.PANEL_SHA256)
        self.assertFalse(reference["truth_mounted"])
        self.assertFalse(reference["synthetic_truth_mounted"])
        self.assertEqual(self.plan["qualification_claim"], "NONE")

    def test_input_manifest_binds_reads_not_truth(self):
        self.assertEqual(len(self.manifest), 64)
        other = runner.Case(**{**self.case.__dict__, "r2_sha256": "c" * 64,
                               "r2_name": R2_NAME})
        self.assertNotEqual(self.manifest, runner.input_manifest([other]))
        with self.assertRaises(ValueError):
            runner.input_manifest([])
        with self.assertRaises(ValueError):
            runner.plan_case(self.case, "not-a-digest", stamp=STAMP, token=TOKEN)

    def test_capacity_gate_blocks_below_reserve(self):
        decision = runner.capacity_decision(32_334_376_960)
        self.assertFalse(decision["capacity_admitted"])
        self.assertGreater(decision["deficit_bytes"], 0)
        self.assertTrue(decision["requires_exclusive_shared_slot"])
        self.assertTrue(decision["requires_independent_review"])
        self.assertFalse(decision["executed"])
        allowed = runner.capacity_decision(34_359_738_368)
        self.assertTrue(allowed["capacity_admitted"])
        self.assertFalse(allowed["executed"])
        with self.assertRaises(ValueError):
            runner.capacity_decision(-1)


class RemapReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="remap-receipt-test-")
        self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        reads = make_read_mount(root)
        self.case = runner.Case(
            alias="H001", cohort="synthetic",
            r1_sha256=launcher.sha256_file(reads / R1_NAME),
            r2_sha256=launcher.sha256_file(reads / R2_NAME),
            reads_dir=str(reads), attempt_dir=str(root / "attempt"),
            timer=str(root / "timer.py"), cidfile=str(root / "cid"),
            storage_root=str(root / "store"), runroot=str(root / "runroot"),
            name="podman-name-remap-H001-test",
            r1_name=R1_NAME, r2_name=R2_NAME,
        )
        self.plan = runner.plan_case(
            self.case, runner.input_manifest([self.case]),
            stamp=STAMP, token=TOKEN)

    def valid_resource(self, **overrides):
        resource = {
            "peak_rss_bytes": 3_100_000_000,
            "samples": 12,
            "observation_ended": True,
            "bound_cid": "a" * 64,
            "peak_ram_method": "container_process_tree_sampled_rss",
            "peak_ram_method_version": "ivanka.px.whole-container-rss.v2",
            "peak_ram_scope": "whole_container_process_tree",
            "guard_receipt": {
                "bound_cid": "a" * 64,
                "rss_limit_bytes": 4_000_000_000,
                "wall_seconds": 2400,
                "cpu_allocation": 2,
                "kernel_enforcement": False,
            },
        }
        resource.update(overrides)
        return resource

    def measured(self, diagnostics=None, resource=None, outputs=None, **kwargs):
        return runner.build_receipt(
            self.plan, status="measured", score=91.25, seconds=812.5,
            diagnostics=diagnostics or {"average_read_depth": 42.0},
            outputs=outputs or {"conseq_csv_sha256": "e" * 64},
            resource=self.valid_resource() if resource is None else resource,
            **kwargs)

    def test_contig_only_metrics_are_null_never_zero(self):
        receipt = self.measured(diagnostics={
            "average_read_depth": 42.0,
            "final_contig_count": 0,
            "unstitched_contig_count": 0,
            "nuc_q15_mean_depth": 12.0,
        })
        for key in runner.NA_METRICS:
            self.assertIsNone(receipt["diagnostics"][key])
            self.assertIn(key, receipt["unavailable"])
        self.assertEqual(receipt["diagnostics"]["average_read_depth"], 42.0)
        self.assertEqual(receipt["outputs"]["unstitched_contigs"],
                         "not-applicable")
        self.assertNotIn("unstitched_contigs.csv", receipt["outputs"])

    def test_peak_ram_is_attested_container_sample_only(self):
        receipt = self.measured()
        diag = receipt["diagnostics"]
        self.assertEqual(diag[METHOD_KEY], COMPARABLE_METHOD)
        self.assertEqual(diag[VERSION_KEY], COMPARABLE_METHOD_VERSION)
        self.assertEqual(diag[SCOPE_KEY], COMPARABLE_SCOPE)
        self.assertEqual(diag[COMPARABLE_KEY], round(3_100_000_000 / 1048576, 6))
        self.assertIsNone(receipt["failure_reason"])
        with self.assertRaises(ValueError):
            runner.build_receipt(
                self.plan, status="measured", score=1.0, seconds=2.0,
                outputs={"conseq_csv_sha256": "e" * 64},
                resource=self.valid_resource(peak_rss_bytes=5_000_000_000))

    def test_failed_and_unavailable_cases_keep_no_measurement(self):
        for status in ("failed", "unavailable"):
            receipt = runner.build_receipt(
                self.plan, status=status, failure_reason="no final MAX consensus")
            self.assertIsNone(receipt["score"])
            self.assertIsNone(receipt["seconds"])
            self.assertEqual(receipt["failure_reason"],
                             "no final MAX consensus")
            with self.assertRaises(ValueError):
                runner.build_receipt(
                    self.plan, status=status, score=0.0, seconds=1.0,
                    failure_reason="x")
        with self.assertRaises(ValueError):
            runner.build_receipt(self.plan, status="measured", score=-1, seconds=1)

    def test_rows_are_bound_distinct_and_tamper_evident(self):
        receipt = self.measured()
        rows = runner.build_rows(
            [receipt], run_id=self.plan["run_id"], cohort="synthetic")
        self.assertEqual(rows["schema"], runner.ROWS_SCHEMA)
        self.assertEqual(rows["tool_id"], "micall-remap")
        self.assertEqual(rows["cases"][0]["alias"], "H001")
        self.assertEqual(rows["cases"][0]["receipt_sha256"],
                         receipt["receipt_sha256"])
        tampered = dict(receipt, score=999.0)
        with self.assertRaises(ValueError):
            runner.build_rows([tampered], run_id=self.plan["run_id"],
                              cohort="synthetic")
        with self.assertRaises(ValueError):
            runner.build_rows([receipt], run_id="remap-real-other-abc123",
                              cohort="synthetic")
        attempted = runner.build_receipt(self.plan, status="attempted",
                                         failure_reason="never launched")
        with self.assertRaises(ValueError):
            runner.build_rows([attempted], run_id=self.plan["run_id"],
                              cohort="synthetic")

    def test_rows_carry_display_boundary_fields_without_skipping(self):
        # The display registry rejects rows lacking these five fields. Assert
        # them locally so an isolated runner PR catches the defect even when
        # the parallel display module is not in this checkout.
        rows = runner.build_rows(
            [self.measured()], run_id=self.plan["run_id"], cohort="synthetic")
        self.assertEqual(rows["mode"], "reference-based")
        self.assertIs(rows["denovo"], False)
        self.assertEqual(rows["image_sha256"], runner.IMAGE_ID)
        self.assertEqual(rows["frozen_master_commit"], runner.SOURCE_COMMIT)
        self.assertEqual(len(rows["invocation_sha256"]), 64)

    def test_rejects_nonfinite_score_time_and_invalid_success_evidence(self):
        base = dict(outputs={"conseq_csv_sha256": "e" * 64}, resource=self.valid_resource())
        for score in (float("nan"), float("inf"), -float("inf"), "1"):
            with self.assertRaises(ValueError):
                runner.build_receipt(self.plan, status="measured", score=score, seconds=1.0, **base)
        for seconds in (float("nan"), float("inf"), 0.0, -1.0, 2401.0):
            with self.assertRaises(ValueError):
                runner.build_receipt(self.plan, status="measured", score=1.0, seconds=seconds, **base)
        with self.assertRaises(ValueError):
            runner.build_receipt(self.plan, status="measured", score=1.0, seconds=1.0,
                                 resource=self.valid_resource(), outputs={})
        with self.assertRaises(ValueError):
            runner.build_receipt(self.plan, status="measured", score=1.0, seconds=1.0,
                                 resource=self.valid_resource(),
                                 outputs={"conseq_csv_sha256": "not-a-hash"})

    def test_rejects_unattested_or_launcher_ram_and_missing_guard_binding(self):
        base = dict(status="measured", score=1.0, seconds=1.0,
                    outputs={"conseq_csv_sha256": "e" * 64})
        with self.assertRaises(ValueError):
            runner.build_receipt(self.plan, resource={"peak_rss_bytes": 1, "samples": 2,
                                 "observation_ended": True, "bound_cid": "a"*64,
                                 "peak_ram_method": "launcher_process_group_rss",
                                 "peak_ram_method_version": "v0",
                                 "peak_ram_scope": "launcher_process_group",
                                 "guard_receipt": self.valid_resource()["guard_receipt"]}, **base)
        for bad in (
            self.valid_resource(observation_ended=False),
            self.valid_resource(samples=1),
            self.valid_resource(bound_cid="short"),
            self.valid_resource(peak_ram_scope="launcher_process_group"),
            {k: v for k, v in self.valid_resource().items() if k != "guard_receipt"},
        ):
            with self.assertRaises(ValueError):
                runner.build_receipt(self.plan, resource=bad, **base)
        bad_guard = self.valid_resource()
        bad_guard["guard_receipt"] = dict(bad_guard["guard_receipt"], bound_cid="b" * 64)
        with self.assertRaises(ValueError):
            runner.build_receipt(self.plan, resource=bad_guard, **base)

    def test_emitted_rows_satisfy_display_registry_when_present(self):
        if importlib.util.find_spec("assembler_bench.remap_diagnostic") is None:
            self.skipTest("display registry module belongs to the parallel PR")
        from assembler_bench import remap_diagnostic as display
        rows = runner.build_rows(
            [self.measured()], run_id=self.plan["run_id"], cohort="synthetic")
        display.validate_rows(rows)


if __name__ == "__main__":
    unittest.main()
