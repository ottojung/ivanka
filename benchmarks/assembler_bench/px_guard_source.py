"""Pinned source identity of the deployed PX guard stack.

A retry authorization must bind to the guard source that is actually present,
not to a self-declared commit string. The digests below are recomputed from the
deployed tree on every authorization and verification; any drift in the reserve
source, the host 4-GB fail-safe, the independent fail-closed watchdog, or the
PR530 natural-exit monitor path fails closed until the pin is deliberately
updated with a reviewed commit.

Evidence: the running watchdog (`ivanka-watchdog`, PID 1882043 at review time)
executes PYTHONPATH=/workspace/ivanka-guard-pr530-staged-20261126, a clean
checkout of f861f25b6e62e1266a498340e7d3cf9a09a9087f (merge of PR #530,
"Attest pilot natural exit by exact CID, not a lagging poll", deployed after the
earlier 3fb720c7 staging). Every digest below was recomputed in that deployed
tree and in the review checkout and matched byte-for-byte. RESERVE_COMMIT is
retained as the origin of the constant-time reserve so older evidence is never
weakened or rewritten.
"""
import hashlib
from pathlib import Path

# Origin of the constant-time shared disk reserve (PR #510). Retained evidence.
RESERVE_COMMIT = "af1f10d19143fa7a00134a01b56a858ef8a09647"
# Current deployed reviewed guard semantics: PR #526 retirement, PR #527
# independent watchdog and PR #530 exact-CID natural-exit monitor, merged at
# f861f25b6e62e1266a498340e7d3cf9a09a9087f.
GUARD_COMMIT = "f861f25b6e62e1266a498340e7d3cf9a09a9087f"

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
    "benchmarks/fail_closed_guard/watchdog_cli.py",
)
# PR #530 critical monitor path: natural exit attested by exact CID, not a
# lagging poll. Changes to any of these invalidate an authorization.
NATURAL_EXIT = (
    "benchmarks/fail_closed_guard/natural_exit.py",
    "benchmarks/fail_closed_guard/watch.py",
    "benchmarks/assembler_bench/exploratory_runtime/monitor.py",
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
    "benchmarks/fail_closed_guard/watchdog_cli.py":
        "e00b83adfbf8356f2f92ce92ecd2226854a182d21a21e24ca87d35ed205b5369",
    "benchmarks/fail_closed_guard/natural_exit.py":
        "0d655667d8ad34f1842ea3d368603398f3d72641c953a37704d54fc525481048",
    "benchmarks/fail_closed_guard/watch.py":
        "a13839f3264770a48bc20e6b52f09d9f1dbea4cb8d0abc1a89dfdf99f44f76b2",
    "benchmarks/assembler_bench/exploratory_runtime/monitor.py":
        "bd88eb3d95c8b7296f49edc3d668589f1c58f7edac70dec1ba4f3f84c9fec4f1",
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
