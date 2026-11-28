"""Independent watchdog over every durable lease in the project root.

The controller owns each arm; this module owns only observation and the
fail-closed consequence. It discovers active leases from the append-only
journal, verifies the exact CID in the pinned store, reads the controller
heartbeat and a bounded process tree, and records immutable evidence of any
action it takes. It never signals a PID, never chooses a container by name or
listing order, and never writes a benchmark receipt.
"""
import json
import math
import os
import time
from pathlib import Path

from . import (binding, build, heartbeat, identity, lease, orphans, proc,
               startup, store, teardown, tree)
from .errors import GuardExceeded

SCHEMA = "ivanka.watchdog-evidence.v1"
HEARTBEAT_SCHEMA = heartbeat.SCHEMA
EVIDENCE_NAME = ".watchdog-evidence.jsonl"

# The policy ceiling is 4 GiB. The enforced arm budget stays the stricter
# decimal 4e9 bytes; the upper bound is never raised to the ceiling.
RSS_UPPER_BOUND = 4 * 1024 ** 3
RSS_LIMIT = 4_000_000_000
DEFAULT_MIN_FREE = 34_359_738_368
DEFAULT_RESERVE = 1024 ** 3
DEFAULT_WALL_SECONDS = 2400
DEFAULT_INTERVAL = 0.5
DEFAULT_HEARTBEAT_MAX_AGE = heartbeat.ALIVE_MAX_AGE
# A cidfile can appear before the controller publishes the bound fingerprint
# or even updates its heartbeat CID. This grace is bounded by durable
# acquisition, a fresh live controller heartbeat, and exact-CID inspection in
# the pinned store; it never extends the arm wall deadline.
DEFAULT_STARTUP_BIND_GRACE = 120.0
# A clean refusal of an unsupported lease is not a failure of the observer.
# Keeping readiness intact lets admission name the unsupported mode itself.
READINESS_PRESERVING_REASONS = frozenset({"unsupported_lease"})

# Distinguishes "the caller did not pre-inspect" from "the exact CID was
# inspected and proved absent". The latter is a verified observation, not an
# omitted step, so it must still take the second-inspect absence path.
_UNSET = object()


def evidence_path(root):
    """Project-owned evidence journal; never supplied by the container."""
    return Path(root) / EVIDENCE_NAME


