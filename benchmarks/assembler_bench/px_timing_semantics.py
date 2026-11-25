"""Comparable in-container runtime for PX arms.

A launcher's wall clock includes Podman startup, image setup and teardown, so
it is not the MiCall runtime that other Assembler Bench arms publish. The
container's timer writes a monotonic in-container duration together with its
origin. That reading becomes comparable only when its exact timer source, its
origin, its version and the digest of its timing record are sealed in the
immutable, index-bound case receipt. Legacy receipts carry an unlabeled
``seconds`` value and keep publishing null runtime.
"""
import hashlib
import json
import math
import re
from pathlib import Path

ORIGIN = "micall_in_container_monotonic_v1"
METHOD_VERSION = "ivanka.px.in-container-runtime.v1"
# Exact bytes of benchmarks/inside_container_timing.py mounted into the run.
TIMER_SOURCE_SHA256 = (
    "c5baab15b8c54f27b5cfbaf459f8647707e1e9618577b803ee3440e3e661eb4e")
LEGACY_ORIGIN = "guarded_launcher_total_wall_with_podman_cleanup_v1"

ORIGIN_KEY = "timing_origin"
VERSION_KEY = "timing_method_version"
TIMER_KEY = "timer_source_sha256"
FILE_KEY = "timing_file_sha256"
RUNTIME_KEY = "runtime_seconds"
LAUNCHER_KEY = "launcher_seconds"
PROOF_KEYS = (ORIGIN_KEY, VERSION_KEY, TIMER_KEY, FILE_KEY)
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def sha256_bytes(data):
    """Hash the exact bytes of a timing record, never a re-serialization."""
    return hashlib.sha256(data).hexdigest()


def timer_is_pinned(path):
    """Verify the exact timer source that the launcher mounts in-container."""
    target = Path(path)
    if not target.is_file():
        return False
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == TIMER_SOURCE_SHA256


def _seconds(value):
    """Accept only a genuine finite, positive duration."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def parse_clock(blob):
    """Validate one timer record and return ``(seconds, sealed proof)``.

    A wrong origin, a nonzero MiCall exit or an implausible duration makes the
    record unusable for a comparable runtime, regardless of what it reports.
    """
    try:
        clock = json.loads(blob)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(clock, dict) or clock.get(ORIGIN_KEY) != ORIGIN:
        return None
    status = clock.get("exit_code")
    if isinstance(status, bool) or not isinstance(status, int) or status != 0:
        return None
    seconds = _seconds(clock.get("seconds"))
    if seconds is None:
        return None
    proof = {
        ORIGIN_KEY: ORIGIN,
        VERSION_KEY: METHOD_VERSION,
        TIMER_KEY: TIMER_SOURCE_SHA256,
        FILE_KEY: sha256_bytes(blob),
    }
    return seconds, proof


def attested(record):
    """Return whether a record carries the complete, pinned timing proof."""
    if not isinstance(record, dict):
        return False
    return (record.get(ORIGIN_KEY) == ORIGIN
            and record.get(VERSION_KEY) == METHOD_VERSION
            and record.get(TIMER_KEY) == TIMER_SOURCE_SHA256
            and isinstance(record.get(FILE_KEY), str)
            and SHA256.fullmatch(record[FILE_KEY]) is not None)


def has_proof_keys(record):
    """Detect partial PX timing labels that must never imply comparability.

    The legacy launcher label is not a partial PX proof: it is an unrelated
    diagnostic origin and stays valid on historical evidence rows.
    """
    if not isinstance(record, dict):
        return False
    return (record.get(ORIGIN_KEY) == ORIGIN
            or any(key in record for key in (VERSION_KEY, TIMER_KEY, FILE_KEY)))


def timing_fields(source):
    """Copy a complete timing proof from runner evidence into a receipt."""
    if not isinstance(source, dict):
        return {}
    fields = {key: source[key] for key in PROOF_KEYS if key in source}
    return fields if attested(fields) else {}


def comparable_seconds(record):
    """Return published runtime only from a complete, immutable timing proof.

    Receipts keep the value in ``seconds``; public case evidence keeps it in
    ``runtime_seconds`` so a legacy launcher reading is never reinterpreted.
    """
    if not attested(record):
        return None
    return _seconds(record.get(RUNTIME_KEY, record.get("seconds")))


def normalize_case(case, receipt=None):
    """Withdraw runtime published without the case's bound timing proof."""
    if attested(receipt) and comparable_seconds(receipt) is not None:
        return
    if RUNTIME_KEY in case:
        case[RUNTIME_KEY] = None
    for key in PROOF_KEYS:
        # A legacy/unavailable origin is a diagnostic label, not a partial
        # in-container proof. Keep it so repeat ingestion reproduces the
        # same provenance; a genuine proof label is still withdrawn when it
        # is not bound to an attested receipt.
        if key == ORIGIN_KEY and case.get(ORIGIN_KEY) == LEGACY_ORIGIN:
            continue
        case.pop(key, None)
