"""Tests for the plan-only ultradeep matched-resource diagnostic."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import p1_ultradeep_matched_runtime as plan

RECEIPT = (
    pathlib.Path(__file__).parent.parent
    / "docs/bench/diagnostics/p1-ultradeep-runtime-20261126.json"
)


class ReceiptTest(unittest.TestCase):
    def test_receipt_pin_and_subset(self) -> None:
        report = plan.load_receipt(RECEIPT)
        self.assertEqual(report["case_count"], 16)
        rows = {row["case"]: row for row in report["cases"]}
        self.assertEqual(rows["ultradeep-s009"]["candidate_seconds"], 836.226300251)
        self.assertEqual(rows["ultradeep-s006"]["frozen_seconds"], 138.544854052)
        self.assertGreater(rows["ultradeep-s009"]["unattributed_delta_seconds"], 600)

    def test_modified_receipt_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "results.json"
            path.write_text(RECEIPT.read_text().replace("s006", "s006x"))
            with self.assertRaises(plan.Refusal):
                plan.load_receipt(path)


class ScheduleTest(unittest.TestCase):
    def test_deterministic_ab_ba_alternation(self) -> None:
        steps = plan.alternating_schedule()
        self.assertEqual(len(steps), 8)
        self.assertEqual(
            [(s["case"][-3:], s["arm"]) for s in steps],
            [("006", "frozen"), ("006", "candidate"),
             ("007", "candidate"), ("007", "frozen"),
             ("008", "frozen"), ("008", "candidate"),
             ("009", "candidate"), ("009", "frozen")],
        )
        self.assertEqual(steps, plan.alternating_schedule())

    def test_single_template_except_image_results_and_name(self) -> None:
        step = {"case": "ultradeep-s006", "arm": "frozen"}
        other = {"case": "ultradeep-s006", "arm": "candidate"}
        root = pathlib.Path("/tmp/fresh-matched-root")
        a, b = plan.argv_for(step, root), plan.argv_for(other, root)
        self.assertEqual(len(a), len(b))
        for left, right in zip(a, b):
            if left in (plan.FROZEN_IMAGE, plan.CANDIDATE_IMAGE):
                continue
            if "p1-ultradeep-matched-" in left:
                continue
            if "/ultradeep-s006/frozen" in left:
                self.assertIn("/ultradeep-s006/candidate", right)
                continue
            self.assertEqual(left, right)
        self.assertIn("--cpus=2", a)
        self.assertIn("--memory=4000000000", a)
        self.assertIn("--pull=never", a)
        self.assertIn("--all_projects", a)
        self.assertNotIn("/workspace/micall-frozen-seven-20261117/phase-synthetic464", " ".join(a))


class HostEvidenceTest(unittest.TestCase):
    def test_effective_cpu_allocation(self) -> None:
        self.assertEqual(plan.effective_cpus("200000 100000"), 2.0)
        self.assertEqual(plan.effective_cpus("150000 100000"), 1.5)
        self.assertIsNone(plan.effective_cpus("max 100000"))
        with self.assertRaises(ValueError):
            plan.effective_cpus("2")

    def test_aggregate_only_no_process_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            cgroup = base / "cg"
            proc = base / "proc"
            cgroup.mkdir()
            proc.mkdir()
            (cgroup / "cpu.max").write_text("200000 100000\n")
            (cgroup / "cpuset.cpus.effective").write_text("0-1\n")
            (cgroup / "cpu.stat").write_text("nr_periods 10\nnr_throttled 1\n")
            (cgroup / "memory.current").write_text("1000000\n")
            (proc / "loadavg").write_text("1.5 2.0 3.0 1/100 1234\n")
            evidence = plan.host_evidence(cgroup, proc)
            self.assertEqual(evidence["effective_cpus"], 2.0)
            self.assertEqual(evidence["loadavg"], [1.5, 2.0, 3.0])
            self.assertEqual(evidence["cpu_stat"]["nr_throttled"], 1)
            self.assertNotIn("cmdline", json.dumps(evidence).lower())
            self.assertEqual(sorted(p.name for p in cgroup.iterdir()), [
                "cpu.max", "cpu.stat", "cpuset.cpus.effective", "memory.current"])
        source = pathlib.Path(plan.__file__).read_text()
        self.assertNotIn("cmdline", source.lower())


class GuardTest(unittest.TestCase):
    def test_dependencies_block_until_both_exact_heads_attested(self) -> None:
        self.assertEqual(plan.readiness(None)["blocked_by"], ["PR535", "PR536"])
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "attestation.json"
            path.write_text(json.dumps({
                "PR535": {"state": "merged", "head": plan.DEPENDENCIES["PR535"]},
                "PR536": {"state": "open", "head": plan.DEPENDENCIES["PR536"]},
            }))
            self.assertEqual(plan.readiness(path)["blocked_by"], ["PR536"])
            path.write_text(json.dumps({
                name: {"state": "merged", "head": head}
                for name, head in plan.DEPENDENCIES.items()
            }))
            self.assertTrue(plan.readiness(path)["ready"])

    def test_output_root_guards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = pathlib.Path(tmp) / "fresh"
            self.assertEqual(plan.check_output_root(fresh), fresh.resolve())
            fresh.mkdir()
            (fresh / "stale.json").write_text("{}")
            with self.assertRaises(plan.Refusal):
                plan.check_output_root(fresh)
            with self.assertRaises(plan.Refusal):
                plan.check_output_root("/")
            with self.assertRaises(plan.Refusal):
                plan.check_output_root(plan.PROTECTED_ROOTS[0] / "new-root")

    def test_plan_is_inert_and_gate_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "out"
            built = plan.build_plan(RECEIPT, root)
            self.assertEqual(built["dependencies"]["blocked_by"], ["PR535", "PR536"])
            self.assertEqual(built["execution"], "blocked")
            self.assertFalse(built["scientific_gates_changed"])
            self.assertFalse(built["formal_qualification"])
            self.assertTrue(built["strong_evidence_not_causal_proof"])
            self.assertEqual(len(built["schedule"]), 8)
            self.assertFalse(root.exists())

    def test_arm_evidence_record_is_aggregate_and_durable(self) -> None:
        step = {"case": "ultradeep-s009", "arm": "candidate"}
        before = {"loadavg": [1.0, 1.2, 1.4], "effective_cpus": 2.0}
        after = {"loadavg": [1.1, 1.3, 1.5], "effective_cpus": 2.0}
        record = plan.arm_evidence_record(
            step, before, after,
            {"timing_origin": "micall_in_container_monotonic_v1",
             "seconds": 836.2, "exit_code": 0},
        )
        self.assertNotIn("cmdline", json.dumps(record).lower())
        with tempfile.TemporaryDirectory() as tmp:
            path = plan.write_arm_evidence(pathlib.Path(tmp), record)
            self.assertEqual(json.loads(path.read_text()), record)


if __name__ == "__main__":
    unittest.main()
