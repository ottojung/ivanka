"""Verified opt-in binding for exact-commit fork-built MiCall candidate images."""
import json
import os
from pathlib import Path
import re

from benchmarks.assembler_bench.fork_image_attestation import verify

VARIABLES = (
    "IVANKA_FORK_SOURCE_ATTESTATION",
    "IVANKA_FORK_SOURCE_CHECKOUT",
    "IVANKA_FORK_IMAGE_MAP",
    "IVANKA_FORK_BASE_IMAGE",
)
HEX64 = re.compile(r"^[a-f0-9]{64}$")


def requested(environ=None):
    source = os.environ if environ is None else environ
    present = [key for key in VARIABLES if key in source]
    if present and len(present) != len(VARIABLES):
        raise ValueError("partial fork image attestation environment")
    return bool(present)


def require_fresh_micall_mode(args):
    """Reject cached controls, unilateral runs or unrecorded project subsets."""
    if (args.mode != "both" or not args.parallel_arms
            or not args.all_projects or args.cache_status
            or args.import_iva_from or args.resume_from
            or args.allow_missing_baseline):
        raise ValueError(
            "fork-built comparison requires fresh complete two-arm MiCall "
            "with all projects and no imported/cached controls")


def check(image, competitor=None, environ=None):
    """Refuse altered image IDs, stale signed evidence and changed MiCall code."""
    env = os.environ if environ is None else environ
    if not requested(env):
        raise ValueError("fork mode requires four explicit attestation inputs")
    attested = json.loads(Path(env[VARIABLES[0]]).read_text())
    images = json.loads(Path(env[VARIABLES[2]]).read_text())
    result = verify(images, env[VARIABLES[3]], env[VARIABLES[1]])
    if result != attested:
        raise ValueError("live fork source audit differs from frozen attestation")
    name = competitor or "ivanka"
    expected = images.get(name)
    if (not isinstance(expected, str) or not HEX64.fullmatch(expected)
            or image != expected
            or result.get("images", {}).get(name, {}).get("image_sha256")
            != expected):
        raise ValueError(f"{name}: candidate image differs from verified fork ID")
    return {"tool": name, "image_id": expected,
            "fork_commit": result["source_commit"],
            "fork_url": result["source_url"]}
