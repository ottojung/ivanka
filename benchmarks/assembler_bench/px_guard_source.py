"""Pinned source identity of the deployed PX constant-time reserve guard.

A retry authorization must bind to the guard source that is actually present,
not to a self-declared commit string. The digest below is recomputed from the
deployed tree on every authorization and verification; any change to the guard
that separates the constant-time reserve from the recursive usage audit fails
closed until the pin is deliberately updated with a reviewed commit.
"""
import hashlib
from pathlib import Path

# The reviewed commit that introduced the deployed constant-time reserve.
GUARD_COMMIT = "af1f10d19143fa7a00134a01b56a858ef8a09647"
RESERVE_SOURCE = "benchmarks/assembler_bench/exploratory_space.py"
# Verified against the deployed source bytes; never trust a caller-supplied pin.
EXPECTED = {
    RESERVE_SOURCE:
        "bffdc90b703475aeb68f31c2df4334cb36a8912ebaba806cd7baee4d2bc18943",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root():
    return Path(__file__).resolve().parents[2]


def verify():
    """Return the deployed guard digests only when every pinned source matches."""
    found = {name: digest(root() / name) for name in EXPECTED}
    if found != EXPECTED:
        raise ValueError("deployed PX guard source drift")
    return found
