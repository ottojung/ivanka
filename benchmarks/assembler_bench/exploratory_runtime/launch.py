"""Exclusive, monitored nonqualifying build or pilot runner."""
import fcntl
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from assembler_bench.exploratory_space import admit_reserve

from fail_closed_guard import heartbeat, identity, lease, teardown, watchdog_contract
from fail_closed_guard import proc as process_snapshot
from fail_closed_guard.errors import GuardExceeded

from .. import job_temp
from .cleanup import clean_stopped_build
from .monitor import attest, watch
from .pilot import bind_pilot, prove_pilot_absent, stop_pilot
from .setup import prepare
from .terminate import group


def operate(registry_path, baseline_path, tool, mode, argv, reserve_bytes):
    root, base, reg, cfg = prepare(registry_path, baseline_path, tool,
                                   mode, argv, reserve_bytes)
    with (root / ".global-worker.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # The advisory lock dies with a crashed launcher; the durable lease
        # journal does not. Never admit a new job while a prior owned resource
        # is alive or its liveness cannot be proven.
        guard_env = {**os.environ,
                     "CONTAINERS_STORAGE_CONF": str(root / "storage.conf")}
        # The strict watchdog contract applies once the independent observer
        # is armed. The launcher cannot rely on inheriting the s6 environment,
        # so the durable ALIVE record naming this exact store is authoritative
        # (WATCHDOG_ARMED remains an explicit operator override). Under that
        # contract readiness is namespace/PID bound and modes the watchdog
        # cannot supervise (builds) are refused before any process spawns.
        graphroot = str(Path(base["image_store"]).resolve() / "store")
        alive = heartbeat.alive_path(root)
        armed = (os.environ.get("WATCHDOG_ARMED") == "1"
                 or watchdog_contract.is_bound(alive, graphroot))
        if armed:
            lease.require_clear(root, guard_env,
                                watchdog_path=alive, graphroot=graphroot,
                                snapshot=process_snapshot.snapshot,
                                wall=time.time)
            watchdog_contract.require_supported_mode(mode)
        else:
            lease.require_clear(root, guard_env,
                                watchdog_path=heartbeat.alive_path(root))
        admit_reserve(reg, base, root, base["image_store"], base["workspace"], reserve_bytes)
        ident = tool + "-" + str(time.time_ns())
        argv, cidfile = bind_pilot(root, mode, argv, ident)
        # Ownership is durably recorded before a process/container exists, so
        # a crash between spawn and teardown still blocks the next admission.
        lease.acquire(root, ident, mode, cidfile=cidfile)
        record = root / ("run-" + ident + ".json")
        log = root / ("run-" + ident + ".log")
        # Podman/import/build temporaries must stay inside the metered project
        # tree; inheriting the host TMPDIR would hide them from real disk accounting.
        # A per-job directory makes teardown provably scoped to this job alone.
        temp = job_temp.job_temp_dir(root, ident)
        temp.mkdir(parents=True, exist_ok=True)
        # The controller proves its own kernel identity before a container can
        # exist and refreshes it throughout the bounded watch below.
        emitter = heartbeat.Emitter(root, ident)
        emitter.before_spawn()
        env = {**os.environ, "CONTAINERS_STORAGE_CONF": str(root / "storage.conf"),
               "TMPDIR": str(temp), "TMP": str(temp), "TEMP": str(temp)}
        with log.open("xb") as output:
            proc = subprocess.Popen(argv, cwd=root, env=env,
                                    stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            state = {"tool": tool, "mode": mode, "status": "unknown",
                     "peak_rss": None, "argv_sha256":
                     hashlib.sha256(repr(argv).encode()).hexdigest()}
            if mode == "build":
                # Bind the launcher after spawn; a very short build may exit
                # before its snapshot is readable, in which case bare-PID
                # liveness is recorded and still fails closed on ambiguity.
                try:
                    observed = process_snapshot.snapshot().get(proc.pid)
                    fingerprint = None
                    if observed is not None:
                        try:
                            fingerprint = identity.bind(observed)
                        except GuardExceeded:
                            pass
                    lease.bind(root, ident, proc.pid, fingerprint)
                except Exception:
                    group(proc)
                    raise
            # Identity-bound guard path: pilots bind the exact issued CID and
            # stop by CID only; builds bind the launcher tree and stop by its
            # exact process group. Legacy positional watch() call preserved.
            cfg["guard_mode"] = mode
            cfg["heartbeat"] = emitter.refresh
            if cidfile is not None:
                cfg["cidfile"] = cidfile
                cfg["env"] = env
            teardown_proof = None

            def on_bind(bound):
                # Keep the exact CID in both the receipt and the durable lease
                # before the monitor can be killed. Cleanup never reads the
                # transient cidfile again once this binding exists.
                state["bound_cid"] = bound["cid"]
                emitter.bound(bound["cid"])
                try:
                    lease.bind_cid(root, ident, bound["cid"], cidfile=cidfile,
                                   pid=bound.get("pid"),
                                   fingerprint=bound.get("fingerprint"))
                except Exception as exc:
                    # An unowned container must not outlive a failed journal
                    # append; remove it by the exact CID just bound.
                    try:
                        teardown.stop_cid(env, bound["cid"])
                    except Exception:
                        pass
                    raise GuardExceeded("lease_unavailable") from exc

            try:
                observation = watch(
                    proc, cfg, on_bind=on_bind if cidfile is not None else None)
                # Publisher RAM scope stays authoritative in PR475/476: attest
                # the observed sampler without changing its public semantics.
                state.update(attest(observation))
                if isinstance(observation, dict):
                    state["guard_result"] = observation
                    state["bound_cid"] = (observation.get("cid")
                                          or state.get("bound_cid"))
                    teardown_proof = observation.get("teardown")
                    state["peak_rss"] = observation.get("peak_rss")
                else:
                    state["peak_rss"] = observation
                state["peak_rss"] = state["peak_rss_bytes"]
                state["status"] = "finished" if proc.returncode == 0 else "failed"
                # A bound monitor may only report success after it proved
                # teardown of the exact resource it watched.
                if teardown_proof is None and (cidfile is not None or mode == "build"):
                    state["status"] = "failed"
                    state["reason"] = "teardown_unverified"
            except GuardExceeded as exc:
                state["status"], state["reason"] = "killed", str(exc)
                # A killed arm keeps its genuine peak and teardown record;
                # failure reason and observed attestation are never replaced
                # by a generic upward error.
                guard_result = getattr(exc, "guard_result", None)
                if guard_result is not None:
                    state["guard_result"] = guard_result
                    # A failed arm attests the same real sampler as a finished
                    # one; carry method/version/scope out of the error path.
                    state.update(attest(guard_result))
                    state["peak_rss"] = state["peak_rss_bytes"]
                elif getattr(exc, "peak_rss", None) is not None:
                    state["peak_rss"] = exc.peak_rss
                if getattr(exc, "teardown", None) is not None:
                    state["bound_cid"] = state.get("bound_cid") or exc.teardown.get("cid")
                if getattr(exc, "teardown_error", None):
                    state["teardown_error"] = exc.teardown_error
                cause = exc.__cause__
                if cause is not None:
                    # Preserve actual measurement failure; never invent an
                    # allocated-byte or RSS reading. Cap forensic details.
                    state["measurement_error_type"] = type(cause).__name__
                    state["measurement_error"] = str(cause)[:320]
                    if isinstance(cause, subprocess.CalledProcessError) and cause.stderr:
                        state["measurement_stderr_tail"] = str(cause.stderr)[-320:]
            finally:
                state["exit_code"] = group(proc)
                if cidfile is not None:
                    cid = state.get("bound_cid")
                    if cid is not None:
                        # The guard proved teardown of this exact CID. Reuse
                        # that proof with a fresh scoped absence check instead
                        # of re-reading a cidfile --rm may already have deleted.
                        try:
                            state["pilot_cleanup"] = prove_pilot_absent(
                                root, env, cid, teardown_proof)
                        except (OSError, ValueError, RuntimeError,
                                subprocess.SubprocessError) as exc:
                            state["pilot_cleanup_error"] = str(exc)[:320]
                    else:
                        # No binding ever happened: the only available exact
                        # identity is still the issued cidfile.
                        try:
                            state["pilot_cleanup"] = stop_pilot(root, env, cidfile)
                        except (OSError, ValueError, RuntimeError,
                                subprocess.SubprocessError) as exc:
                            state["pilot_cleanup_error"] = str(exc)[:320]
                    if "pilot_cleanup_error" in state and state["status"] == "finished":
                        state["status"] = "failed"
                        state["reason"] = "pilot_cleanup_unverified"
                if mode == "build":
                    # External Buildah "Storage" work containers survive a
                    # build and are invisible to ordinary podman ps/prune.
                    # They leak on SUCCESS as well as on failure, so every
                    # stopped build must reclaim them before its lease closes;
                    # otherwise the next image build is blocked by orphans the
                    # launcher itself left behind. Cleanup stays restricted to
                    # this project's exact graphroot and runs ONLY after the
                    # monitored process group has been reaped above.
                    try:
                        state["orphan_cleanup"] = clean_stopped_build(root, env)
                    except (OSError, ValueError, RuntimeError,
                            subprocess.SubprocessError) as exc:
                        state["orphan_cleanup_error"] = str(exc)[:320]
                # Reclaim ONLY this job's temp directory after the monitored
                # group is reaped and every pilot/build teardown check passed.
                # A stopped infrastructure attempt is safe once its container
                # is reaped; an unverified teardown keeps its temp for diagnosis.
                teardown_ok = (
                    state.get("exit_code") is not None
                    and "pilot_cleanup_error" not in state
                    and not state.get("orphan_cleanup_error")
                    # A build must carry a real cleanup proof, not merely the
                    # absence of an error, before its lease may be released.
                    and (mode != "build" or bool(state.get("orphan_cleanup"))))
                if teardown_ok:
                    try:
                        state["job_temp_cleanup"] = job_temp.clean_job_temp(
                            root, ident, env=env, lock_held_by_caller=True)
                    except (OSError, ValueError, RuntimeError) as exc:
                        state["job_temp_cleanup_error"] = str(exc)[:320]
                else:
                    state["job_temp_cleanup"] = {
                        "removed": False, "reason": "teardown_unverified"}
                # Close the durable lease only after teardown is proven. An
                # unverified teardown leaves it active so startup reconciliation
                # refuses the next admission until an owner reconciles it.
                if teardown_ok:
                    cid = (state.get("bound_cid")
                           or (state.get("pilot_cleanup") or {}).get("pilot_container_id"))
                    lease.release(root, ident, cid=cid,
                                  proof=(state.get("pilot_cleanup")
                                         or state.get("orphan_cleanup")
                                         or state.get("guard_result")))
                else:
                    state["lease_state"] = "active_unreleased"
                # A watchdog that fail-closed and tore down this arm must never
                # leave a "finished" receipt, even if the launcher itself
                # exited cleanly before the observer acted.
                try:
                    state = watchdog_contract.downgrade_on_watchdog_teardown(
                        root, ident, state)
                except GuardExceeded as exc:
                    state["status"] = "failed"
                    state["reason"] = "watchdog_evidence_unreadable"
                    state["watchdog_error"] = exc.reason
                state["recorded_utc"] = time.time()
                output.flush()
                os.fsync(output.fileno())
                with log.open("rb") as log_stream:
                    state["log_sha256"] = hashlib.file_digest(log_stream, "sha256").hexdigest()
                with record.open("x") as out:
                    json.dump(state, out, sort_keys=True)
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
        return state
