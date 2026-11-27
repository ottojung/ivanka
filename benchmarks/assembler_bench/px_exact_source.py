"""Load only the exact pinned MiCall source bytes for opt-in PX diagnostics."""
import hashlib
import os
from pathlib import Path
from types import ModuleType

from .exact_cache import SOURCE_SHA256


def calculator():
    path = os.environ.get("PX_EXACT_COVERAGE_MODULE")
    if not path:
        raise ImportError("PX exact-coverage source is not configured")
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ImportError("PX exact-coverage source is unavailable")
    try:
        blob = source.read_bytes()
    except OSError as exc:
        raise ImportError("PX exact-coverage source is unreadable") from exc
    if hashlib.sha256(blob).hexdigest() != SOURCE_SHA256:
        raise ImportError("PX exact-coverage source hash disagrees with frozen pin")
    # Execute the checked bytes, not a second path read or cached .pyc.
    module = ModuleType("px_pinned_micall_exact_coverage")
    exec(compile(blob, str(source), "exec"), module.__dict__)
    return module.calculate_exact_coverage
