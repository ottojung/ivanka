"""Gated front-end that drives the inert PX planner through the guarded launcher.

No process is created here. Each arm is delegated to a callable runner that must
be the PR411 exclusive single-worker launcher. The supervisor is inert until an
image-agent handoff is attested and tests have passed, so importing this module
can never start a competing benchmark worker.
"""
import json
import time
from pathlib import Path

from . import exploratory_policy
from . import px_cohort_scheduler as sched

HANDOFF_SCHEMA = "ivanka.px.supervisor.handoff.v1"
PX_BOARD = "V9roZ0y80gjXs7WrOCgNbH-moral"
IMAGE_AGENT = "1D79tewyrbAaSBjpKyQzmY-curtis"
STOP_FILE = "STOP"


class HandoffRequired(Exception):
    """Raised whenever execution is attempted before eligibility is proven."""


def handoff_path(root, tool):
    return Path(root) / "handoff" / (tool + ".json")


def make_handoff(root, registry, tool):
    """Write a handoff only from verified image AND two-cohort pilot receipts."""
    data = exploratory_policy.checked(registry)
    item = next(x for x in data["candidates"] if x["id"] == tool)
    if not exploratory_policy.eligible(data, tool):
        raise HandoffRequired("tool has no certified pilot/image proof")
    bound = dict(item, adapter_commit=data["adapter_branch_commits"][tool])
    if not exploratory_policy.verified_receipt(
            bound, item.get("image_evidence"), "image"):
        raise HandoffRequired("image receipt is not source-bound")
    pilot = item.get("pilot_evidence")
    if not exploratory_policy.verified_receipt(bound, pilot, "pilot"):
        # An image receipt alone proves no pilot: tests_passed must never be
        # asserted from it. Both cohorts need their own attested receipt.
        raise HandoffRequired("no SHA-verified two-cohort pilot evidence")
    record = {"schema": HANDOFF_SCHEMA, "tool_id": tool, "board": PX_BOARD,
              "agent": IMAGE_AGENT, "tests_passed": True,
              "image_sha256": item["image_sha256"],
              "image_receipt_sha256": item["image_evidence"]["sha256"],
              "pilot_receipt_sha256": pilot["sha256"]}
    path = handoff_path(root, tool)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return path


def verify_handoff(root, registry, tool, *, provenance_root=None):
    """Refuse to run unless board, agent, tests and image proof all agree."""
    path = handoff_path(root, tool)
    if not path.is_file():
        return False
    record = json.loads(path.read_bytes())
    if (record.get("schema") != HANDOFF_SCHEMA
            or record.get("tool_id") != tool
            or record.get("board") != PX_BOARD
            or record.get("agent") != IMAGE_AGENT
            or record.get("tests_passed") is not True):
        return False
    data = exploratory_policy.checked(registry, provenance_root=provenance_root)
    if not exploratory_policy.eligible(data, tool):
        return False
    item = next(x for x in data["candidates"] if x["id"] == tool)
    evidence = item.get("image_evidence")
    pilot = item.get("pilot_evidence")
    if (not isinstance(evidence, dict)
            or record.get("image_sha256") != item["image_sha256"]
            or record.get("image_receipt_sha256") != evidence.get("sha256")
            or not isinstance(pilot, dict)
            or record.get("pilot_receipt_sha256") != pilot.get("sha256")):
        return False
    bound = dict(item, adapter_commit=data["adapter_branch_commits"][tool])
    if not exploratory_policy.verified_receipt(
            bound, evidence, "image", provenance_root):
        return False
    return exploratory_policy.verified_receipt(
        bound, pilot, "pilot", provenance_root)


