"""Reviewed source-byte identity for the deployed PX guard stack.

This module verifies checked-out source bytes and reviewed manifests. It does
NOT prove which code a live watchdog/supervisor process is executing; live
service attestation is a separate read-only step that must bind s6/runtime
pins, /proc identity and active-lease boundaries before any cutover or
authorization.

Two explicit, non-self-referential identities are bound by reviewed source
hashes and operator-attested manifests:

* the immutable guard deployment checkout (``DEPLOYED_ROOT``) is the reviewed,
  reviewed PR597 source ``b777f349``. It may be staged as a git checkout or a COPY
  image. If ``.git`` exists, HEAD is checked against ``DEPLOYED_HEAD``. In all
  cases the reviewed manifest and exact module-byte chain are required.
  ``DEPLOYED_EXPECTED`` binds those new bytes; ``EXPECTED`` remains the
  unchanged control-checkout module map so ``verify_control()`` stays valid
  against the live ``b8720600`` control root without a control redeploy.
* the operator/retry/supervisor control checkout (``CONTROL_ROOT``) is created
  from reviewed main ``07231fa1`` plus this PR. Its identity is pinned by
  reviewed source hashes (not by an arbitrary/self-referential git hash).

A missing ``.git`` directory never silently skips identity verification. A
checked-out byte match never implies live process attestation.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

COMMIT = re.compile(r"^[a-f0-9]{40}$")

# Operator/retry/supervisor control checkout. Pinned by reviewed source bytes
# in a separate manifest (not a self-referential git hash).
CONTROL_ROOT = Path("/workspace/ivanka-px-control-cutover")
CONTROL_IDENTITY_NAME = "px_control_identity.json"
CONTROL_IDENTITY_SCHEMA = "ivanka.px.control-source-identity.v1"
CONTROL_IDENTITY_SHA256 = "43f712fb5c48ab9c291a6e822fcbe552b21ea9b4dbd3552b1b753b0e23a80af2"
CONTROL_RETRY_SOURCE = "benchmarks/assembler_bench/px_retry_authorization.py"
CONTROL_RETRY_SHA256 = "0ba6009b3bb63411e92b159d54e7cb7e62bef9fb7d0cc31113b5320792acb3e6"
CONTROL_GUARD_SOURCE_SHA256 = "660b464b9bc4eed31d8b815ed821541633c31aafa763e8e2bd81613f5482d517"

# Immutable guard deployment checkout (reviewed, signed integration). Preserve .git.
DEPLOYED_ROOT = Path("/workspace/ivanka-guard-pr597-candidate-b777f349-20261128")
DEPLOYED_HEAD = "b777f34976bb338ba3652239feffe99510326e44"
IDENTITY_NAME = "px_guard_identity.json"
IDENTITY_SCHEMA = "ivanka.px.guard-source-identity.v1"
IDENTITY_SHA256 = "5822b1a9f00da556f5a554d038119b7937000592829eea96545fad7f76485e88"

# Origin of the constant-time shared disk reserve (PR #510). Retained evidence.
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
NATURAL_EXIT = (
    "benchmarks/fail_closed_guard/natural_exit.py",
    "benchmarks/fail_closed_guard/watch.py",
    "benchmarks/assembler_bench/exploratory_runtime/monitor.py",
)

# Reviewed deployment runtime-module bytes. This is the exact digest chain in
# the reviewed manifest; module bytes are checked in every deployment form.
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

# Reviewed module bytes of the new staged guard. EXPECTED above stays bound to
# the live control checkout at b8720600; only these five guards differ, and a
# guard-only root swap must not silently repin control verification.
DEPLOYED_EXPECTED = dict(EXPECTED)
DEPLOYED_EXPECTED.update({
    "benchmarks/fail_closed_guard/build.py":
        "4d01b152b5970b14d9084b1137af5c776b5b742fe257509c69038207c3a64119",
    "benchmarks/fail_closed_guard/copy_overlay.py":
        "7f4158ebf99af727aaa59528dabb5979624c5ce55ab2875c3f8a68764a25f53e",
    "benchmarks/fail_closed_guard/natural_exit.py":
        "9e7e4dda884896fa102e0d5af50d743780aa5617025698ea2574284b7af55daa",
    "benchmarks/fail_closed_guard/proc.py":
        "ee1438ba99b936a1a799913407e391f03bf90b0c22c89fd73a42570cdddef78a",
    "benchmarks/fail_closed_guard/watchdog.py":
        "95f2877f356747aa7601261081ed76bd645d8065c488813025155d160e5da2c4",
    "benchmarks/fail_closed_guard/watchdog_contract.py":
        "6bede6e674d633caf503877af2bd3ca444d96846650ed56418bf21250e00076b",
})


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
            or identity.get("sources") != DEPLOYED_EXPECTED):
        raise ValueError("deployed PX guard identity manifest drift")
    return identity


def verify_deployment(root=None):
    """Verify staged deployment bytes; not live process attestation.

    If ``.git`` exists, HEAD must equal the reviewed ``DEPLOYED_HEAD``. The
    reviewed manifest and exact module-byte chain are required in every form,
    including a COPY build that has no ``.git``.
    """
    base = Path(root) if root is not None else DEPLOYED_ROOT
    if (base / ".git").exists():
        if _git_head(base) != DEPLOYED_HEAD:
            raise ValueError("deployed checkout HEAD drift")
        git_state = "git_head_verified"
    else:
        git_state = "git_absent_manifest_attested"
    _read_identity(base)
    found = {}
    for name, expected in DEPLOYED_EXPECTED.items():
        path = base / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError("deployed PX guard source drift")
        found[name] = expected
    return {
        "kind": "staged_deployment_bytes",
        "root": str(base),
        "source_commit": DEPLOYED_HEAD,
        "git_state": git_state,
        "identity_sha256": IDENTITY_SHA256,
        "modules": found,
    }


def _read_control_identity(repo_root=None):
    base = Path(repo_root) if repo_root is not None else root()
    path = base / "benchmarks" / "assembler_bench" / CONTROL_IDENTITY_NAME
    if path.is_symlink() or not path.is_file():
        raise ValueError("control identity manifest missing")
    if digest(path) != CONTROL_IDENTITY_SHA256:
        raise ValueError("control identity manifest drift")
    try:
        identity = json.loads(path.read_bytes())
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("control identity manifest unreadable") from exc
    sources = identity.get("sources")
    if (not isinstance(identity, dict)
            or identity.get("schema") != CONTROL_IDENTITY_SCHEMA
            or not isinstance(sources, dict)):
        raise ValueError("control identity manifest drift")
    for name, value in sources.items():
        if (not isinstance(name, str) or not isinstance(value, str)
                or not re.fullmatch(r"[a-f0-9]{64}", value)):
            raise ValueError("control identity manifest drift")
    return identity


def verify_control(control_root=None, *, identity_root=None):
    """Verify control-checkout source bytes by reviewed hashes.

    The control checkout must be a real git checkout, but its HEAD is not
    pinned to an arbitrary/self-referential hash. Reviewed source hashes in
    the control identity manifest are the authority.
    """
    base = Path(control_root) if control_root is not None else CONTROL_ROOT
    if not (base / ".git").exists():
        raise ValueError("control checkout git identity missing")
    head = _git_head(base)
    identity = _read_control_identity(identity_root)
    found = {}
    for name, expected in identity["sources"].items():
        path = base / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError("control PX source drift: " + name)
        found[name] = expected
    # Self-hash with canonicalized constant to avoid circular manifest pinning.
    gs_name = "benchmarks/assembler_bench/px_guard_source.py"
    gs_path = base / gs_name
    if gs_path.is_symlink() or not gs_path.is_file():
        raise ValueError("control PX source drift: " + gs_name)
    gs_text = gs_path.read_text()
    gs_canon = re.sub(r'CONTROL_GUARD_SOURCE_SHA256 = "[a-f0-9]{64}"',
                      'CONTROL_GUARD_SOURCE_SHA256 = "' + "0" * 64 + '"',
                      gs_text, count=1)
    if hashlib.sha256(gs_canon.encode()).hexdigest() != CONTROL_GUARD_SOURCE_SHA256:
        raise ValueError("control PX source drift: " + gs_name)
    found[gs_name] = CONTROL_GUARD_SOURCE_SHA256
    for name, expected in EXPECTED.items():
        path = base / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError("control PX guard source drift: " + name)
        found[name] = expected
    return {
        "kind": "control_checkout_bytes",
        "root": str(base),
        "head": head,
        "head_pinned": False,
        "identity_sha256": CONTROL_IDENTITY_SHA256,
        "sources": found,
    }


def verify(root=None, *, control_root=None):
    """Return deployed guard digests only when both byte identities verify.

    Production (no args): verifies both pinned roots. Fixture mode
    (explicit ``root``): verifies staged deployment bytes only and still
    requires the reviewed manifest; it never silently skips identity checks.
    """
    deployment = verify_deployment(root)
    if root is None or control_root is not None:
        verify_control(control_root)
    return deployment["modules"]
