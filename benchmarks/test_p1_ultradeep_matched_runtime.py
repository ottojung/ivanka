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


def host(load: float = 1.0, cpu_max: str = "200000 100000",
         cpuset: str = "0-1", periods: int = 100, throttled: int = 0) -> dict:
    return {"loadavg": [load, load, load], "cpu_max": cpu_max,
            "effective_cpus": plan.effective_cpus(cpu_max),
            "cpuset_effective": cpuset,
            "cpu_stat": {"nr_periods": periods, "nr_throttled": throttled},
            "memory_current": 1000000}


def attestation() -> dict:
    """Truthful record: exact merged sources and reviewed deployed guard pins."""
    return {
        "schema": plan.ATTESTATION_SCHEMA,
        "PR535": {"state": "merged", "head": plan.SOURCE_PINS["PR535"]["head"],
                  "merge_commit": plan.SOURCE_PINS["PR535"]["merge_commit"]},
        "PR536": {"state": "merged", "head": plan.SOURCE_PINS["PR536"]["head"],
                  "merge_commit": plan.SOURCE_PINS["PR536"]["merge_commit"]},
        "deployed_sources": {"PR535": True, "PR536": True},
        "deployed_guard": {
            "source_head": plan.DEPLOYED_PINS["guard_source_head"],
            "root_head": plan.DEPLOYED_PINS["deployed_root_head"],
            "tree_clean": True,
            "guard_sha256": dict(plan.DEPLOYED_PINS["guard_sha256"]),
            "px_service_head": plan.DEPLOYED_PINS["px_service_head"],
            "watchdog_service_head": plan.DEPLOYED_PINS["watchdog_service_head"],
            "watchdog_alive_fresh": True, "lease_clear": True,
            "idle_boundary_attested": True,
        },
        "attested_by": "operator",
        "attested_at_utc": "2026-11-26T20:30:00Z",
    }


def write_attestation(folder: pathlib.Path, record: dict | None = None) -> pathlib.Path:
    path = folder / "attestation.json"
    path.write_text(json.dumps(record if record is not None else attestation()))
    return path


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

    def test_cpuset_capacity_and_host_fallback(self) -> None:
        self.assertEqual(plan.cpuset_count("0-31"), 32)
        self.assertEqual(plan.cpuset_count("0,2-3"), 3)
        self.assertIsNone(plan.cpuset_count("bogus"))
        unlimited = host(cpu_max="max 100000", cpuset="0-31")
        self.assertEqual(plan.host_cpu_capacity(unlimited), 32)
        self.assertEqual(plan.host_cpu_capacity(host()), 2.0)

    def test_contention_abort_rules(self) -> None:
        self.assertFalse(plan.contention_check(host())["abort"])
        self.assertTrue(plan.contention_check(host(load=5.0))["abort"])
        self.assertTrue(plan.contention_check(host(throttled=20))["abort"])
        self.assertTrue(plan.contention_check(host(cpu_max="100000 100000"))["abort"])
        self.assertTrue(plan.contention_check({"cpu_stat": {}})["abort"])

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
    def test_incomplete_attestation_stays_blocked(self) -> None:
        record = attestation()
        record["deployed_guard"]["watchdog_alive_fresh"] = False
        record["deployed_guard"]["lease_clear"] = False
        with tempfile.TemporaryDirectory() as tmp:
            gate = plan.readiness(write_attestation(pathlib.Path(tmp), record))
        self.assertFalse(gate["ready"])
        self.assertIn("deployed_guard", gate["blocked_by"])
        self.assertIn("watchdog ALIVE not fresh", gate["reasons"])
        self.assertIn("shared lease not clear", gate["reasons"])

    def test_truthful_reviewed_deployed_guard_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gate = plan.readiness(write_attestation(pathlib.Path(tmp)))
        self.assertTrue(gate["ready"])
        self.assertEqual(gate["blocked_by"], [])
        self.assertEqual(gate["reasons"], [])

    def test_deployed_pins_are_separate_and_exact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            for mutate in (
                lambda r: r["PR535"].update(head="b" * 64),
                lambda r: r["PR535"].update(merge_commit="b" * 64),
                lambda r: r["PR536"].update(head="b" * 64),
                lambda r: r["deployed_guard"].update(source_head="b" * 64),
                lambda r: r["deployed_guard"].update(root_head="b" * 64),
                lambda r: r["deployed_guard"]["guard_sha256"].update(watch_sha256="b" * 64),
                lambda r: r["deployed_guard"].update(px_service_head="b" * 64),
                lambda r: r["deployed_guard"].update(watchdog_service_head="b" * 64),
                lambda r: r["deployed_guard"].update(watchdog_alive_fresh=False),
                lambda r: r["deployed_guard"].update(lease_clear=False),
                lambda r: r["deployed_guard"].update(idle_boundary_attested=False),
                lambda r: r["deployed_sources"].update(PR535=False),
                lambda r: r["deployed_sources"].update(PR535="yes"),
                lambda r: r.update(schema="wrong"),
            ):
                record = attestation()
                mutate(record)
                self.assertFalse(plan.readiness(write_attestation(folder, record))["ready"])

    def test_exact_source_heads_replaced_stale_pins(self) -> None:
        self.assertEqual(plan.SOURCE_PINS["PR535"]["head"],
                         "39317f021f4e5c00f5da859bcdcf755de4c6d353")
        self.assertEqual(plan.SOURCE_PINS["PR535"]["merge_commit"],
                         "165a86b38c0bc29b4f8e0281a39ca59b909a6563")
        self.assertEqual(plan.DEPLOYED_PINS["deployed_root_head"],
                         "165a86b38c0bc29b4f8e0281a39ca59b909a6563")
        self.assertEqual(plan.DEPLOYED_PINS["px_service_head"],
                         "b8720600c9f10e71472b2b55210badeabc257a81")

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

    def test_plan_is_inert_with_truthful_attested_deployed_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "out"
            attestation_path = write_attestation(pathlib.Path(tmp))
            built = plan.build_plan(RECEIPT, root, attestation=attestation_path)
            self.assertTrue(built["dependencies"]["ready"])
            self.assertEqual(built["dependencies"]["blocked_by"], [])
            self.assertEqual(built["execution"], "blocked")
            self.assertFalse(built["scientific_gates_changed"])
            self.assertFalse(built["formal_qualification"])
            self.assertTrue(built["strong_evidence_not_causal_proof"])
            self.assertEqual(len(built["schedule"]), 8)
            self.assertEqual(built["source_pins"], plan.SOURCE_PINS)
            self.assertEqual(built["deployed_pins"], plan.DEPLOYED_PINS)
            self.assertEqual(built["comparability_plan"]["required_container_effective_cpus"], 2.0)
            self.assertFalse(root.exists())
            self.assertNotIn("execute", built)


