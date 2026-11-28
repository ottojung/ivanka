"""Dry-run safety gate for registered Antonina managed build caches.

This is deliberately *not* a general-purpose cleaner. It never scans a declared
``cwd``, never infers ownership from a directory name, and never removes a file
itself. Ownership comes only from an explicitly registered
``managed-cache.json`` marker (schema ``antonina.managed-build-cache.v1``) whose
agent id, path, nonce and inode are checked exactly. Any actual retirement is
delegated to the registered ``antonina agent cache-clean`` command, which
re-verifies the same evidence under its own ownership lock.

Every guard is re-derived immediately before any action; nothing is cached from
the planning scan and reused at deletion time. Evidence that cannot be read is
treated as a reference and blocks the candidate (fail closed).

Default mode is dry-run. Even ``--apply`` is refused unless the operator has
passed ``--operator-approved``; no such approval exists at the time of writing,
so this tool has no unattended deletion path.
"""
import argparse
import fcntl
import json
import os
import stat
import subprocess
import sys
import time
from contextlib import contextmanager

MANAGED_CACHE_SCHEMA = "antonina.managed-build-cache.v1"
MANAGED_CACHE_MARKER = "managed-cache.json"
MANAGED_CACHE_LEAF = "target"
BUILD_CACHE_DIR = "build-cache"
LOCK_FILE = ".retire.lock"
DEFAULT_STATE_ROOT = "/home/lubko/.local/state/antonina"
DEFAULT_PROC_ROOT = "/proc"
# Suffixes that mark scientific/final evidence rather than rebuildable output.
SUSPICIOUS_SUFFIXES = (
    ".git", "receipt", "manifest", ".csv", ".fasta", ".fastq", ".sam",
    ".bam", ".bundle", ".patch", ".jsonl",
)
PROC_LINK_KEYS = ("cwd", "root", "exe")
PROC_BLOB_KEYS = ("environ", "cmdline", "mountinfo")


class EvidenceUnreadable(Exception):
    """Ownership or liveness evidence could not be read; the caller must skip."""


class ReferenceUnreadable(EvidenceUnreadable):
    """A proc/log reference could not be read; treat the path as referenced."""


class OwnerLockBusy(EvidenceUnreadable):
    """Another verifier holds the exclusive ownership lock for this agent."""


def _as_int(value, field_name, where):
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceUnreadable(f"{where}: {field_name} is not an integer")
    return value


