"""Verified opt-in binding for exact-commit fork-built MiCall candidate images."""
import json
import os
from pathlib import Path
import re

from benchmarks.assembler_bench.image_source_attestation import verify

VARIABLES = (
    "IVANKA_FORK_SOURCE_ATTESTATION",
    "IVANKA_FORK_SOURCE_CHECKOUT",
    "IVANKA_FORK_IMAGE_MAP",
    "IVANKA_FORK_BASE_IMAGE",
)
HEX64 = re.compile(r"^[a-f0-9]{64}$")
SHARED_CONTROL_MANIFEST = "IVANKA_FORK_SHARED_IVA_MANIFEST"


def requested(environ=None):
    source = os.environ if environ is None else environ
    present = [key for key in VARIABLES if key in source]
    if present and len(present) != len(VARIABLES):
        raise ValueError("partial fork image attestation environment")
    return bool(present)


def require_fresh_micall_mode(args):
    """Accept only paired fresh arms or proof-gated one-time shared controls."""
    proof=os.environ.get(SHARED_CONTROL_MANIFEST)
    shared=False
    if proof:
        path=Path(proof).resolve(strict=True)
        stamp=json.loads(path.read_text())
        cache=os.environ.get("IVANKA_IVA_BASELINE_CACHE")
        if (path.name!="shared-iva-controls.json"
                or stamp.get("schema")!="ivanka.expanded.single-iva-controls.v1"
                or stamp.get("control_image_id")!=os.environ.get("IVANKA_IVA_IMAGE")
                or not cache or Path(cache).resolve()!=path.parent/"iva-baselines"
                or not stamp.get("samples")):
            raise ValueError("unverified shared IVA control manifest")
        shared=(args.mode=="ivanka" and not args.parallel_arms)
    paired=(args.mode=="both" and args.parallel_arms and not proof)
    if (not (shared or paired) or not args.all_projects
            or args.cache_status or args.import_iva_from or args.resume_from
            or args.allow_missing_baseline):
        raise ValueError(
            "fork-built comparison requires fresh complete two-arm MiCall "
            "or one-time source-authenticated IVA controls with all projects")


def check(image, competitor=None, environ=None):
    """Refuse altered image IDs, stale signed evidence and changed MiCall code."""
    env = os.environ if environ is None else environ
    if not requested(env):
        raise ValueError("fork mode requires four explicit attestation inputs")
    attested = json.loads(Path(env[VARIABLES[0]]).read_text())
    images = json.loads(Path(env[VARIABLES[2]]).read_text())
    result = verify(images, env[VARIABLES[0]],
                    env[VARIABLES[1]], env[VARIABLES[3]])
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
            "fork_commit": result["images"][name]["source_commit"],
            "fork_url": result["images"][name]["source_url"]}
