"""Pinned source identity of the deployed PX guard stack.

A retry authorization must bind to the guard bytes that the live services
actually execute, never to a self-declared commit string. Two distinct,
reviewed checkouts are bound explicitly:

* the immutable guard deployment checkout (``DEPLOYED_ROOT``) runs the
  independent fail-closed watchdog. It may be a COPY build with no ``.git``;
  its identity is then proven by ``IDENTITY_NAME``, a reviewed manifest whose
  bytes are pinned here and whose digest chain covers every runtime module.
* the operator/retry/supervisor control checkout (``CONTROL_ROOT``) runs the
  PX supervisor and the retry authorization. It is a git checkout whose retry
  implementation is pinned by ``CONTROL_RETRY_SHA256`` and carries
  byte-identical copies of the same modules.

The deployment checkout is pinned to the reviewed PR535 merge, a commit that
does not contain this verifier. The control checkout is pinned by reviewed
source bytes instead of a commit hash, so the verifier never has to name its
own future commit. Neither identity is self-referential. Production
verification checks BOTH service identities and every byte. A missing
``.git`` directory is never treated as "nothing to check": without a real
checkout or the reviewed manifest, verification fails closed.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

COMMIT = re.compile(r"^[a-f0-9]{40}$")

# Operator/retry/supervisor control checkout (created from reviewed main after
# PR550 plus this PR). Its identity is pinned by reviewed source bytes, never
# by a commit hash that would point back at this verifier.
CONTROL_ROOT = Path("/workspace/ivanka-px-control-cutover")
CONTROL_RETRY_SOURCE = "benchmarks/assembler_bench/px_retry_authorization.py"
CONTROL_RETRY_SHA256 = "0ba6009b3bb63411e92b159d54e7cb7e62bef9fb7d0cc31113b5320792acb3e6"

# Immutable guard deployment checkout (reviewed PR535 merge). A COPY build has
# no .git, so the reviewed manifest below is the authority for its identity.
DEPLOYED_ROOT = Path("/workspace/ivanka-guard-pr535-staged-20261127")
DEPLOYED_HEAD = "165a86b38c0bc29b4f8e0281a39ca59b909a6563"
IDENTITY_NAME = "px_guard_identity.json"
IDENTITY_SCHEMA = "ivanka.px.guard-source-identity.v1"
IDENTITY_SHA256 = "7675143e1c2892383b59b2ca17f5fd7845c14945aacf1e175365862d0c6a04d9"

# Origin of the constant-time shared disk reserve (PR #510). Retained evidence;
# the reviewed deployment head below supersedes it for current guard semantics.
RESERVE_COMMIT = "af1f10d19143fa7a00134a01b56a858ef8a09647"
GUARD_COMMIT = DEPLOYED_HEAD

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
    "benchmarks/fail_closed_guard/build.py",
    "benchmarks/fail_closed_guard/copy_overlay.py",
    "benchmarks/fail_closed_guard/copy_overlay_helper.py",
    "benchmarks/fail_closed_guard/lease.py",
    "benchmarks/fail_closed_guard/orphans.py",
)
# Critical natural-exit/monitor path: natural exit attested by exact CID, not a
# lagging poll. Changes to any of these invalidate an authorization.
NATURAL_EXIT = (
    "benchmarks/fail_closed_guard/natural_exit.py",
    "benchmarks/fail_closed_guard/watch.py",
    "benchmarks/assembler_bench/exploratory_runtime/monitor.py",
)

# Reviewed bytes of every runtime guard module in the deployment checkout.
# The three modules changed by PR535 and the five it adds are rebound here;
# the unchanged modules keep their original digests. This map is identical to
# the ``sources`` chain in the reviewed identity manifest.
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
        "2a3c1756af427bdd5945b66245a0e6d31b2f37d2cb3e287341833d016c322cae",
    "benchmarks/fail_closed_guard/watchdog.py":
        "d434154db326f120d9a441ba6cf9f4df85eb34d28f80bb578cc50f923bfdbe10",
    "benchmarks/fail_closed_guard/watchdog_contract.py":
        "70f79793c90269b011c70d598a141606279a07768cbd2eb8e5fa522d9a22b4ea",
    "benchmarks/fail_closed_guard/binding.py":
        "1e764c6a358ddc3b58fe09aa0948d6309b00942936ac525d93ef17d19516e945",
    "benchmarks/fail_closed_guard/identity.py":
        "1feecc9e75e71c4bf54b2dbd960cc92886fa00cd9a564c7d220e90f4163aa973",
    "benchmarks/fail_closed_guard/startup.py":
        "80b07ce334fa99691ed0a89baf9aa803d4e67631be72c022188963f094ae7b6d",
    "benchmarks/fail_closed_guard/watchdog_cli.py":
        "e00b83adfbf8356f2f92ce92ecd2226854a182d21a21e24ca87d35ed205b5369",
    "benchmarks/fail_closed_guard/natural_exit.py":
        "f7f6028273a5d7775b8d4ca6139e9659ca475a0aa36a3d12b1a736e429202cd6",
    "benchmarks/fail_closed_guard/watch.py":
        "07356fc4b29e1e6bc5b11659048bc5437a70037a29dde197dd795540fd66da96",
    "benchmarks/assembler_bench/exploratory_runtime/monitor.py":
        "b0bbefa221ff092acf33021b0203f2b07a912c250fc0893e8fdd59dad642293c",
    "benchmarks/fail_closed_guard/build.py":
        "edf6585f84f919db6d677e34a4597dc57e9dcc6d2d77ab06e81ee6c33c9c80dd",
    "benchmarks/fail_closed_guard/copy_overlay.py":
        "f59049e5c0a8dd3e042bd723ffbeb3caaba2af386b7158016bf160824300da31",
    "benchmarks/fail_closed_guard/copy_overlay_helper.py":
        "8242d81c9c6b169dfbfac1b837ae9c23e1e3f1259190438871dee89dccdf0bc5",
    "benchmarks/fail_closed_guard/lease.py":
        "02f9e4932ce01697a6baa6b3200673cf3df0d52f7be7292d657991a10184ac03",
    "benchmarks/fail_closed_guard/orphans.py":
        "6d5e7d3c62a2bdba7a15af2ea69b99b8c6674cab72996e660d39a148587e41b2",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root():
    """Source checkout root (the canonical manifest lives under it)."""
    return Path(__file__).resolve().parents[2]


def identity_path(base=None):
    return (Path(base) if base is not None else DEPLOYED_ROOT) / IDENTITY_NAME


def _git_head(base):
    result = subprocess.run(["git", "-C", str(base), "rev-parse", "HEAD"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError("checkout HEAD unavailable")
    head = result.stdout.strip()
    if not COMMIT.fullmatch(head):
        raise ValueError("checkout HEAD malformed")
    return head


def _read_identity(base):
    """Verify the reviewed manifest bytes and their exact digest chain."""
    path = identity_path(base)
    if path.is_symlink() or not path.is_file():
        raise ValueError("deployed PX guard identity manifest missing")
    if digest(path) != IDENTITY_SHA256:
        raise ValueError("deployed PX guard identity manifest drift")
    try:
        identity = json.loads(path.read_bytes())
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("deployed PX guard identity manifest unreadable") from exc
    if (not isinstance(identity, dict)
            or identity.get("schema") != IDENTITY_SCHEMA
            or identity.get("source_commit") != DEPLOYED_HEAD
            or identity.get("sources") != EXPECTED):
        raise ValueError("deployed PX guard identity manifest drift")
    return identity


def _verify_control(base):
    """Prove the operator/retry/supervisor service identity and byte parity."""
    if not (base / ".git").exists():
        raise ValueError("control checkout git identity missing")
    # A real checkout is required; the reviewed retry bytes, not its mutable
    # commit hash, are the authority for the control service identity.
    _git_head(base)
    retry = base / CONTROL_RETRY_SOURCE
    if (retry.is_symlink() or not retry.is_file()
            or digest(retry) != CONTROL_RETRY_SHA256):
        raise ValueError("control PX retry source drift")
    for name, expected in EXPECTED.items():
        path = base / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError("control PX guard source drift")


def verify(root=None, *, control_root=None):
    """Return deployed guard digests only for both reviewed service identities.

    With no arguments this is production verification: the control checkout is
    proven by git HEAD and byte digests, and the deployment checkout is proven
    by its reviewed manifest and byte digests. An explicit ``root`` is used
    only by the isolated test fixture; it still requires the reviewed manifest,
    so removing git can never silently skip identity verification.
    """
    production = root is None
    base = Path(root) if root is not None else DEPLOYED_ROOT
    control = Path(control_root) if control_root is not None else CONTROL_ROOT
    if production or control_root is not None:
        _verify_control(control)
    _read_identity(base)
    found = {}
    for name, expected in EXPECTED.items():
        path = base / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError("deployed PX guard source drift")
        found[name] = expected
    return found
