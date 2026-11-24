"""Exclusive, monitored nonqualifying build or pilot runner."""
import fcntl
import hashlib
import json
import os
import subprocess
import time

from assembler_bench.exploratory_space import admit

from fail_closed_guard import binding, identity, lease
from fail_closed_guard import proc as process_snapshot

from .. import job_temp
from .cleanup import clean_stopped_build
from .monitor import GuardExceeded, watch
from .pilot import bind_pilot, stop_pilot
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
        lease.require_clear(root, guard_env)
        admit(reg, base, root, base["image_store"], base["workspace"], reserve_bytes)
        ident = tool + "-" + str(time.time_ns())
        argv, cidfile = bind_pilot(root, mode, argv, ident)
        # Ownership is durably recorded before a process/container exists, so
        # a crash between spawn and teardown still blocks the next admission.
        lease.acquire(root, ident, mode, cidfile=cidfile)
        record = root / ("run-" + ident + ".json")
        log = root / ("run-" + ident + ".log")
        # Podman/import/build temporaries must stay inside the metered project
        # tree; inheriting the host TMPDIR would hide them from the 20 GiB cap.
        # A per-job directory makes teardown provably scoped to this job alone.
        temp = job_temp.job_temp_dir(root, ident)
        temp.mkdir(parents=True, exist_ok=True)
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
            if cidfile is not None:
                cfg["cidfile"] = cidfile
                cfg["env"] = env
            teardown_proof = None
            try:
                result = watch(proc, cfg)
                if isinstance(result, dict):
                    state["guard_result"] = result
                    state["peak_rss"] = result.get("peak_rss")
                    state["bound_cid"] = result.get("cid")
                    teardown_proof = result.get("teardown")
                else:
                    state["peak_rss"] = result
                state["status"] = "finished" if proc.returncode == 0 else "failed"
                # A bound monitor may only report success after it proved
                # teardown of the exact resource it watched.
                if teardown_proof is None and (cidfile is not None or mode == "build"):
                    state["status"] = "failed"
                    state["reason"] = "teardown_unverified"
            except GuardExceeded as exc:
                state["status"], state["reason"] = "killed", str(exc)
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
                    try:
                        state["pilot_cleanup"] = stop_pilot(root, env, cidfile)
                    except (OSError, ValueError, RuntimeError,
                            subprocess.SubprocessError) as exc:
                        state["pilot_cleanup_error"] = str(exc)[:320]
                        if state["status"] == "finished":
                            state["status"] = "failed"
                            state["reason"] = "pilot_cleanup_unverified"
                if mode == "build" and state["status"] != "finished":
                    # External Buildah "Storage" work containers survive
                    # SIGTERM and are invisible to ordinary podman ps/prune.
                    # Cleanup is restricted to this project's exact graphroot
                    # and occurs ONLY after the monitored build group stopped.
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
                    and not state.get("orphan_cleanup_error"))
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
                    cid = state.get("bound_cid")
                    if cid is None and cidfile is not None:
                        try:
                            cid = binding.read_cid(cidfile)
                        except GuardExceeded:
                            cid = None
                    lease.release(root, ident, cid=cid,
                                  proof=(state.get("pilot_cleanup")
                                         or state.get("orphan_cleanup")
                                         or state.get("guard_result")))
                else:
                    state["lease_state"] = "active_unreleased"
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
