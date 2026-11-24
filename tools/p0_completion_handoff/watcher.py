#!/usr/bin/env python3
"""Supervised, read-only P0 completion handoff.

The watcher polls only the controller's public health snapshot. It acts on a
terminal *transition* (FATAL or a genuine 198/198 completion), never on case
counts, and never launches or reruns a benchmark. On complete evidence it runs
the merged PR433 exact readback and PR435 final-decision tools exactly once,
atomically preserves their anonymized output outside both audited roots with
SHA-256 proof, and posts one durable board notification naming the exact next
action. Restarts and repeated polls reuse the verified artifacts.

Infrastructure failures (tool exit, timeout, board-post failure) are retried
with bounded backoff; malformed or unattested evidence is fail-closed and never
reported as a scientific pass. This module deliberately avoids ``assert`` so
its behaviour is unchanged under ``python -O``.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

MANIFEST_SCHEMA = "ivanka.p0.completion-handoff-manifest.v1"
JOURNAL_SCHEMA = "ivanka.p0.completion-handoff-journal.v1"
HEALTH_SCHEMA = "ivanka.p0.frozen-rust-only-continuation-health.v1"
AUDIT_SCHEMA = "ivanka.p0.independent-frozen-original-partial-psi-audit.v1"
DECISION_SCHEMA = "ivanka.p0.final-physical-decision.v1"
EXPECTED_CASES = 198

PINNED_IMAGE = "73f29f0233da2ecd1ab126178cba4deb9e246bff5a6f770ab021a8f36d71081b"
PINNED_MANIFEST = "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f"
PINNED_PANEL = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"

FATAL_STATE = "FATAL_MANUAL_REVIEW_REQUIRED"
PAUSED_PREFIX = "PAUSED"
COMPLETE_STATES = frozenset({
    "P0_FULL_SEVEN_QUALIFIED",
    "P0_IVA_GATE_PASSED_SEVEN_WAY_COMPARATOR_FAILURE_BLOCKED",
    "P0_ALL198_COMPLETE_SCIENTIFIC_GATES_FAIL_MANUAL_REVIEW",
})
NONTERMINAL_STATES = frozenset({
    "RUNNING_SOURCE_FROZEN_P0",
    "BOUNDED_BATCH_DONE",
    "PREFLIGHT_READY",
    "WAITING_FOR_THREE_INDEPENDENT_CANARIES",
})

TERMINAL_ACT = frozenset({"FATAL", "COMPLETE"})


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(message):
    print(f"{utcnow()} P0_COMPLETION_WATCH {message}", flush=True)


class InfraError(RuntimeError):
    """A retryable infrastructure failure, never a scientific verdict."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path, document):
    """Durably replace one JSON file so a crash never leaves a partial record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if tmp.exists():
        tmp.unlink()
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    with tmp.open("x", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def read_json(path):
    """Return (document, error). Kept separate from classification on purpose."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, repr(exc)


def classify(health):
    """Map a health snapshot to a phase without ever scoring evidence.

    A completion is recognised only from an explicit terminal controller state
    *and* a full attested count. The controller's ``P0_FULL_SEVEN_QUALIFIED``
    label is treated as a trigger for independent reconciliation, never as a
    scientific pass (Intent 006 still requires the expanded 464-synthetic gate).
    """
    if not isinstance(health, dict):
        return "MALFORMED", "health document is not an object"
    if health.get("schema") != HEALTH_SCHEMA:
        return "MALFORMED", "health schema drift"
    state = health.get("state")
    completed = health.get("completed")
    total = health.get("total")
    if not isinstance(state, str) or not isinstance(completed, int) or not isinstance(total, int):
        return "MALFORMED", "health state/count fields missing"
    if state == FATAL_STATE:
        return "FATAL", state
    if state.startswith(PAUSED_PREFIX):
        return "PAUSED", state
    if state in COMPLETE_STATES:
        if completed == EXPECTED_CASES and total == EXPECTED_CASES:
            return "COMPLETE", state
        return "MALFORMED", "terminal state without a full 198/198 cohort"
    if state in NONTERMINAL_STATES:
        return "RUNNING", state
    return "UNKNOWN", state


