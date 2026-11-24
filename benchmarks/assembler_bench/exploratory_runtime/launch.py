"""Exclusive, monitored nonqualifying build or pilot runner."""
import fcntl
import hashlib
import json
import os
import subprocess
import time

from assembler_bench.exploratory_space import admit

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
        admit(reg, base, root, base["image_store"], base["workspace"], reserve_bytes)
        ident = tool + "-" + str(time.time_ns())
        argv, cidfile = bind_pilot(root, mode, argv, ident)
        record = root / ("run-" + ident + ".json")
        log = root / ("run-" + ident + ".log")
        # Podman/import/build temporaries must stay inside the metered project
        # tree; inheriting the host TMPDIR would hide them from the cap. A
        # per-job directory makes teardown provably scoped to this job alone.
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
            try:
                state["peak_rss"] = watch(proc, cfg)
                state["status"] = "finished" if proc.returncode == 0 else "failed"
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