class EvidenceTest(unittest.TestCase):
    def test_sampled_rss_and_cpu_quota_are_recorded(self) -> None:
        step = {"case": "ultradeep-s009", "arm": "candidate"}
        record = plan.arm_evidence_record(
            step, host(), host(load=1.1),
            {"timing_origin": "micall_in_container_monotonic_v1",
             "seconds": 836.2, "exit_code": 0},
            sampled_rss_bytes=1_500_000_000, container_cpu_max="200000 100000")
        self.assertEqual(record["sampled_peak_rss_bytes"], 1_500_000_000)
        self.assertEqual(record["cpu_quota"]["container_effective_cpus"], 2.0)
        self.assertTrue(plan.evidence_complete(record))
        self.assertFalse(record["kernel_enforcement"])
        self.assertNotIn("cmdline", json.dumps(record).lower())
        with tempfile.TemporaryDirectory() as tmp:
            path = plan.write_arm_evidence(pathlib.Path(tmp), record)
            self.assertEqual(json.loads(path.read_text()), record)

    def test_incomplete_evidence_is_refused(self) -> None:
        step = {"case": "ultradeep-s006", "arm": "frozen"}
        for rss, quota in ((None, "200000 100000"), (10, None), (True, "200000 100000")):
            record = plan.arm_evidence_record(
                step, host(), host(), {"seconds": 1.0, "exit_code": 0},
                sampled_rss_bytes=rss, container_cpu_max=quota)
            self.assertFalse(plan.evidence_complete(record))

    def test_comparability_of_a_full_ab_ba_set(self) -> None:
        records = []
        for step in plan.alternating_schedule():
            records.append(plan.arm_evidence_record(
                step, host(), host(load=1.1),
                {"seconds": 100.0, "exit_code": 0},
                sampled_rss_bytes=1_000_000_000, container_cpu_max="200000 100000"))
        decision = plan.comparability_check(records)
        self.assertTrue(decision["comparable"])
        self.assertFalse(decision["abort"])
        self.assertEqual(decision["reasons"], [])

    def test_comparability_aborts_on_imbalance_or_contention(self) -> None:
        def full(load: float = 1.0, throttled: int = 0) -> list:
            result = []
            for step in plan.alternating_schedule():
                result.append(plan.arm_evidence_record(
                    step, host(load=load, throttled=throttled), host(load=load),
                    {"seconds": 100.0, "exit_code": 0},
                    sampled_rss_bytes=1_000_000_000,
                    container_cpu_max="200000 100000"))
            return result

        self.assertTrue(plan.comparability_check(full(throttled=20))["abort"])
        self.assertTrue(plan.comparability_check(full(load=5.0))["abort"])
        incomplete = full()
        incomplete[0]["sampled_peak_rss_bytes"] = None
        incomplete[0]["rss_evidence_complete"] = False
        self.assertTrue(plan.comparability_check(incomplete)["abort"])
        mixed = full(load=1.0) + []
        mixed[0]["host_before"] = host(load=0.2)
        mixed[0]["host_after"] = host(load=0.2)
        self.assertTrue(plan.comparability_check(mixed)["abort"])
        self.assertTrue(plan.comparability_check(full()[:4])["abort"])


if __name__ == "__main__":
    unittest.main()
