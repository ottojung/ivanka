"""Gated front-end that drives the inert PX planner through the guarded launcher.

No process is created here. Each arm is delegated to a callable runner that must
be the PR411 exclusive single-worker launcher. The supervisor is inert until an
image-agent handoff is attested and tests have passed, so importing this module
can never start a competing benchmark worker.
"""
import fcntl
import json
import logging
import time
from collections import deque
from pathlib import Path

from . import exploratory_policy
from . import px_cohort_scheduler as sched
from . import px_disk_retry_admission as disk_admission
from . import px_retry_authorization as authz

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
    if not exploratory_policy.cohort_eligible(data, tool):
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


def balanced_pending(plan, pending):
    """Dispatch least-complete tools first, without changing plan identity.

    Pending is the receipt-authoritative result of resume(). All tools in
    a cohort share the same denominator. Count accepted terminal arms as
    expected minus pending; a retryable infrastructure failure stays pending.
    Keep canonical alias order within each tool and registry order for ties.
    The original plan (including its digest) is never modified.
    """
    tools = plan["tools"]
    for cohort in sched.COHORTS:
        queues = {tool: deque() for tool in tools}
        for arm in pending:
            if arm["cohort"] == cohort:
                queues[arm["tool_id"]].append(arm)
        while any(queues.values()):
            # Larger remaining count means fewer finished arms. max() keeps
            # the first registry-order tool on equal counts.
            tool = max(tools, key=lambda name: len(queues[name]))
            yield queues[tool].popleft()


