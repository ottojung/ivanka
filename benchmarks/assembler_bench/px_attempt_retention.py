"""Retire only rebuildable reads/mappings of superseded PX failures.

Dry run by default. Apply requires the existing exclusive worker lock and a
fresh absence probe in the pinned dedicated store. Never retire an orphan,
an ambiguous log, an unresolved infrastructure failure or a scientific file.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
from pathlib import Path

from benchmarks.retained_artifacts import (
    INTERMEDIATE_CSV, _load_sealed_evidence, logical_name, seal_terminal_evidence)

from . import px_cohort_scheduler as sched
from .px_retention import _observed_dead

ARCHIVE = re.compile(r"([a-z0-9-]+)-(PX-[RH][0-9]{3})\.attempt-001\Z")
SEAL = "superseded_disposable_evidence.json"
READ_SUFFIXES = {".fastq", ".fq", ".sam", ".bam", ".bai"}
INDEX_SUFFIXES = {".bt2", ".bt2i", ".bt2b", ".ebwt"}


def _regular(path):
    if path.resolve() != path or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("nonregular or symlinked evidence")
    return path


def _read(path):
    value = json.loads(_regular(path).read_bytes())
    if not isinstance(value, dict):
        raise ValueError("evidence must be a JSON object")
    return value


def _sha(path):
    return sched.sha256_file(_regular(path))


def _absence(proof, cid):
    return (isinstance(proof, dict)
            and proof.get("pilot_container_id") == cid
            and proof.get("fresh_absence_check") is True)


def _reports(root):
    by_hash = {}
    for path in root.glob("run-*.json"):
        report = _read(path)
        digest = report.get("log_sha256")
        if isinstance(digest, str):
            by_hash.setdefault(digest, []).append((path, report))
    return by_hash


def _leases(root):
    records = {}
    for line in _regular(root / ".worker-lease.jsonl").read_text().splitlines():
        record = json.loads(line)
        if (not isinstance(record, dict) or not isinstance(record.get("lease"), str)
                or record.get("schema") != "ivanka.worker-lease.v1"):
            raise ValueError("unknown worker lease schema")
        records.setdefault(record["lease"], []).append((line, record))
    return records


def _bound_report(root, prior, reports, leases):
    digest = prior.get("runner_receipt_sha256")
    if not isinstance(digest, str) or not sched.SHA256.fullmatch(digest):
        raise ValueError("missing launcher log digest")
    matches = reports.get(digest, [])
    if len(matches) != 1:
        raise ValueError("ambiguous or missing launcher report")
    path, report = matches[0]
    log = path.with_suffix(".log")
    if _sha(log) != digest:
        raise ValueError("launcher log digest mismatch")
    cid = report.get("bound_cid")
    expected_reason = prior["failure_reason"]
    reason = report.get("reason")
    if reason == "disk_limit":
        reason = "disk_stop"
    if (report.get("tool") != prior["tool_id"] or report.get("mode") != "pilot"
            or report.get("status") != "killed" or reason != expected_reason
            or not isinstance(cid, str) or not sched.SHA256.fullmatch(cid)
            or "pilot_cleanup_error" in report
            or not _absence(report.get("pilot_cleanup"), cid)):
        raise ValueError("launcher lacks matching terminal CID proof")
    rows = leases.get(path.stem.removeprefix("run-"), [])
    if not rows:
        raise ValueError("missing worker lease")
    line, last = rows[-1]
    if (last.get("state") != "released" or last.get("cid") != cid
            or not _absence(last.get("proof"), cid)
            or not any(r.get("state") == "active" and r.get("cid") == cid
                       for _, r in rows[:-1])):
        raise ValueError("worker lease not released for exact CID")
    return cid, {"launcher_report": _sha(path), "launcher_log": digest,
                 "released_lease": hashlib.sha256(line.encode()).hexdigest()}


def _bind(root, archive, reports, leases):
    match = ARCHIVE.fullmatch(archive.name)
    if not match or archive.resolve() != archive or not archive.is_dir():
        raise ValueError("not an exact superseded-attempt directory")
    tool, alias = match.groups()
    cohort = "physical" if alias.startswith("PX-R") else "synthetic"
    ident = f"{tool}-{cohort}-{alias}"
    canonical = root / "receipts" / (ident + ".json")
    original = root / "receipts" / "attempts" / (ident + ".attempt-001.json")
    _regular(canonical)
    _regular(sched.index_path(root))
    prior = _read(original)
    arm = {key: prior[key] for key in ("tool_id", "cohort", "alias",
           "input_sha256", "source_commit", "adapter_commit", "image_sha256")}
    if (sched.receipt_id(arm) != ident or prior.get("attempt") != 1
            or prior.get("outcome") != "failure"
            or prior.get("failure_reason") not in sched.INFRASTRUCTURE_FAILURE_REASONS):
        raise ValueError("not a pinned infrastructure failure")
    current = sched.verify_receipt(root, arm)
    if (not current or current.get("attempt") != 2
            or current.get("failure_reason") in sched.INFRASTRUCTURE_FAILURE_REASONS):
        raise ValueError("no resolved superseding terminal attempt")
    retry = sched.attempt_path(root, arm, 2)
    if _sha(retry) != _sha(canonical):
        raise ValueError("superseding receipt copy differs")
    if current["outcome"] == "success":
        output = root / "outputs" / f"{tool}-{alias}"
        finals = (output / sched.MAX_ARTIFACT,
                  output / "scratch" / sched.MAX_ARTIFACT)
        if not any(p.is_file() and _sha(p) == current["output_sha256"]
                   for p in finals):
            raise ValueError("superseding final MAX is not preserved")
    cid, source = _bound_report(root, prior, reports, leases)
    source.update(original_receipt=_sha(original),
                  superseding_receipt=_sha(canonical), launcher_container_id=cid)
    return prior, cid, source


def _disposable(path, scratch):
    # At top level MiCall's reads, alignments, indices and read-level tables
    # are reproducible. Nested native outputs are not: only the explicitly
    # known paired-read input is eligible there.
    if path.parent == scratch:
        name = logical_name(path.name)
        return (Path(name).suffix in READ_SUFFIXES | INDEX_SUFFIXES
                or name in INTERMEDIATE_CSV)
    return (path.name == "both_mates.fastq"
            and path.parent.parent == scratch
            and path.parent.name.startswith("assembly_"))


def _candidates(archive):
    scratch = archive / "scratch"
    if not scratch.exists():
        return []
    if scratch.resolve() != scratch or not scratch.is_dir():
        raise ValueError("unsafe scratch directory")
    paths = []
    for path in sorted(scratch.rglob("*")):
        if _disposable(path, scratch):
            info = _regular(path).stat()
            if info.st_nlink != 1:
                raise ValueError("multiply linked scratch file")
            paths.append((path, info.st_size, info.st_blocks * 512))
    return paths


def _apply(archive, prior, cid, source, dead, root):
    if not dead(root, cid):
        raise ValueError("exact CID absence not freshly observed")
    seal = archive / SEAL
    if not seal.exists() and not seal.is_symlink():
        files = [{"path": str(p.relative_to(archive)), "sha256": _sha(p),
                  "bytes": size} for p, size, _ in _candidates(archive)]
        seal_terminal_evidence(archive, {"failure": prior, "files": files},
                               source, name=SEAL)
    evidence = _load_sealed_evidence(seal, source)
    if evidence.get("failure") != prior:
        raise ValueError("sealed failure receipt differs")
    entries = evidence.get("files")
    if not isinstance(entries, list):
        raise ValueError("missing disposable manifest")
    planned = {}
    for item in entries:
        path = archive / item["path"]
        if (path.resolve() != path or not path.is_relative_to(archive / "scratch")
                or not _disposable(path, archive / "scratch") or path in planned):
            raise ValueError("unsafe sealed disposable path")
        planned[path] = item
    present = {p for p, _, _ in _candidates(archive)}
    if not present.issubset(planned):
        raise ValueError("scratch changed after seal")
    # Verify every remaining file before unlinking any. An interrupted cleanup
    # can resume from the same sealed manifest without replacing evidence.
    for path in present:
        item = planned[path]
        if path.stat().st_size != item["bytes"] or _sha(path) != item["sha256"]:
            raise ValueError("sealed disposable file changed")
    reclaimed = 0
    for path in sorted(present):
        reclaimed += path.stat().st_blocks * 512
        path.unlink()
    return reclaimed


def _scan(root, *, apply, only, dead):
    output = {"eligible": [], "skipped": [], "reclaimed_bytes": 0}
    archives = root / "outputs" / "attempts"
    if not archives.exists():
        return output
    if archives.resolve() != archives or not archives.is_dir():
        raise ValueError("unsafe attempt archive root")
    reports, leases = _reports(root), _leases(root)
    for archive in sorted(archives.iterdir()):
        if only is not None and archive.name != only:
            continue
        try:
            prior, cid, source = _bind(root, archive, reports, leases)
            size = sum(allocated for _, _, allocated in _candidates(archive))
            if not size:
                continue
            if apply:
                output["reclaimed_bytes"] += _apply(
                    archive, prior, cid, source, dead, root)
            output["eligible"].append({"archive": archive.name, "bytes": size})
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
            output["skipped"].append({"archive": archive.name, "reason": str(exc)})
    return output


def retire(root, *, apply=False, only=None, dead=_observed_dead):
    root = Path(root).resolve(strict=True)
    if not apply:
        return _scan(root, apply=False, only=only, dead=dead)
    # Do not create a substitute lock: the actual shared worker lock must
    # already exist, and its inode must not be replaced.
    lock_path = _regular(root / ".global-worker.lock")
    with lock_path.open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not os.path.samestat(os.fstat(lock.fileno()), _regular(lock_path).stat()):
            raise ValueError("worker lock inode changed")
        return _scan(root, apply=True, only=only, dead=dead)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", help="one exact attempt archive name")
    args = parser.parse_args()
    print(json.dumps(retire(args.root, apply=args.apply, only=args.only), indent=2))


if __name__ == "__main__":
    main()
