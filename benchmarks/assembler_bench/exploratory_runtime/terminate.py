"""Stop the exact new process group; never touch shared benchmark workers."""
import os
import signal
import subprocess


def group(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=3)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return proc.wait(timeout=5)