class BackgroundSupervisor:
    """Sequential, resumable driver. ``runner`` is the guarded launcher adapter."""

    def __init__(self, registry, baseline, source, root, runner,
                 reserve_bytes=1024**3, clock=time.monotonic, sleep=time.sleep,
                 diagnostics=None, retain=None, scorer=None, scorer_sha=None,
                 disk_retry_extra_bytes=disk_admission.DEFAULT_EXTRA_BYTES):
        self.registry = Path(registry)
        self.baseline = json.loads(Path(baseline).read_text())
        self.source, self.root = source, Path(root)
        self.runner = runner
        self.reserve_bytes = reserve_bytes
        self.disk_retry_extra_bytes = disk_retry_extra_bytes
        self.disk_retry_reserve_bytes, self.disk_retry_unavailable_reason = (
            disk_admission.retry_reservation_or_reason(
                reserve_bytes, disk_retry_extra_bytes))
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
        completed, deferred = [], []
        stopped = False
        for arm in balanced_pending(plan, pending):
            if self._stopped():
                stopped = True
                break
            outcome = self._run_arm(arm, plan, completed)
            if outcome == "stopped":
                # The inner drain boundary may have observed a STOP that the
                # owner retired before control returned here. Remember it so
                # no later arm is dispatched and the status stays stopped.
                stopped = True
                break
            if outcome == "deferred":
                deferred.append(sched.receipt_id(arm))
        status = "stopped" if (stopped or self._stopped()) else (
            "deferred" if deferred else "idle" if not pending else "advanced")
        return {"status": status, "completed": completed, "deferred": deferred,
                "remaining": len(pending) - len(completed)}

    def _dispatch_reserve(self, arm, attempt):
        """Extra headroom for disk_stop retries; base reserve otherwise.

        The larger reservation is checked again under the actual launcher lock
        by passing it to the guarded runner/operate path before any child spawn.
        """
        prior = sched.verify_receipt(self.root, arm)
        if not (attempt > 1 and isinstance(prior, dict)
                and prior.get("failure_reason") == "disk_stop"):
            return self.reserve_bytes, None
        if self.disk_retry_reserve_bytes is None:
            return None, {
                "schema": disk_admission.ADMISSION_SCHEMA,
                "action": "defer",
                "base_reservation_bytes": self.reserve_bytes,
                "extra_headroom_bytes": 0,
                "proposed_reservation_bytes": None,
                "reason": self.disk_retry_unavailable_reason,
            }
        decision = disk_admission.evaluate(
            self.registry, self.baseline, self.root, self.reserve_bytes,
            extra_bytes=self.disk_retry_extra_bytes)
        if decision["action"] != "retry":
            return None, decision
        return self.disk_retry_reserve_bytes, decision

    def _locked_admit(self, reserve_bytes):
        """Recheck admission under the same worker lock used by operate()."""
        lock_path = self.root / ".global-worker.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            sched.admit_arm(self.registry, self.baseline, self.root,
                            reserve_bytes)

    def _stopped(self):
        """Read the owner-bound drain sentinel at a single narrow boundary."""
        return (self.root / STOP_FILE).is_file()

    def _run_runner(self, arm, case, reserve_bytes):
        # The reservation is part of the guarded execution contract. An
        # exception may occur after side effects; never retry an invocation
        # by changing its signature or dropping its admitted reservation.
        return self.runner(arm, case, reserve_bytes=reserve_bytes)

    def _run_arm(self, arm, plan, completed):
        existing = sched.verify_receipt(self.root, arm)
        first = 1 if existing is None else existing.get("attempt", 1) + 1
        for attempt in range(first, sched.AUTHORIZED_EXTRA_ATTEMPT + 1):
            if attempt > sched.MAX_INFRA_ATTEMPTS:
                if self._stopped():
                    # A drain armed after a previous terminal outcome is not
                    # a completed arm. Leave the retry authorization untouched
                    # and report the explicit boundary to the caller.
                    return "stopped"
                if authz.verify(self.root, arm) is None:
                    break
            prior = sched.verify_receipt(self.root, arm)
            dispatch_reserve, disk_decision = self._dispatch_reserve(arm, attempt)
            if dispatch_reserve is None:
                if prior is not None:
                    disk_admission.record_deferred(
                        self.root, arm, disk_decision, prior=prior)
                    logging.warning("PX disk_stop retry deferred for %s: %s",
                                    sched.receipt_id(arm),
                                    disk_decision["reason"])
                return "deferred"
            if prior is not None:
                # Every dispatch after a failure, including resume after STOP
                # or a rejected admission, must archive the failed output first.
                self._prepare_retry(arm, prior, attempt - 1)
            # Pre-lock admission is fail-closed; the guarded runner rechecks the
            # same reservation under the actual worker lock before spawn.
            sched.admit_arm(self.registry, self.baseline, self.root,
                            dispatch_reserve)
            case = self.source.case(arm["cohort"], arm["alias"])
            if dispatch_reserve != self.reserve_bytes:
                # Extra disk_stop headroom must be verified under the actual
                # worker lock before claim/spawn; fail closed before consuming
                # any one-shot authorization.
                self._locked_admit(dispatch_reserve)
            # Drain boundary: a STOP may be armed after the pre-loop check,
            # during admission/case resolution, or while the optional
            # under-lock re-admission runs. Recheck immediately before
            # consuming a one-shot authorization or dispatching any child.
            # This is an advisory-filesystem check outside the launcher lock;
            # a STOP armed in the remaining subsecond window before operate()
            # takes that lock is a documented residual race, not a reason to
            # weaken the dispatch contract here.
            if self._stopped():
                return "stopped"
            if attempt > sched.MAX_INFRA_ATTEMPTS:
                # Consume the one-shot durably before any child can spawn; an
                # interrupted dispatch must not be dispatchable again.
                authz.claim(self.root, arm)
            report = self._run_runner(arm, case, dispatch_reserve)
            receipt = self._record(arm, report)
            # Publish observed RAM for EVERY terminal arm, including failures;
            # a null measurement remains null rather than being fabricated.
            sched.write_resource(self.root, arm, receipt)
            retryable = (receipt.get("outcome") == "failure"
                         and receipt.get("failure_reason")
                         in sched.INFRASTRUCTURE_FAILURE_REASONS)
            authorized = (retryable
                          and receipt.get("attempt") == sched.MAX_INFRA_ATTEMPTS
                          and authz.verify(self.root, arm) is not None)
            if ((retryable and attempt < sched.MAX_INFRA_ATTEMPTS) or authorized):
                if not (self.root / STOP_FILE).is_file():
                    continue
            self._posthoc(arm, case, receipt)
            if report.get("retention_container_id"):
                from .px_retention import retire_finished_arm
                retire_finished_arm(self.root, arm, receipt, report)
            completed.append(sched.receipt_id(arm))
            sched.write_checkpoint(self.root, plan, completed)
            self._retire_superseded(arm, receipt)
            return
        completed.append(sched.receipt_id(arm))
        sched.write_checkpoint(self.root, plan, completed)

    def _retire_superseded(self, arm, receipt):
        if receipt.get("attempt") != 2:
            return
        from .px_attempt_retention import retire
        name = f"{arm['tool_id']}-{arm['alias']}.attempt-001"
        try:
            result = retire(self.root, apply=True, only=name)
            if result["skipped"]:
                logging.warning("PX attempt archival deferred: %s", result["skipped"])
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            # A cleanup refusal must not invalidate a terminal scientific
            # receipt or block subsequent arms. The operator can retry it.
            logging.warning("PX attempt archival deferred: %s", exc)

    def _prepare_retry(self, arm, prior, expected_attempt):
        """Fail closed unless the prior receipt authorizes exactly this retry."""
        if prior.get("attempt") != expected_attempt:
            raise ValueError("prior receipt is not the dispatch being retried")
        if (prior.get("outcome") != "failure"
                or prior.get("failure_reason")
                not in sched.INFRASTRUCTURE_FAILURE_REASONS):
            raise ValueError("prior terminal receipt is not a retryable failure")
        if (prior.get("attempt") == sched.MAX_INFRA_ATTEMPTS
                and authz.verify(self.root, arm) is None):
            raise ValueError("exhausted PX attempt is not authorized")
        if prior.get("attempt") >= sched.AUTHORIZED_EXTRA_ATTEMPT:
            raise ValueError("no further attempts beyond the authorized retry")
        self._preserve_attempt(arm, expected_attempt)

    def _preserve_attempt(self, arm, attempt):
        output = self.root / "outputs" / (arm["tool_id"] + "-" + arm["alias"])
        if not output.exists():
            return
        if not output.is_dir():
            raise ValueError("canonical output is not a directory")
        archive = (self.root / "outputs" / "attempts"
                   / (arm["tool_id"] + "-" + arm["alias"]
                      + f".attempt-{attempt:03d}"))
        if archive.exists():
            # A preserved archive alongside a live output directory is an
            # interrupted retry; moving one over the other would mix attempts.
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
            runner_receipt_sha256=report.get("runner_receipt_sha256"),
            runner_attestation=report)