def transition_key(phase, health):
    """Stable idempotency key surviving restarts and repeated terminal polls."""
    if phase == "COMPLETE":
        return "complete:" + str(health.get("final_all_r_sha256") or health.get("utc") or "198")
    if phase == "FATAL":
        return "fatal:" + str(health.get("utc") or health.get("error") or "unknown")
    return phase + ":" + str(health.get("utc") or "")


def load_journal(path):
    doc, error = read_json(path)
    if error or not isinstance(doc, dict) or doc.get("schema") != JOURNAL_SCHEMA:
        return {"schema": JOURNAL_SCHEMA, "last_phase": None, "handled": {}, "history": []}
    return doc


class ToolRunner:
    """Invoke the exact merged PR433/PR435 tools from a pinned source root."""

    def __init__(self, python, source_root, audited_root, frozen_root, projects_json, hxb2_fasta):
        self.python = str(python)
        self.source_root = Path(source_root)
        self.audited_root = Path(audited_root)
        self.frozen_root = Path(frozen_root)
        self.projects_json = Path(projects_json)
        self.hxb2_fasta = Path(hxb2_fasta)

    def _run(self, script, args, out):
        cmd = [self.python, "-u", str(self.source_root / "benchmarks" / script), *args, "--out", str(out)]
        try:
            proc = subprocess.run(cmd, cwd=str(self.source_root), capture_output=True,
                                  text=True, timeout=1800)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InfraError(f"{script} could not complete: {exc!r}") from exc
        if proc.returncode != 0:
            raise InfraError(f"{script} exit {proc.returncode}: {proc.stderr[-1000:]}")
        return proc.stdout

    def readback(self, out):
        return self._run("independent_frozen_psi_audit.py", [
            "--root", str(self.audited_root),
            "--frozen-root", str(self.frozen_root),
            "--projects-json", str(self.projects_json),
            "--hxb2-fasta", str(self.hxb2_fasta),
        ], out)

    def decision(self, report, out):
        return self._run("final_p0_decision.py", ["--report", str(report)], out)


