"""Fail-closed command validation and attempt lifecycle for the narrow canary.

This module is a *source-only* repair of the guarded-canary launcher integration
that failed its prelaunch gate on 2026-11-24 (board finding 23:39Z).  It does not
change the candidate source, its image, any frozen/sealed root, or any live
service; it is meant to be adopted by the owner of the guarded canary.

Failure modes repaired here
---------------------------

1. Loose ``".fa" in argv`` reference blindness rejected the legitimate paired
   reads (``/reads/R1.fastq.gz``) because ``".fa"`` is a substring of
   ``".fastq.gz"``.  Validation is now an exact allowlist: FASTA references are
   recognised by an explicit *suffix* on the basename, never by a substring.
2. A failed attempt created the case folder before validation, so a service
   restart hit "refusing to overwrite existing case folder" and left an empty
   result.  Each launch now owns a unique, exclusively created attempt
   namespace; prior evidence is never truncated or overwritten.
3. An unbounded restart/retry loop could storm the host.  Retries are a bounded
   budget with an append-only, fsynced audit and fail closed on exhaustion.

Nothing here evaluates scientific scores or makes a qualification claim.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import secrets
import tempfile
import time
from dataclasses import dataclass

Path = pathlib.Path

# Exact bind targets.  Any other target (including a second /reads mount) is
# rejected; the sources must equal the three pinned inputs supplied by caller.
ALLOWED_MOUNT_TARGETS = frozenset(
    {"/reads:ro", "/results:rw", "/ivanka-timer.py:ro"})
# A FASTA reference is identified by a basename suffix, never a substring:
# ".fastq.gz" intentionally does NOT appear here.
FASTA_SUFFIXES = (".fa", ".fasta", ".fna", ".fas", ".faf", ".mpfa")
FORBIDDEN_PATH_COMPONENTS = frozenset(
    {"hidden-truth", "haplotypes.fasta", "reference", "truth", "panel", "hxb2"})
MICALL_TAIL = (
    "/ivanka-timer.py", "/results/timing.json", "micall", "analyze", "sample",
    "/reads/R1.fastq.gz", "/reads/R2.fastq.gz", "/results", "--denovo",
    "--keep_scratch", "--bad_cycles_csv", "/results/bad_cycles.csv",
    "--all_projects",
)
# Exact argv shape before the MiCall tail; ``None`` marks a caller-pinned value
# that is validated separately (paths, digest, name, numeric limits).
EXPECTED_ARGV_PREFIX = (
    "podman", "--root", None, "--runroot", None, "run", "--pull=never",
    "--network=none", "--userns=host", "--cidfile", None, "--name", None,
    None, None, "--timeout", None, "--entrypoint", "/opt/venv/bin/python", None,
)
BAD_CYCLES_HEADER = b"tile,cycle\n"
SAFE_CASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$")
ALLOWED_RECEIPT_STATUSES = frozenset({"attempted", "failed", "success"})
RECEIPT_FIELDS = frozenset({
    "schema", "case", "attempt_id", "status", "qualification_claim",
    "argv_sha256", "bad_cycles_sha256", "guard_bounds",
})
MAX_ATTEMPT_SUFFIX = 1000
MAX_PID = 4_194_303
MAX_RETRY_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 5.0

SCHEMA_ATTEMPT = "ivanka.guarded-canary.attempt.v1"
SCHEMA_LOG = "ivanka.guarded-canary.log.v1"
SCHEMA_RECEIPT = "ivanka.guarded-canary.receipt.v1"


class LauncherError(ValueError):
    """Base class for fail-closed launcher rejections."""


class ReferenceLeak(LauncherError):
    """An argv/mount token could admit truth or reference data."""


class UnsafeCommand(LauncherError):
    """The command is not the exact allowlisted launcher contract."""


class AttemptCollision(LauncherError):
    """An attempt namespace cannot be created without overwriting evidence."""


class RetryExhausted(LauncherError):
    """A bounded retry budget was consumed without success."""


@dataclass(frozen=True)
class GuardBounds:
    """Hard, explicit ceilings for the bounded guard; never inferred at runtime."""

    rss_limit_bytes: int = 4_000_000_000
    wall_seconds: int = 2400
    cid_bind_timeout_seconds: int = 30
    max_retry_attempts: int = 1

    def validate(self) -> "GuardBounds":
        checks = (
            ("rss_limit_bytes", self.rss_limit_bytes, 1, 4_000_000_000),
            ("wall_seconds", self.wall_seconds, 1, 2400),
            ("cid_bind_timeout_seconds", self.cid_bind_timeout_seconds, 1, 60),
            ("max_retry_attempts", self.max_retry_attempts, 0, MAX_RETRY_ATTEMPTS),
        )
        for name, value, low, high in checks:
            if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                raise UnsafeCommand(f"guard bound {name} outside [{low}, {high}]: {value!r}")
        return self


STRICT_GUARD = GuardBounds()


@dataclass(frozen=True)
class RetryBudget:
    """A bounded, auditable retry allowance. Default: no retries at all."""

    max_attempts: int = 1
    delay_seconds: float = 0.0

    def validate(self) -> "RetryBudget":
        if (not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool)
                or not 1 <= self.max_attempts <= MAX_RETRY_ATTEMPTS):
            raise UnsafeCommand(f"retry attempts must be 1..{MAX_RETRY_ATTEMPTS}")
        if (not isinstance(self.delay_seconds, (int, float))
                or isinstance(self.delay_seconds, bool)
                or not 0.0 <= self.delay_seconds <= MAX_RETRY_DELAY_SECONDS):
            raise UnsafeCommand("retry delay outside [0, 5] seconds")
        return self


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: os.PathLike[str] | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_fasta_token(token: str) -> bool:
    """Explicit basename-suffix FASTA test (never a substring of '.fastq.gz')."""
    name = token.rsplit("/", 1)[-1].lower()
    return name.endswith(FASTA_SUFFIXES)


def _mount(token: str) -> tuple[str, str, str]:
    parts = token.rsplit(":", 2)
    if len(parts) != 3 or not all(parts):
        raise UnsafeCommand(f"mount is not src:dst:mode: {token}")
    source, target, mode = parts
    return source, f"{target}:{mode}", mode


def _validate_bounded_number(token: str, prefix: str, low: int, high: int, label: str) -> int:
    """Parse an exact numeric flag and enforce its hard bound in the validator."""
    if not token.startswith(prefix):
        raise UnsafeCommand(f"{label} is not the exact {prefix} flag")
    value = token[len(prefix):]
    if not re.fullmatch(r"[0-9]+", value):
        raise UnsafeCommand(f"{label} is not a non-negative integer: {value!r}")
    number = int(value)
    if not low <= number <= high:
        raise UnsafeCommand(f"{label} outside [{low}, {high}]: {number}")
    return number


def assert_reference_blind(argv, *, allowed_values, expected_sources):
    """Validate an *exact* allowlisted command; fail closed on anything else.

    ``allowed_values`` is the exact set of non-mount tokens the caller built;
    ``expected_sources`` is the exact set of three resolved bind sources.  A
    FASTA reference cannot be confused with FASTQ input because the check uses
    basename suffixes, not the loose ``".fa"`` substring.
    """
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(a, str) for a in argv):
        raise UnsafeCommand("command must be a non-empty list of strings")
    if not isinstance(allowed_values, (set, frozenset)) or not isinstance(expected_sources, (set, frozenset)):
        raise UnsafeCommand("allowlists must be sets")

    mounts: list[str] = []
    non_mount: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "-v":
            if index + 1 >= len(argv):
                raise UnsafeCommand("-v without a mount")
            mounts.append(argv[index + 1])
            index += 2
            continue
        non_mount.append(token)
        index += 1

    if len(mounts) != len(ALLOWED_MOUNT_TARGETS):
        raise UnsafeCommand(f"expected exactly 3 mounts, got {len(mounts)}")
    seen_targets: set[str] = set()
    seen_sources: set[str] = set()
    for mount in mounts:
        source, target, mode = _mount(mount)
        if target not in ALLOWED_MOUNT_TARGETS or target in seen_targets:
            raise UnsafeCommand(f"unexpected or duplicate mount target: {target}")
        if mode not in ("ro", "rw"):
            raise UnsafeCommand(f"unexpected mount mode: {mode}")
        if source not in expected_sources or source in seen_sources:
            raise UnsafeCommand(f"unexpected or duplicate mount source: {source}")
        seen_targets.add(target)
        seen_sources.add(source)
    if seen_targets != ALLOWED_MOUNT_TARGETS or seen_sources != set(expected_sources):
        raise UnsafeCommand("mount allowlist not satisfied exactly")

    for token in non_mount:
        if token not in allowed_values:
            raise UnsafeCommand(f"argv token outside allowlist: {token}")
        if _is_fasta_token(token) or any(
                part in FORBIDDEN_PATH_COMPONENTS for part in token.split("/")):
            raise ReferenceLeak(f"reference/truth reached the assembler argv: {token}")

    if len(non_mount) != len(EXPECTED_ARGV_PREFIX) + len(MICALL_TAIL):
        raise UnsafeCommand("argv length differs from exact guarded launcher contract")
    for position, (expected, token) in enumerate(zip(EXPECTED_ARGV_PREFIX, non_mount)):
        if expected is not None and token != expected:
            raise UnsafeCommand(f"argv token {position} differs from exact contract")
    _validate_bounded_number(non_mount[13], "--cpus=", 1, 32, "cpu limit")
    _validate_bounded_number(non_mount[14], "--memory=", 1, 4_000_000_000, "memory limit")
    _validate_bounded_number("--timeout=" + non_mount[16], "--timeout=", 1, 2400, "timeout")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", non_mount[19]):
        raise UnsafeCommand("image is not an exact sha256 digest")
    tail = tuple(non_mount[-len(MICALL_TAIL):])
    if tail != MICALL_TAIL:
        raise UnsafeCommand("integrated MiCall tail differs from exact contract")
    return True


def build_command(
    *,
    image: str,
    reads_dir: os.PathLike[str] | str,
    attempt_dir: os.PathLike[str] | str,
    timer: os.PathLike[str] | str,
    cidfile: os.PathLike[str] | str,
    storage_root: os.PathLike[str] | str,
    runroot: os.PathLike[str] | str,
    name: str,
    cpus: int = 2,
    memory_bytes: int = 4_000_000_000,
    timeout: int = 2398,
) -> list[str]:
    """Build the exact guarded Podman+MiCall argv, then validate it closed."""
    for label, value, high in (("cpus", cpus, 32), ("timeout", timeout, 2400)):
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= high:
            raise UnsafeCommand(f"{label} outside [1, {high}]: {value!r}")
    if (not isinstance(memory_bytes, int) or isinstance(memory_bytes, bool)
            or not 1 <= memory_bytes <= 4_000_000_000):
        raise UnsafeCommand(f"memory_bytes outside [1, 4000000000]: {memory_bytes!r}")
    if not re.fullmatch(r"podman-name-[A-Za-z0-9_.-]{1,64}", name):
        raise UnsafeCommand(f"unsafe container name: {name!r}")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise UnsafeCommand("candidate image must be an exact sha256 digest")

    reads_source = str(Path(reads_dir).resolve())
    results_source = str(Path(attempt_dir).resolve())
    timer_source = str(Path(timer).resolve())
    mounts = [
        f"{reads_source}:/reads:ro",
        f"{results_source}:/results:rw",
        f"{timer_source}:/ivanka-timer.py:ro",
    ]
    argv = [
        "podman", "--root", str(Path(storage_root).resolve()),
        "--runroot", str(Path(runroot).resolve()), "run", "--pull=never",
        "--network=none", "--userns=host", "--cidfile", str(Path(cidfile)),
        "--name", name, f"--cpus={cpus}", f"--memory={memory_bytes}",
        "--timeout", str(timeout),
    ]
    for mount in mounts:
        argv.extend(("-v", mount))
    argv.extend(("--entrypoint", "/opt/venv/bin/python", image))
    argv.extend(MICALL_TAIL)
    allowed_values = frozenset(
        value for value in argv if value not in mounts) | frozenset({"podman"})
    assert_reference_blind(
        argv, allowed_values=allowed_values,
        expected_sources=frozenset({reads_source, results_source, timer_source}))
    return argv


def _unique_attempt_path(root, case: str, stamp: str, pid: int, token: str,
                         max_suffix: int) -> Path:
    if not SAFE_CASE.fullmatch(case):
        raise UnsafeCommand(f"unsafe case identifier: {case!r}")
    if not re.fullmatch(r"[0-9a-f]{12}", token):
        raise UnsafeCommand("attempt token must be 12 lowercase hex chars")
    base = Path(root).resolve() / "attempts" / case / f"{stamp}-p{pid}-{token}"
    for suffix in range(max_suffix + 1):
        candidate = base if suffix == 0 else Path(f"{base}-{suffix:03d}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise AttemptCollision(f"attempt namespace exhausted for {base}")


def new_attempt(root, case: str, *, stamp: str | None = None, pid: int | None = None,
                token: str | None = None, max_suffix: int = MAX_ATTEMPT_SUFFIX) -> Path:
    """Exclusively create a unique attempt namespace; never overwrite evidence."""
    if not isinstance(max_suffix, int) or isinstance(max_suffix, bool) \
            or not 1 <= max_suffix <= MAX_ATTEMPT_SUFFIX:
        raise UnsafeCommand(f"max_suffix outside [1, {MAX_ATTEMPT_SUFFIX}]")
    pid = os.getpid() if pid is None else pid
    if not isinstance(pid, int) or isinstance(pid, bool) or not 0 <= pid <= MAX_PID:
        raise UnsafeCommand(f"pid must be an int in [0, {MAX_PID}]: {pid!r}")
    if stamp is None:
        now = datetime.datetime.now(datetime.timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond:06d}Z"
    if not isinstance(stamp, str) or not re.fullmatch(r"\d{8}T\d{12}Z", stamp):
        raise UnsafeCommand("stamp must be YYYYmmddTHHMMSSffffffZ")
    token = secrets.token_hex(6) if token is None else token
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{12}", token):
        raise UnsafeCommand("attempt token must be 12 lowercase hex chars")
    for label, value in (("case", case), ("stamp", stamp), ("token", token)):
        if "/" in value or ".." in value:
            raise UnsafeCommand(f"{label} contains a path escape: {value!r}")
    return _unique_attempt_path(root, case, stamp, pid, token, max_suffix)


class AppendOnlyLog:
    """Append-only, fsynced JSONL durable log in an attempt namespace."""

    def __init__(self, path: os.PathLike[str] | str):
        self.path = Path(path)
        self._stream = self.path.open("a", encoding="utf-8")

    def append(self, record: dict) -> dict:
        payload = dict(record, schema=SCHEMA_LOG)
        self._stream.write(json.dumps(payload, sort_keys=True) + "\n")
        self._stream.flush()
        os.fsync(self._stream.fileno())
        return payload

    def records(self) -> list[dict]:
        with self.path.open("r", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def close(self) -> None:
        self._stream.close()

    def __enter__(self) -> "AppendOnlyLog":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def run_bounded(function, budget: RetryBudget, log: AppendOnlyLog, *, attempt_id: str):
    """Call ``function`` at most ``budget.max_attempts`` times; fail closed."""
    budget.validate()
    last_error = None
    for attempt in range(1, budget.max_attempts + 1):
        log.append({"attempt_id": attempt_id, "attempt": attempt,
                    "max_attempts": budget.max_attempts, "event": "start"})
        try:
            result = function()
            log.append({"attempt_id": attempt_id, "attempt": attempt, "event": "success"})
            return result
        except Exception as exc:  # noqa: BLE001 - audited, then re-raised closed
            last_error = exc
            log.append({"attempt_id": attempt_id, "attempt": attempt,
                        "event": "failure", "error": f"{type(exc).__name__}: {exc}"})
            if attempt < budget.max_attempts and budget.delay_seconds:
                time.sleep(budget.delay_seconds)
    raise RetryExhausted(
        f"attempt {attempt_id} failed after {budget.max_attempts} bounded attempt(s): {last_error}")


def setup_bad_cycles(attempt: os.PathLike[str] | str) -> Path:
    """Exclusively create the exact bad_cycles seed; never overwrite it."""
    path = Path(attempt) / "bad_cycles.csv"
    with path.open("xb") as stream:
        stream.write(BAD_CYCLES_HEADER)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def verify_bad_cycles(path: os.PathLike[str] | str) -> bool:
    with open(path, "rb") as stream:
        data = stream.read()
    if data != BAD_CYCLES_HEADER:
        raise UnsafeCommand("bad_cycles.csv does not match the exact seed header")
    return True


def _atomic_json(path: Path, payload: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".receipt-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_receipt(attempt, *, case: str, attempt_id: str, argv: list[str],
                  guard: GuardBounds = STRICT_GUARD, status: str = "attempted") -> dict:
    """Write a durable, self-verifying receipt inside the attempt namespace."""
    if not SAFE_CASE.fullmatch(case) or not attempt_id:
        raise UnsafeCommand("invalid case or attempt id for receipt")
    guard.validate()
    if status not in ALLOWED_RECEIPT_STATUSES:
        raise UnsafeCommand(f"receipt status outside allowlist: {status!r}")
    target = Path(attempt) / "receipt.json"
    if target.exists():
        raise UnsafeCommand("receipt.json already exists in this attempt; never overwrite")
    bad_cycles = Path(attempt) / "bad_cycles.csv"
    verify_bad_cycles(bad_cycles)
    receipt = {
        "schema": SCHEMA_RECEIPT,
        "case": case,
        "attempt_id": attempt_id,
        "status": status,
        "qualification_claim": "NONE",
        "argv_sha256": sha256_bytes(json.dumps(argv, sort_keys=True).encode()),
        "bad_cycles_sha256": sha256_file(bad_cycles),
        "guard_bounds": {
            "rss_limit_bytes": guard.rss_limit_bytes,
            "wall_seconds": guard.wall_seconds,
            "cid_bind_timeout_seconds": guard.cid_bind_timeout_seconds,
            "max_retry_attempts": guard.max_retry_attempts,
        },
    }
    _atomic_json(target, receipt)
    return receipt


def verify_receipt(attempt, *, case: str, attempt_id: str, argv: list[str],
                   expected_status: str = "attempted") -> dict:
    """Re-read a receipt and prove it still binds to this exact attempt."""
    receipt = json.loads((Path(attempt) / "receipt.json").read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS:
        raise UnsafeCommand("receipt field set differs from exact contract")
    if receipt["schema"] != SCHEMA_RECEIPT:
        raise UnsafeCommand("receipt schema mismatch")
    if receipt["status"] not in ALLOWED_RECEIPT_STATUSES:
        raise UnsafeCommand(f"receipt status outside allowlist: {receipt['status']!r}")
    if receipt["status"] != expected_status:
        raise UnsafeCommand("receipt status differs from the expected attempt status")
    if receipt["qualification_claim"] != "NONE":
        raise UnsafeCommand("receipt claims qualification; fail closed")
    if receipt["case"] != case or receipt["attempt_id"] != attempt_id:
        raise UnsafeCommand("receipt is bound to a different attempt")
    if receipt.get("argv_sha256") != sha256_bytes(json.dumps(argv, sort_keys=True).encode()):
        raise UnsafeCommand("receipt argv digest differs")
    if receipt.get("bad_cycles_sha256") != sha256_file(Path(attempt) / "bad_cycles.csv"):
        raise UnsafeCommand("receipt bad_cycles digest differs")
    GuardBounds(**receipt["guard_bounds"]).validate()
    return receipt
