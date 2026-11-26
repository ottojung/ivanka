"""Pinned source identity of the deployed PX guard stack.

A retry authorization must bind to the guard source that is actually present,
not to a self-declared commit string. The digests below are recomputed from the
deployed tree on every authorization and verification; any drift in the reserve
source, the host 4-GB fail-safe or the independent fail-closed watchdog fails
closed until the pin is deliberately updated with a reviewed commit.

Evidence: the running watchdog (s6 `ivanka-watchdog`, PID 1503395 at review time)
executes PYTHONPATH=/workspace/ivanka-oci-transfer-20261126, a clean checkout of
main 3fb720c7fd74e08b77d453441c10fdfed3eb305f (PR #527 merge, deployed 18:18Z).
Every digest below was recomputed there and in the review checkout and matched
byte-for-byte. RESERVE_COMMIT is retained as the origin of the constant-time
reserve so the older evidence is never weakened or rewritten.
"""
import hashlib
from pathlib import Path

# Origin of the constant-time shared disk reserve (PR #510). Retained evidence.
RESERVE_COMMIT = "af1f10d19143fa7a00134a01b56a858ef8a09647"
# Current deployed reviewed guard semantics: PR #526 retirement + PR #527
# independent fail-closed watchdog, merged at 3fb720c7 and deployed 18:18Z.
GUARD_COMMIT = "3fb720c7fd74e08b77d453441c10fdfed3eb305f"

RESERVE_SOURCE = "benchmarks/assembler_bench/exploratory_space.py"
MEMORY_GUARD = (
    "benchmarks/memory_guard/proc.py",
    "benchmarks/memory_guard/guard.py",
    "benchmarks/memory_guard/signals.py",
)
WATCHDOG = (
    "benchmarks/fail_closed_guard/proc.py",
    "benchmarks/fail_closed_guard/watchdog.py",
    "benchmarks/fail_closed_guard/watchdog_contract.py",
    "benchmarks/fail_closed_guard/binding.py",
    "benchmarks/fail_closed_guard/identity.py",
    "benchmarks/fail_closed_guard/startup.py",
)
# Verified against the deployed source bytes; never trust a caller-supplied pin.
EXPECTED = {
    RESERVE_SOURCE:
        "bffdc90b703475aeb68f31c2df4334cb36a8912ebaba806cd7baee4d2bc18943",
    "benchmarks/memory_guard/proc.py":
        "086ce9aca6d73703216e841d8e9b580cab6678e743f868d6e133a50ba0d69e72",
    "benchmarks/memory_guard/guard.py":
        "6e096ffb7cae5014595a6aaa889beb2ed7d05172588556adb6a82ffa23e32dbe",
    "benchmarks/memory_guard/signals.py":
        "b5a4dc351da3fc9144bcfad7a26059a849e9c5a58980c26e3c004ad817d88c53",
    "benchmarks/fail_closed_guard/proc.py":
        "e8b4c9ebe1a8a3a509466cf824873820df962577352457c879090fd795030b31",
    "benchmarks/fail_closed_guard/watchdog.py":
        "a67bac2672efb961408f2401163b49e12e01c07c6300ffb200519c1cc07a6d5e",
    "benchmarks/fail_closed_guard/watchdog_contract.py":
        "a2d198b35f0c756cce68f094bebdf79068ad1a585f1f5f061e4e9c2c74906365",
    "benchmarks/fail_closed_guard/binding.py":
        "1e764c6a358ddc3b58fe09aa0948d6309b00942936ac525d93ef17d19516e945",
    "benchmarks/fail_closed_guard/identity.py":
        "1feecc9e75e71c4bf54b2dbd960cc92886fa00cd9a564c7d220e90f4163aa973",
    "benchmarks/fail_closed_guard/startup.py":
        "80b07ce334fa99691ed0a89baf9aa803d4e67631be72c022188963f094ae7b6d",
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
