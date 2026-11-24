"""Source-pinned digests for posthoc scoring and exact-coverage helpers.

A scorer identity is only trustworthy when the canonical source it actually
executes is bound to a digest recorded here. Recompute from the rebased tree
before pinning; a mismatch fails closed in the scorer constructor.
"""
import hashlib
from pathlib import Path

# Relative to the repository root; verified at construction time.
SCORER_SOURCES = (
    "benchmarks/expanded/score.py",
    "benchmarks/expanded/micall_dominant.py",
    "benchmarks/reference_panel.py",
    "benchmarks/project_references.py",
)
EXACT_SOURCE = "benchmarks/assembler_bench/exact_cache.py"
EXPECTED = {
    "benchmarks/expanded/score.py":
        "95aad29cfaffc48eddd88fb5796c9ecbc9b3b0f6fe4fe80a38b151be07070b15",
    "benchmarks/expanded/micall_dominant.py":
        "3bac60fdc2c1849c9a63520ec925a944695a4c472046d2bc7a60b1eb2f68c3ac",
    "benchmarks/reference_panel.py":
        "b8307caf141eb92eabcee92da22bac994904a8220194a91839387a555aef5c5e",
    "benchmarks/project_references.py":
        "1b01adada226de1ed7b506094625535fa9c775688922cef3aa68fb8b89fec7a2",
    "benchmarks/assembler_bench/exact_cache.py":
        "c5142261b9bafc1393cd754c5f62154143da8b57114eb6ead77dacc49ac0a7f1",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root():
    return Path(__file__).resolve().parents[2]


def verify():
    """Return the digest map only when every canonical source is unchanged."""
    found = {name: digest(root() / name) for name in SCORER_SOURCES + (EXACT_SOURCE,)}
    if found != EXPECTED:
        raise ValueError("canonical scorer or exact-coverage source drift")
    return found
