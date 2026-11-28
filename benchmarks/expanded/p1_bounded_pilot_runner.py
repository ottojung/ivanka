"""Bounded prospective P1 pilot controller for the combined 950fe331 candidate.

Rebased source-only entrypoint: the previous hwe8M runner (babc4dba,
"fix/p1-bounded-pilot-runner-integration") is re-based on exact PR527
``aad9a2cde61d7e8b12b44268f0135ee5060911ef``. On PR527 the shared guard
``fail_closed_guard.p1_harness.run_prospective`` already owns a REAL durable
controller heartbeat (``heartbeat.Emitter`` before spawn, ``bound(cid)`` and a
fresh refresh on every watch sample). This controller therefore does NOT inject
or override a heartbeat: it relies on the guard's real one. It adds only the
pilot-specific source pins, the matching pinned PX store binding, the 32 GiB
reserve + 1 GiB reservation admission, its owner-bound STOP and the bounded
explicit case list.

Cross-campaign exclusion is NOT provided by a pilot-private lock. This
controller must prove it operates inside the ACTUAL shared PX worker boundary
(``.global-worker.lock`` plus the watchdog's durable ``.worker-lease.jsonl``
root and its matching graphroot) or fail closed at ``--check`` time.

No live container, image build, large image import, STOP mutation, lease
creation or truth-in-assembly occurs by default. ``--check`` is read-only and
produces a prepared manifest. Execution requires ``--armed`` plus an exact
operator-issued slot token; until then this is source only.

Truth/reference files are verified but never mounted or passed to the
assembler. Post-hoc scoring happens only after the guarded container has exited
and exact teardown is proven.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import time
import tomllib
from pathlib import Path

from benchmarks.fail_closed_guard import lease, proc, startup, watchdog, watchdog_contract
from benchmarks.fail_closed_guard import stop as guard_stop
from benchmarks.fail_closed_guard import p1_harness
from benchmarks.fail_closed_guard.errors import GuardExceeded

from .micall_dominant import MULTITRUTH_SCORE_ORIGIN, evaluate_final_alignment
from .micall_synthetic_constants import TIMING_ORIGIN
from .p1_full464_controller import (
    ADMISSION_GIB,
    DEFAULT_DATA,
    DEFAULT_FROZEN,
    DEFAULT_TIMER,
    MEMORY_BYTES,
    ORIGINAL_IVANKA_IMAGE,
    PODMAN_TIMEOUT_SECONDS,
    PINS,
    RESERVE_GIB,
    WALL_CAP_SECONDS,
    assert_reference_blind,
    atomic_append,
    atomic_json,
    candidate_source_hashes,
    input_fingerprint,
    load_frozen,
    sha256,
    verify_case_hashes,
)

SCHEMA = "ivanka.p1.bounded-pilot-controller.v2"
STATUS = "ATTEMPTED_NOT_QUALIFIED"
SOURCE_COMMIT = "950fe331dfcd857011bfd63f9eeca92462708545"
BINARY_SHA = "8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786"
PARENT_IMAGE = ORIGINAL_IVANKA_IMAGE
FROZEN_MANIFEST_SHA256 = "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f"
INTEGRATION_BASE = "07231fa1a06b2cdd7d43d9896935f5050b7df4f5"

CASES_MANIFEST = Path(__file__).with_name("p1_pilot_cases.json")
IMAGE_MANIFEST = Path(__file__).with_name("p1_pilot_image_manifest.json")
CONTAINERFILE = Path(__file__).with_name(
    "Containerfile.p1-pilot-950fe331-binary-only")

PINS_V2 = {
    "cases_manifest": "629c8ec03802f7c2a29c36b863dc93ace675658e32d22bd7ccba183f9f258eea",
    "image_manifest": "1e2ac3fa6c688c3dc7bc45e04a59981d2dabbb4dddf7fb3e84c7aad0bf9dd9cb",
    "storage_conf": "fdf5ce294ebcd8a950d1ae2016032a2620e9b16cabf33c772dc43ab425ecec21",
    "physical_spec": "478c1b7b68943ac5e1ef565c257fd96ba6871184425ace80b026dd2b18cf8f87",
}

# Operator-admission policy: 32 GiB independent reserve plus a 1 GiB
# reservation, i.e. >= 33 GiB free on the shared workspace before any arm.
PILOT_RESERVE_GIB = 32
PILOT_RESERVATION_GIB = 1
PILOT_REQUIRED_FREE_BYTES = (PILOT_RESERVE_GIB + PILOT_RESERVATION_GIB) * 1024 ** 3

# ACTUAL shared PX worker boundary. A pilot-private lock or lease root cannot
# exclude a live PX arm: cross-campaign exclusion requires the real
# ``.global-worker.lock`` and the same durable lease journal the independent
# watchdog supervises. The graphroot comes from PX's own pinned storage.conf so
# readiness is bound to the same store namespace. All of these are proven by
# ``verify_shared_px_boundary`` before any admission; never assumed.
SHARED_PX_BOUNDARY = {
    "worker_root": "/workspace/ivanka-exploratory-ten-20261121",
    "global_lock": "/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock",
    "lease_root": "/workspace/ivanka-exploratory-ten-20261121",
    "lease_journal": "/workspace/ivanka-exploratory-ten-20261121/.worker-lease.jsonl",
    "storage_conf": "/workspace/ivanka-exploratory-ten-20261121/storage.conf",
    "storage_conf_sha256": "fdf5ce294ebcd8a950d1ae2016032a2620e9b16cabf33c772dc43ab425ecec21",
    "graphroot": "/workspace/ivanka-exploratory-podman-20261121/store",
    "watchdog_alive": "/workspace/ivanka-exploratory-ten-20261121/.watchdog-alive.json",
}
PX_ROOT = Path(SHARED_PX_BOUNDARY["worker_root"])

PILOT_ROOT = Path("/workspace/ivanka-p1-pilot-950fe331-20261126")
# Exclusion primitives are SHARED with PX; only the STOP sentinel stays
# owner-bound (it is a boundary request, not an exclusion primitive).
DEFAULT_LOCK = SHARED_PX_BOUNDARY["global_lock"]
DEFAULT_LEASE_ROOT = SHARED_PX_BOUNDARY["lease_root"]
DEFAULT_STOP = str(PILOT_ROOT / "p1-prospective.STOP")
DEFAULT_STORAGE_CONF = SHARED_PX_BOUNDARY["storage_conf"]
DEFAULT_EVIDENCE_ROOT = str(PILOT_ROOT / "evidence")
SLOT_AUTH_PATH = PILOT_ROOT / "operator-slot.json"
# Operator-owned, fixed authorization root. Slot consumption is GLOBAL here:
# a caller cannot evade replay by pointing --out at a different evidence root.
SLOT_AUTH_ROOT = Path("/workspace/ivanka-p1-operator-auth-20261126")
SLOT_AUTH_LOCK = SLOT_AUTH_ROOT / "slot.lock"
SLOT_LEDGER_NAME = "slot-consumption.jsonl"
PENDING_SLOT = "NO-SLOT-GRANTED"


def load_pinned_json(path, expected_sha, *, label):
    """Read a durable pin-verified JSON manifest (never a symlink)."""
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"{label}: manifest missing or symlink")
    actual = sha256(target)
    if actual != expected_sha:
        raise ValueError(f"{label}: pin mismatch {actual} != {expected_sha}")
    return json.loads(target.read_text()), actual


def load_case_manifest():
    return load_pinned_json(CASES_MANIFEST, PINS_V2["cases_manifest"],
                            label="cases")


def load_image_manifest():
    return load_pinned_json(IMAGE_MANIFEST, PINS_V2["image_manifest"],
                            label="image")


def explicit_cases(cases_manifest):
    """Exactly six residual + two control synthetic cases, no full464."""
    residual = tuple(cases_manifest["residual_cases"])
    control = tuple(cases_manifest["control_cases"])
    if len(residual) != 6 or len(control) != 2:
        raise ValueError("pilot case design must be 6 residual + 2 control")
    if set(residual) & set(control):
        raise ValueError("residual and control case sets overlap")
    return residual + control


def verify_px_store_binding(storage_conf, *, expected_graphroot=None,
                            expected_sha=None):
    """Derive the graphroot from the pinned PX storage.conf, fail closed.

    The watchdog ALIVE record must name this exact graphroot. Passing an
    operator-supplied string would allow a ready record from a different store
    to unblock admission; deriving it from the pinned config makes the binding
    match by construction. No Podman command is run in this read-only helper.
    """
    conf = Path(storage_conf)
    if conf.is_symlink() or not conf.is_file():
        raise ValueError("pinned PX storage.conf missing or symlink")
    digest = sha256(conf)
    if digest != (expected_sha or PINS_V2["storage_conf"]):
        raise ValueError("pinned PX storage.conf hash differs")
    try:
        data = tomllib.loads(conf.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("pinned PX storage.conf is not valid TOML") from exc
    if not isinstance(data, dict) or not isinstance(data.get("storage"), dict):
        raise ValueError("pinned PX storage.conf lacks [storage]")
    graphroot = data["storage"].get("graphroot")
    if not isinstance(graphroot, str) or not graphroot:
        raise ValueError("pinned PX storage.conf lacks graphroot")
    if expected_graphroot is not None and graphroot != str(expected_graphroot):
        raise ValueError("watchdog graphroot does not match pinned PX store")
    return {"storage_conf": str(conf), "storage_conf_sha256": digest,
            "graphroot": graphroot}


def verify_shared_px_boundary(*, lock, lease_root, watchdog_path,
                              storage_conf, graphroot, expected=None):
    """Fail closed unless the pilot is inside the ACTUAL shared PX boundary.

    A pilot-private ``pilot.lock`` or a private lease journal cannot exclude a
    live PX arm. Exclusion is only real when both campaigns contend for the
    same ``.global-worker.lock`` and write leases to the same durable journal
    that the independent watchdog discovers and supervises. Readiness must be
    bound to that watchdog's graphroot. This proof is read-only: it never
    acquires a lock, writes a lease, creates a STOP or touches a container.
    """
    exp = dict(expected or SHARED_PX_BOUNDARY)

    def _resolve(value, label):
        path = Path(value)
        if path.is_symlink():
            raise ValueError(f"shared PX {label} is a symlink")
        return path.resolve()

    lock_path = _resolve(lock, "global worker lock")
    if lock_path != Path(exp["global_lock"]).resolve():
        raise ValueError("lock is not the actual PX .global-worker.lock; "
                         "a pilot-private lock cannot exclude PX")
    if not lock_path.is_file():
        raise ValueError("actual PX global-worker lock is missing")

    lease_path = _resolve(lease_root, "lease root")
    if lease_path != Path(exp["lease_root"]).resolve():
        raise ValueError("lease root is not the shared PX worker root")
    if not lease_path.is_dir():
        raise ValueError("shared PX lease root is missing")

    journal = _resolve(Path(lease_root) / ".worker-lease.jsonl", "lease journal")
    if journal != Path(exp["lease_journal"]).resolve():
        raise ValueError("lease journal is not the PX durable lease journal")
    if not journal.is_file():
        raise ValueError("shared PX durable lease journal is missing")

    conf = _resolve(storage_conf, "storage.conf")
    if conf != Path(exp["storage_conf"]).resolve():
        raise ValueError("storage.conf is not the actual PX storage.conf")
    if not conf.is_file():
        raise ValueError("actual PX storage.conf is missing")
    if sha256(conf) != exp["storage_conf_sha256"]:
        raise ValueError("PX storage.conf pin differs")

    if str(graphroot) != str(exp["graphroot"]):
        raise ValueError("graphroot differs from the PX watchdog graphroot; "
                         "readiness would bind to a foreign store")

    alive = _resolve(watchdog_path, "watchdog readiness record")
    if alive != Path(exp["watchdog_alive"]).resolve():
        raise ValueError("watchdog readiness record is not the shared PX ALIVE record")

    return {
        "shared": True,
        "global_lock": str(lock_path),
        "lease_root": str(lease_path),
        "lease_journal": str(journal),
        "storage_conf": str(conf),
        "storage_conf_sha256": exp["storage_conf_sha256"],
        "graphroot": str(graphroot),
        "watchdog_alive": str(alive),
        "watchdog_alive_present": alive.is_file(),
        "kernel_enforcement": False,
    }


# Ambient container selectors must never leak into a guarded arm: they can
# silently redirect Podman to a different store, imageroot or client config.
AMBIENT_CONTAINER_SELECTORS = ("CONTAINERS_CONF", "CONTAINERS_STORAGE_CONF",
                               "CONTAINERS_STORAGE_RUNROOT", "CONTAINERS_IMAGEROOT",
                               "CONTAINERS_STORAGE_DRIVER", "CONTAINERS_ROOTLESS")


# Prospective pin to the reviewed, MERGED PR535/PR553 combined guard. Deployment
# is a separate operator action; this source pin must never imply readiness.
# The previous live PR536 head is retained for old-root verification only: it is
# not an alternative accepted identity and never bypasses a source or live check.
PREVIOUS_REVIEWED_GUARD_HEAD = "091f56275ae823cb3291b81dbdf016fcf16c3ea0"
REVIEWED_GUARD_HEAD = "165a86b38c0bc29b4f8e0281a39ca59b909a6563"
REVIEWED_GUARD_DIGESTS = {
    "natural_exit": ("fail_closed_guard/natural_exit.py",
                     "f7f6028273a5d7775b8d4ca6139e9659ca475a0aa36a3d12b1a736e429202cd6"),
    "watch": ("fail_closed_guard/watch.py",
              "07356fc4b29e1e6bc5b11659048bc5437a70037a29dde197dd795540fd66da96"),
    "monitor": ("assembler_bench/exploratory_runtime/monitor.py",
                "b0bbefa221ff092acf33021b0203f2b07a912c250fc0893e8fdd59dad642293c"),
    "p1_helper": ("fail_closed_guard/p1_helper.py",
                  "b950ff947da8144271d8f4f0064fe72b4d6b1a492591e36610b942a553f21a27"),
    "p1_harness": ("fail_closed_guard/p1_harness.py",
                   "a6295c71f6b4ef3318cb7f0f9bcdc9109f82a2649dbbe86dca2c94c878ff560a"),
}


def verify_guard_source_pins(bench_dir=None):
    """Prove the SOURCE guard matches the reviewed combined guard head (no deploy claim)."""
    base = Path(bench_dir) if bench_dir else Path(__file__).resolve().parents[1]
    got = {}
    for name, (relative, expected) in REVIEWED_GUARD_DIGESTS.items():
        path = base / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"reviewed guard module missing: {name}")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"reviewed guard pin mismatch: {name}")
        got[name] = actual
    return {"head": REVIEWED_GUARD_HEAD, "digests": got,
            "prospective": True, "deployed": False}


# COPY_OVERLAY_ADMISSION_MERGE and COPY_OVERLAY_ADMISSION_PR_HEAD record the
# historical PR535 lineage only; they are not the identity of the current
# launcher bytes. The digests below are a separately reviewed amendment to
# that lineage -- the original merge never contained these bytes -- and bind
# a guarded pilot against an ungated or altered launcher. Deployment of a
# built image remains a separate operator action.
COPY_OVERLAY_ADMISSION_MERGE = "165a86b38c0bc29b4f8e0281a39ca59b909a6563"
COPY_OVERLAY_ADMISSION_PR_HEAD = "39317f021f4e5c00f5da859bcdcf755de4c6d353"
COPY_OVERLAY_ADMISSION_DIGESTS = {
    "copy_overlay": ("fail_closed_guard/copy_overlay.py",
                     "7f4158ebf99af727aaa59528dabb5979624c5ce55ab2875c3f8a68764a25f53e"),
    "copy_overlay_helper": ("fail_closed_guard/copy_overlay_helper.py",
                            "8242d81c9c6b169dfbfac1b837ae9c23e1e3f1259190438871dee89dccdf0bc5"),
    "build": ("fail_closed_guard/build.py",
              "4d01b152b5970b14d9084b1137af5c776b5b742fe257509c69038207c3a64119"),
    "watchdog_cli": ("fail_closed_guard/watchdog_cli.py",
                     "e00b83adfbf8356f2f92ce92ecd2226854a182d21a21e24ca87d35ed205b5369"),
}


def verify_copy_overlay_admission_pins(bench_dir=None):
    """Prove the reviewed COPY-only admission amendment is exact.

    The lineage constants above name the historical PR535 merge; these digests
    identify the current reviewed source, which is a later amendment and not
    bytes contained in that merge. This is a source/prospective pin only: it
    does not build, run, import, deploy or claim a ready watchdog. The pilot
    still needs the live operator-bound watchdog proof before any arm.
    """
    base = Path(bench_dir) if bench_dir else Path(__file__).resolve().parents[1]
    got = {}
    for name, (relative, expected) in COPY_OVERLAY_ADMISSION_DIGESTS.items():
        path = base / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"copy-overlay admission module missing: {name}")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"copy-overlay admission pin mismatch: {name}")
        got[name] = actual
    return {"merge": COPY_OVERLAY_ADMISSION_MERGE,
            "pr_head": COPY_OVERLAY_ADMISSION_PR_HEAD, "digests": got,
            "prospective": True, "deployed": False, "build_executed": False}


# Separate, exact portable-artifact plan. The pinned NATIVE binaries carry a
# Guix PT_INTERP that does not exist in the frozen base image; a portable
# artifact must be retargeted and newly pinned, never silently substituted.
PORTABLE_PLAN = Path(__file__).with_name("p1_pilot_portable_image_manifest.json")
PORTABLE_PLAN_SHA256 = "0384d9d5bb1bb7f68725e833cae081ee0317dd456df91400e941098299f19afc"
PORTABLE_INTERP = "/lib64/ld-linux-x86-64.so.2"
PORTABLE_NEEDED = ("libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2")
PORTABLE_MAX_GLIBC_MINOR = 34


def load_portable_plan(expected_sha=None):
    """Read the pinned plan; a changed plan is refused, not reinterpreted."""
    if PORTABLE_PLAN.is_symlink() or not PORTABLE_PLAN.is_file():
        raise ValueError("portable artifact plan missing or symlink")
    actual = sha256(PORTABLE_PLAN)
    if actual != (expected_sha or PORTABLE_PLAN_SHA256):
        raise ValueError(f"portable artifact plan pin mismatch: {actual}")
    doc = json.loads(PORTABLE_PLAN.read_text())
    if doc.get("schema") != "ivanka.p1.portable-artifact-plan.v1":
        raise ValueError("unknown portable artifact plan schema")
    return doc


def verify_portable_plan(plan=None):
    """Validate the portability contract for planned or produced portable bytes.

    Produced portable bytes are allowed only when their exact path/SHA are
    pinned and the image remains unbuilt/unverified. No silent native
    substitution and no image-build/arm claim are permitted here.
    """
    doc = plan or load_portable_plan()
    contract = doc.get("contract") or {}
    if not doc.get("prepared_only") or doc.get("build_executed") is not False:
        raise ValueError("portable plan must be prepared-only and unexecuted")
    if contract.get("pt_interp_required") != PORTABLE_INTERP:
        raise ValueError("portable plan interpreter pin differs")
    if (not contract.get("guix_store_runpath_forbidden")
            or not contract.get("needed_unchanged")
            or not contract.get("native_artifact_retained")
            or not contract.get("silent_substitution_forbidden")
            or not contract.get("verify_before_arm")
            or not contract.get("post_build_image_identity_gate_required")):
        raise ValueError("portable plan contract weakened")
    candidates = doc.get("candidates")
    # The two original reviewed candidates remain pinned and preserved; the
    # third row is the separately measured 87ce + native-fragment candidate.
    # Extra rows are never accepted implicitly: each must pass every pin below.
    if not isinstance(candidates, list) or len(candidates) not in (2, 3):
        raise ValueError("portable plan must cover only reviewed exact candidates")
    produced = 0
    for row in candidates:
        native = row.get("native_binary_sha256")
        commit = row.get("source_commit")
        if (len(native or "") != 64 or len(commit or "") < 7
                or "/gnu/store/" not in row.get("native_interp", "")):
            raise ValueError("portable plan candidate pin incomplete")
        portable = row.get("portable_binary_sha256")
        image = row.get("portable_image")
        built = row.get("image_built")
        verified = row.get("image_identity_verified")
        if portable is None:
            if image is not None or built or verified:
                raise ValueError("portable plan image state without portable bytes")
            continue
        if (len(portable) != 64
                or not isinstance(row.get("portable_binary_path"), str)
                or not row["portable_binary_path"]):
            raise ValueError("portable plan portable pin incomplete")
        if portable == native:
            raise ValueError("portable plan silently substitutes native artifact")
        if built not in (False, None) or verified not in (False, None):
            raise ValueError("portable plan may not claim image build/verification")
        if image is not None:
            raise ValueError("portable image identity must be null before verified build")
        produced += 1
    return {"schema": doc["schema"], "candidates": len(candidates),
            "produced": produced, "build_executed": False}


def inspect_elf_portability(path):
    """Read-only ELF facts: PT_INTERP, dynamic RUNPATH and DT_NEEDED entries.

    Only the live dynamic section is authoritative: a cleared RUNPATH may
    still leave inert /gnu/store strings in debug data, as the prior portable
    artifact demonstrates.
    """
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("binary missing or symlink")
    data = target.read_bytes()
    if (len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2
            or data[5] != 1):
        raise ValueError("not a 64-bit little-endian ELF")
    phoff = int.from_bytes(data[32:40], "little")
    phentsize = int.from_bytes(data[54:56], "little")
    phnum = int.from_bytes(data[56:58], "little")
    if phentsize < 56 or phnum < 1:
        raise ValueError("invalid ELF program header table")
    interp = None
    loads = []
    dynamic = None
    for index in range(phnum):
        off = phoff + index * phentsize
        if off + 56 > len(data):
            raise ValueError("truncated ELF program header")
        kind = int.from_bytes(data[off:off + 4], "little")
        p_offset = int.from_bytes(data[off + 8:off + 16], "little")
        p_vaddr = int.from_bytes(data[off + 16:off + 24], "little")
        p_filesz = int.from_bytes(data[off + 32:off + 40], "little")
        if kind == 3:  # PT_INTERP
            if p_offset + p_filesz > len(data) or p_filesz == 0:
                raise ValueError("invalid PT_INTERP")
            interp = data[p_offset:p_offset + p_filesz].split(b"\0", 1)[0].decode("ascii")
        elif kind == 1:  # PT_LOAD
            loads.append((p_vaddr, p_offset, p_filesz))
        elif kind == 2:  # PT_DYNAMIC
            if p_offset + p_filesz > len(data):
                raise ValueError("invalid PT_DYNAMIC")
            dynamic = (p_offset, p_filesz)
    if interp is None:
        raise ValueError("ELF has no PT_INTERP")

    def vaddr_to_offset(vaddr):
        for base_vaddr, base_offset, filesz in loads:
            if base_vaddr <= vaddr < base_vaddr + filesz:
                return base_offset + (vaddr - base_vaddr)
        raise ValueError("dynamic address unmapped in ELF")

    needed_offsets, search_offsets = [], []
    strtab_vaddr, strtab_size = None, 0
    if dynamic is not None:
        off, size = dynamic
        for cursor in range(off, off + size - 15, 16):
            tag = int.from_bytes(data[cursor:cursor + 8], "little", signed=True)
            value = int.from_bytes(data[cursor + 8:cursor + 16], "little")
            if tag == 1:  # DT_NEEDED
                needed_offsets.append(value)
            elif tag == 5:  # DT_STRTAB
                strtab_vaddr = value
            elif tag == 10:  # DT_STRSZ
                strtab_size = value
            elif tag in (15, 29):  # DT_RPATH / DT_RUNPATH
                search_offsets.append(value)
    needed, runpath = [], []
    if strtab_vaddr is not None:
        base = vaddr_to_offset(strtab_vaddr)
        table = data[base:base + strtab_size] if strtab_size else data[base:]

        def string_at(index):
            if index >= len(table):
                raise ValueError("dynamic string offset out of range")
            return table[index:].split(b"\0", 1)[0].decode("ascii", "replace")

        needed = [string_at(index) for index in needed_offsets]
        runpath = [string_at(index) for index in search_offsets]
    versions = sorted({int(match.group(1))
                       for match in re.finditer(rb"GLIBC_2\.(\d+)", data)})
    return {"interp": interp,
            "guix_store_runpath": any("/gnu/store/" in path for path in runpath),
            "runpath": runpath, "glibc_minor_versions": versions,
            "needed": needed}


def verify_portable_binary(path, source_commit=None, *, plan=None):
    """Fail closed on Guix-interpreter binaries; require an exact new pin."""
    doc = plan or load_portable_plan()
    verify_portable_plan(doc)
    digest = sha256(Path(path))
    rows = [row for row in doc["candidates"]
            if source_commit is None
            or row["source_commit"] == source_commit]
    if len(rows) != 1:
        raise ValueError("portable plan candidate not uniquely selected")
    row = rows[0]
    info = inspect_elf_portability(path)
    if info["interp"] != PORTABLE_INTERP or info["guix_store_runpath"]:
        if digest == row["native_binary_sha256"]:
            raise ValueError("native artifact retained; no silent substitution")
        raise ValueError("binary interpreter is not portable")
    if (info["needed"] != list(PORTABLE_NEEDED)
            or (info["glibc_minor_versions"]
                and max(info["glibc_minor_versions"]) > PORTABLE_MAX_GLIBC_MINOR)):
        raise ValueError("binary symbol/NEEDED contract differs from base")
    expected = row["portable_binary_sha256"]
    if not expected or digest != expected:
        raise ValueError("portable artifact not produced/pinned")
    return {"source_commit": row["source_commit"], "sha256": digest,
            "image": row["portable_image"], "portable": True}


PORTABLE_POSTBUILD_SCHEMA = "ivanka.p1.portable-postbuild-receipt.v1"


def normalize_digest(value):
    if isinstance(value, str):
        bare = value.strip().removeprefix("sha256:").lower()
        if len(bare) == 64 and all(c in "0123456789abcdef" for c in bare):
            return bare
    raise ValueError("invalid digest")


def expected_portable_labels(row):
    """Exact labels the guarded COPY-only build must set for this role.

    The binary label is the PORTABLE SHA, never the native pin; the source
    commit is the candidate's own commit (for example the PCR candidate), not
    the controller's default. Derived only from the immutable prebuild plan.
    """
    return {
        "org.ottojung.ivanka.source-commit": row["source_commit"],
        "org.ottojung.micall.frozen-image-id": PARENT_IMAGE,
        "org.ottojung.ivanka.binary-sha256": row["portable_binary_sha256"],
        "org.ottojung.ivanka.frozen-manifest-sha256": FROZEN_MANIFEST_SHA256,
        "org.ottojung.ivanka.pilot-role": row["role"],
    }


def portable_image_contract(row):
    """Per-portable-role image contract consumed by verify_image_contract."""
    return {
        "candidate_source_commit": row["source_commit"],
        "expected_labels": expected_portable_labels(row),
        "layer_contract": {
            "kind": "one_layer_binary_only_overlay",
            "no_source_or_truth_in_image": True,
            "verify": ("child.RootFS.Layers[:-1] == parent.RootFS.Layers and "
                       "the added layer contains only /usr/local/bin/ivanka "
                       "with the pinned portable sha256"),
            "binary_sha256": row["portable_binary_sha256"],
        },
    }


def load_portable_postbuild_receipt(path, *, expected_sha):
    """Load an authenticated postbuild receipt; SHA pin is mandatory."""
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("portable postbuild receipt SHA pin required")
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("portable postbuild receipt missing or symlink")
    actual = sha256(target)
    if actual != expected_sha:
        raise ValueError(f"portable postbuild receipt pin mismatch: {actual}")
    doc = json.loads(target.read_text())
    if doc.get("schema") != PORTABLE_POSTBUILD_SCHEMA:
        raise ValueError("unknown portable postbuild receipt schema")
    return doc, actual


def verify_copy_overlay_lease(root, ident, *, plan_sha, base_layers,
                              teardown, orphan_baseline_ids):
    """Prove one authentic lease acquire -> bind_group -> release lifecycle.

    ``lease.acquire`` really emits ``state=active, mode=copy_overlay, pid=None``
    and ``bind_group`` emits a SECOND ``active`` event with ``helper=True``.
    The bind must therefore be selected by the unique helper=True marker, not
    by the first active event, and the whole lifecycle must be unique/ordered.
    """
    root = Path(root or SHARED_PX_BOUNDARY["worker_root"])
    try:
        events = lease.events(root)
        fail_closed = [event for event in watchdog.read_evidence(root)
                       if event.get("worker") == ident
                       and event.get("result") == "fail_closed"]
    except GuardExceeded as exc:
        raise ValueError(f"copy_overlay journal unavailable: {exc.reason}") from exc
    if fail_closed:
        raise ValueError("copy_overlay watchdog fail-closed evidence present")

    scoped = [event for event in events if event.get("lease") == ident]
    acquired = [event for event in scoped
                if event.get("state") == "active"
                and event.get("mode") == "copy_overlay"
                and event.get("pid") is None
                and event.get("helper") is not True]
    binds = [event for event in scoped
             if event.get("state") == "active"
             and event.get("mode") == "copy_overlay"
             and event.get("helper") is True]
    releases = [event for event in scoped if event.get("state") == "released"]
    if len(acquired) != 1 or len(binds) != 1 or len(releases) != 1:
        raise ValueError("copy_overlay lease lifecycle not unique")
    acquire, bind, release = acquired[0], binds[0], releases[0]
    if not (events.index(acquire) < events.index(bind) < events.index(release)):
        raise ValueError("copy_overlay lease lifecycle out of order")
    if (acquire.get("owner") != ident or bind.get("owner") != ident
            or release.get("owner") != ident):
        raise ValueError("copy_overlay lease owner changed")

    pid = bind.get("pid")
    if (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
            or bind.get("pgid") != pid
            or not isinstance(bind.get("fingerprint"), list)
            or len(bind["fingerprint"]) < 2
            or acquire.get("at_utc") != bind.get("at_utc")):
        raise ValueError("copy_overlay bind identity invalid")
    if (bind.get("plan_sha256") != plan_sha
            or bind.get("graphroot") != SHARED_PX_BOUNDARY["graphroot"]
            or bind.get("storage_conf_sha256") != PINS_V2["storage_conf"]
            or bind.get("base_image") != PARENT_IMAGE
            or [normalize_digest(x) for x in (bind.get("base_layers") or [])]
            != [normalize_digest(x) for x in base_layers]):
        raise ValueError("copy_overlay bind evidence mismatch")
    expected_baseline = sorted(orphan_baseline_ids)
    if sorted(bind.get("baseline_ids") or []) != expected_baseline:
        raise ValueError("copy_overlay bind baseline mismatch")

    if not isinstance(teardown, dict):
        raise ValueError("copy_overlay teardown proof missing")
    cleanup = teardown.get("orphan_cleanup")
    if (teardown.get("process_group") != pid
            or teardown.get("stopped") is not True
            or teardown.get("method") != "verified_exact_group"
            or teardown.get("kernel_enforcement") is not False
            or not isinstance(cleanup, dict)
            or cleanup.get("method") != "exact_full_id_base_proof"
            or cleanup.get("graphroot") != SHARED_PX_BOUNDARY["graphroot"]
            or cleanup.get("expected_base") != PARENT_IMAGE
            or cleanup.get("fresh_absence_check") is not True
            or cleanup.get("kernel_enforcement") is not False
            or sorted(cleanup.get("baseline_ids") or []) != expected_baseline):
        raise ValueError("copy_overlay teardown proof incomplete")
    if release.get("proof") != teardown:
        raise ValueError("copy_overlay release proof mismatch")
    return bind

def verify_copy_overlay_result(path, *, expected_sha, expected_plan_sha,
                               expected_image, expected_labels, root=None):
    """Validate the ACTUAL copy_overlay result.json and its durable journals.

    Nothing nested inside the postbuild receipt is trusted as build evidence:
    the result file is SHA-pinned and its completion, exact plan sha, owner,
    released lease proof, image receipt and absence of fail-closed evidence
    are read from disk. The image/layer contract is independently inspected by
    verify_image_contract/verify_image_layer_contract in prepare().
    """
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("copy_overlay result SHA pin required")
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("copy_overlay result missing or symlink")
    actual = sha256(target)
    if actual != expected_sha:
        raise ValueError(f"copy_overlay result pin mismatch: {actual}")
    state = json.loads(target.read_text())
    if not isinstance(state, dict):
        raise ValueError("copy_overlay result schema invalid")
    if state.get("tool") != "copy_overlay":
        raise ValueError("copy_overlay result tool invalid")
    if state.get("status") != "completed" or state.get("reason") is not None:
        raise ValueError("copy_overlay result not completed cleanly")
    if state.get("exit_code") != 0:
        raise ValueError("copy_overlay result exit code nonzero")
    if state.get("enforcement") != "userspace_observed":
        raise ValueError("copy_overlay result enforcement invalid")
    plan_sha = normalize_digest(state.get("plan_sha256"))
    if plan_sha != normalize_digest(expected_plan_sha):
        raise ValueError("copy_overlay result plan sha mismatch")
    ident = "copy-" + plan_sha[:16]
    if state.get("lease") != ident or state.get("owner") != ident:
        raise ValueError("copy_overlay result lease/owner mismatch")

    evidence = state.get("image_receipt")
    if not isinstance(evidence, dict):
        raise ValueError("copy_overlay result image receipt missing")
    if evidence.get("image") != expected_image:
        raise ValueError("copy_overlay result image mismatch")
    if evidence.get("one_layer_overlay") is not True:
        raise ValueError("copy_overlay result missing one-layer evidence")
    base_layers = evidence.get("base_layers")
    layers = evidence.get("layers")
    if (not isinstance(base_layers, list) or not base_layers
            or not isinstance(layers, list)
            or [normalize_digest(x) for x in layers[:-1]] != [normalize_digest(x) for x in base_layers]
            or len(layers) != len(base_layers) + 1
            or normalize_digest(layers[-1]) == normalize_digest(base_layers[-1])):
        raise ValueError("copy_overlay result layer evidence invalid")
    labels = evidence.get("labels")
    if not isinstance(labels, dict):
        raise ValueError("copy_overlay result labels missing")
    for key, value in expected_labels.items():
        if labels.get(key) != value:
            raise ValueError(f"copy_overlay result label mismatch: {key}")

    verify_copy_overlay_lease(
        root, ident, plan_sha=plan_sha, base_layers=base_layers,
        teardown=state.get("teardown"),
        orphan_baseline_ids=state.get("orphan_baseline_ids") or [])
    return {"path": str(target), "sha256": actual, "plan_sha256": plan_sha,
            "lease": ident, "owner": ident, "released": True,
            "fail_closed_events": 0, "image": expected_image,
            "one_layer_overlay": True, "labels": labels}


def verify_portable_postbuild_receipt(path, *, expected_sha,
                                      source_commit=None, plan=None, root=None):
    """Validate a pinned postbuild receipt against the actual copy_overlay build.

    The immutable prebuild plan and its exact candidate/portable pins are bound
    to a SHA-pinned receipt, which points at the actual copy_overlay result.json
    (itself SHA-pinned). Self-declared nested evidence is never accepted.
    """
    doc, receipt_sha = load_portable_postbuild_receipt(
        path, expected_sha=expected_sha)
    prebuild = plan or load_portable_plan()
    verify_portable_plan(prebuild)
    if doc.get("prebuild_plan_sha256") != PORTABLE_PLAN_SHA256:
        raise ValueError("portable postbuild receipt not bound to prebuild plan")
    if not doc.get("build_executed") or not doc.get("image_identity_verified"):
        raise ValueError("portable postbuild receipt missing verified build evidence")
    commit = doc.get("source_commit")
    if source_commit is not None and commit != source_commit:
        raise ValueError("portable postbuild receipt source commit differs")
    rows = [row for row in prebuild["candidates"]
            if row["source_commit"] == commit]
    if len(rows) != 1:
        raise ValueError("portable postbuild receipt candidate not uniquely selected")
    row = rows[0]
    portable_sha = doc.get("portable_binary_sha256")
    if (portable_sha != row["portable_binary_sha256"]
            or doc.get("native_binary_sha256") != row["native_binary_sha256"]
            or doc.get("portable_binary_path") != row["portable_binary_path"]):
        raise ValueError("portable postbuild receipt portable pin mismatch")
    image = normalize_digest(doc.get("image_digest"))
    if image != normalize_digest(doc.get("portable_image")):
        raise ValueError("portable postbuild receipt image digest mismatch")

    result_ref = doc.get("copy_overlay_result")
    if not isinstance(result_ref, dict):
        raise ValueError("portable postbuild receipt missing copy_overlay result binding")
    result = verify_copy_overlay_result(
        result_ref.get("path"), expected_sha=result_ref.get("sha256"),
        expected_plan_sha=result_ref.get("plan_sha256"),
        expected_image=image, expected_labels=expected_portable_labels(row),
        root=root)
    return {"schema": doc["schema"], "receipt_sha256": receipt_sha,
            "source_commit": commit, "image": image,
            "portable_binary_sha256": portable_sha,
            "portable_binary_path": row["portable_binary_path"],
            "role": row["role"], "image_identity_verified": True,
            "build_executed": True, "copy_overlay_result": result,
            "candidate_row": row}


def require_portable_image_identity_verified(source_commit, image_digest,
                                             *, plan=None, postbuild_receipt=None,
                                             postbuild_receipt_sha256=None,
                                             root=None):
    """Fail closed until a guarded COPY-only build produced a verified image.

    Portable bytes may be pinned before an image exists, but no arm may use
    them until a SHA-pinned postbuild receipt is bound to the actual
    copy_overlay result and journals. No manual manifest build claim is
    accepted, and the image/layer contract is independently inspected by the
    caller before this identity is used.
    """
    prebuild = plan or load_portable_plan()
    verify_portable_plan(prebuild)
    if not isinstance(image_digest, str) or len(image_digest) != 64:
        raise ValueError("portable image digest must be a full sha256")
    if postbuild_receipt is None:
        raise ValueError("portable image identity not verified post-build")
    verified = verify_portable_postbuild_receipt(
        postbuild_receipt, expected_sha=postbuild_receipt_sha256,
        source_commit=source_commit, plan=prebuild, root=root)
    if verified["image"] != normalize_digest(image_digest):
        raise ValueError("portable image identity not verified post-build")
    return verified


def pinned_podman_env(storage_conf=None, *, expected_sha=None):
    """Minimal env with ONLY the verified shared store selector set.

    Unlike the inherited podman_env(), this drops every ambient CONTAINERS_*
    selector instead of copying os.environ into the arm. Production callers
    must use the default expected_sha (the durable shared-store pin); the
    override exists solely so isolated CI fixtures can supply their own
    synthetic conf/hash without depending on a private host path.
    """
    conf = Path(storage_conf or SHARED_PX_BOUNDARY["storage_conf"])
    if conf.is_symlink() or not conf.is_file():
        raise ValueError("pinned shared PX storage.conf missing or symlink")
    if sha256(conf) != (expected_sha or PINS_V2["storage_conf"]):
        raise ValueError("pinned shared PX storage.conf hash differs")
    env = {key: value for key, value in os.environ.items()
           if key not in AMBIENT_CONTAINER_SELECTORS
           and not key.startswith("CONTAINERS_")}
    env["CONTAINERS_STORAGE_CONF"] = str(conf.resolve())
    return env


def pinned_inspect_env(storage_conf=None):
    """Build an inspect env pinned to the ACTUAL shared PX store (read-only)."""
    return pinned_podman_env(storage_conf)


def _default_inspect(image, fmt, *, env=None):
    """Read-only Podman inspect in the pinned store; never import/tag/delete."""
    result = subprocess.run(
        ["podman", "image", "inspect", "--format", fmt, image],
        env=env, capture_output=True, text=True, timeout=60, check=False)
    return result.returncode, result.stdout.strip()


def verify_image_contract(image, commit, *, env=None, inspect=None,
                          image_manifest=None):
    """Bind image to source, binary and frozen parent without building it.

    Inspection must use the pinned shared PX storage.conf: an ambient Podman
    store could resolve a different image with the same digest string.
    """
    manifest = image_manifest or load_image_manifest()[0]
    if (len(image) != 64 or any(c not in "0123456789abcdef" for c in image)):
        raise ValueError("candidate image must be a full immutable SHA-256")
    if image == PARENT_IMAGE:
        raise ValueError("frozen baseline image may not be rerun as candidate")
    if commit != manifest["candidate_source_commit"]:
        raise ValueError("candidate source commit differs from pinned image manifest")
    inspect_env = env or pinned_inspect_env()
    if inspect_env.get("CONTAINERS_STORAGE_CONF") != SHARED_PX_BOUNDARY["storage_conf"]:
        raise ValueError("image inspection must use the pinned shared PX storage.conf")
    run_inspect = inspect or (lambda i, f: _default_inspect(i, f, env=inspect_env))
    rc, identity = run_inspect(image, "{{.Id}}")
    if rc != 0 or identity.removeprefix("sha256:") != image:
        raise ValueError("candidate image identity differs from its digest")
    rc, raw_labels = run_inspect(image, "{{json .Config.Labels}}")
    if rc != 0:
        raise ValueError("candidate image labels unreadable")
    labels = json.loads(raw_labels)
    for key, value in manifest["expected_labels"].items():
        if labels.get(key) != value:
            raise ValueError(f"candidate image label {key} differs from pin")
    rc, child = run_inspect(image, "{{json .RootFS.Layers}}")
    rc_parent, parent = run_inspect(PARENT_IMAGE, "{{json .RootFS.Layers}}")
    if rc != 0 or rc_parent != 0:
        raise ValueError("image layer inspection unavailable")
    child_layers = json.loads(child)
    parent_layers = json.loads(parent)
    if child_layers[:-1] != parent_layers or len(child_layers) != len(parent_layers) + 1:
        raise ValueError("candidate is not a one-layer binary-only overlay")
    return {"labels": labels, "parent": PARENT_IMAGE,
            "layer_contract": manifest["layer_contract"],
            "image_digest": image}


def verify_binary_stage(stage_dir, *, expected_sha=None):
    """Host pre-build proof: the stage holds exactly the pinned ELF binary.

    Source-only and read-only. This is the check that permits a copy-only
    Containerfile (no RUN, therefore a single added layer).
    """
    base = Path(stage_dir)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("build context missing or symlink")
    entries = sorted(path.name for path in base.iterdir())
    if entries != ["combined-950fe331"]:
        raise ValueError("build context must contain exactly combined-950fe331")
    binary = base / "combined-950fe331"
    if binary.is_symlink() or not binary.is_file():
        raise ValueError("staged binary missing or symlink")
    digest = sha256(binary)
    if digest != (expected_sha or BINARY_SHA):
        raise ValueError("staged binary SHA256 differs from pin")
    with binary.open("rb") as stream:
        magic = stream.read(4)
    if magic != b"\x7fELF":
        raise ValueError("staged binary lacks ELF magic")
    mode = stat.S_IMODE(binary.stat().st_mode)
    if mode != 0o755:
        raise ValueError("staged binary mode must be 0755")
    return {"verified": True, "path": str(binary), "sha256": digest,
            "elf_magic": magic.hex(), "mode": "0755", "entries": entries}


def verify_binary_layer_entries(entries, *, expected_sha=None):
    """Independent proof that the single added layer has only the pinned binary."""
    want = {"/usr/local/bin/ivanka": expected_sha or BINARY_SHA}
    if not isinstance(entries, dict) or entries != want:
        raise ValueError("added layer contents differ from the binary-only contract")
    return {"verified": True, "expected_entries": want}


def acquire_added_layer_evidence(image, *, env=None, inspect=None, graphroot=None):
    """Read-only ACQUISITION of the exact added layer from the pinned store.

    No operator-supplied dictionary or placeholder is accepted: layer digests
    come from Podman inspection of the exact image and its frozen parent under
    the pinned storage env, the added digest is resolved through the store's
    own overlay-layers/layers.json, and the layer diff tree is hashed on disk.
    """
    env = env or pinned_inspect_env()
    run = inspect or (lambda i, f: _default_inspect(i, f, env=env))
    rc, raw_child = run(image, "{{json .RootFS.Layers}}")
    rc_parent, raw_parent = run(PARENT_IMAGE, "{{json .RootFS.Layers}}")
    if rc != 0 or rc_parent != 0:
        raise ValueError("image layer inspection unavailable in pinned store")
    child, parent = json.loads(raw_child), json.loads(raw_parent)
    if (not isinstance(child, list) or not isinstance(parent, list)
            or child[:-1] != parent or len(child) != len(parent) + 1):
        raise ValueError("candidate is not a one-layer binary-only overlay")
    added = child[-1]
    digest = added.removeprefix("sha256:") if isinstance(added, str) else ""
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("added layer digest is not a sha256 digest")
    root = Path(graphroot or SHARED_PX_BOUNDARY["graphroot"])
    if root.is_symlink() or not root.is_dir():
        raise ValueError("pinned graphroot unavailable")
    index = root / "overlay-layers" / "layers.json"
    if index.is_symlink() or not index.is_file():
        raise ValueError("pinned overlay layer index unavailable")
    rows = json.loads(index.read_text())
    layer_id = None
    for row in rows:
        if (row.get("diff-digest") in (added, "sha256:" + digest)
                or row.get("compressed-diff-digest") in (added, "sha256:" + digest)):
            layer_id = row.get("id")
            break
    if (not isinstance(layer_id, str)
            or not re.fullmatch(r"[0-9a-f]{64}", layer_id)):
        raise ValueError("added layer digest not found in pinned store index")
    diff = root / "overlay" / layer_id / "diff"
    if diff.is_symlink() or not diff.is_dir():
        raise ValueError("added layer diff tree unavailable")
    entries = {}
    for path in sorted(diff.rglob("*")):
        if path.is_symlink():
            raise ValueError("added layer contains a symlink")
        if path.is_file():
            entries["/" + str(path.relative_to(diff))] = sha256(path)
    return {"image": image, "parent": PARENT_IMAGE, "added_digest": added,
            "layer_id": layer_id, "entries": entries}


def verify_image_layer_contract(image, *, env=None, inspect=None, graphroot=None,
                                image_manifest=None, expected_sha=None):
    """Acquire and verify the exact added layer evidence before any arm."""
    if isinstance(image, dict):
        raise ValueError("image must be a digest string, not a manifest")
    evidence = acquire_added_layer_evidence(
        image, env=env, inspect=inspect, graphroot=graphroot)
    if evidence["image"] != image or evidence["parent"] != PARENT_IMAGE:
        raise ValueError("layer evidence is not bound to this image and parent")
    verified = verify_binary_layer_entries(
        evidence["entries"], expected_sha=expected_sha or BINARY_SHA)
    return {"verified": True, "image": image, "parent": PARENT_IMAGE,
            "added_digest": evidence["added_digest"],
            "layer_id": evidence["layer_id"],
            "entries": evidence["entries"], "binary_contract": verified}


# Exact fields an operator slot must bind before every arm.
SLOT_BINDING_KEYS = ("source_commit", "image", "cases_sha256", "owner",
                     "evidence_root")


def verify_operator_slot(slot, *, path=SLOT_AUTH_PATH, wall=None, **bindings):
    """Require an exact, currently-valid slot bound to this specific arm.

    A slot is valid only for the exact source commit, candidate image digest,
    explicit case list hash and owner it was granted for, and only until its
    expiry. Callers must re-check before EACH arm so a stale/expired or
    different-target token cannot authorize another case.
    """
    if not isinstance(slot, str) or not slot or slot == PENDING_SLOT:
        raise ValueError("no operator slot granted")
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise ValueError("operator slot authorization missing")
    record = json.loads(target.read_text())
    if record.get("schema") != "ivanka.p1.operator-slot.v1":
        raise ValueError("unknown operator slot schema")
    if record.get("slot") != slot:
        raise ValueError("operator slot differs from granted slot")
    expiry = record.get("expires_utc")
    if (not isinstance(expiry, (int, float)) or not math.isfinite(expiry)
            or (wall or time.time)() > expiry):
        raise ValueError("operator slot expired")
    for key in SLOT_BINDING_KEYS:
        expected = bindings.get(key)
        if expected is None:
            raise ValueError(f"slot binding {key} was not supplied by caller")
        if record.get(key) != expected:
            raise ValueError(f"slot binding {key} differs from granted slot")
    return record


def slot_bindings(manifest, explicit_cases_sha):
    """Exact target identity a slot must be bound to for this pilot run."""
    return {"source_commit": manifest["candidate_source_commit"],
            "image": manifest["candidate_image"],
            "cases_sha256": explicit_cases_sha,
            "owner": manifest["owner"],
            "evidence_root": str(Path(manifest["paths"]["evidence_root"]).resolve())}


def claim_slot(out, slot, *, owner, cases_sha256, wall=None,
               evidence_root=None, auth_root=None):
    """Consume a slot GLOBALLY under the operator-owned auth root/lock.

    A marker under the caller's evidence root can be bypassed with a different
    ``--out``. Consumption therefore lives in the fixed operator auth root,
    protected by a real non-blocking flock, and binds the canonical evidence
    root and exact case list. The ledger and its parent directory are fsynced
    before any arm may proceed.
    """
    auth = Path(auth_root or SLOT_AUTH_ROOT)
    if auth.is_symlink():
        raise ValueError("operator auth root is a symlink")
    auth.mkdir(parents=True, exist_ok=True)
    lock_path = auth / SLOT_AUTH_LOCK.name
    if lock_path.is_symlink():
        raise ValueError("operator slot lock is a symlink")
    canonical_out = str(Path(out).resolve())
    if evidence_root is not None and canonical_out != str(Path(evidence_root).resolve()):
        raise ValueError("evidence root differs from the operator-bound slot root")
    digest = hashlib.sha256(slot.encode()).hexdigest()
    ledger = auth / SLOT_LEDGER_NAME
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if ledger.is_symlink():
            raise ValueError("slot ledger is a symlink")
        if ledger.is_file():
            for line in ledger.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    raise ValueError("corrupt slot ledger") from exc
                if row.get("slot_sha256") == digest:
                    raise ValueError("operator slot already consumed (replay refused)")
        event = {"schema": "ivanka.p1.slot-consumption.v1",
                 "slot_sha256": digest, "owner": str(owner),
                 "cases_sha256": cases_sha256, "evidence_root": canonical_out,
                 "at_utc": (wall or time.time)()}
        with ledger.open("a", buffering=1) as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # fsync the parent directory so the ledger entry itself is durable.
        dir_fd = os.open(auth, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return ledger
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def check_own_stop(stop_path, owner):
    """Read-only owner check; does not create or retire the STOP sentinel."""
    target = Path(stop_path)
    if target.is_symlink() or not target.is_file():
        return False
    return target.read_text().strip() == str(owner)


def require_live_watchdog_ready(path, graphroot, *, wall=None, snapshot=None):
    """Read-only LIVE watchdog readiness; a path alone is not readiness.

    Uses the guard contract with a real /proc snapshot and independently
    re-checks the immutable fingerprint of the live watchdog PID.
    """
    checker = snapshot or proc.snapshot
    target = Path(path)
    try:
        readiness = watchdog_contract.require_watchdog_readiness(
            target, graphroot=graphroot, wall=wall, snapshot=checker)
    except GuardExceeded as exc:
        raise ValueError(f"live watchdog readiness failed: {exc.reason}") from exc
    try:
        record = json.loads(target.read_text())
        live = checker().get(int(record["pid"]))
        if (live is None
                or tuple(record["fingerprint"]) != startup.stable_fingerprint(live)):
            raise ValueError("live watchdog identity mismatch")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"live watchdog identity unavailable: {exc}") from exc
    return readiness


def build_command(case_dir, output_dir, image, timer, container_name, cidfile):
    """Exact integrated MiCall command with a harness-pinned cidfile."""
    return [
        "podman", "run", "--pull=never", "--network=none",
        "--userns=host", "--cpus=2", "--memory=" + str(MEMORY_BYTES),
        "--name", container_name, "--cidfile", str(cidfile),
        "--timeout", str(PODMAN_TIMEOUT_SECONDS), "--stop-timeout", "2",
        "-v", str(Path(case_dir) / "reads") + ":/reads:ro",
        "-v", str(Path(output_dir)) + ":/results:rw",
        "-v", str(Path(timer)) + ":/ivanka-timer.py:ro",
        "--entrypoint", "/opt/venv/bin/python", image,
        "/ivanka-timer.py", "/results/timing.json",
        "micall", "analyze", "sample",
        "/reads/R1.fastq.gz", "/reads/R2.fastq.gz", "/results",
        "--denovo", "--keep_scratch", "--bad_cycles_csv",
        "/results/bad_cycles.csv", "--all_projects",
    ]


def wait_for_cidfile(cidfile, process, timeout=60, clock=time.monotonic,
                     sleep=time.sleep):
    """Block until Podman has written a valid CID or the spawn has failed."""
    deadline = clock() + timeout
    path = Path(cidfile)
    while clock() < deadline:
        if path.is_file() and not path.is_symlink():
            text = path.read_text().strip()
            if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
                return text
        if process.poll() is not None:
            if path.is_file() and not path.is_symlink():
                text = path.read_text().strip()
                if len(text) == 64 and all(c in "0123456789abcdef" for c in text):
                    return text
            raise RuntimeError("podman exited before cidfile was written")
        sleep(0.2)
    raise RuntimeError("cidfile was not written before spawn timeout")


class CaseExecution:
    """Mutable per-case holder shared by spawn/running/measure closures."""

    def __init__(self, command, env, log_path):
        self.command = list(command)
        self.env = dict(env)
        self.log_path = Path(log_path)
        self.process = None
        self.started = None
        self.log_handle = None

    def spawn(self, cidfile, env, timeout=60):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = self.log_path.open("wb")
        self.process = subprocess.Popen(
            self.command, env=self.env, stdout=self.log_handle,
            stderr=subprocess.STDOUT)
        self.started = time.monotonic()
        wait_for_cidfile(cidfile, self.process, timeout=timeout)
        return self.process

    def running(self):
        return self.process is not None and self.process.poll() is None

    def measure(self):
        # watch_bound samples tree RSS from the exact bound CID.
        return True

    def close(self):
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None


def _prepare_case_dir(destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"case directory already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "bad_cycles.csv").write_text("tile,cycle\n")
    return destination


def stage_physical_canary(destination, spec):
    """Stage attested physical reads into the same reference-blind contract."""
    r042 = spec["r042"]
    target = _prepare_case_dir(destination)
    (target / "reads").mkdir()
    staged = {}
    for key, name in (("r1_sha256", "R1.fastq.gz"), ("r2_sha256", "R2.fastq.gz")):
        source = Path(r042["reads_dir"]) / r042["r1" if name.startswith("R1") else "r2"]
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"physical canary read missing: {source}")
        if sha256(source) != r042[key]:
            raise ValueError(f"physical canary read pin differs: {source}")
        link = target / "reads" / name
        try:
            os.link(source, link)
        except OSError:
            link.write_bytes(source.read_bytes())
        staged["reads/" + name] = r042[key]
    manifest = {
        "schema": "ivanka.p1.physical-canary-case.v1",
        "id": "physical-canary-R042",
        "family": "physical",
        "hidden_truth_file": None,
        "score_model_revision": 2,
        "sha256": staged,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return target, staged


def score_case(case_dir, destination, record, image):
    """Post-hoc scoring only: hidden truth never enters the container argv."""
    manifest_data = json.loads((Path(case_dir) / "manifest.json").read_text())
    clock = json.loads((Path(destination) / "timing.json").read_text())
    if (clock.get("timing_origin") != TIMING_ORIGIN
            or clock.get("exit_code") != 0
            or not isinstance(clock.get("seconds"), (int, float))
            or not math.isfinite(clock["seconds"]) or clock["seconds"] <= 0):
        raise ValueError("invalid in-container timing")
    metrics = evaluate_final_alignment(
        manifest_data,
        Path(case_dir) / "hidden-truth/haplotypes.fasta",
        Path(destination))
    if metrics["score_origin"] != MULTITRUTH_SCORE_ORIGIN:
        raise ValueError("wrong final MiCall score origin")
    record.update(
        status="success", seconds=clock["seconds"], timing=clock,
        score=metrics["score"], dominant_exact=metrics["dominant_exact"],
        final_dominant=metrics["source"], per_truth=metrics["source"]["per_truth"],
        sha256=image,
    )
    return record


def _physical_result(destination, record, image):
    """Physical canary: attest timing + output hashes, never score with truth."""
    clock = json.loads((Path(destination) / "timing.json").read_text())
    if (clock.get("timing_origin") != TIMING_ORIGIN
            or clock.get("exit_code") != 0
            or not isinstance(clock.get("seconds"), (int, float))
            or not math.isfinite(clock["seconds"]) or clock["seconds"] <= 0):
        raise ValueError("invalid in-container timing")
    outputs = {}
    for path in sorted(Path(destination).glob("outcome*.json")):
        outputs[path.name] = sha256(path)
    record.update(status="success", seconds=clock["seconds"], timing=clock,
                  output_sha256=outputs, score=None, sha256=image,
                  truth_used_at_assembly_time=False)
    return record


def run_case(*, case_id, role, case_dir, destination, image, commit, timer,
             env, owner, lock_path, stop_path, lease_root, disk_path,
             watchdog_path, watchdog_graphroot, case_hashes=None,
             watchdog_ready=None, watchdog_snapshot=None, disk_usage=None,
             limit=MEMORY_BYTES, wall_seconds=WALL_CAP_SECONDS,
             deadline_utc=None, snapshot=None, clock=None, sleep=None,
             audit=None, bind_container=None, stop_cid_fn=None,
             spawn_timeout=60, physical=False):
    """Run one bounded case under the shared guard's real-heartbeat lifecycle."""
    case_dir = Path(case_dir)
    destination = Path(destination)
    manifest_data = json.loads((case_dir / "manifest.json").read_text())
    expected_hashes = case_hashes or manifest_data["sha256"]
    if manifest_data.get("sha256") != expected_hashes:
        raise ValueError("case manifest hash differs from frozen cohort")
    if manifest_data.get("score_model_revision") != 2:
        raise ValueError("case manifest differs from expected provenance")
    if not physical and manifest_data.get("hidden_truth_file") != (
            "hidden-truth/haplotypes.fasta"):
        raise ValueError("synthetic case hidden-truth provenance differs")
    hashes = verify_case_hashes(case_dir, expected_hashes)

    dest = _prepare_case_dir(destination)
    container_name = "ivanka-p1-pilot-" + hashlib.sha256(
        (case_id + ":" + image + ":" + str(dest)).encode()).hexdigest()[:18]
    cidfile_holder = {}

    def command_builder(cidfile):
        command = build_command(case_dir, dest, image, timer,
                                container_name, cidfile)
        assert_reference_blind(command)
        atomic_json(dest / "argv.json", command)
        return command

    execution = CaseExecution([], env, dest / "podman.log")

    def spawn(cidfile, spawn_env):
        cidfile_holder["path"] = cidfile
        command = command_builder(cidfile)
        execution.command = command
        execution.env = dict(spawn_env)
        execution.spawn(cidfile, spawn_env, timeout=spawn_timeout)

    # PR527 guard owns the real durable heartbeat (before_spawn / bound /
    # refresh). No caller-supplied heartbeat is passed or overridden here.
    guard_stop.arm(stop_path, owner)
    source_hashes = candidate_source_hashes(dest, hashes, image)

    record = {
        "status": "failed", "score": None,
        "score_origin": None if physical else MULTITRUTH_SCORE_ORIGIN,
        "timing_origin": TIMING_ORIGIN,
        "sha256": image, "container_name": container_name,
        "exit_code": None, "per_truth": {}, "diagnostics": {},
        "argv": None, "role": role,
        "truth_used_at_assembly_time": False,
    }

    guard_result = None
    try:
        guard_result = p1_harness.run_prospective(
            owner=owner, lease_root=lease_root, stop_path=stop_path,
            disk_path=disk_path, spawn=spawn, env=env, lock_path=lock_path,
            watchdog_ready=watchdog_ready, watchdog_path=watchdog_path,
            watchdog_graphroot=watchdog_graphroot,
            watchdog_snapshot=watchdog_snapshot,
            disk_reserve_bytes=PILOT_RESERVE_GIB * 1024 ** 3,
            disk_usage=disk_usage, limit=limit, wall_seconds=wall_seconds,
            deadline_utc=deadline_utc, running=execution.running,
            measure=execution.measure, snapshot=snapshot, clock=clock,
            sleep=sleep, audit=audit, bind_container=bind_container,
            stop_cid=stop_cid_fn)
        record["exit_code"] = (execution.process.returncode
                               if execution.process is not None else None)
        record["returncode"] = record["exit_code"]
        record["argv"] = execution.command
        guard_info = guard_result.get("result") or {}
        record["peak_sampled_rss_bytes"] = guard_info.get("peak_rss")
        record["rss_sample_scope"] = guard_info.get("rss_sample_scope")
        record["kernel_enforcement"] = guard_info.get("kernel_enforcement")
        record["teardown"] = guard_info.get("teardown")
        record["container_dead"] = True
        if physical:
            _physical_result(dest, record, image)
        else:
            score_case(case_dir, dest, record, image)
    except GuardExceeded as exc:
        record["error"] = exc.reason
        record["guard_error"] = exc.reason
        record["guard_teardown_error"] = exc.teardown_error
        record["guard_result"] = exc.guard_result
        if execution.process is not None:
            record["exit_code"] = execution.process.returncode
            record["returncode"] = execution.process.returncode
        record["argv"] = execution.command
        guard_result = {"status": "fail_closed", "reason": exc.reason,
                        "result": exc.guard_result, "teardown": exc.teardown}
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["argv"] = execution.command
        guard_result = {"status": "error", "reason": record["error"],
                        "result": None}
    finally:
        execution.close()

    if record.get("status") == "success":
        try:
            verify_case_hashes(case_dir, hashes)
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"post_score_input_drift:{exc}"
            record["score"] = None

    source_hashes = candidate_source_hashes(
        dest, hashes, image,
        {"podman.log": sha256(dest / "podman.log")}
        if (dest / "podman.log").is_file() else None)
    record["source_hashes"] = source_hashes
    try:
        record["diagnostics"] = (
            {"physical_canary": True} if physical else _public_diagnostics(dest))
    except Exception as exc:
        record["diagnostics"] = {"error": f"{type(exc).__name__}: {exc}"}

    row = {
        "schema": "ivanka.p1.bounded-pilot-case.v2",
        "status": STATUS,
        "case_id": case_id,
        "role": role,
        "candidate_source_commit": commit,
        "candidate_image": image,
        "input_sha256": input_fingerprint(hashes),
        "case_hashes": hashes,
        "result": record,
        "guard": {
            "status": (guard_result or {}).get("status"),
            "lease": (guard_result or {}).get("lease"),
            "deadline_utc": (guard_result or {}).get("deadline_utc"),
            "stop_retired_by": (guard_result or {}).get("stop_retired_by"),
            "teardown": ((guard_result or {}).get("result") or {}).get(
                "teardown") or (guard_result or {}).get("teardown"),
            "peak_rss": ((guard_result or {}).get("result") or {}).get(
                "peak_rss"),
            "rss_sample_scope": ((guard_result or {}).get("result") or {}).get(
                "rss_sample_scope"),
            "kernel_enforcement": ((guard_result or {}).get("result") or {}).get(
                "kernel_enforcement"),
            "heartbeat": "guard_owned_real_emitter",
        },
    }
    atomic_json(dest / "case.json", row)
    return row


