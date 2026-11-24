"""Inert proofs of the source-attested PX executable integration."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import exploratory_policy, px_metrics
from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_execution as exe
from assembler_bench import px_supervisor as sup

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "benchmarks/assembler_bench/exploratory_candidates.json"
TOOLS = ("skesa", "minia")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    return path


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.physical = self.root / "physical"
        self.synthetic = self.root / "synthetic"
        self.physical.mkdir()
        self.synthetic.mkdir()
        self.px = self.root / "px"
        self.px.mkdir()
        self._make_physical()
        self._make_synthetic()
        self.policy = patch.object(exploratory_policy, "PROVENANCE_ROOT", self.root)
        self.manifest_patch = patch.object(
            sched, "PHYSICAL_MANIFEST_SHA256",
            sha(self.physical / "manifest.tsv"))
        self.cohort_patch = patch.object(
            sched, "SYNTHETIC_COHORT_SHA256",
            sha(self.synthetic / "cohort.json"))
        self.cohort_path = patch.object(
            sched, "SYNTHETIC_COHORT", self.synthetic / "cohort.json")
        for item in (self.policy, self.manifest_patch,
                     self.cohort_patch, self.cohort_path):
            item.start()
            self.addCleanup(item.stop)

    def _make_physical(self):
        self.sample_ids = [f"sample-{i:03d}" for i in range(1, 199)]
        shuffled = self.sample_ids[::-1]
        rows = "sample\tkive_run_id\n" + "".join(
            f"{sample}\trun-{sample}\n" for sample in shuffled)
        (self.physical / "manifest.tsv").write_text(rows)
        for sample in shuffled:
            folder = self.physical / "samples" / sample
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{sample}_L001_R1_001.fastq.gz").write_bytes(b"@r1\n")
            (folder / f"{sample}_L001_R2_001.fastq.gz").write_bytes(b"@r2\n")

    def _make_synthetic(self):
        self.case_ids = [f"case-{i:03d}" for i in range(1, 465)]
        records = []
        for case_id in reversed(self.case_ids):
            reads = self.synthetic / case_id / "reads"
            reads.mkdir(parents=True)
            r1, r2 = reads / "R1.fastq.gz", reads / "R2.fastq.gz"
            r1.write_bytes(b"@s1\n")
            r2.write_bytes(b"@s2\n")
            records.append({"id": case_id, "sha256": {
                "reads/R1.fastq.gz": sha(r1), "reads/R2.fastq.gz": sha(r2),
                "hidden-truth/haplotypes.fasta": "f" * 64}})
        write_json(self.synthetic / "cohort.json", {"cases": records})

    def source(self):
        return exe.load_cohort(self.physical, self.synthetic)

    def promoted_registry(self):
        data = json.loads(REGISTRY.read_text())
        for tool in TOOLS:
            item = next(x for x in data["candidates"] if x["id"] == tool)
            image = {"schema": "ivanka.exploratory.image.receipt.v1",
                     "tool_id": tool, "source_commit": item["source_commit"],
                     "adapter_commit": data["adapter_branch_commits"][tool],
                     "image_sha256": "b" * 64, "qualifying": False,
                     "native_binary_sha256": "a" * 64}
            ipath = write_json(self.root / "receipts" / (tool + "-image.json"),
                               image)
            pilot = {"schema": "ivanka.exploratory.pilot.receipt.v1",
                     "tool_id": tool, "source_commit": item["source_commit"],
                     "adapter_commit": data["adapter_branch_commits"][tool],
                     "image_sha256": "b" * 64, "qualifying": False,
                     "physical": {"source_input_sha256": "c" * 64,
                                  "status": "success"},
                     "synthetic": {"source_input_sha256": "d" * 64,
                                   "status": "success"}}
            ppath = write_json(self.root / "receipts" / (tool + "-pilot.json"),
                               pilot)
            item.update(status="pilot", image_sha256="b" * 64,
                        image_evidence={"path": str(ipath), "sha256": sha(ipath)},
                        pilot_evidence={"path": str(ppath), "sha256": sha(ppath)})
        return write_json(self.root / "registry.json", data)

    def baseline(self):
        return write_json(self.root / "baseline.json", {
            "schema": "ivanka.exploratory.storage-baseline.v1",
            "root": str(self.px), "image_store": str(self.px),
            "workspace": str(self.root), "base_store_bytes": 0,
            "frozen_manifest_sha256": "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f",
            "active_job": None})

    def test_loaders_produce_one_based_original_aliases(self):
        physical = exe.load_physical(self.physical)
        synthetic = exe.load_synthetic(self.synthetic)
        self.assertEqual(len(physical), 198)
        self.assertEqual(len(synthetic), 464)
        self.assertEqual({c.alias for c in physical},
                         {sched._alias(i, "physical") for i in range(1, 199)})
        self.assertEqual({c.alias for c in synthetic},
                         {sched._alias(i, "synthetic") for i in range(1, 465)})
        self.assertEqual(next(c for c in physical if c.source_id == "sample-053").alias,
                         "PX-R053")
        ordered = sorted(self.case_ids)
        self.assertEqual(next(c for c in synthetic
                              if c.source_id == ordered[191]).alias, "PX-H192")
        self.assertEqual(len(exe.load_cohort(self.physical, self.synthetic)
                             .cases("physical")), 198)

    def test_loader_order_is_canonical_even_if_input_manifests_are_shuffled(self):
        physical_manifest = self.physical / "manifest.tsv"
        rows = physical_manifest.read_text().splitlines()
        physical_manifest.write_text("\n".join([rows[0], *reversed(rows[1:])]) + "\n")
        cohort_manifest = self.synthetic / "cohort.json"
        cohort_data = json.loads(cohort_manifest.read_text())
        cohort_data["cases"].reverse()
        cohort_manifest.write_text(json.dumps(cohort_data))
        with (patch.object(sched, "PHYSICAL_MANIFEST_SHA256", sha(physical_manifest)),
              patch.object(sched, "SYNTHETIC_COHORT_SHA256", sha(cohort_manifest))):
            physical = exe.load_physical(self.physical)
            synthetic = exe.load_synthetic(self.synthetic)
        self.assertEqual([c.alias for c in physical],
                         [sched._alias(i, "physical") for i in range(1, 199)])
        self.assertEqual([c.alias for c in synthetic],
                         [sched._alias(i, "synthetic") for i in range(1, 465)])

    def test_changed_source_sha_is_rejected(self):
        (self.physical / "manifest.tsv").write_text("sample\nother\n")
        with self.assertRaisesRegex(ValueError, "manifest SHA256 changed"):
            exe.load_physical(self.physical)
        self._make_physical()
        with (patch.object(sched, "PHYSICAL_MANIFEST_SHA256", "0" * 64),
              self.assertRaisesRegex(ValueError, "manifest SHA256 changed")):
            exe.load_physical(self.physical)

    def test_assembler_argv_contains_only_reads_and_no_truth(self):
        case = exe.load_physical(self.physical)[0]
        argv = exe.micall_argv("skesa", "b" * 64, case, self.px / "out")
        self.assertEqual(argv[:2], ["podman", "run"])
        self.assertNotIn("--detach", argv)
        for flag in ("--memory", "--network"):
            self.assertFalse(any(a == flag or str(a).startswith(flag + "=")
                                 for a in argv))
        text = json.dumps(argv)
        self.assertNotIn("truth", text)
        self.assertNotIn("hidden", text)
        self.assertNotIn("manifest.tsv", text)
        with self.assertRaisesRegex(ValueError, "reference or truth"):
            exe.assert_reference_blind(["podman", "run", "hidden-truth"])

    def test_run_guarded_delegates_once_and_hashes_final_max(self):
        case = exe.load_physical(self.physical)[0]
        arm = {"tool_id": "skesa", "cohort": "physical",
               "alias": case.alias, "input_sha256": case.input_hashes(),
               "source_commit": "a" * 40, "adapter_commit": "a" * 40,
               "image_sha256": "b" * 64}
        output = self.px / "out"
        output.mkdir()
        calls = []

        def operate(registry, baseline, tool, mode, argv, reserve):
            calls.append((tool, mode, argv, reserve))
            (output / "conseq.csv").write_bytes(b"final-MAX\n")
            (output / "timing.json").write_text(
                json.dumps({"exit_code": 0, "seconds": 12.5}))
            return {"status": "finished", "peak_rss": 1_000_000,
                    "log_sha256": "c" * 64}

        report = exe.run_guarded("reg", "base", arm, case, output, operate)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "pilot")
        self.assertEqual(report["outcome"], "success")
        self.assertEqual(Path(report["output_path"]).name, sched.MAX_ARTIFACT)
        self.assertEqual(report["seconds"], 12.5)
        self.assertEqual(report["alias"], case.alias)

    def test_failure_classification_is_bounded(self):
        case = exe.load_synthetic(self.synthetic)[0]
        arm = {"tool_id": "skesa", "cohort": "synthetic",
               "alias": case.alias, "input_sha256": case.input_hashes(),
               "source_commit": "a" * 40, "adapter_commit": "a" * 40,
               "image_sha256": "b" * 64}
        for reason, expected in (("wall_limit", "wall_limit"),
                                 ("disk_limit", "disk_stop"),
                                 ("observed_rss_limit", "observed_rss_limit"),
                                 ("measurement_unavailable", "measurement_unavailable"),
                                 ("unexpected", "error")):
            with self.subTest(reason=reason):
                report = exe.run_guarded("reg", "base", arm, case,
                                         self.px / "out",
                                         lambda *a, reason=reason: {
                                             "status": "killed",
                                             "reason": reason})
                self.assertEqual(report["outcome"], "failure")
                self.assertIn(report["failure_reason"], sched.FAILURE_REASONS)
                self.assertEqual(report["failure_reason"], expected)
        output = self.px / "out"
        output.mkdir(exist_ok=True)
        report = exe.run_guarded("reg", "base", arm, case, output,
                                 lambda *a: {"status": "finished"})
        self.assertEqual(report["failure_reason"], "no_final_max")

    def test_supervisor_never_repeats_terminal_arms(self):
        registry = self.promoted_registry()
        for tool in TOOLS:
            sup.make_handoff(self.px, registry, tool)
        admission = patch("assembler_bench.exploratory_space.admit",
                          return_value={"incremental_bytes": 0,
                                        "free_bytes": 100 * 1024**3,
                                        "admitted_reservation_bytes": 1024**3})
        admission.start()
        self.addCleanup(admission.stop)
        calls = []

        def operate(registry_path, baseline, tool, mode, argv, reserve):
            mount = next(a for a in argv if str(a).endswith(":/results:rw"))
            output = Path(str(mount).split(":")[0])
            calls.append(str(output))
            if len(calls) == 2:
                (self.px / sup.STOP_FILE).write_text("stop\n")
            (output / "conseq.csv").write_bytes(b"MAX\n")
            (output / "timing.json").write_text(
                json.dumps({"exit_code": 0, "seconds": 3.0}))
            return {"status": "finished", "peak_rss": 1_000_000,
                    "log_sha256": "c" * 64}

        first = sup.BackgroundSupervisor(
            registry, self.baseline(), self.source(), self.px,
            exe.SupervisedRunner(registry, self.baseline(), operate, self.px),
            reserve_bytes=exe.RESERVE_BYTES).start(armed=True)
        self.assertEqual(len(first["completed"]), 2)
        self.assertEqual(len(calls), 2)
        pending = sched.build_plan(registry, self.source(),
                                   self.px)["pending"]
        self.assertTrue(all(a["cohort"] == "physical"
                            for a in pending[:394]))
        self.assertTrue(all(a["cohort"] == "synthetic"
                            for a in pending[394:]))
        (self.px / sup.STOP_FILE).unlink()

        resumed = []

        def second_operate(registry_path, baseline, tool, mode, argv, reserve):
            mount = next(a for a in argv if str(a).endswith(":/results:rw"))
            output = str(mount).split(":")[0]
            resumed.append(output)
            (self.px / sup.STOP_FILE).write_text("stop\n")
            return {"status": "finished"}

        second = sup.BackgroundSupervisor(
            registry, self.baseline(), self.source(), self.px,
            exe.SupervisedRunner(registry, self.baseline(), second_operate,
                                 self.px)).start(armed=True)
        self.assertEqual(len(second["completed"]), 1)
        self.assertFalse(set(resumed) & set(calls[:2]))

    def test_posthoc_scoring_and_cleanup_after_hashes(self):
        plan = sched.build_plan(self.promoted_registry(), self.source(), self.px)
        arm = plan["pending"][0]
        case = self.source().case(arm["cohort"], arm["alias"])
        output = self.px / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
        output.mkdir(parents=True)
        (output / "conseq.csv").write_bytes(b"MAX\n")
        sched.record_outcome(self.px, arm, output / "conseq.csv", "success",
                             seconds=3.0)

        class Scorer:
            source_sha256 = "e" * 64

            def score(self, alias, cohort, output_sha256):
                return {"alias": alias, "outcome": "success",
                        "score": 101.5, "seconds": 3.0}

        path, digest = exe.posthoc(self.px, arm, Scorer(), "e" * 64)
        self.assertEqual(sched.sha256_file(path), digest)
        exe.extract_diagnostics(self.px, arm, output,
                                fastq_sha256=[case.input_hashes()["R1"],
                                              case.input_hashes()["R2"]])
        scratch = output / "scratch"
        scratch.mkdir(parents=True)
        (scratch / "tmp.csv").write_text("disposable")
        cleaned = exe.cleanup_disposable(self.px, scratch, arm, path)
        self.assertFalse(scratch.exists())
        self.assertEqual(cleaned["reason"], "diagnostics_measured_hashes_verified")
        with self.assertRaisesRegex(ValueError, "verified terminal receipt"):
            exe.cleanup_disposable(self.px, scratch, plan["pending"][1], path)

    def test_s6_service_defers_to_exclusive_worker(self):
        script = ROOT / "scripts/px_cohort_s6_service.sh"
        subprocess.run(["sh", "-n", str(script)], check=True)
        text = script.read_text()
        self.assertIn("flock -n", text)
        self.assertIn("$STOP", text)
        self.assertIn("--check-ready", text)
        self.assertIn("--supervise --armed", text)
        self.assertNotIn("--memory", text)
        # s6 runs from the PX data root: both package roots must be
        # importable, and the executable service must actually be executable.
        self.assertEqual(text.count('PYTHONPATH="$PX_CODE:$PX_CODE/benchmarks"'), 2)
        self.assertTrue(script.stat().st_mode & 0o111)
        with tempfile.TemporaryDirectory() as elsewhere:
            env = dict(os.environ, PYTHONPATH=str(ROOT) + ":" +
                       str(ROOT / "benchmarks"))
            check = subprocess.run(
                [sys.executable, "-m", "assembler_bench.px_execution", "--help"],
                cwd=elsewhere, env=env, check=False, capture_output=True,
                text=True)
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_live_baseline_must_match_immutable_budget_receipt(self):
        from assembler_bench.px_execution import checked_baseline
        registry = json.loads(REGISTRY.read_text())
        registry["policy"]["dedicated_image_store_root"] = str(self.px)
        baseline = self.px / "budget-baseline.json"
        contents = {
            "schema": "ivanka.exploratory.storage-baseline.v1",
            "root": str(self.px), "image_store": str(self.px),
            "workspace": "/workspace", "active_job": None,
            "frozen_manifest_sha256":
            registry["policy"]["frozen_seven_manifest_sha256"],
        }
        write_json(baseline, contents)
        registry["storage_baseline_sha256"] = sha(baseline)
        self.assertEqual(checked_baseline(self.px, registry), baseline)
        baseline.rename(self.px / "baseline.json")
        self.assertIsNone(checked_baseline(self.px, registry))
        old = self.px / "baseline.json"
        old.rename(baseline)
        contents["active_job"] = "fake running job"
        write_json(baseline, contents)
        self.assertIsNone(checked_baseline(self.px, registry))
        contents["active_job"] = None
        contents["workspace"] = "/unrelated"
        write_json(baseline, contents)
        registry["storage_baseline_sha256"] = sha(baseline)
        self.assertIsNone(checked_baseline(self.px, registry))
        contents["workspace"] = "/workspace"
        write_json(baseline, contents)
        registry["storage_baseline_sha256"] = sha(baseline)
        self.assertEqual(checked_baseline(self.px, registry), baseline)

    def test_cli_cannot_supervise_without_arming(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "benchmarks"))
        result = subprocess.run(
            [sys.executable, "-m", "assembler_bench.px_execution",
             "--registry", str(self.promoted_registry()),
             "--root", str(self.px), "--supervise"],
            capture_output=True, text=True, env=env, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("armed", result.stderr)

    def test_check_ready_refuses_unproven_tools(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "benchmarks"))
        registry = json.loads(REGISTRY.read_text())
        path = write_json(self.root / "unproven-registry.json", registry)
        result = subprocess.run(
            [sys.executable, "-m", "assembler_bench.px_execution",
             "--registry", str(path), "--root", str(self.px), "--check-ready"],
            capture_output=True, text=True, env=env, check=False)
        self.assertEqual(result.returncode, 1)

    def test_private_paths_never_reach_receipts_or_results(self):
        plan = sched.build_plan(self.promoted_registry(), self.source(), self.px)
        self.assertNotIn("/workspace", json.dumps(plan))
        self.assertNotIn("manifest.tsv", json.dumps(plan))
        arm = plan["pending"][0]
        output = self.px / "out"
        output.mkdir()
        (output / "conseq.csv").write_bytes(b"MAX\n")
        sched.record_outcome(self.px, arm, output / "conseq.csv", "success",
                             seconds=1.0)
        text = sched.receipt_path(self.px, arm).read_text()
        self.assertNotIn("sample-", text)
        self.assertNotIn(".fastq", text)


    def _arm_output(self, arm):
        output = self.px / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
        output.mkdir(parents=True, exist_ok=True)
        return output

    def _record_success(self, arm, output, content=b"region,MAX\nHIV1,ACGT\n"):
        (output / "conseq.csv").write_bytes(content)
        sched.record_outcome(self.px, arm, output / "conseq.csv", "success",
                             seconds=3.0, peak_rss=1_000_000)
        return sched.verify_receipt(self.px, arm)

    def test_diagnostics_require_explicit_metric_status(self):
        plan = sched.build_plan(self.promoted_registry(), self.source(), self.px)
        arm = plan["pending"][0]
        case = self.source().case(arm["cohort"], arm["alias"])
        output = self._arm_output(arm)
        self._record_success(arm, output, b"consensus-percent-cutoff,sequence\nMAX,\n")
        path, digest = exe.extract_diagnostics(
            self.px, arm, output,
            fastq_sha256=[case.input_hashes()["R1"], case.input_hashes()["R2"]])
        record = json.loads(path.read_bytes())
        self.assertEqual(record["schema"], px_metrics.SCHEMA)
        for name in px_metrics.METRICS:
            metric = record["metrics"][name]
            self.assertIn(metric["status"], {"extracted", "unavailable"})
            if metric["status"] == "unavailable":
                self.assertIsInstance(metric["unavailable_reason"], str)
            else:
                self.assertIsNone(metric["unavailable_reason"])
        self.assertEqual(record["metrics"]["exact_coverage"]["status"], "unavailable")
        self.assertIn("no final MAX", record["metrics"]["exact_coverage"]["unavailable_reason"])
        self.assertEqual(digest, sched.sha256_file(path))
        self.assertTrue((Path(str(path) + ".sha256")).is_file())

    def test_retention_refuses_without_complete_diagnostics(self):
        plan = sched.build_plan(self.promoted_registry(), self.source(), self.px)
        arm = plan["pending"][0]
        case = self.source().case(arm["cohort"], arm["alias"])
        output = self._arm_output(arm)
        self._record_success(arm, output)
        path, _ = exe.posthoc(self.px, arm, type("S", (), {
            "source_sha256": "e" * 64,
            "score": lambda self, **k: {"alias": k["alias"], "outcome": "success",
                                        "score": 1.0, "seconds": 3.0}})(), "e" * 64)
        scratch = output / "scratch"
        scratch.mkdir()
        (scratch / "tmp.csv").write_text("x")
        with self.assertRaisesRegex(ValueError, "diagnostics and results must be attested"):
            exe.cleanup_disposable(self.px, scratch, arm, path)
        exe.extract_diagnostics(self.px, arm, output,
                                fastq_sha256=[case.input_hashes()["R1"],
                                              case.input_hashes()["R2"]])
        removed = exe.cleanup_disposable(self.px, scratch, arm, path)
        self.assertFalse(scratch.exists())
        self.assertEqual(removed["reason"], "diagnostics_measured_hashes_verified")

    def test_retention_revalidates_stale_plan(self):
        plan = sched.build_plan(self.promoted_registry(), self.source(), self.px)
        arm = plan["pending"][0]
        case = self.source().case(arm["cohort"], arm["alias"])
        output = self._arm_output(arm)
        self._record_success(arm, output)
        exe.posthoc(self.px, arm, type("S", (), {
            "source_sha256": "e" * 64,
            "score": lambda self, **k: {"alias": k["alias"], "outcome": "success",
                                        "score": 1.0, "seconds": 3.0}})(), "e" * 64)
        exe.extract_diagnostics(self.px, arm, output,
                                fastq_sha256=[case.input_hashes()["R1"],
                                              case.input_hashes()["R2"]])
        scratch = output / "scratch"
        scratch.mkdir()
        (scratch / "tmp.csv").write_text("x")
        decision = exe.retention_plan(self.px, [arm], allocated=lambda p: 10)
        (output / "conseq.csv").write_bytes(b"tampered\n")
        with self.assertRaisesRegex(ValueError, "stale retention plan|no longer reclaimable|changed"):
            exe.apply_retention(self.px, decision)

    def test_retention_handles_outside_scratch_archive(self):
        plan = sched.build_plan(self.promoted_registry(), self.source(), self.px)
        arm = plan["pending"][0]
        case = self.source().case(arm["cohort"], arm["alias"])
        output = self._arm_output(arm)
        self._record_success(arm, output)
        exe.posthoc(self.px, arm, type("S", (), {
            "source_sha256": "e" * 64,
            "score": lambda self, **k: {"alias": k["alias"], "outcome": "success",
                                        "score": 1.0, "seconds": 3.0}})(), "e" * 64)
        exe.extract_diagnostics(self.px, arm, output,
                                fastq_sha256=[case.input_hashes()["R1"],
                                              case.input_hashes()["R2"]])
        archive = output / "scratch.tar.gz"
        archive.write_bytes(b"big")
        decision = exe.retention_plan(self.px, [arm], allocated=lambda p: 10)
        self.assertTrue(any(e["target"].endswith("scratch.tar.gz")
                            for e in decision["reclaim"]))
        removed = exe.apply_retention(self.px, decision)
        self.assertFalse(archive.exists())
        self.assertTrue((output / "conseq.csv").is_file())
        self.assertTrue(removed)

    def test_infrastructure_failure_preserved_and_retried(self):
        registry = self.promoted_registry()
        for tool in TOOLS:
            sup.make_handoff(self.px, registry, tool)
        calls = []
        source = self.source()
        first = sched.build_plan(registry, source, self.px)["pending"][0]

        def operate(registry_path, baseline, tool, mode, argv, reserve):
            mount = next(a for a in argv if str(a).endswith(":/results:rw"))
            output = Path(str(mount).split(":")[0])
            calls.append(output.name)
            if len(calls) == 1:
                return {"status": "killed", "reason": "disk_limit",
                        "log_sha256": "c" * 64}
            (output / "conseq.csv").write_bytes(b"region,MAX\nHIV1,ACGT\n")
            (output / "timing.json").write_text(
                json.dumps({"exit_code": 0, "seconds": 3.0}))
            (self.px / sup.STOP_FILE).write_text("stop\n")
            return {"status": "finished", "peak_rss": 1_000_000,
                    "log_sha256": "d" * 64}

        with patch("assembler_bench.exploratory_space.admit",
                   return_value={"incremental_bytes": 0,
                                 "free_bytes": 100 * 1024**3,
                                 "admitted_reservation_bytes": 1024**3}):
            sup.BackgroundSupervisor(
                registry, self.baseline(), source, self.px,
                exe.SupervisedRunner(registry, self.baseline(), operate, self.px),
            ).start(armed=True)
        receipt = sched.verify_receipt(self.px, first)
        self.assertEqual(receipt["outcome"], "success")
        self.assertEqual(receipt["attempt"], 2)
        original = sched.attempt_path(self.px, first, 1)
        self.assertTrue(original.is_file())
        original_data = json.loads(original.read_bytes())
        self.assertEqual(original_data["failure_reason"], "disk_stop")
        self.assertEqual(original_data["attempt"], 1)
        self.assertEqual(len(calls), 2)


    def test_header_only_conseq_scores_without_rerun(self):
        plan = sched.build_plan(self.promoted_registry(), self.source(), self.px)
        arm = plan["pending"][0]
        case = self.source().case(arm["cohort"], arm["alias"])
        output = self._arm_output(arm)
        header = b"region,q-cutoff,consensus-percent-cutoff,offset,sequence\n"
        (output / "conseq.csv").write_bytes(header)
        sched.record_outcome(self.px, arm, output / "conseq.csv", "success",
                             seconds=1.0, peak_rss=1)
        from assembler_bench.px_posthoc import PxScorer
        scorer = PxScorer()
        result = sched.posthoc_score(self.px, arm, scorer, scorer.source_sha256,
                                     output_dir=output, case=case)
        self.assertEqual(result["samples"][0]["score"], 0.0)
        self.assertEqual(result["samples"][0]["outcome"], "success")
        self.assertEqual(result["samples"][0]["method"],
                         "best_final_max_contig_local_alignment_over_reference_panel")

    def test_retry_preserves_immutable_attempt_output(self):
        registry = self.promoted_registry()
        for tool in TOOLS:
            sup.make_handoff(self.px, registry, tool)
        calls = []
        source = self.source()
        first = sched.build_plan(registry, source, self.px)["pending"][0]

        def operate(registry_path, baseline, tool, mode, argv, reserve):
            mount = next(a for a in argv if str(a).endswith(":/results:rw"))
            output = Path(str(mount).split(":")[0])
            calls.append(output.name)
            if len(calls) == 1:
                (output / "conseq.csv").write_bytes(b"attempt1\n")
                return {"status": "killed", "reason": "disk_limit",
                        "log_sha256": "c" * 64}
            (output / "conseq.csv").write_bytes(b"region,MAX\nHIV1,ACGT\n")
            (output / "timing.json").write_text(
                json.dumps({"exit_code": 0, "seconds": 3.0}))
            (self.px / sup.STOP_FILE).write_text("stop\n")
            return {"status": "finished", "peak_rss": 1_000_000,
                    "log_sha256": "d" * 64}

        with patch("assembler_bench.exploratory_space.admit",
                   return_value={"incremental_bytes": 0,
                                 "free_bytes": 100 * 1024**3,
                                 "admitted_reservation_bytes": 1024**3}):
            sup.BackgroundSupervisor(
                registry, self.baseline(), source, self.px,
                exe.SupervisedRunner(registry, self.baseline(), operate, self.px),
            ).start(armed=True)
        preserved = self.px / "outputs" / "attempts" / (
            "skesa-" + first["alias"] + ".attempt-001")
        self.assertTrue(preserved.is_dir())
        self.assertEqual((preserved / "conseq.csv").read_bytes(), b"attempt1\n")
        self.assertEqual(sched.attempt_path(self.px, first, 1).is_file(), True)

    def test_full_two_arm_pipeline_and_restart_reconciliation(self):
        registry = self.promoted_registry()
        for tool in TOOLS:
            sup.make_handoff(self.px, registry, tool)
        calls = []

        class Scorer:
            source_sha256 = "e" * 64

            def score(self, **kwargs):
                return {"alias": kwargs["alias"], "outcome": "success",
                        "score": 1.0, "seconds": 3.0}

        scorer = Scorer()

        def operate(registry_path, baseline, tool, mode, argv, reserve):
            mount = next(a for a in argv if str(a).endswith(":/results:rw"))
            output = Path(str(mount).split(":")[0])
            calls.append(output.name)
            (Path(output) / "conseq.csv").write_bytes(b"region,MAX\nHIV1,ACGT\n")
            (Path(output) / "timing.json").write_text(
                json.dumps({"exit_code": 0, "seconds": 3.0}))
            if len(calls) == 2:
                (self.px / sup.STOP_FILE).write_text("stop\n")
            return {"status": "finished", "peak_rss": 1_000_000,
                    "log_sha256": "c" * 64}

        with patch("assembler_bench.exploratory_space.admit",
                   return_value={"incremental_bytes": 0,
                                 "free_bytes": 100 * 1024**3,
                                 "admitted_reservation_bytes": 1024**3}):
            first_run = sup.BackgroundSupervisor(
                registry, self.baseline(), self.source(), self.px,
                exe.SupervisedRunner(registry, self.baseline(), operate, self.px),
                scorer=scorer, scorer_sha=scorer.source_sha256,
            ).start(armed=True)
        self.assertEqual(len(first_run["completed"]), 2)
        (self.px / sup.STOP_FILE).unlink()
        resumed_calls = []

        def operate2(registry_path, baseline, tool, mode, argv, reserve):
            mount = next(a for a in argv if str(a).endswith(":/results:rw"))
            output = Path(str(mount).split(":")[0])
            resumed_calls.append(output.name)
            (self.px / sup.STOP_FILE).write_text("stop\n")
            (Path(output) / "conseq.csv").write_bytes(b"region,MAX\nHIV1,ACGT\n")
            (Path(output) / "timing.json").write_text(
                json.dumps({"exit_code": 0, "seconds": 3.0}))
            return {"status": "finished", "peak_rss": 1_000_000,
                    "log_sha256": "d" * 64}

        with patch("assembler_bench.exploratory_space.admit",
                   return_value={"incremental_bytes": 0,
                                 "free_bytes": 100 * 1024**3,
                                 "admitted_reservation_bytes": 1024**3}):
            sup.BackgroundSupervisor(
                registry, self.baseline(), self.source(), self.px,
                exe.SupervisedRunner(registry, self.baseline(), operate2, self.px),
                scorer=scorer, scorer_sha=scorer.source_sha256,
            ).start(armed=True)
        self.assertFalse(set(resumed_calls) & set(calls))
        for arm in sched.build_plan(registry, self.source(), self.px)["pending"][:2]:
            pass
        self.assertTrue(len(calls) == 2)


if __name__ == "__main__":
    unittest.main()