def read_registration(marker_path):
    """Read and fully validate one registered managed-cache marker.

    No field is inferred and no substitution is allowed: schema, agent id, path,
    nonce and inode must all be present and internally consistent.
    """
    try:
        with open(marker_path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise EvidenceUnreadable(f"marker unreadable: {marker_path}: {exc}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise EvidenceUnreadable(f"marker is not valid JSON: {marker_path}") from exc
    if not isinstance(value, dict):
        raise EvidenceUnreadable(f"marker is not an object: {marker_path}")
    if value.get("schema") != MANAGED_CACHE_SCHEMA:
        raise EvidenceUnreadable(f"marker schema mismatch: {marker_path}")
    agent_id = value.get("agent_id")
    path = value.get("path")
    nonce = value.get("nonce")
    if not isinstance(agent_id, str) or not agent_id:
        raise EvidenceUnreadable(f"marker agent_id invalid: {marker_path}")
    if not isinstance(path, str) or not os.path.isabs(path):
        raise EvidenceUnreadable(f"marker path invalid: {marker_path}")
    if not isinstance(nonce, str) or not nonce:
        raise EvidenceUnreadable(f"marker nonce invalid: {marker_path}")
    return {
        "agent_id": agent_id,
        "path": path,
        "nonce": nonce,
        "created_at": _as_int(value.get("created_at"), "created_at", marker_path),
        "dev": _as_int(value.get("dev"), "dev", marker_path),
        "ino": _as_int(value.get("ino"), "ino", marker_path),
        "marker_path": marker_path,
    }


def discover_registrations(state_root):
    """Return ``{realpath: registration}`` for valid registrations only.

    A malformed, unreadable or inode-mismatched registration is skipped, never
    guessed. Nothing outside the dedicated build-cache root is ever considered.
    """
    root = os.path.join(state_root, BUILD_CACHE_DIR)
    claims = {}
    try:
        entries = os.listdir(root)
    except FileNotFoundError:
        return claims
    except OSError as exc:
        raise EvidenceUnreadable(f"build-cache root unreadable: {root}: {exc}") from exc
    for agent_dir in entries:
        marker_path = os.path.join(root, agent_dir, MANAGED_CACHE_MARKER)
        try:
            reg = read_registration(marker_path)
        except EvidenceUnreadable:
            continue
        if reg["agent_id"] != agent_dir:
            continue
        expected = os.path.join(root, agent_dir, MANAGED_CACHE_LEAF)
        if os.path.realpath(reg["path"]) != os.path.realpath(expected):
            continue
        try:
            st = os.lstat(reg["path"])
        except OSError:
            continue
        if (not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)
                or st.st_dev != reg["dev"] or st.st_ino != reg["ino"]):
            continue
        claims.setdefault(os.path.realpath(reg["path"]), reg)
    return claims


def capture_identity(path, suspicious_suffixes=SUSPICIOUS_SUFFIXES):
    """Capture the directory's identity and allocation at this instant.

    The returned dev/ino/mtime_ns are scan-time facts. A later verification
    compares against these exact values rather than sampling a fresh baseline.
    Unreadable tree entries raise instead of being silently ignored.
    """
    try:
        top = os.lstat(path)
    except OSError as exc:
        raise EvidenceUnreadable(f"cannot stat cache root: {path}: {exc}") from exc
    if not stat.S_ISDIR(top.st_mode) or stat.S_ISLNK(top.st_mode):
        raise EvidenceUnreadable(f"cache root is not a plain directory: {path}")
    allocated = apparent = files = latest = 0
    suspicious = []
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [d for d in dirnames
                       if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                st = os.lstat(full)
            except OSError as exc:
                raise EvidenceUnreadable(f"tree entry unreadable: {full}: {exc}") from exc
            if stat.S_ISLNK(st.st_mode):
                continue
            allocated += st.st_blocks * 512
            apparent += st.st_size
            files += 1
            latest = max(latest, st.st_mtime_ns)
            low = name.lower()
            if name != ".rustc_info.json" and any(s in low for s in suspicious_suffixes):
                suspicious.append(full)
    return {
        "path": path,
        "dev": top.st_dev,
        "ino": top.st_ino,
        "mtime_ns": top.st_mtime_ns,
        "allocated": allocated,
        "apparent": apparent,
        "files": files,
        "latest_ns": latest,
        "suspicious": tuple(suspicious),
    }


def owner_terminal(status):
    """Strict exact-field terminal check for the registered owner.

    A running/alive agent, a non-zero exit, or any pending prompt, steer,
    reservation or deletion flag means the owner may still use its cache.
    """
    if not isinstance(status, dict):
        return False
    if status.get("state") != "clearexit":
        return False
    if status.get("alive") is not False or status.get("exit_code") != 0:
        return False
    if status.get("finished_at") is None:
        return False
    pending = ("steers_pending", "active_runner", "reservation_in_flight",
               "delete_pending", "pending_prompt")
    for key in pending:
        if key not in status:
            continue
        value = status[key]
        if value is not None and value is not False and value != 0:
            return False
    return True


def default_status_reader(agent_id):
    proc = subprocess.run(
        ["antonina", "agent", "status", "--id", agent_id, "--json"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise EvidenceUnreadable(f"status failed for {agent_id}: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise EvidenceUnreadable(f"status not JSON for {agent_id}") from exc


def default_log_reader(agent_id):
    path = f"/home/lubko/.local/state/antonina/agents/{agent_id}/output.log"
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8", "ignore")


def default_running_agents():
    """Exact ids of RUNNING agents (self excluded), read from the CLI.

    An unreadable listing raises: without it we cannot prove that no running
    agent references a candidate, so the run must fail closed.
    """
    ids = []
    self_id = os.environ.get("ANTONINA_AGENT_ID", "")
    page = 1
    while page <= 30:
        proc = subprocess.run(
            ["antonina", "agent", "list", "--page", str(page),
             "--limit", "200", "--json"],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise EvidenceUnreadable(f"agent list failed: {proc.stderr.strip()}")
        try:
            batch = json.loads(proc.stdout).get("agents", [])
        except ValueError as exc:
            raise EvidenceUnreadable("agent list not JSON") from exc
        if not batch:
            break
        for entry in batch:
            if (isinstance(entry, dict) and entry.get("state") == "running"
                    and entry.get("id") != self_id):
                ids.append(entry["id"])
        page += 1
    return tuple(ids)


class ReferenceSnapshot:
    """Fresh proc/log reference evidence captured at one instant.

    ``unreadable`` is never discarded: if any probe failed, ``blocks`` returns
    True for every path because absence of a reference cannot be proven.
    """

    def __init__(self, references, unreadable):
        self.references = tuple(references)
        self.unreadable = tuple(unreadable)

    def blocks(self, path):
        if self.unreadable:
            return True
        real = os.path.realpath(path)
        for ref in self.references:
            try:
                real_ref = os.path.realpath(ref)
            except (ValueError, OSError):
                # An unparseable reference cannot be ruled out: fail closed.
                return True
            if real_ref == real or real_ref.startswith(real + os.sep):
                return True
        return False


def take_reference_snapshot(proc_root=DEFAULT_PROC_ROOT, running_agent_ids=(),
                            log_reader=None):
    """Snapshot proc and running-agent-log references; record unreadable probes."""
    references = []
    unreadable = []
    try:
        pids = os.listdir(proc_root)
    except OSError as exc:
        return ReferenceSnapshot((), (f"proc root unreadable: {exc}",))
    for pid in pids:
        if not pid.isdigit():
            continue
        for key in PROC_LINK_KEYS:
            target = os.path.join(proc_root, pid, key)
            try:
                references.append(os.readlink(target))
            except OSError as exc:
                unreadable.append(f"proc link {target}: {exc}")
        fd_dir = os.path.join(proc_root, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError as exc:
            unreadable.append(f"proc fd dir {fd_dir}: {exc}")
        else:
            for fd in fds:
                target = os.path.join(fd_dir, fd)
                try:
                    references.append(os.readlink(target))
                except OSError as exc:
                    unreadable.append(f"proc fd {target}: {exc}")
        for key in PROC_BLOB_KEYS:
            target = os.path.join(proc_root, pid, key)
            try:
                with open(target, "rb") as handle:
                    text = handle.read().decode("utf-8", "ignore")
            except OSError as exc:
                unreadable.append(f"proc blob {target}: {exc}")
            else:
                # cmdline/environ are NUL-separated; keep each token distinct
                # so realpath never sees an embedded NUL.
                references.extend(token for token in text.replace("\x00", "\n").splitlines()
                                  if token)
    if log_reader is not None:
        for agent_id in running_agent_ids:
            try:
                references.append(log_reader(agent_id))
            except Exception as exc:  # a log reader may use arbitrary I/O
                unreadable.append(f"running-agent log {agent_id}: {exc}")
    return ReferenceSnapshot(references, unreadable)


@contextmanager
def ownership_lock(state_root, agent_id):
    """Exclusive, non-blocking flock keyed by the registered owner id.

    The lock is held across verification and the registered cleanup call so a
    concurrent verifier cannot retire the same cache. The caller must re-read
    the owner's status *inside* this context; a restarted owner is refused.
    """
    directory = os.path.join(state_root, BUILD_CACHE_DIR, agent_id)
    lock_path = os.path.join(directory, LOCK_FILE)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        raise OwnerLockBusy(f"ownership lock busy for {agent_id}: {exc}") from exc
    try:
        yield lock_path
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def plan_retirements(state_root, proc_root=DEFAULT_PROC_ROOT,
                     running_agent_ids=(), log_reader=None,
                     status_reader=None, identity_reader=None):
    """Dry-run plan: ``(candidates, blocked)``.

    Caches that are unregistered, non-terminal, recently written, referenced or
    unreadable are blocked. A fresh reference snapshot is taken for planning;
    apply always takes another fresh one, so this snapshot is never reused.
    """
    if status_reader is None:
        status_reader = default_status_reader
    if identity_reader is None:
        identity_reader = capture_identity
    claims = discover_registrations(state_root)
    if running_agent_ids is None:
        try:
            running_agent_ids = default_running_agents()
        except EvidenceUnreadable as exc:
            return [], [(path, f"running-agent list unreadable: {exc}")
                        for path in claims]
    if log_reader is None and running_agent_ids:
        log_reader = default_log_reader
    snapshot = take_reference_snapshot(proc_root, running_agent_ids, log_reader)
    candidates = []
    blocked = []
    for path, reg in claims.items():
        if snapshot.blocks(path):
            blocked.append((path, "live or unreadable reference at scan"))
            continue
        try:
            status = status_reader(reg["agent_id"])
        except EvidenceUnreadable as exc:
            blocked.append((path, f"owner status unreadable: {exc}"))
            continue
        if not owner_terminal(status):
            blocked.append((path, "owner is not terminal"))
            continue
        finished_at = status.get("finished_at")
        try:
            identity = identity_reader(path)
        except EvidenceUnreadable as exc:
            blocked.append((path, f"identity unreadable: {exc}"))
            continue
        try:
            finished = float(finished_at)
        except (TypeError, ValueError):
            blocked.append((path, "owner finished_at unreadable"))
            continue
        if identity["latest_ns"] / 1e9 > finished + 2:
            blocked.append((path, "written after owner finished"))
            continue
        candidates.append({"path": path, "registration": reg,
                           "identity": identity})
    return candidates, blocked


def predelete_reverify(candidate, status_reader, registration_reader, snapshot):
    """Re-derive every guard with fresh evidence; return ``(ok, reason)``.

    Compared against the *scan-time* identity captured in ``candidate``, never a
    baseline sampled at deletion time. ``snapshot`` must be freshly taken.
    """
    reg = candidate["registration"]
    identity = candidate["identity"]
    try:
        status = status_reader(reg["agent_id"])
    except Exception as exc:
        return False, f"owner status unreadable: {exc}"
    if not owner_terminal(status):
        return False, "owner restarted or no longer terminal"
    try:
        fresh_reg = registration_reader(reg["marker_path"])
    except Exception as exc:
        return False, f"registration unreadable: {exc}"
    if fresh_reg != reg:
        return False, "registration changed since scan"
    try:
        st = os.lstat(identity["path"])
    except OSError as exc:
        return False, f"path unreadable: {exc}"
    if (st.st_dev, st.st_ino) != (identity["dev"], identity["ino"]):
        return False, "directory inode changed since scan"
    try:
        fresh = capture_identity(identity["path"])
    except EvidenceUnreadable as exc:
        return False, f"cache tree unreadable: {exc}"
    old_keys = ("dev", "ino", "mtime_ns", "allocated", "latest_ns")
    if any(fresh[key] != identity[key] for key in old_keys):
        return False, "cache tree changed since scan"
    if fresh["suspicious"]:
        return False, "suspicious files present"
    if snapshot.blocks(identity["path"]):
        return False, "live or unreadable reference"
    return True, "ok"


def apply_retirements(candidates, state_root, proc_root=DEFAULT_PROC_ROOT,
                      running_agent_ids=(), log_reader=None, status_reader=None,
                      snapshot_reader=None, cleanup=None):
    """Verified, locked, registered-only apply. Never removes files itself.

    ``cleanup`` defaults to invoking ``antonina agent cache-clean``; tests inject
    a recorder. Each candidate is verified under an exclusive ownership lock
    with a fresh reference snapshot taken at that moment.
    """
    if status_reader is None:
        status_reader = default_status_reader
    if snapshot_reader is None:
        snapshot_reader = take_reference_snapshot
    if cleanup is None:
        def cleanup():
            subprocess.run(["antonina", "agent", "cache-clean"], check=True)
    applied = []
    refused = []
    for candidate in candidates:
        path = candidate["path"]
        agent_id = candidate["registration"]["agent_id"]
        try:
            with ownership_lock(state_root, agent_id):
                ok, reason = predelete_reverify(
                    candidate, status_reader, read_registration,
                    snapshot_reader(proc_root, running_agent_ids, log_reader))
                if not ok:
                    refused.append((path, reason))
                    continue
                cleanup()
                applied.append(path)
        except OwnerLockBusy as exc:
            refused.append((path, str(exc)))
    return applied, refused


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default=DEFAULT_STATE_ROOT)
    parser.add_argument("--proc-root", default=DEFAULT_PROC_ROOT)
    parser.add_argument("--min-gib", type=float, default=0.25)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--apply", action="store_true",
                        help="gated real retirement (default: dry run)")
    parser.add_argument("--operator-approved", action="store_true",
                        help="required in addition to --apply; no approval exists yet")
    args = parser.parse_args(argv)
    if args.apply and not args.operator_approved:
        print("refusing --apply: operator approval for unattended retirement "
              "has not been granted; use registered cache-clean instead",
              file=sys.stderr)
        return 2
    try:
        running = default_running_agents()
    except EvidenceUnreadable as exc:
        print(f"refusing: running-agent list unreadable: {exc}", file=sys.stderr)
        return 0
    candidates, blocked = plan_retirements(
        args.state_root, args.proc_root, running, default_log_reader)
    eligible = [c for c in candidates
                if c["identity"]["allocated"] >= args.min_gib * 2 ** 30]
    total = sum(c["identity"]["allocated"] for c in eligible)
    print(f"mode={'APPLY' if args.apply else 'dry-run'} eligible={len(eligible)} "
          f"blocked={len(blocked)} allocated={total} B ({total / 2 ** 30:.2f} GiB)")
    for cand in eligible:
        print(f"  {cand['identity']['allocated']:>12d} B "
              f"{cand['registration']['agent_id']} {cand['path']}")
    if args.json:
        json.dump({"candidates": eligible, "blocked": blocked}, sys.stdout, indent=1)
    if not args.apply or not eligible:
        return 0
    applied, refused = apply_retirements(
        eligible, args.state_root, args.proc_root, running, default_log_reader)
    print(f"applied={len(applied)} refused={len(refused)} "
          f"at={time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