class BoardPoster:
    def __init__(self, command, author, issues):
        self.command = list(command)
        self.author = author
        self.issues = list(issues)

    def post(self, issue, body):
        cmd = [*self.command, "--id", issue, "--body", body,
               "--author", self.author, "--json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InfraError(f"board post to {issue} failed: {exc!r}") from exc
        if proc.returncode != 0:
            raise InfraError(f"board post to {issue} exit {proc.returncode}: {proc.stderr[-800:]}")
        return proc.stdout


def with_retry(fn, label, attempts=3, base_seconds=2.0):
    """Retry only infrastructure operations; never reinterpret a verdict."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except InfraError as exc:
            if attempt == attempts:
                raise
            delay = base_seconds * (2 ** (attempt - 1))
            log(f"{label} infra failure {attempt}/{attempts}: {exc}; retry in {delay:g}s")
            time.sleep(delay)
    raise InfraError(f"{label} exhausted retries")


def validate_audit(report):
    """Return a list of integrity reasons; an empty list means admissible."""
    reasons = []
    if not isinstance(report, dict):
        return ["audit_not_object"]
    if report.get("schema") != AUDIT_SCHEMA:
        reasons.append("audit_schema_drift")
    if report.get("qualification_claim") != "NONE":
        reasons.append("audit_qualification_claim_not_none")
    if report.get("attested_finished_cases") != EXPECTED_CASES:
        reasons.append("audit_not_198_attested")
    pinned = report.get("pinned") or {}
    if pinned.get("image_sha256") != PINNED_IMAGE:
        reasons.append("audit_image_hash_mismatch")
    if pinned.get("manifest_sha256") != PINNED_MANIFEST:
        reasons.append("audit_manifest_hash_mismatch")
    if pinned.get("panel_sha256") != PINNED_PANEL:
        reasons.append("audit_panel_hash_mismatch")
    return reasons


def validate_decision(result):
    reasons = []
    if not isinstance(result, dict):
        return ["decision_not_object"]
    if result.get("schema") != DECISION_SCHEMA:
        reasons.append("decision_schema_drift")
    if result.get("qualification_claim") != "NONE" or result.get("expanded_claim") != "NONE":
        reasons.append("decision_claim_not_none")
    if result.get("contains_sample_identifiers") is not False:
        reasons.append("decision_may_contain_sample_identifiers")
    if (result.get("cohort") or {}).get("attested_finished_cases") != EXPECTED_CASES:
        reasons.append("decision_cohort_not_198")
    if not isinstance(result.get("decision"), str) or not result["decision"]:
        reasons.append("decision_state_missing")
    return reasons


def _valid_artifacts(manifest, artifacts_dir):
    """True only if a prior run left a complete, hash-attested evidence set."""
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        return False
    for name in ("readback", "decision"):
        entry = (manifest.get(name) or {})
        path = artifacts_dir / entry.get("name", "")
        try:
            if not path.is_file() or sha256_file(path) != entry.get("sha256"):
                return False
        except OSError:
            return False
    return bool(validate_audit(manifest.get("_audit_cached")) == []) and \
        bool(validate_decision(manifest.get("_decision_cached")) == [])


def ensure_artifacts(config, runner):
    """Run each expensive tool at most once and preserve output atomically.

    Returns (manifest, reasons). ``reasons`` non-empty is an integrity failure
    that is fail-closed and never converted into a pass.
    """
    artifacts_dir = Path(config["artifacts_dir"])
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = artifacts_dir / "manifest.json"
    manifest, _ = read_json(manifest_path)
    if _valid_artifacts(manifest, artifacts_dir):
        log("verified existing hash-attested artifacts; skipping rescoring")
        return manifest, []

    readback_name = "readback-audit-198.json"
    decision_name = "final-p0-decision-198.json"
    for name in (readback_name, decision_name):
        for stale in artifacts_dir.glob(f".{name}.tmp.*"):
            stale.unlink()

    readback_tmp = artifacts_dir / f".{readback_name}.tmp.{os.getpid()}"
    decision_tmp = artifacts_dir / f".{decision_name}.tmp.{os.getpid()}"
    stdout = with_retry(lambda: runner.readback(readback_tmp), "PR433 readback")
    log("PR433 readback stdout: " + stdout.strip().replace("\n", " | ")[-300:])
    audit_doc, error = read_json(readback_tmp)
    reasons = validate_audit(audit_doc) if error is None else [f"audit_unreadable:{error}"]
    if not reasons:
        with_retry(lambda: runner.decision(readback_tmp, decision_tmp), "PR435 decision")
        decision_doc, derr = read_json(decision_tmp)
        reasons = validate_decision(decision_doc) if derr is None else [f"decision_unreadable:{derr}"]

    if reasons:
        log("INTEGRITY_FAILURE reasons=" + ",".join(reasons))
        for stale in (readback_tmp, decision_tmp):
            if stale.exists():
                stale.unlink()
        return None, reasons

    os.replace(readback_tmp, artifacts_dir / readback_name)
    os.replace(decision_tmp, artifacts_dir / decision_name)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "created_utc": utcnow(),
        "readback": {"name": readback_name, "sha256": sha256_file(artifacts_dir / readback_name)},
        "decision": {"name": decision_name, "sha256": sha256_file(artifacts_dir / decision_name),
                     "state": decision_doc["decision"]},
        "attested_finished_cases": audit_doc["attested_finished_cases"],
        "pinned": audit_doc["pinned"],
        "board_notification": None,
        "_audit_cached": audit_doc,
        "_decision_cached": decision_doc,
    }
    atomic_write_json(manifest_path, manifest)
    log(f"preserved anonymized evidence: decision={decision_doc['decision']}")
    return manifest, []


def build_body(phase, context):
    """Durable, anonymized notification carrying the exact next action."""
    head = [
        "[p0-completion-handoff]",
        f"state: {context['headline']}",
        f"owner: {context['owner']}",
        f"repository: {context['repository']}",
        f"source_commit: {context['source_commit']}",
        f"controller_state: {context['controller_state']}",
        "host: marceline-dev",
    ]
    if phase == "COMPLETE":
        manifest = context.get("manifest")
        if manifest is None:
            reasons = context.get("reasons") or []
            head += [
                "attested_finished_cases: UNVERIFIED",
                "final_decision: INTEGRITY_FAILURE",
                "integrity_reasons: " + ",".join(reasons),
                "next: Do NOT claim a pass or tag. Independent reviewer must inspect the "
                "preserved evidence and re-run PR433/PR435 from exact pinned source "
                "(issue h4u6MKP9T9prsOqr3ZULCZ-liver); no controller/candidate edit, no P1, no PX.",
            ]
        else:
            decision = manifest["decision"]["state"]
            head += [
                "controller_completed: 198/198",
                f"attested_finished_cases: {manifest['attested_finished_cases']}",
                f"final_decision: {decision}",
                "decision_scope: PHYSICAL_ORIGINAL_198_ONLY",
                "expanded_claim: NONE",
                "qualification_claim: NONE",
                "readback_sha256: " + manifest["readback"]["sha256"],
                "decision_sha256: " + manifest["decision"]["sha256"],
                "pinned_image: " + str(manifest["pinned"].get("image_sha256")),
                "pinned_manifest: " + str(manifest["pinned"].get("manifest_sha256")),
                "pinned_panel: " + str(manifest["pinned"].get("panel_sha256")),
                "artifact_dir: " + context["artifacts_dir"],
                "next: 1) independent reviewer re-runs the exact PR433 readback and PR435 "
                "fail-closed decision from this exact source in its own directory; 2) perform "
                "the full 198/198 all-r re-audit including missing rival arms and high-r tails "
                "recorded in h4u6MKP9T9prsOqr3ZULCZ-liver; 3) only after independent review and "
                "the expanded 464-synthetic seven-way gate (Intent 006) may any pass/tag be "
                "considered. No recomputation by this watcher; no new MiCall runs; no PX; no "
                "controller, candidate, threshold or frozen-source edit.",
            ]
    elif phase == "FATAL":
        head += [
            "error: " + str(context.get("error") or "controller fail-closed"),
            "next: Controller is FATAL_MANUAL_REVIEW_REQUIRED. Inspect preserved candidate "
            "scratch/receipts and disk capacity; do NOT blindly restart the s6 service or "
            "recompute completed cases; require independent review before any resume. "
            "Final evidence is NOT available, so no scientific decision was run.",
        ]
    return "\n".join(head) + "\n"


def record_board(context, manifest_path, body, board):
    """Post once per issue; persist proof so a restart never double-posts."""
    manifest = None
    if manifest_path is not None and manifest_path.is_file():
        manifest, _ = read_json(manifest_path)
    already = set()
    if isinstance(manifest, dict):
        already = {entry.get("issue") for entry in (manifest.get("board_notification") or [])}
    posted = []
    for issue in board.issues:
        if issue in already:
            log(f"board issue {issue} already notified; skipping")
            continue
        board.post(issue, body)
        posted.append({"issue": issue, "utc": utcnow(), "body_sha256":
                       hashlib.sha256(body.encode("utf-8")).hexdigest()})
    if isinstance(manifest, dict):
        manifest["board_notification"] = (manifest.get("board_notification") or []) + posted
        atomic_write_json(manifest_path, manifest)


def handle_terminal(config, phase, health, journal, runner, board):
    """Execute one terminal transition. Returns True when fully handled."""
    key = transition_key(phase, health)
    handled = journal["handled"].get(key)
    if handled and handled.get("done"):
        log(f"transition {key} already handled; nothing to do")
        return True

    attempts = int((handled or {}).get("attempts", 0)) + 1
    context = {
        "headline": "COMPLETE_EVIDENCE_AVAILABLE" if phase == "COMPLETE" else "CONTROLLER_FATAL",
        "owner": config["owner"],
        "repository": config["repository"],
        "source_commit": config["source_commit"],
        "controller_state": health.get("state"),
        "error": health.get("error"),
        "artifacts_dir": config["artifacts_dir"],
        "manifest": None,
        "reasons": [],
    }

    manifest_path = Path(config["artifacts_dir"]) / "manifest.json"
    if phase == "COMPLETE":
        manifest, reasons = ensure_artifacts(config, runner)
        context["manifest"] = manifest
        context["reasons"] = reasons
        # Integrity failure is a verdict, not an infra error: notify once, no retry loop.
        if reasons:
            body = build_body(phase, context)
            with_retry(lambda: record_board(context, None, body, board), "board integrity notice")
            journal["handled"][key] = {"phase": phase, "done": True, "attempts": attempts,
                                       "outcome": "INTEGRITY_FAILURE", "reasons": reasons,
                                       "utc": utcnow()}
            return True
        manifest, _ = read_json(manifest_path)
        if manifest.get("board_notification"):
            log("board notification already recorded in manifest")
            journal["handled"][key] = {"phase": phase, "done": True, "attempts": attempts,
                                       "outcome": "notified", "utc": utcnow()}
            return True
    else:
        notice = {
            "schema": "ivanka.p0.completion-handoff-fatal.v1",
            "utc": utcnow(),
            "health": health,
            "health_sha256": hashlib.sha256(json.dumps(health, sort_keys=True).encode()).hexdigest(),
        }
        atomic_write_json(Path(config["artifacts_dir"]) / f"fatal-{attempts}.json", notice)

    body = build_body(phase, context)
    try:
        with_retry(lambda: record_board(context, manifest_path if phase == "COMPLETE" else None,
                                        body, board), "board notification")
    except InfraError as exc:
        if attempts >= config.get("max_attempts", 5):
            log(f"board notification permanently failed after {attempts} attempts: {exc}")
            journal["handled"][key] = {"phase": phase, "done": True, "attempts": attempts,
                                       "outcome": "board_post_exhausted", "utc": utcnow()}
            return True
        journal["handled"][key] = {"phase": phase, "done": False, "attempts": attempts,
                                   "outcome": "retry_pending", "utc": utcnow()}
        log(f"board notification deferred to next poll ({attempts} attempts)")
        return False

    journal["handled"][key] = {"phase": phase, "done": True, "attempts": attempts,
                               "outcome": "notified", "utc": utcnow()}
    log(f"durable board notification posted for {key}")
    return True


def run(config, max_polls=None):
    """Poll cheaply and act only on terminal transitions. Returns exit status."""
    artifacts_dir = Path(config["artifacts_dir"])
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    journal_path = artifacts_dir / "journal.json"
    journal = load_journal(journal_path)
    runner = ToolRunner(config["python"], config["source_root"], config["audited_root"],
                        config["frozen_root"], config["projects_json"], config["hxb2_fasta"])
    board = BoardPoster(config.get("board_command", ["antonina", "board", "comment"]),
                        config["owner"], config.get("board_issues", []))
    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1
        health, error = read_json(config["health"])
        if error is not None:
            log(f"health unreadable ({error}); no action this poll")
        else:
            phase, reason = classify(health)
            if phase != journal.get("last_phase"):
                log(f"phase transition {journal.get('last_phase')} -> {phase} ({reason})")
                journal["last_phase"] = phase
                journal.setdefault("history", []).append(
                    {"utc": utcnow(), "phase": phase, "reason": reason,
                     "completed": health.get("completed") if isinstance(health, dict) else None})
                journal["history"] = journal["history"][-50:]
                atomic_write_json(journal_path, journal)
            if phase in TERMINAL_ACT:
                done = handle_terminal(config, phase, health, journal, runner, board)
                atomic_write_json(journal_path, journal)
                if done and config.get("exit_when_done"):
                    log("handoff complete; exiting so s6 can hold instead of restart")
                    return 0
        if max_polls is not None and polls >= max_polls:
            break
        time.sleep(float(config.get("interval", 60)))
    return 0


def load_config(path):
    doc, error = read_json(path)
    if error:
        raise SystemExit(f"cannot read config {path}: {error}")
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="JSON handoff configuration")
    parser.add_argument("--polls", type=int, default=None,
                        help="run at most N polls (testing); default is forever")
    parser.add_argument("--once", action="store_true", help="alias for --polls 1")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    return run(config, 1 if args.once else args.polls)


if __name__ == "__main__":
    sys.exit(main())
