"""Independently check full 50-minute MiCall process and output evidence."""
from pathlib import Path
import math

from benchmarks.container_completion import verified_internal_seconds
from benchmarks.expanded.real_resume import digest

LIMIT_SECONDS = 3000


def authenticate(arm, image, artifacts):
    if (not isinstance(arm, dict) or arm.get("image_id") != image
            or arm.get("exit_code") != 0
            or arm.get("timing_origin") != "micall_in_container_monotonic_v1"):
        raise ValueError("invalid extended MiCall image/exit/timing origin")
    seconds = arm.get("seconds")
    wall = arm.get("container_wall_seconds")
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or type(wall) not in (int, float) or not math.isfinite(wall)
            or not 0 < seconds <= LIMIT_SECONDS
            or not 0 < wall <= LIMIT_SECONDS):
        raise ValueError("extended MiCall timer violates 3000-second budget")
    folder = Path(arm.get("artifact_dir", "")).resolve()
    if not folder.is_relative_to(Path(artifacts).resolve()) or not folder.is_dir():
        raise ValueError("extended MiCall artifacts outside retry directory")
    outputs = arm.get("metrics", {}).get("outputs", {})
    if not isinstance(outputs, dict) or len(outputs) < 10:
        raise ValueError("missing extended MiCall output inventory")
    for filename, proof in outputs.items():
        if (not isinstance(filename, str) or "/" in filename
                or filename.startswith(".") or not isinstance(proof, dict)):
            raise ValueError("malformed extended MiCall output inventory")
        found = next((p for p in (folder / filename, folder / "scratch" / filename)
                      if p.is_file()), None)
        if proof.get("exists") is True:
            if found is None or digest(found) != proof.get("sha256"):
                raise ValueError("extended MiCall output hash mismatch")
        elif proof != {"exists": False} or found is not None:
            raise ValueError("extended MiCall output inventory changed")
    log = folder / "podman.stderr.log"
    with log.open("rb") as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 4096))
        if b"micall.process_run(): Done." not in stream.read():
            raise ValueError("missing extended MiCall completion witness")
    measured = verified_internal_seconds(
        folder / "micall_internal_timing.json", wall)
    if abs(measured - seconds) > 1e-9:
        raise ValueError("extended MiCall timer evidence differs")
