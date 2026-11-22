"""Exclusive, monitored nonqualifying build or pilot runner."""
import fcntl
import hashlib
import json
import os
import subprocess
import time

from assembler_bench.exploratory_space import admit

from .monitor import GuardExceeded, watch
from .setup import prepare
from .terminate import group


def operate(registry_path, baseline_path, tool, mode, argv, reserve_bytes):
    root, base, reg, cfg = prepare(registry_path, baseline_path, tool,
                                   mode, argv, reserve_bytes)
    with (root / ".global-worker.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        admit(reg, base, root, base["image_store"], base["workspace"], reserve_bytes)
        ident = tool + "-" + str(time.time_ns())
        record = root / ("run-" + ident + ".json")
        log = root / ("run-" + ident + ".log")
        env = {**os.environ, "CONTAINERS_STORAGE_CONF": str(root / "storage.conf")}
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