def _public_diagnostics(dest):
    from benchmarks.assembler_bench.sam_metrics import public_diagnostics
    return public_diagnostics(dest)


def prepare(args, *, image_inspect=None, image_manifest=None,
            store_conf=None, disk_usage_fn=None, wall=None,
            postbuild_receipt_sha256=None, copy_overlay_root=None):
    """Read-only gate evaluation and durable prepared manifest, no spawn."""
    cases_manifest, cases_sha = load_case_manifest()
    image_doc, image_sha = load_image_manifest()
    selected = explicit_cases(cases_manifest)
    requested = tuple(args.cases.split(",")) if args.cases else selected
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("invalid or duplicate explicit case list")
    known = set(selected) | {cases_manifest["physical_canary"]["case_id"]}
    unknown = [case for case in requested if case not in known]
    if unknown:
        raise ValueError(f"unknown case(s): {', '.join(unknown)}")

    portable_postbuild = None
    contract_manifest = image_doc or image_manifest
    layer_expected_sha = None
    portable_plan = load_portable_plan()
    verify_portable_plan(portable_plan)
    portable_candidate = next(
        (row for row in portable_plan["candidates"]
         if row["source_commit"] == args.commit), None)
    if getattr(args, "portable_postbuild_receipt", None):
        receipt_sha = (postbuild_receipt_sha256 or
                       getattr(args, "portable_postbuild_receipt_sha256", None))
        if portable_candidate is None:
            raise ValueError("portable postbuild receipt source commit not planned")
        provisional = verify_portable_postbuild_receipt(
            args.portable_postbuild_receipt, expected_sha=receipt_sha,
            source_commit=args.commit, plan=portable_plan,
            root=copy_overlay_root)
        expected_image = (args.image
                          if args.image not in (None, "", "PENDING_CANDIDATE_IMAGE_DIGEST")
                          else provisional["image"])
        portable_postbuild = require_portable_image_identity_verified(
            args.commit, expected_image, plan=portable_plan,
            postbuild_receipt=args.portable_postbuild_receipt,
            postbuild_receipt_sha256=receipt_sha, root=copy_overlay_root)
        if (args.image not in (None, "", "PENDING_CANDIDATE_IMAGE_DIGEST")
                and normalize_digest(args.image) != portable_postbuild["image"]):
            raise ValueError("portable postbuild receipt image differs from --image")
        # The exact per-role contract pins the PORTABLE binary SHA and this
        # candidate's own source commit; the native image manifest would
        # reject the PCR source and expect the native SHA.
        contract_manifest = portable_image_contract(portable_candidate)
        layer_expected_sha = portable_candidate["portable_binary_sha256"]
        args = argparse.Namespace(**{**vars(args),
                                     "image": portable_postbuild["image"],
                                     "commit": portable_postbuild["source_commit"]})
    elif (portable_candidate is not None
          and portable_candidate.get("portable_binary_sha256") is not None):
        raise ValueError("portable postbuild receipt required for produced portable candidate")

    verify_pins(Path(args.data), Path(args.frozen_results), Path(args.timer))
    guard_pins = verify_guard_source_pins()
    admission_pins = verify_copy_overlay_admission_pins()
    store = verify_px_store_binding(
        store_conf or args.storage_conf, expected_sha=PINS_V2["storage_conf"])
    shared = verify_shared_px_boundary(
        lock=args.lock, lease_root=args.lease_root,
        watchdog_path=args.watchdog_path,
        storage_conf=store_conf or args.storage_conf,
        graphroot=store["graphroot"])
    verified_env = pinned_podman_env(store["storage_conf"])
    contract = verify_image_contract(
        args.image, args.commit, env=verified_env,
        inspect=image_inspect, image_manifest=contract_manifest)
    layer = verify_image_layer_contract(
        args.image, env=verified_env, inspect=image_inspect,
        graphroot=store["graphroot"], expected_sha=layer_expected_sha)

    free = (disk_usage_fn or _disk_free)(args.disk_path)
    if free < PILOT_REQUIRED_FREE_BYTES:
        raise ValueError(
            f"disk admission: {free} free < {PILOT_REQUIRED_FREE_BYTES} required")

    owner = args.owner or f"p1-pilot:{os.getpid()}"
    manifest = {
        "schema": SCHEMA,
        "status": STATUS,
        "qualified": False,
        "guard_status": "NO-GO pending independent reviewer approval and operator slot",
        "integration_base": INTEGRATION_BASE,
        "reviewed_guard_pins": guard_pins,
        "copy_overlay_admission_pins": admission_pins,
        "portable_postbuild_receipt": portable_postbuild,
        "candidate_source_commit": args.commit,
        "candidate_image": args.image,
        "candidate_portable_role": (portable_candidate["role"]
                                    if portable_postbuild else None),
        "candidate_image_contract": contract,
        "added_layer_evidence": layer,
        "cases_manifest_sha256": cases_sha,
        "image_manifest_sha256": image_sha,
        "storage": store,
        "shared_px_boundary": shared,
        "watchdog": {
            "path": str(args.watchdog_path),
            "graphroot": store["graphroot"],
            "graphroot_source": "shared PX storage.conf (match by construction)",
        },
        "disk_admission": {
            "reserve_gib": PILOT_RESERVE_GIB,
            "reservation_gib": PILOT_RESERVATION_GIB,
            "required_free_bytes": PILOT_REQUIRED_FREE_BYTES,
            "observed_free_bytes": int(free),
        },
        "limits": {
            "wall_seconds": WALL_CAP_SECONDS,
            "memory_bytes": MEMORY_BYTES,
            "podman_timeout_seconds": PODMAN_TIMEOUT_SECONDS,
            "reserve_gib": RESERVE_GIB,
            "admission_gib": ADMISSION_GIB,
        },
        "paths": {
            "lock": str(args.lock), "stop": str(args.stop),
            "lease_root": str(args.lease_root), "disk_path": str(args.disk_path),
            "evidence_root": str(args.out), "slot_auth": str(SLOT_AUTH_PATH),
        },
        "owner": owner,
        "explicit_case_list": list(requested),
        "design": {
            "residual": list(cases_manifest["residual_cases"]),
            "control": list(cases_manifest["control_cases"]),
            "physical_canary": cases_manifest["physical_canary"]["case_id"],
        },
        "no_full464_rerun": True,
        "truth_used_at_assembly_time": False,
        "heartbeat": "shared guard real durable heartbeat (not caller injected)",
        "spawned": False,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    atomic_json(out / "prepared_manifest.json", manifest)
    return manifest


def _disk_free(path):
    import shutil
    return shutil.disk_usage(str(path)).free


def verify_pins(data, frozen_path, timer):
    """Fail closed if any frozen input/score pin differs."""
    for path, pin in ((Path(data) / "cohort.json", PINS["cohort.json"]),
                      (Path(frozen_path), PINS["phase-synthetic464/results.jsonl"]),
                      (Path(timer), PINS["inside_container_timing.py"])):
        if sha256(path) != pin:
            raise ValueError(f"source hash gate failed for {path}")
    return True


def load_case_hashes(data, frozen_path):
    cohort = json.loads((Path(data) / "cohort.json").read_text())
    case_hashes = {entry["id"]: entry["sha256"] for entry in cohort["cases"]}
    frozen, frozen_hash = load_frozen(
        Path(frozen_path), PINS["phase-synthetic464/results.jsonl"], case_hashes)
    return case_hashes, frozen, frozen_hash


def run(args, *, env=None, image_inspect=None, image_manifest=None,
        store_conf=None, watchdog_ready=None, watchdog_snapshot=None,
        snapshot=None, clock=None, sleep=None, audit=None, disk_usage=None,
        disk_usage_fn=None, bind_container=None, stop_cid_fn=None,
        wall=None, live_watchdog_check=None, postbuild_receipt_sha256=None,
        copy_overlay_root=None):
    manifest = prepare(args, image_inspect=image_inspect,
                       image_manifest=image_manifest, store_conf=store_conf,
                       disk_usage_fn=disk_usage_fn, wall=wall,
                       postbuild_receipt_sha256=postbuild_receipt_sha256,
                       copy_overlay_root=copy_overlay_root)
    # --check must prove a LIVE, identity-bound watchdog, not merely a path.
    (live_watchdog_check or require_live_watchdog_ready)(
        args.watchdog_path, manifest["storage"]["graphroot"], wall=wall)
    out = Path(args.out)
    # Build the arm environment from the VERIFIED manifest path, never from
    # args.storage_conf (which was not proven by the store pin) or ambient env.
    if env is None:
        env = pinned_podman_env(manifest["storage"]["storage_conf"])
    else:
        env = dict(env)
        stray = [key for key in env if key.startswith("CONTAINERS_")
                 and key != "CONTAINERS_STORAGE_CONF"]
        if stray:
            raise ValueError("ambient container selector in caller env: "
                             + ", ".join(sorted(stray)))
        if env.get("CONTAINERS_STORAGE_CONF") != manifest["storage"]["storage_conf"]:
            raise ValueError("caller env store selector differs from verified manifest")
    summary = {
        "schema": SCHEMA, "status": STATUS, "qualified": False,
        "guard_status": manifest["guard_status"],
        "prepared_manifest_sha256": sha256(out / "prepared_manifest.json"),
        "spawned": False,
    }
    # Check-only is the default-preparation path: no STOP, no lease, no spawn.
    if args.check:
        atomic_json(out / "check_summary.json", summary)
        return summary

    explicit_cases_sha = hashlib.sha256(json.dumps(
        manifest["explicit_case_list"], sort_keys=True).encode()).hexdigest()
    bindings = slot_bindings(manifest, explicit_cases_sha)
    # Bind the operator slot to the post-build identity that verification
    # actually observed, never to a placeholder or an invented digest.
    bindings["image"] = manifest["candidate_image_contract"].get(
        "image_digest", manifest["candidate_image"])
    slot = verify_operator_slot(args.slot, wall=wall, **bindings)
    if not args.armed:
        raise ValueError("--armed required to spawn; source-only until slot granted")
    if not manifest.get("shared_px_boundary", {}).get("shared"):
        raise ValueError("shared PX worker boundary not proven at preparation")
    if (args.lock != SHARED_PX_BOUNDARY["global_lock"]
            or args.lease_root != SHARED_PX_BOUNDARY["lease_root"]):
        raise ValueError("execution must use the shared PX lock and lease root")
    if manifest["paths"]["stop"] != DEFAULT_STOP:
        raise ValueError("pilot must use its own owner-bound STOP")
    summary["slot"] = slot["slot"]
    claim_slot(out, args.slot, owner=manifest["owner"],
               cases_sha256=explicit_cases_sha, wall=wall,
               evidence_root=bindings["evidence_root"])

    case_hashes, _frozen, frozen_hash = load_case_hashes(args.data,
                                                          args.frozen_results)
    cases_doc, _cases_sha = load_case_manifest()
    role_by_id = {}
    for cid in cases_doc["residual_cases"]:
        role_by_id[cid] = "residual"
    for cid in cases_doc["control_cases"]:
        role_by_id[cid] = "control"
    canary = cases_doc["physical_canary"]
    role_by_id[canary["case_id"]] = "physical_canary"

    owner = manifest["owner"]
    results_path = out / "results.jsonl"
    completed = []
    for case_id in manifest["explicit_case_list"]:
        # Re-check expiry AND exact target binding before EVERY arm; a slot
        # that expired or was re-targeted mid-run cannot authorize this case.
        verify_operator_slot(args.slot, wall=wall, **bindings)
        physical = case_id == canary["case_id"]
        if physical:
            spec, _ = load_pinned_json(
                canary["spec_path"], PINS_V2["physical_spec"], label="physical spec")
            case_dir, hashes = stage_physical_canary(out / case_id, spec)
        else:
            case_dir = Path(args.data) / case_id
            hashes = case_hashes[case_id]
            verify_case_hashes(case_dir, hashes)
        row = run_case(
            case_id=case_id, role=role_by_id[case_id], case_dir=case_dir,
            destination=out / case_id, image=manifest["candidate_image"],
            commit=manifest["candidate_source_commit"],
            timer=args.timer, env=env, owner=owner, lock_path=args.lock,
            stop_path=args.stop, lease_root=args.lease_root,
            disk_path=str(args.disk_path), watchdog_path=args.watchdog_path,
            watchdog_graphroot=manifest["storage"]["graphroot"],
            case_hashes=hashes, watchdog_ready=watchdog_ready,
            watchdog_snapshot=watchdog_snapshot, disk_usage=disk_usage,
            snapshot=snapshot, clock=clock, sleep=sleep, audit=audit,
            bind_container=bind_container, stop_cid_fn=stop_cid_fn,
            physical=physical)
        atomic_append(results_path, row)
        completed.append(row)
        print("P1_PILOT_CASE", case_id, role_by_id[case_id],
              row["result"]["status"], row["result"].get("error", ""), flush=True)
        if row["result"]["status"] != "success":
            break
        # Physical canary runs last, after a fresh 32+1 GiB disk admission.
        if physical:
            free = (disk_usage_fn or _disk_free)(args.disk_path)
            if free < PILOT_REQUIRED_FREE_BYTES:
                raise ValueError("post-canary disk admission shortfall")

    summary.update(
        spawned=True,
        cases_selected=list(manifest["explicit_case_list"]),
        cases_completed=[row["case_id"] for row in completed],
        cases_succeeded=[row["case_id"] for row in completed
                         if row["result"]["status"] == "success"],
        all_succeeded=all(row["result"]["status"] == "success"
                          for row in completed)
        and len(completed) == len(manifest["explicit_case_list"]),
        frozen_results_sha256=frozen_hash,
    )
    atomic_json(out / "summary.json", summary)
    print("P1_BOUNDED_PILOT", STATUS, "cases", len(completed),
          "all_succeeded", summary["all_succeeded"], flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(DEFAULT_DATA))
    parser.add_argument("--frozen-results", type=Path, default=Path(DEFAULT_FROZEN))
    parser.add_argument("--timer", type=Path, default=Path(DEFAULT_TIMER))
    parser.add_argument("--out", type=Path, default=Path(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--image", default="PENDING_CANDIDATE_IMAGE_DIGEST")
    parser.add_argument("--commit", default=SOURCE_COMMIT)
    parser.add_argument("--portable-postbuild-receipt", type=Path, default=None,
                        help="SHA-pinned postbuild receipt for a portable COPY-only build")
    parser.add_argument("--portable-postbuild-receipt-sha256", default=None,
                        help="required SHA-256 pin of --portable-postbuild-receipt")
    parser.add_argument("--storage-conf", type=Path, default=Path(DEFAULT_STORAGE_CONF))
    parser.add_argument("--lock", default=DEFAULT_LOCK)
    parser.add_argument("--stop", default=DEFAULT_STOP)
    parser.add_argument("--lease-root", default=DEFAULT_LEASE_ROOT)
    parser.add_argument("--disk-path", type=Path, default=Path("/workspace"))
    parser.add_argument("--watchdog-path", type=Path, required=True)
    parser.add_argument("--owner", default=None)
    parser.add_argument("--cases", help="comma-separated explicit case IDs")
    parser.add_argument("--check", action="store_true",
                        help="read-only preparation; no STOP, lease or spawn")
    parser.add_argument("--armed", action="store_true",
                        help="required together with an exact operator slot")
    parser.add_argument("--slot", default=PENDING_SLOT,
                        help="exact operator-granted slot token")
    args = parser.parse_args(argv)
    if not args.check and (not args.armed or args.slot == PENDING_SLOT):
        parser.error("execution requires --armed --slot <operator slot>; use --check to prepare")
    try:
        summary = run(args,
                      postbuild_receipt_sha256=args.portable_postbuild_receipt_sha256)
    except ValueError as exc:
        parser.error(f"gate failed closed: {exc}")
    return 0 if (args.check or summary["all_succeeded"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
