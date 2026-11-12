"""Exact benchmark source digests expected inside external MiCall images."""
import hashlib
from pathlib import Path

EXTERNAL = ("haploflow", "megahit", "abyss", "spades", "velvet")


def source_hashes(name):
    if name not in EXTERNAL:
        raise ValueError("not an approved expanded benchmark competitor")
    root = Path(__file__).resolve().parent
    return tuple(hashlib.sha256((root / path).read_bytes()).hexdigest()
                 for path in ("micall_entrypoint.py", "adapters.py"))