class BackgroundSupervisor:
    """Sequential, resumable driver. ``runner`` is the guarded launcher adapter."""

    def __init__(self, registry, baseline, source, root, runner,
                 reserve_bytes=1024**3, clock=time.monotonic, sleep=time.sleep,
                 diagnostics=None, retain=None, scorer=None, scorer_sha=None):
        self.registry = Path(registry)
        self.baseline = json.loads(Path(baseline).read_text())
        self.source, self.root = source, Path(root)
        self.runner = runner
        self.reserve_bytes = reserve_bytes
        self.clock, self.sleep = clock, sleep
        self.diagnostics = diagnostics
        self.retain = retain
        self.scorer = scorer
        self.scorer_sha = scorer_sha
        if not sched.MIN_RESERVE <= reserve_bytes <= sched.MAX_RESERVE:
            raise ValueError("PX supervisor reservation must be 1-4 GiB")

    def start(self, *, armed=False):
        """Stay inert without explicit, verified handoff and arming."""
        if not armed:
            raise HandoffRequired("supervisor is inert until armed")
        plan = sched.build_plan(self.registry, self.source, self.root)
        for tool in plan["tools"]:
            if not verify_handoff(self.root, self.registry, tool):
                raise HandoffRequired("no verified image-agent handoff for " + tool)
        pending = sched.resume(plan, self.root)
        completed = []
        for arm in pending:
            if (self.root / STOP_FILE).is_file():
                break
            self._run_arm(arm, plan, completed)
        return {"status": "stopped" if (self.root / STOP_FILE).is_file()
                else "idle" if not pending else "advanced",
                "completed": completed, "remaining": len(pending) - len(completed)}

    def _run_arm(self, arm, plan, completed):
        for _ in range(sched.MAX_INFRA_ATTEMPTS):
            sched.admit_arm(self.registry, self.baseline, self.root,
                            self.reserve_bytes)
            case = self.source.case(arm["cohort"], arm["alias"])
            report = self.runner(arm, case)
            receipt = self._record(arm, report)
            # Publish observed RAM for EVERY terminal arm, including failures;
            # a null measurement remains null rather than being fabricated.
            sched.write_resource(self.root, arm, receipt)
            retryable = (receipt.get("outcome") == "failure"
                         and receipt.get("failure_reason")
                         in sched.INFRASTRUCTURE_FAILURE_REASONS
                         and receipt.get("attempt", 1) < sched.MAX_INFRA_ATTEMPTS)
            if retryable and not (self.root / STOP_FILE).is_file():
                self._preserve_attempt(arm, receipt.get("attempt", 1))
                continue
            self._posthoc(arm, case, receipt)
            if report.get("retention_container_id"):
                from .px_retention import retire_finished_arm
                retire_finished_arm(self.root, arm, receipt, report)
            completed.append(sched.receipt_id(arm))
            sched.write_checkpoint(self.root, plan, completed)
            return
        completed.append(sched.receipt_id(arm))
        sched.write_checkpoint(self.root, plan, completed)

    def _preserve_attempt(self, arm, attempt):
        output = self.root / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
        if not output.exists():
            return
        archive = (self.root / "outputs" / "attempts"
                   / (arm["tool_id"] + "-" + arm["alias"]
                      + f".attempt-{attempt:03d}"))
        if archive.exists():
            raise ValueError("attempt output already preserved")
        archive.parent.mkdir(parents=True, exist_ok=True)
        output.rename(archive)

    def _posthoc(self, arm, case, receipt):
        if receipt.get("outcome") != "success":
            return
        if self.diagnostics is not None:
            self.diagnostics(self.root, arm, case, receipt)
            if self.retain is not None:
                self.retain(self.root, arm, case, receipt)
            return
        if self.retain is not None:
            self.retain(self.root, arm, case, receipt)
            return
        from .px_execution import posthoc_extract_and_retain
        posthoc_extract_and_retain(self.root, arm, case, receipt,
                                   scorer=self.scorer,
                                   scorer_sha=self.scorer_sha)

    def _record(self, arm, report):
        if not isinstance(report, dict) or report.get("outcome") not in (
                "success", "failure"):
            raise ValueError("guarded runner returned no terminal outcome")
        if (report.get("alias") != arm["alias"]
                or report.get("cohort") != arm["cohort"]
                or report.get("input_sha256") != arm["input_sha256"]):
            # A result from another case must never be attributed to this
            # canonical alias, even when read digests happen to be equal.
            raise ValueError("guarded runner report does not match dispatched case")
        failure = report.get("failure_reason")
        if report["outcome"] == "failure" and failure not in sched.FAILURE_REASONS:
            raise ValueError("runner failure reason is not classified")
        return sched.record_outcome(
            self.root, arm, report.get("output_path"), report["outcome"],
            seconds=report.get("seconds"), peak_rss=report.get("peak_rss"),
            failure_reason=failure,
            runner_receipt_sha256=report.get("runner_receipt_sha256"))