def append_evidence(root, event):
    """Append one fsynced observation; earlier evidence is never rewritten."""
    fd = os.open(str(evidence_path(root)), os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                 0o600)
    try:
        os.write(fd, (json.dumps(event, sort_keys=True, default=str) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def read_evidence(root):
    """Return validated evidence, failing closed on tamper or corruption."""
    path = evidence_path(root)
    if not path.exists() and not path.is_symlink():
        return []
    if path.is_symlink() or not path.is_file():
        raise GuardExceeded("journal_unavailable")
    table = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise GuardExceeded("journal_unreadable") from exc
        if not isinstance(event, dict) or event.get("schema") != SCHEMA:
            raise GuardExceeded("journal_unreadable")
        table.append(event)
    return table


pin_env = store.pin_env
verify_namespace = store.verify_namespace


def read_heartbeat(path, *, monotonic=None,
                   max_age=DEFAULT_HEARTBEAT_MAX_AGE, worker=None):
    """Read a heartbeat; malformed, future, non-finite or stale ages fail."""
    clock = monotonic if monotonic is not None else time.monotonic
    target = Path(path)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise GuardExceeded("heartbeat_unreadable")
    if not target.exists():
        raise GuardExceeded("heartbeat_missing")
    try:
        lines = target.read_text().splitlines()
        event = json.loads(lines[-1])
    except (OSError, ValueError, IndexError) as exc:
        raise GuardExceeded("heartbeat_unreadable") from exc
    finger = event.get("fingerprint") if isinstance(event, dict) else None
    pid = event.get("pid") if isinstance(event, dict) else None
    if (not isinstance(event, dict) or event.get("schema") != HEARTBEAT_SCHEMA
            or (worker is not None and event.get("lease") != str(worker))
            or not isinstance(pid, int) or pid <= 0
            or not isinstance(finger, list) or len(finger) < 2):
        raise GuardExceeded("heartbeat_unreadable")
    try:
        at = float(event["at_monotonic"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GuardExceeded("heartbeat_unreadable") from exc
    age = clock() - at
    if not math.isfinite(at) or not math.isfinite(age) or age < 0:
        raise GuardExceeded("heartbeat_unreadable")
    if age > max_age:
        raise GuardExceeded("heartbeat_stale")
    return {"lease": event.get("lease"), "pid": pid,
            "fingerprint": tuple(finger),
            "cmdline_sha": event.get("cmdline_sha"), "cid": event.get("cid"),
            "age_seconds": age}


def observe_controller(heartbeat_record, table):
    """Confirm the heartbeat still belongs to a live process with that identity."""
    finger = heartbeat_record["fingerprint"]
    bound = {"pid": heartbeat_record["pid"], "fingerprint": list(finger),
             "starttime": finger[0], "pid_ns": finger[1],
             "cmdline_sha": heartbeat_record.get("cmdline_sha"),
             "stable": len(finger) == 2}
    if bound["stable"]:
        pid = startup.locate(bound, table, bound_pid=heartbeat_record["pid"])
    else:
        pid = identity.locate(tuple(finger), table,
                              bound_pid=heartbeat_record["pid"])
    return {"pid": pid, "identity": startup.observation(bound, table)}


def discover_workers(root):
    """Every active lease is supervised; ids are never pinned by an operator."""
    current = lease.latest(lease.events(root))
    return sorted(worker for worker, event in current.items()
                  if event.get("state") == "active")


def bound_from_lease(root, worker, env):
    """Resolve the exact CID from a durable lease or its trusted cidfile.

    A cidfile recorded in an active lease may appear after its owner dies. It
    is read only from the project-owned lease path, never discovered by
    listing containers. The resulting CID is still verified in the pinned
    store before any action is taken.
    """
    current = lease.latest(lease.events(root)).get(str(worker))
    if current is None:
        return {"state": "absent"}
    state = current.get("state")
    if state in lease.CLOSED:
        return {"state": "released", "cid": current.get("cid")}
    if state == "active" and current.get("mode") == "copy_overlay":
        start = current.get("at_utc")
        if not isinstance(start, (int, float)) or not math.isfinite(start):
            raise GuardExceeded("invalid_lease")
        pid, pgid = current.get("pid"), current.get("pgid")
        finger = current.get("fingerprint")
        if (isinstance(pid, int) and pid > 0 and pgid == pid
                and isinstance(finger, (list, tuple)) and len(finger) >= 2):
            return {"state": "bound_group", "mode": "copy_overlay",
                    "pid": pid, "pgid": pgid, "fingerprint": finger,
                    "stable": len(finger) == 2,
                    "plan_sha256": current.get("plan_sha256"),
                    "graphroot": current.get("graphroot"),
                    "baseline_ids": current.get("baseline_ids") or [],
                    "base_image": current.get("base_image"),
                    "base_layers": current.get("base_layers") or [],
                    "durable_start": start}
        # A crash before the post-spawn group bind owns no process yet; the
        # active lease still blocks admission until an owner reconciles it.
        return {"state": "pending_group", "mode": "copy_overlay",
                "durable_start": start}
    if state != "active" or current.get("mode") != "pilot":
        return {"state": "unsupported"}
    start = current.get("at_utc")
    if not isinstance(start, (int, float)) or not math.isfinite(start):
        raise GuardExceeded("invalid_lease")
    cid = current.get("cid")
    source = "journal"
    if cid is None and current.get("cidfile"):
        try:
            cid = binding.read_cid(current["cidfile"])
        except GuardExceeded:
            cid = None
        source = "cidfile" if cid is not None else None
    if cid is None:
        return {"state": "pending", "cidfile": current.get("cidfile"),
                "durable_start": start, "cid_source": None}
    if not isinstance(cid, str) or not binding.CID.fullmatch(cid):
        raise GuardExceeded("invalid_lease")
    finger = current.get("fingerprint")
    bound = {"state": "bound", "cid": cid, "pid": current.get("pid"),
             "fingerprint": finger, "cidfile": current.get("cidfile"),
             "cid_source": source, "durable_start": start}
    if isinstance(finger, (list, tuple)) and len(finger) >= 2:
        bound["stable"] = len(finger) == 2
    return bound


def _group_anchor(bound, pid):
    finger = bound["fingerprint"]
    return {"pid": pid, "fingerprint": list(finger),
            "starttime": finger[0], "pid_ns": finger[1],
            "cmdline_sha": finger[2] if len(finger) > 2 else None,
            "stable": bound.get("stable", len(finger) == 2)}


def group_still_owned(bound, table):
    """True only when the exact bound leader and group are still live."""
    try:
        verify_group_bound(bound, table)
        return True
    except GuardExceeded:
        return False


def group_absent(bound, table):
    """True when neither the bound kernel identity nor its PGID remain."""
    identity_keys = tuple(bound["fingerprint"][:2])
    for record in table.values():
        if ((record.get("starttime"), record.get("pid_ns")) == identity_keys
                or record.get("pgid") == bound.get("pgid")):
            return False
    return True


def _quiesced_member(record):
    """True only for a stat-proven zombie with valid structural facts.

    A quiescent zombie is no longer runnable. Positive RSS, an unreadable or
    unknown state, or missing structural identity make the member ambiguous and
    must fail closed.
    """
    if record.get("structural_unavailable"):
        return False
    state = record.get("state")
    if state != "Z":
        return False
    if any(record.get(key) is None for key in ("starttime", "pid_ns", "pgid")):
        return False
    rss = record.get("rss")
    return rss is None or (isinstance(rss, int) and rss == 0)


def group_quiesced(bound, table):
    """True when the bound group has no live/runnable members.

    After natural completion a descendant may remain as a kernel-verified zombie
    (state Z) with the original PGID. That member is quiescent, not reaped; the
    proof accepts it only when every member of the exact bound PGID is a proven
    zombie with valid structural facts and no positive RSS. Membership is by the
    bound PGID alone: a process that merely shares the leader's starttime and
    PID-namespace tick but sits in a different PGID is unrelated and must never
    be treated as bound. Any live, unreadable, unknown, reused-leader, ambiguous,
    positive-RSS zombie or escaped live descendant fails closed.
    """
    identity_keys = tuple(bound["fingerprint"][:2])
    pgid = bound.get("pgid")
    bound_pid = bound.get("pid")
    # Bind members by the exact PGID, never by the leader's starttime tick. A
    # same-tick process in another PGID is neither a bound member nor exempt
    # from any check merely because it shares the leader's immutable identity.
    members = [(pid, record) for pid, record in table.items()
               if record.get("pgid") == pgid]
    if any(record.get("structural_unavailable") for _, record in members):
        return False
    if not members:
        return False
    # The leader is located by its exact bound PID plus immutable kernel facts,
    # never by starttime alone: unrelated processes can share a starttime tick.
    # It may be absent (reaped) or present as a quiescent zombie.
    leader = table.get(bound_pid)
    if leader is not None:
        if ((leader.get("starttime"), leader.get("pid_ns")) != identity_keys
                or leader.get("pgid") != pgid
                or not _quiesced_member(leader)):
            return False
    for pid, record in members:
        # Only the exact bound PID was validated above. Every other member of
        # the bound PGID must independently prove it is a quiescent zombie,
        # including any same-tick sibling that the old tick-based skip ignored.
        if pid == bound_pid:
            continue
        if record.get("pgid") != pgid:
            return False
        if not _quiesced_member(record):
            return False
    # Descendants of a quiescent group cannot be live; a live or ambiguous
    # process reparented outside the PGID is an escaped descendant.
    member_pids = {pid for pid, _ in members}
    descendants = set(tree.descendants(table, bound_pid))
    for pid, record in table.items():
        if pid in member_pids:
            continue
        if pid in descendants or record.get("ppid") == bound_pid:
            if record.get("structural_unavailable"):
                return False
            if not _quiesced_member(record):
                return False
    # Explicitly a quiescence proof: no reaping is claimed and no absence is
    # asserted for the still-visible zombie PIDs/PGID.
    return {"quiescent": True, "quiescent_zombies": len(members)}


def group_absence_proven(bound, table):
    """True only when a trustworthy snapshot proves the exact group is gone.

    An unreadable /proc record leaves the bound group's fate unknown, so a
    partial snapshot cannot prove absence. This is the proof consumed by group
    teardown, including the case where a fast COPY-only helper exited on its
    own before its stop callback ran.
    """
    if any(item.get("structural_unavailable") for item in table.values()):
        return False
    return group_absent(bound, table)


def verify_group_bound(bound, table):
    """Verify the exact session leader and its process group, never a reused PID."""
    finger = bound["fingerprint"]
    anchor = _group_anchor(bound, bound["pid"])
    if anchor["stable"]:
        pid = startup.locate(anchor, table, bound_pid=bound["pid"])
    else:
        pid = identity.locate(tuple(finger), table, bound_pid=bound["pid"])
    record = table[pid]
    pgid = record.get("pgid")
    if pgid is None:
        raise GuardExceeded("measurement_unavailable")
    if pgid != bound["pgid"] or bound["pgid"] != bound["pid"]:
        raise GuardExceeded("identity_lost")
    members = {member for member, item in table.items()
               if item.get("pgid") == pgid}
    members.update(tree.descendants(table, pid))
    return {"pid": pid, "pgid": pgid,
            "rss": tree.rss_bytes(table, members), "members": len(members),
            "identity": startup.observation(anchor, table)}


def verify_bound(bound, env, table, *, heartbeat_record=None, wall=None,
                 startup_bind_grace=DEFAULT_STARTUP_BIND_GRACE,
                 controller_live=False, first_pid=_UNSET):
    """Re-inspect the exact CID in the pinned store and measure its tree.

    ``check_once`` inspects the exact CID *before* it samples ``table`` and
    passes that result as ``first_pid``. This function then re-inspects the
    same CID before measuring or permitting a pending bind: a different PID is
    terminal identity drift. Neither form of pending bind (published or
    unpublished heartbeat CID) outlives the bounded durable-start grace.
    Direct callers that do not supply ``first_pid`` keep the legacy
    single-inspect behaviour.

    A cidfile can appear before the controller publishes the bound fingerprint
    or updates its heartbeat CID from None. While the controller heartbeat is
    fresh/live, the exact CID still resolves to the same PID, and the arm is
    within a bounded startup grace from durable acquisition, that is a healthy
    bind in progress, not an orphan: observe it without teardown. A dead/expired
    heartbeat never reaches this branch (check_once fails closed first) and a
    heartbeat naming a different CID is identity_lost, so pending_bind cannot
    mask an orphan.

    A naturally exited or already removed CID is not a breach: a live controller
    is allowed to finalize its own natural completion. Absence is accepted only
    on two consecutive exact-CID inspections while a freshly verified, matching
    live controller is present; a PID that was live at the first inspection
    needs a third inspection proving it did not reappear or drift. No receipt
    or lease is released by this observation. Malformed or mismatched inspect
    output is a verification failure, never an absence, and a dead, foreign or
    uncertain controller with an absent CID still fails closed.
    """
    if bound.get("state") == "bound_group":
        return verify_group_bound(bound, table)
    cid = bound["cid"]
    if not isinstance(cid, str) or not binding.CID.fullmatch(cid):
        raise GuardExceeded("binding_unavailable")
    diagnosis = None
    absence_inspections = 2

    def fail(reason):
        exc = GuardExceeded(reason)
        if diagnosis is not None:
            exc.sample_diagnostic = diagnosis
        raise exc

    if first_pid is _UNSET:
        pid = binding.inspect_pid_if_live(cid, env)
    else:
        pid = first_pid
        # The sample was taken after `first_pid`, so this is the same CID's
        # second inspection: nothing may be measured or granted grace unless
        # it still names the identical init PID.
        second = binding.inspect_pid_if_live(cid, env)
        diagnosis = {"sample_after_inspect": True, "first_pid": pid,
                     "second_pid": second}

        if pid is None:
            if second is not None:
                fail("binding_unavailable")  # absence then reappearance
        elif second is None:
            # A PID that was live at the first inspection may have exited in
            # between. Accept it as natural exit only for a matching, freshly
            # verified live controller and only after a third inspection
            # proves two consecutive absences with no reappearance or drift.
            if not (controller_live and heartbeat_record is not None
                    and heartbeat_record.get("cid") == cid):
                fail("binding_unavailable")
            third = binding.inspect_pid_if_live(cid, env)
            diagnosis["third_pid"] = third
            diagnosis["natural_exit_after_live"] = True
            if third is not None:
                fail("identity_lost" if third != pid
                     else "binding_unavailable")
            pid = None
            absence_inspections = 3
        elif second != pid:
            fail("identity_lost")
    if pid is None:
        if not controller_live:
            fail("binding_unavailable")
        if first_pid is _UNSET and binding.inspect_pid_if_live(cid, env) is not None:
            fail("binding_unavailable")
        absence = {"observed_absent": True, "method": "exact_cid_inspect"}
        if diagnosis is not None:
            absence["inspections"] = absence_inspections
        observed = {"state": "natural_exit", "pid": None, "rss": None,
                    "members": 0, "identity": None, "absence_proof": absence}
        if diagnosis is not None:
            observed["sample_diagnostic"] = diagnosis
        return observed
    if bound.get("pid") is not None and int(bound["pid"]) != pid:
        fail("identity_lost")
    finger = bound.get("fingerprint")
    if not isinstance(finger, (list, tuple)) or len(finger) < 2:
        beat_cid = (heartbeat_record.get("cid")
                    if heartbeat_record is not None else None)
        cid_match = beat_cid == cid
        cid_unpublished = (beat_cid is None and heartbeat_record is not None)
        # Both published and unpublished CID binds share the same finite
        # durable-start grace; neither may wait indefinitely for a fingerprint.
        start = bound.get("durable_start")
        clock = wall if wall is not None else time.time
        within_grace = (isinstance(start, (int, float)) and math.isfinite(start)
                        and clock() - start <= startup_bind_grace)
        if (controller_live and heartbeat_record is not None
                and (cid_match or cid_unpublished) and within_grace
                and pid in table):
            observed = {"state": "pending_bind", "pid": pid, "rss": None,
                        "members": 0, "identity": None,
                        "pending_reason": ("heartbeat_cid_match"
                                           if cid_match
                                           else "startup_bind_grace")}
            if diagnosis is not None:
                observed["sample_diagnostic"] = diagnosis
            return observed
        fail("binding_unavailable")
    if bound.get("stable"):
        anchor = {"pid": pid, "fingerprint": list(finger),
                  "starttime": finger[0], "pid_ns": finger[1],
                  "cmdline_sha": bound.get("cmdline_sha"), "stable": True}
        observation = startup.observation(anchor, table)
        try:
            found = startup.locate(anchor, table, bound_pid=pid)
        except GuardExceeded as exc:
            exc.identity_observation = observation
            if diagnosis is not None:
                exc.sample_diagnostic = diagnosis
            raise
    else:
        try:
            found = identity.locate(tuple(finger), table, bound_pid=pid)
        except GuardExceeded as exc:
            if diagnosis is not None:
                exc.sample_diagnostic = diagnosis
            raise
        observation = None
    group = tree.members(table, found, tuple(finger))
    observed = {"pid": found, "rss": tree.rss_bytes(table, group),
                "members": len(group), "identity": observation}
    if diagnosis is not None:
        observed["sample_diagnostic"] = diagnosis
    return observed


def check_disk(free, *, min_free, reserve):
    """Reject unreadable or reserve-breaching free space without inventing bytes."""
    try:
        value = int(free)
    except (TypeError, ValueError) as exc:
        raise GuardExceeded("measurement_unavailable") from exc
    if value - reserve < min_free:
        raise GuardExceeded("disk_limit")
    return value


def teardown_if_owned(root, worker, cid, env, *, stop=None,
                      before_teardown=None):
    """Re-resolve ownership immediately before CID-only teardown.

    ``before_teardown`` persists the already-made fail-closed decision while
    ownership is still held, so a teardown/receipt race cannot erase it. It is
    called only after ownership is re-proven and before the destructive action.
    """
    current = bound_from_lease(root, worker, env)
    if current.get("state") != "bound" or current.get("cid") != cid:
        return {"action": "release_raced", "cid": cid, "teardown": None}
    if before_teardown is not None:
        before_teardown()
    terminate = stop if stop is not None else (
        lambda value: teardown.stop_verified_cid(env, value))
    try:
        proof = terminate(cid)
    except Exception as exc:
        return {"action": "teardown_failed", "cid": cid, "teardown": None,
                "teardown_error": str(exc)[:320]}
    return {"action": "teardown", "cid": cid, "teardown": proof}


def group_callbacks(bound):
    """Conservative proof callbacks for an exact bound process group."""
    return (lambda _pgid, table: group_still_owned(bound, table),
            lambda _pgid, table: group_absence_proven(bound, table))


def teardown_group_if_owned(root, worker, bound, env, *, stop=None,
                            cleanup=None, before_teardown=None,
                            snapshot=None):
    """Re-resolve group ownership before stopping it and reclaiming orphans."""
    current = bound_from_lease(root, worker, env)
    pgid = bound.get("pgid")
    if (current.get("state") != "bound_group"
            or current.get("pgid") != pgid
            or current.get("fingerprint") != bound.get("fingerprint")):
        return {"action": "release_raced", "cid": None, "teardown": None}
    if before_teardown is not None:
        before_teardown()
    verify, absent = group_callbacks(bound)
    take = snapshot if snapshot is not None else proc.snapshot
    terminate = stop if stop is not None else (
        lambda value: build.stop_group_by_id(value, snapshot=take,
                                              verify=verify, absent=absent))
    reclaim = cleanup if cleanup is not None else (
        lambda: orphans.reclaim_owned(
            env, graphroot_of(bound), bound.get("baseline_ids") or {},
            expected_base=bound.get("base_image"),
            base_layers=bound.get("base_layers") or [],
            command_fn=binding.command))
    try:
        proof = terminate(pgid)
        if reclaim is not None:
            proof["orphan_cleanup"] = reclaim()
    except Exception as exc:
        return {"action": "teardown_failed", "cid": None, "teardown": None,
                "teardown_error": str(exc)[:320]}
    return {"action": "teardown", "cid": None, "teardown": proof}


def graphroot_of(bound):
    """Pinned graphroot carried by a group lease, never inferred."""
    value = bound.get("graphroot")
    if not isinstance(value, str) or not value:
        raise GuardExceeded("binding_unavailable")
    return value


def _evidence(root, worker, *, reason, result, bound, observations, action,
              rss_limit):
    return {
        "schema": SCHEMA,
        "at_utc": time.time(),
        "worker": str(worker),
        "lease_state": bound.get("state"),
        "cid": bound.get("cid"),
        "process_group": bound.get("pgid"),
        "cid_source": bound.get("cid_source"),
        "durable_start": bound.get("durable_start"),
        "reason": reason,
        "result": result,
        "action": action["action"],
        "teardown": action.get("teardown"),
        "teardown_error": action.get("teardown_error"),
        "observations": observations,
        "rss_limit_bytes": rss_limit,
        "rss_upper_bound_bytes": RSS_UPPER_BOUND,
        "enforcement": "userspace_observed",
        "kernel_enforcement": False,
    }


def append_group_evidence(root, worker, *, reason, result, proof, observations=None):
    """Record a process-group teardown decision before any lease is closed."""
    event = _evidence(
        root, worker, reason=reason, result=result,
        bound={"state": "bound_group", "pgid": proof.get("process_group")},
        observations=observations or {},
        action={"action": "teardown", "cid": None, "teardown": proof},
        rss_limit=RSS_LIMIT)
    append_evidence(root, event)
    return event


def blocked_evidence(root, worker, reason, detail=None):
    """Record a blocked admission without ever claiming a successful outcome."""
    event = _evidence(root, worker, reason=reason, result="fail_closed",
                      bound={"state": "absent"},
                      observations={"detail": detail},
                      action={"action": "none", "cid": None, "teardown": None},
                      rss_limit=RSS_LIMIT)
    append_evidence(root, event)
    return event


def check_once(root, worker, *, storage_conf, graphroot, env=None,
               min_free=DEFAULT_MIN_FREE, reserve=DEFAULT_RESERVE,
               rss_limit=RSS_LIMIT, wall_seconds=DEFAULT_WALL_SECONDS,
               max_age=DEFAULT_HEARTBEAT_MAX_AGE, heartbeat_path=None,
               monotonic=None, wall_clock=None, snapshot=None, measure=None,
               stop=None, group_cleanup=None, namespace_cache=None,
               startup_bind_grace=DEFAULT_STARTUP_BIND_GRACE):
    """One independent observation of one active lease.

    The wall deadline comes from the lease's durable start, so restarting the
    watchdog cannot extend an arm. Every fail-closed decision is written to
    the evidence journal before it is raised. For a CID-bound lease the exact
    CID is inspected before the process sample; the same CID/PID is inspected
    again before the sample is used for measurement or a pending bind, so a
    PID issued during startup cannot be mistaken for identity drift or an
    orphan.
    """
    mono = monotonic if monotonic is not None else time.monotonic
    wall = wall_clock if wall_clock is not None else time.time
    take = snapshot if snapshot is not None else proc.snapshot
    if (measure is None or rss_limit <= 0 or wall_seconds <= 0
            or min_free <= 0 or reserve < 0 or max_age <= 0):
        raise GuardExceeded("invalid_config")
    # Policy ceilings are absolute; a caller cannot relax them by injection.
    rss_limit = min(rss_limit, RSS_LIMIT)
    wall_seconds = min(wall_seconds, DEFAULT_WALL_SECONDS)
    pinned = pin_env(env, storage_conf=storage_conf)
    namespace_ok = False
    bound = {"state": "absent"}
    observations = {}
    failure = None
    reason = "observing"
    action = {"action": "none", "cid": None, "teardown": None}
    result = "observing"
    try:
        if heartbeat._namespace_verified(namespace_cache, graphroot, wall()):
            namespace_ok = True
        else:
            namespace_ok = bool(verify_namespace(pinned, graphroot))
            if isinstance(namespace_cache, dict):
                namespace_cache.clear()
                namespace_cache.update({"graphroot": str(graphroot),
                                        "verified_at": wall()})
        bound = bound_from_lease(root, worker, pinned)
        if bound["state"] == "unsupported":
            raise GuardExceeded("unsupported_lease")
        start = bound.get("durable_start")
        if start is None:
            raise GuardExceeded("invalid_lease")
        if wall() - start >= wall_seconds:
            raise GuardExceeded("wall_limit")
        source = heartbeat_path or heartbeat.path(root, worker)
        beat = read_heartbeat(source, monotonic=mono, max_age=max_age,
                              worker=worker)
        if (bound.get("cid") is not None and beat.get("cid") is not None
                and beat["cid"] != bound["cid"]):
            raise GuardExceeded("identity_lost")
        observations["heartbeat"] = {
            "pid": beat["pid"], "cid": beat.get("cid"),
            "age_seconds": beat["age_seconds"]}
        # Verify the exact CID before any /proc sample is used for this arm.
        # The sample below must describe the process that inspection attests,
        # not a table captured while the container was still being issued.
        first_pid = _UNSET
        if bound["state"] == "bound":
            try:
                first_pid = binding.inspect_pid_if_live(bound["cid"], pinned)
            except GuardExceeded as exc:
                exc.sample_diagnostic = {
                    "sample_after_inspect": False,
                    "stage": "first_exact_cid_inspect"}
                raise
        table = take()
        observations["controller"] = observe_controller(beat, table)
        controller_live = observations["controller"].get("pid") is not None
        if bound["state"] in ("bound", "bound_group"):
            try:
                kwargs = {}
                if first_pid is not _UNSET:
                    kwargs["first_pid"] = first_pid
                observations["bound"] = verify_bound(
                    bound, pinned, table, heartbeat_record=beat, wall=wall,
                    startup_bind_grace=startup_bind_grace,
                    controller_live=controller_live, **kwargs)
            except GuardExceeded as exc:
                if getattr(exc, "identity_observation", None) is not None:
                    observations["bound"] = {
                        "state": "identity_failed",
                        "identity": exc.identity_observation}
                if getattr(exc, "sample_diagnostic", None) is not None:
                    observations["binding_sample"] = exc.sample_diagnostic
                raise
        else:
            observations["bound"] = {"state": bound["state"]}
        observations["disk_free_bytes"] = check_disk(
            measure(), min_free=min_free, reserve=reserve)
        used = observations["bound"].get("rss")
        if used is not None and used > rss_limit:
            raise GuardExceeded("observed_rss_limit")
    except GuardExceeded as exc:
        failure = exc
        reason = exc.reason
        result = "fail_closed"
        if getattr(exc, "sample_diagnostic", None) is not None:
            observations.setdefault("binding_sample", exc.sample_diagnostic)
    except Exception as exc:
        # Inspection, journal or fsync failures are not clean observations.
        failure = GuardExceeded("inspection_unavailable")
        failure.__cause__ = exc
        reason = failure.reason
        result = "fail_closed"
    if failure is not None:
        # Persist the real limit/failure decision while ownership is still
        # held and BEFORE the destructive action. A controller writing its
        # receipt during teardown then always finds this evidence; it cannot
        # race ahead of a decision made only after the container was removed.
        decision_event = None

        def persist(hint):
            nonlocal decision_event
            decision_event = _evidence(root, worker, reason=reason, result=result,
                                       bound=bound, observations=observations,
                                       action=hint, rss_limit=rss_limit)
            append_evidence(root, decision_event)

        if namespace_ok and bound.get("state") == "bound":
            action = teardown_if_owned(
                root, worker, bound["cid"], pinned, stop=stop,
                before_teardown=lambda: persist(
                    {"action": "teardown", "cid": bound["cid"],
                     "teardown": None}))
        elif namespace_ok and bound.get("state") == "bound_group":
            action = teardown_group_if_owned(
                root, worker, bound, pinned, stop=stop,
                cleanup=group_cleanup, snapshot=take,
                before_teardown=lambda: persist(
                    {"action": "teardown", "cid": None,
                     "process_group": bound["pgid"], "teardown": None}))
        else:
            action = {"action": "none", "cid": bound.get("cid"),
                      "teardown": None}
        if action["action"] == "teardown_failed":
            # Append-only follow-up: the decision above already blocks a
            # success claim, this records why no proof was produced.
            append_evidence(root, _evidence(
                root, worker, reason=reason, result=result, bound=bound,
                observations=observations, action=action,
                rss_limit=rss_limit))
        elif action["action"] == "teardown" and bound.get("state") == "bound_group":
            # A group teardown has no client receipt to carry its proof, so the
            # independent journal records the actual group + orphan evidence.
            append_evidence(root, _evidence(
                root, worker, reason=reason, result=result, bound=bound,
                observations=observations, action=action,
                rss_limit=rss_limit))
        if decision_event is None:
            persist(action)
        # A failed observation withdraws readiness: a watchdog that just
        # failed closed must not unblock a future admission. A clean refusal
        # of an unsupported lease is the one exception; the observer is still
        # healthy and admission names the mode itself.
        if reason not in READINESS_PRESERVING_REASONS:
            heartbeat.withdraw(root, target=heartbeat.alive_path(root), wall=wall,
                               reason=reason)
        failure.identity_observation = observations.get("bound", {}).get("identity")
        failure.teardown = action.get("teardown")
        failure.evidence = decision_event
        failure.watchdog_result = {
            "schema": SCHEMA, "result": result, "reason": reason,
            "worker": str(worker), "cid": bound.get("cid"),
            "process_group": bound.get("pgid"),
            "action": action["action"], "teardown": action.get("teardown"),
            "evidence": str(evidence_path(root)),
            "enforcement": "userspace_observed", "kernel_enforcement": False}
        raise failure
    # Only a clean observation may advertise readiness. A stale or failed
    # watchdog that observes its own failure must never unblock admission.
    heartbeat.advertise(root, storage_conf=storage_conf, graphroot=graphroot,
                        env=env, wall=wall, namespace_cache=namespace_cache)
    return {"schema": SCHEMA, "result": result, "reason": reason,
            "worker": str(worker), "cid": bound.get("cid"),
            "lease_state": bound["state"], "enforcement": "userspace_observed",
            "kernel_enforcement": False}


def watch(root, worker, **kwargs):
    """Bounded single-lease loop, primarily for deterministic crash replay."""
    nap = kwargs.pop("sleep", None) or time.sleep
    interval = kwargs.pop("interval", DEFAULT_INTERVAL)
    while True:
        check_once(root, worker, **kwargs)
        nap(interval)


def supervise(root, *, storage_conf, graphroot, env=None, stop_path=None,
              ticks=None, sleep=None, interval=DEFAULT_INTERVAL, **kwargs):
    """Permanent service loop: discover and observe every active lease.

    STOP requests a boundary between arms. It never disables monitoring of a
    live arm; when no active lease remains, the watchdog keeps idling and
    advertising readiness so restart churn cannot make readiness stale.
    """
    nap = sleep if sleep is not None else time.sleep
    wall = kwargs.get("wall_clock") or time.time
    count = 0
    workers = []
    namespace_cache = kwargs.pop("namespace_cache", {})
    while ticks is None or count < ticks:
        workers = discover_workers(root)
        failed = False
        for worker in workers:
            try:
                check_once(root, worker, storage_conf=storage_conf,
                           graphroot=graphroot, env=env,
                           namespace_cache=namespace_cache, **kwargs)
            except GuardExceeded:
                failed = True
        if not workers and not failed:
            # Idle watchdogs keep advertising readiness so restart churn
            # cannot make the record stale. An observer that just failed
            # closed never re-advertises until a clean observation does.
            heartbeat.advertise(root, storage_conf=storage_conf,
                                graphroot=graphroot, env=env, wall=wall,
                                namespace_cache=namespace_cache)
        count += 1
        # Boundary requested: no new admissions should happen, but the service
        # stays alive to preserve readiness and observe any unexpected lease.
        if stop_path and Path(stop_path).exists() and not discover_workers(root):
            workers = []
        nap(interval)
    boundary = bool(stop_path and Path(stop_path).exists()
                   and not discover_workers(root))
    return {"result": "boundary" if boundary else "observing",
            "ticks": count, "workers": workers}


# Re-exported so admission and the CLI use one availability contract.
ping = heartbeat.ping
read_alive = heartbeat.read_alive
alive_path = heartbeat.alive_path
