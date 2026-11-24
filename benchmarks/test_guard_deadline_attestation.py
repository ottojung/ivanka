"""Shared watchdog deadline, honest samples and bound-only receipt attestation."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from assembler_bench import px_cohort_scheduler as sched
from assembler_bench import px_execution as exe
from assembler_bench import px_supervisor as sup
from assembler_bench.exploratory_policy import checked
from assembler_bench.exploratory_runtime import launch, monitor, terminate
from assembler_bench.px_ram_semantics import (COMPARABLE_KEY,
                                              COMPARABLE_METHOD,
                                              COMPARABLE_METHOD_VERSION,
                                              COMPARABLE_SCOPE, METHOD_KEY,
                                              SCOPE_KEY, VERSION_KEY, attested)
from fail_closed_guard import binding, build
from fail_closed_guard.errors import GuardExceeded

CID = "a" * 64
RAW = 83197952
REG = Path(__file__).parent / "assembler_bench/exploratory_candidates.json"
ATTESTATION = {METHOD_KEY: COMPARABLE_METHOD,
               VERSION_KEY: COMPARABLE_METHOD_VERSION,
               SCOPE_KEY: COMPARABLE_SCOPE}


def rec(pid, ppid, rss):
    return {"pid": pid, "ppid": ppid, "rss": rss, "pid_ns": 7,
            "starttime": 100, "cmdline_sha": "micall", "cgroup": "0::/"}


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Handle:
    """Launcher handle that stays alive for a bounded number of polls."""

    def __init__(self, live_polls=None):
        self.calls = 0
        self.live_polls = live_polls

    def poll(self):
        self.calls += 1
        if self.live_polls is not None and self.calls > self.live_polls:
            return 0
        return None


class SharedDeadlineTests(unittest.TestCase):
    """Startup wait and sampling share a single full-budget deadline."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cidfile = self.root / "pilot.cid"

    def run_pilot(self, *, wall, write_at, live_polls=None, rss=25):
        clock = Clock()
        config = {"rss_bytes": 4_000_000_000, "wall_seconds": wall,
                  "registry": {}, "baseline": {}, "root": str(self.root),
                  "image_store": str(self.root), "workspace": str(self.root),
                  "budget_bytes": 10**12}
        stopped = []
        proof = {"cid": CID, "container_removed": True}

        def advance(seconds):
            clock.sleep(seconds)
            if write_at is not None and len(clock.sleeps) == write_at:
                self.cidfile.write_text(CID)

        with patch.object(binding, "inspect_pid", return_value=9), \
                patch.object(monitor.proc, "snapshot",
                             return_value={9: rec(9, 0, rss)}):
            try:
                result = monitor.watch_pilot(
                    Handle(live_polls), config, cidfile=self.cidfile, env={},
                    interval=1, clock=clock, sleep=advance,
                    measure=lambda *args: {"incremental_bytes": 0},
                    stop=lambda cid: (stopped.append(cid), proof)[1])
                return result, None, clock, stopped
            except GuardExceeded as exc:
                return None, exc, clock, stopped

    def test_failed_run_shares_one_forty_minute_deadline(self):
        result, exc, clock, stopped = self.run_pilot(
            wall=2400, write_at=2390)
        self.assertIsNone(result)
        self.assertEqual(exc.reason, "wall_limit")
        # Binding spent 2390 seconds; the sampler must not receive a second
        # 2400-second budget on top of it.
        self.assertEqual(clock(), 2400)
        self.assertEqual(stopped, [CID])
        self.assertEqual(exc.teardown["cid"], CID)
        self.assertEqual(exc.guard_result["peak_rss"], 25)
        self.assertTrue(attested(exc.guard_result))

    def test_late_successful_binding_finishes_inside_total_budget(self):
        result, exc, clock, stopped = self.run_pilot(
            wall=2400, write_at=2390, live_polls=2392)
        self.assertIsNone(exc)
        self.assertEqual(result["cid"], CID)
        self.assertEqual(result["peak_rss"], 25)
        self.assertTrue(attested(result))
        self.assertEqual(stopped, [CID])
        self.assertTrue(result["teardown"]["container_removed"])
        self.assertLessEqual(clock(), 2400)

    def test_no_sample_reports_null_not_zero(self):
        self.cidfile.write_text(CID)
        result, exc, clock, stopped = self.run_pilot(
            wall=2400, write_at=None, live_polls=0)
        self.assertIsNone(exc)
        self.assertIsNone(result["peak_rss"])
        self.assertEqual(stopped, [CID])
        # The bound sampler is real even though it collected no sample; an
        # absent reading never becomes a comparable byte count.
        self.assertTrue(attested(result))
        self.assertIsNone(sched.peak_ram_fields(result).get(
            "peak_ram_observed_mib"))


