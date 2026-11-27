"""Operator-facing, fail-closed readiness/dry-run CLI for the remap pilot.

This module is a read-only *interface* over the merged remap pilot
controller. It deliberately has NO execution path: it never calls
``remap_pilot_controller.execute_case``, never launches Podman/MiCall, never
mounts truth/panel data and never touches frozen, registry or publisher state.

It answers one question: "if an authorized operator asked for the first guarded
remap pilot case right now, would the reviewed gate admit it?" Every input is
re-derived from primary sources (the pinned private read-pair manifest, the
frozen source/image pins, the shared guard paths) and passed through the *same*
merged ``preflight`` that the real controller uses. A blocked report is a
typed refusal with reasons, never a partial GO.

Usage (read-only, no container)::

    PYTHONPATH=.:benchmarks python3 -m assembler_bench.remap_pilot_cli readiness \\
      --alias R001 --reads-dir /attested/originals/R001 \\
      --attempt-dir /sealed/remap-R001 --cidfile /sealed/remap-R001/cid \\
      --stamp 20261127T120000Z --token <operator-token>

Exit codes: 0 = admitted (still NOT a run authorization), 2 = blocked,
1 = usage/internal error. See docs/bench/remap-pilot-cli.md.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from fail_closed_guard import disk, errors as guard_errors, p1_harness, proc, stop

from . import remap_guarded_exec as gexec
from . import remap_pilot_controller as ctl
from . import remap_runner as runner

SCHEMA = "ivanka.remap.pilot-readiness.v1"
EXIT_ADMITTED = 0
EXIT_BLOCKED = 2
EXIT_ERROR = 1

# Shown in every report so an operator can never mistake readiness for a run.
NO_EXECUTION = {
    "executed": False,
    "would_execute": False,
    "execution_authorized": False,
    "qualification_claim": "NONE",
}


def digest_file(path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _storage_paths(conf) -> tuple[str, str]:
    """Parse the pinned shared storage.conf; fail closed on missing keys."""
    data = tomllib.loads(Path(conf).read_text())
    section = data.get("storage")
    if not isinstance(section, dict):
        raise ValueError("storage.conf has no [storage] section")
    graphroot, runroot = section.get("graphroot"), section.get("runroot")
    if not graphroot or not runroot:
        raise ValueError("storage.conf is missing graphroot/runroot")
    return str(graphroot), str(runroot)


def detect_read_names(reads_dir, r1_sha256, r2_sha256) -> tuple[str, str]:
    """Identify the two original FASTQs by their attested hashes only.

    The directory must contain exactly two regular non-symlink files whose
    digests are the pinned R1/R2 values. This is a read-only verification; it
    never copies, links, or rewrites a read.
    """
    root = Path(reads_dir)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("attested reads directory is unavailable")
    entries = sorted(root.iterdir(), key=lambda item: item.name)
    if len(entries) != 2 or any(item.is_symlink() or not item.is_file()
                                for item in entries):
        raise ValueError("reads directory must hold exactly two regular FASTQs")
    by_hash = {}
    for entry in entries:
        name = entry.name
        if not name.endswith(".fastq.gz") or "/" in name or ".." in name:
            raise ValueError("unexpected read basename")
        by_hash.setdefault(digest_file(entry), []).append(name)
    first = by_hash.get(r1_sha256, [])
    second = by_hash.get(r2_sha256, [])
    if len(first) != 1 or len(second) != 1 or first == second:
        raise ValueError("read hash pins do not match the two original FASTQs")
    return first[0], second[0]


@dataclass(frozen=True)
class ReadinessConfig:
    """All trust roots, with production defaults from the merged modules."""

    manifest_path: Path = gexec.ORIGINAL_MANIFEST
    manifest_sha256: str = gexec.ORIGINAL_MANIFEST_SHA256
    guard_root: Path = gexec.GUARD_ROOT
    lock_path: Path = gexec.LOCK_PATH
    stop_path: Path = gexec.STOP_PATH
    watchdog_path: Path = gexec.GUARD_ROOT / ".watchdog-alive.json"
    storage_conf: Path = gexec.STORAGE_CONF
    reserve_bytes: int = runner.RESERVE_BYTES
    image_id: str = runner.IMAGE_ID
    image_digest: str = runner.IMAGE_DIGEST


class LiveProbes:
    """Read-only probes for the real shared admission state.

    Every method is replaceable in hermetic tests; no method writes benchmark,
    guard, receipt, registry or publisher state. The lock probe takes and
    immediately releases an advisory flock (the same primitive as the real
    ExclusiveLock) without creating files.
    """

    def disk_free(self, path, *, reserve_bytes=None) -> int | None:
        """Free bytes via the same fail-closed guard check used at execution."""
        try:
            return int(disk.check_reserve(
                path, reserve_bytes or runner.RESERVE_BYTES,
                usage=lambda target: _Usage(shutil.disk_usage(str(target)).free)))
        except guard_errors.GuardExceeded:
            # Report the real (short) free bytes so the blocker is measurable.
            try:
                return int(shutil.disk_usage(str(path)).free)
            except OSError:
                return None
        except OSError:
            return None

    def lock_free(self, path) -> bool:
        target = Path(path)
        if target.is_symlink() or not target.is_file():
            return False
        try:
            fd = os.open(target, os.O_RDWR)
        except OSError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def stop(self, path) -> dict:
        target = Path(path)
        armed = stop.is_armed(target)
        owner = None
        if armed:
            try:
                owner = target.read_text().strip() or None
            except OSError:
                armed = False
        return {"armed": armed, "owner": owner}

    def watchdog(self, path, graphroot, snapshot=None) -> dict:
        try:
            result = p1_harness.require_watchdog_ready(
                path=path, graphroot=graphroot,
                snapshot=snapshot if snapshot is not None else proc.snapshot)
            return {"ready": True, "result": result}
        except guard_errors.GuardExceeded as exc:
            return {"ready": False, "reason": exc.reason}
        except Exception as exc:  # unreadable /proc or record: never a pass
            return {"ready": False, "reason": "watchdog_unavailable",
                    "detail": type(exc).__name__}

    def image(self, image_id, image_digest, storage_conf) -> dict:
        try:
            graphroot, runroot = _storage_paths(storage_conf)
        except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
            return {"present": False, "reason": "storage_conf_unreadable",
                    "detail": type(exc).__name__}
        env = dict(os.environ)
        env["CONTAINERS_STORAGE_CONF"] = str(storage_conf)
        command = [
            "podman", "--root", graphroot, "--runroot", runroot,
            "--storage-driver", "overlay", "images", "--digests",
            "--format", "{{.ID}} {{.Digest}}",
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=30, env=env)
        except (OSError, subprocess.SubprocessError):
            return {"present": False, "reason": "image_inspection_unavailable"}
        if result.returncode != 0:
            return {"present": False, "reason": "image_inspection_failed"}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith(image_id) and parts[1] == image_digest:
                return {"present": True, "digest": image_digest}
        return {"present": False, "reason": "image_missing_or_digest_drift"}

    def environment(self, storage_conf) -> dict:
        ambient = sorted(
            key for key in os.environ
            if key.startswith(("CONTAINERS_", "PODMAN_", "DOCKER_")))
        configured = os.environ.get("CONTAINERS_STORAGE_CONF")
        foreign = configured is not None and str(configured) != str(storage_conf)
        return {"clean": not ambient and not foreign,
                "ambient": ambient, "foreign_storage_conf": foreign}

    def cid_absent(self, cidfile) -> bool:
        target = Path(cidfile)
        return bool(target.name) and not target.exists() and not target.is_symlink()

    def git_head(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True,
                text=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None


class _Usage:
    """Minimal freeBytes object for the read-only statvfs probe."""

    def __init__(self, free):
        self.free = free


def build_readiness_report(*, alias, reads_dir, attempt_dir, cidfile, stamp,
                           token, config=None, probes=None, snapshot=None) -> dict:
    """Derive a typed, fail-closed readiness report. NEVER executes a case."""
    config = config or ReadinessConfig()
    probes = probes or LiveProbes()
    blockers: list[str] = []
    report = {
        "schema": SCHEMA,
        **NO_EXECUTION,
        "alias": alias,
        "stamp": stamp,
        "token": token,
        "config": {
            "manifest_path": str(config.manifest_path),
            "manifest_sha256": config.manifest_sha256,
            "guard_root": str(config.guard_root),
            "lock_path": str(config.lock_path),
            "stop_path": str(config.stop_path),
            "watchdog_path": str(config.watchdog_path),
            "storage_conf": str(config.storage_conf),
            "reserve_bytes": config.reserve_bytes,
        },
        "git_head": probes.git_head(),
        "blockers": blockers,
        "admitted": False,
    }

    # 0) Capacity is reported even if inputs are unavailable, so an operator
    #    always sees the hard no-run blocker with a measurable deficit.
    free = probes.disk_free(config.guard_root, reserve_bytes=config.reserve_bytes)
    if free is None or free < 0:
        blockers.append("capacity_unreadable")
        free = 0
    elif int(free) < config.reserve_bytes:
        blockers.append("reserve")
    report["capacity"] = {
        "free_bytes": int(free),
        "reserved_bytes": config.reserve_bytes,
        "deficit_bytes": max(0, config.reserve_bytes - int(free)),
    }

    # 1) Trust root: the independently attested private manifest (SHA pinned).
    try:
        manifest = gexec.load_original_input_manifest(
            config.manifest_path, expected_sha=config.manifest_sha256)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append("manifest_unattested:" + type(exc).__name__)
        return report
    report["manifest"] = {
        "sha256": manifest["manifest_sha256"],
        "counts": {"physical": 198, "synthetic": 464},
        "truth_opened": manifest["truth_opened"],
        "physical_manifest_sha256": manifest["physical_manifest_sha256"],
        "synthetic_cohort_sha256": manifest["synthetic_cohort_sha256"],
        "cases": len(manifest["cases"]),
    }

    # 2) Exact case binding from the manifest, never from CLI-supplied hashes.
    entry = next((item for item in manifest["cases"]
                  if item["alias"] == alias), None)
    if entry is None:
        blockers.append("alias_not_attested")
        return report

    try:
        graphroot, runroot = _storage_paths(config.storage_conf)
        r1_name, r2_name = detect_read_names(
            reads_dir, entry["read_sha256"]["R1"], entry["read_sha256"]["R2"])
        case = runner.Case(
            alias=alias, cohort=entry["cohort"],
            r1_sha256=entry["read_sha256"]["R1"],
            r2_sha256=entry["read_sha256"]["R2"],
            reads_dir=str(reads_dir), attempt_dir=str(attempt_dir),
            timer=str(Path(attempt_dir) / "timer.json"),
            cidfile=str(cidfile), storage_root=graphroot, runroot=runroot,
            name=f"podman-name-remap-{alias}-{token}", stamp=stamp, token=token,
            r1_name=r1_name, r2_name=r2_name)
        manifest_digest = runner.input_manifest([case])
        plan = runner.plan_case(case, manifest_digest, stamp=stamp, token=token)
        binding = gexec.bind_plan_to_original_manifest(plan, manifest)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        blockers.append("input_or_plan_rejected:" + type(exc).__name__)
        return report

    report["inputs"] = {
        "alias": alias,
        "cohort": entry["cohort"],
        "read_sha256": dict(entry["read_sha256"]),
        "read_basenames": [r1_name, r2_name],
        "paired_input_sha256": plan["inputs"]["paired_input_sha256"],
        "canonical_manifest_sha256": manifest_digest,
        "original_input_binding": binding,
    }
    report["plan"] = {
        "run_id": plan["run_id"],
        "argv_sha256": plan["argv_sha256"],
        "argv": plan["argv"],
        "image": plan["image"],
        "source": plan["source"],
        "reference": plan["reference"],
        "guard": plan["guard"],
    }

    # 3) The SAME merged preflight the real controller uses.
    image = probes.image(config.image_id, config.image_digest,
                         config.storage_conf)
    report["image"] = image
    preflight = ctl.preflight(
        plan, free_bytes=int(free),
        exclusive_slot=bool(probes.lock_free(config.lock_path)),
        image_present=bool(image.get("present")), image_rebuilt=False)
    report["preflight"] = preflight
    blockers.extend(preflight.get("reasons", []))

    # 4) Exact shared-guard state (read-only observations).
    lock_free = bool(probes.lock_free(config.lock_path))
    lock_state = {"free": lock_free}
    report["shared_guard"] = {"lock": lock_state}
    if not lock_free:
        blockers.append("exclusive_slot")  # de-duplicated below

    stop_state = probes.stop(config.stop_path)
    report["shared_guard"]["stop"] = stop_state
    if not stop_state.get("armed"):
        blockers.append("stop_not_armed")

    watchdog_state = probes.watchdog(
        config.watchdog_path, graphroot, snapshot=snapshot)
    report["shared_guard"]["watchdog"] = watchdog_state
    if not watchdog_state.get("ready"):
        blockers.append("watchdog_not_ready:" +
                        str(watchdog_state.get("reason", "unknown")))

    env_state = probes.environment(config.storage_conf)
    report["shared_guard"]["environment"] = env_state
    if not env_state.get("clean"):
        blockers.append("ambient_selector_or_foreign_storage_conf")

    cid_fresh = bool(probes.cid_absent(cidfile))
    report["shared_guard"]["cidfile"] = {
        "path": str(cidfile), "fresh": cid_fresh}
    if not cid_fresh:
        blockers.append("cidfile_not_fresh")

    # Plan argv must pin the SAME graphroot/runroot as the shared storage.conf.
    argv = plan["argv"]
    if (graphroot not in argv or runroot not in argv
            or "--root" not in argv or "--runroot" not in argv):
        blockers.append("storage_binding_drift")

    blockers = list(dict.fromkeys(blockers))
    report["blockers"] = blockers
    report["admitted"] = bool(preflight.get("admitted")) and not blockers
    if not report["admitted"]:
        report["next_action"] = (
            "Clear every blocker, re-run readiness, then obtain explicit "
            "operator authorization before any guarded execution.")
    else:
        report["next_action"] = (
            "Admitted means the reviewed gate is satisfied, NOT that a pilot "
            "may start. No execution is implemented by this interface.")
    return report


def main(argv=None, *, config=None, probes=None) -> int:
    """CLI entry point. Prints one JSON report; never starts a container."""
    parser = argparse.ArgumentParser(
        prog="remap_pilot_cli",
        description="Read-only, fail-closed readiness/dry-run for the first "
                    "guarded remap pilot case. No container is ever run.")
    sub = parser.add_subparsers(dest="command", required=True)
    ready = sub.add_parser(
        "readiness", help="verify pins and shared admission state; no execution")
    ready.add_argument("--alias", required=True, help="canonical alias, e.g. R001")
    ready.add_argument("--reads-dir", required=True,
                       help="directory holding exactly the two attested FASTQs")
    ready.add_argument("--attempt-dir", required=True,
                       help="sealed attempt directory for retained artifacts")
    ready.add_argument("--cidfile", required=True,
                       help="fresh unique CID file path (must not pre-exist)")
    ready.add_argument("--stamp", required=True, help="UTC stamp for run identity")
    ready.add_argument("--token", required=True, help="operator token for run identity")
    ready.add_argument("--manifest", default=None,
                       help="override private manifest PATH only; SHA pin unchanged")
    ready.add_argument("--output", default=None,
                       help="also write the JSON report to this file")
    args = parser.parse_args(argv)

    active = config or ReadinessConfig()
    if args.manifest is not None:
        active = replace(active, manifest_path=Path(args.manifest))
    try:
        report = build_readiness_report(
            alias=args.alias, reads_dir=Path(args.reads_dir),
            attempt_dir=Path(args.attempt_dir), cidfile=Path(args.cidfile),
            stamp=args.stamp, token=args.token, config=active, probes=probes)
        exit_code = EXIT_ADMITTED if report["admitted"] else EXIT_BLOCKED
    except Exception as exc:  # fail closed on internal error too
        report = {"schema": SCHEMA, **NO_EXECUTION, "admitted": False,
                  "blockers": ["internal_error:" + type(exc).__name__],
                  "detail": str(exc)}
        exit_code = EXIT_ERROR

    payload = json.dumps(report, sort_keys=True, indent=2)
    print(payload)
    if args.output:
        try:
            Path(args.output).write_text(payload + "\n")
        except OSError:
            print("warning: report could not be written to --output",
                  file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