class ReceiptAttestationTests(unittest.TestCase):
    """Runner evidence reaches the immutable receipt; legacy arms do not."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "receipts").mkdir()
        baseline = self.root / "baseline.json"
        baseline.write_text("{}")
        self.supervisor = sup.BackgroundSupervisor(
            self.root, baseline, None, self.root, lambda arm, case: {})

    def arm(self, alias="PX-R001"):
        return {"tool_id": "skesa", "cohort": "physical", "alias": alias,
                "input_sha256": {"R1": "1" * 64, "R2": "2" * 64},
                "source_commit": "3" * 40, "adapter_commit": "4" * 40,
                "image_sha256": "5" * 64}

    def case(self):
        reads = self.root / "reads"
        reads.mkdir(exist_ok=True)
        r1, r2 = reads / "R1.fastq.gz", reads / "R2.fastq.gz"
        r1.write_bytes(b"@r1\n")
        r2.write_bytes(b"@r2\n")
        return SimpleNamespace(r1=r1, r2=r2)

    def output(self):
        folder = self.root / "outputs" / "skesa-PX-R001"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "conseq.csv").write_bytes(b"MAX\n")
        (folder / "timing.json").write_text(
            json.dumps({"exit_code": 0, "seconds": 12.5}))
        return folder

    def report(self, state):
        return exe.run_guarded(None, None, self.arm(), self.case(),
                               self.output(), lambda *args: state)

    def state(self, *, status="finished", peak=RAW, fields=True):
        state = {"status": status, "reason": None, "peak_rss": peak,
                 "peak_rss_bytes": peak, "log_sha256": "6" * 64,
                 "pilot_cleanup": {"pilot_container_id": CID}}
        if fields:
            state.update(ATTESTATION)
        return state

    def test_true_successful_run_attests_receipt_and_resource(self):
        report = self.report(self.state())
        self.assertEqual(report["outcome"], "success")
        self.assertTrue(attested(report))
        receipt = self.supervisor._record(self.arm(), report)
        self.assertTrue(attested(receipt))
        self.assertEqual(receipt["peak_rss_bytes"], RAW)
        self.assertEqual(sched.verify_receipt(self.root, self.arm()), receipt)
        path, _ = sched.write_resource(self.root, self.arm(), receipt)
        resource = json.loads(path.read_text())
        self.assertEqual(resource[COMPARABLE_KEY], round(RAW / 1048576, 6))
        self.assertTrue(resource["measurement_present"])

    def test_failed_run_keeps_real_peak_and_attestation(self):
        state = self.state(status="killed")
        state["reason"] = "wall_limit"
        report = self.report(state)
        self.assertEqual(report["outcome"], "failure")
        self.assertEqual(report["failure_reason"], "wall_limit")
        receipt = self.supervisor._record(self.arm(), report)
        self.assertEqual(receipt["failure_reason"], "wall_limit")
        self.assertEqual(receipt["peak_rss_bytes"], RAW)
        self.assertTrue(attested(receipt))

    def test_null_sample_stays_null_on_receipt_and_resource(self):
        state = self.state(status="killed", peak=None)
        state["reason"] = "wall_limit"
        receipt = self.supervisor._record(self.arm(), self.report(state))
        self.assertIsNone(receipt["peak_rss_bytes"])
        self.assertTrue(attested(receipt))
        path, _ = sched.write_resource(self.root, self.arm(), receipt)
        resource = json.loads(path.read_text())
        self.assertIsNone(resource[COMPARABLE_KEY])
        self.assertFalse(resource["measurement_present"])

    def test_legacy_and_partial_labels_never_claim_container_scope(self):
        for alias, fields in (
                ("PX-R001", None),
                ("PX-R002", {METHOD_KEY: COMPARABLE_METHOD,
                             SCOPE_KEY: COMPARABLE_SCOPE})):
            with self.subTest(fields=fields):
                arm = self.arm(alias)
                state = self.state(status="killed", fields=False)
                state["reason"] = "error"
                if fields:
                    state.update(fields)
                report = self.report(state)
                report["alias"] = alias
                receipt = self.supervisor._record(arm, report)
                self.assertFalse(attested(receipt))
                self.assertNotIn(METHOD_KEY, receipt)

    def test_existing_receipt_is_not_rewritten(self):
        report = self.report(self.state())
        self.supervisor._record(self.arm(), report)
        with self.assertRaisesRegex(ValueError, "may not be recomputed"):
            self.supervisor._record(self.arm(), report)


class LaunchTeardownTests(unittest.TestCase):
    """Pre-bind failure and group teardown keep their exact ownership."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        self.cidfile = self.root / "pilot.cid"
        self.cidfile.write_text(CID)
        policy = copy.deepcopy(checked(REG))
        policy["policy"]["dedicated_podman_storage_conf"] = str(
            self.root / "storage.conf")
        policy["policy"]["dedicated_image_store_root"] = str(self.store)
        (self.root / "storage.conf").write_text(
            '[storage]\ndriver = "overlay"\ngraphroot = "'
            + str(self.store / "store") + '"\nrunroot = "'
            + str(self.store / "run") + '"\n')
        base = {"schema": "ivanka.exploratory.storage-baseline.v1",
                "root": str(self.root), "image_store": str(self.store),
                "workspace": str(self.root), "base_store_bytes": 0,
                "frozen_manifest_sha256":
                    policy["policy"]["frozen_seven_manifest_sha256"],
                "active_job": None}
        self.baseline = self.root / "baseline.json"
        self.baseline.write_text(json.dumps(base))
        policy["storage_baseline_sha256"] = hashlib.sha256(
            self.baseline.read_bytes()).hexdigest()
        for target, value in (
                ("assembler_bench.exploratory_runtime.setup.checked", policy),
                ("assembler_bench.exploratory_runtime.setup.eligible", True),
                ("assembler_bench.exploratory_space.available", 100 * 1024**3)):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        def finish(proc):
            proc.wait(timeout=5)
            return 0

        patcher = patch("assembler_bench.exploratory_runtime.launch.group",
                        finish)
        patcher.start()
        self.addCleanup(patcher.stop)

    def operate(self):
        return launch.operate(REG, self.baseline, "skesa", "pilot",
                              [sys.executable, "-c", "print('hello')"], 1024**3)

    def test_prebind_failure_reaps_exact_cid_and_keeps_attestation(self):
        failure = GuardExceeded("binding_unavailable")
        failure.guard_result = {"cid": CID, "peak_rss": None, "teardown": None,
                                **ATTESTATION}

        def watch(proc, cfg, on_bind=None, **kwargs):
            raise failure

        with patch.object(launch, "bind_pilot",
                          return_value=([sys.executable], self.cidfile)), \
                patch.object(launch, "watch", side_effect=watch), \
                patch.object(launch, "stop_pilot",
                             return_value={"pilot_container_id": CID,
                                           "container_removed": True}) as stop, \
                patch.object(launch, "prove_pilot_absent",
                             side_effect=AssertionError("bound without a CID")):
            state = self.operate()

        stop.assert_called_once()
        self.assertEqual(stop.call_args[0][2], self.cidfile)
        self.assertEqual(state["status"], "killed")
        self.assertEqual(state["reason"], "binding_unavailable")
        self.assertEqual(state[METHOD_KEY], COMPARABLE_METHOD)
        self.assertEqual(state[VERSION_KEY], COMPARABLE_METHOD_VERSION)
        self.assertIsNone(state["peak_rss"])
        event = next(iter(launch.lease.latest(
            launch.lease.events(self.root)).values()))
        self.assertEqual(event["state"], "released")

    def test_group_teardown_signals_only_own_process_group(self):
        proc = SimpleNamespace(pid=4242, poll=lambda: None,
                               wait=lambda timeout=None: 0)
        with patch("assembler_bench.exploratory_runtime.terminate.os.killpg") \
                as kill:
            self.assertEqual(terminate.group(proc), 0)
        self.assertEqual([call.args[0] for call in kill.call_args_list],
                         [4242, 4242])
        self.assertEqual([call.args[1] for call in kill.call_args_list],
                         [15, 9])

    def test_build_group_stop_uses_bound_pgid_not_bare_pid(self):
        table = {77: rec(77, 0, 100), 78: rec(78, 77, 200)}
        bound = build.bind_launcher(77, snapshot=table)
        proc = SimpleNamespace(pid=4242, wait=lambda timeout=None: 0)
        with patch("fail_closed_guard.build.os.killpg",
                   side_effect=[None, ProcessLookupError()]) as kill:
            proof = build.stop_group(bound, proc)
        self.assertTrue(proof["stopped"])
        self.assertEqual(kill.call_args_list[0].args, (77, 15))


if __name__ == "__main__":
    unittest.main()
