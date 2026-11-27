"""Retire only rebuildable reads/mappings of superseded PX failures.

Dry run by default. Apply requires the existing exclusive worker lock and a
fresh absence probe in the pinned dedicated store. The default storage mode
keeps each retired file as a proven, reversible zstd pair at its original
logical path; delete mode is an explicit operator choice. Never touch an
orphan, an ambiguous log, an unresolved infrastructure failure or a
scientific file.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path

from benchmarks import compressed_tables as codec
from benchmarks.retained_artifacts import (
    INTERMEDIATE_CSV, _load_sealed_evidence, logical_name, seal_terminal_evidence)

from . import px_cohort_scheduler as sched
from .px_retention import _observed_dead

ARCHIVE = re.compile(r"([a-z0-9-]+)-(PX-[RH][0-9]{3})\.attempt-001\Z")
SEAL = "superseded_disposable_evidence.json"
READ_SUFFIXES = {".fastq", ".fq", ".sam", ".bam", ".bai"}
INDEX_SUFFIXES = {".bt2", ".bt2i", ".bt2b", ".ebwt"}
ARCHIVE_MODE = "archive"
DELETE_MODE = "delete"
MODES = frozenset((ARCHIVE_MODE, DELETE_MODE))


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


def _variant(path):
    """A stored compression frame or proof is not a new source candidate."""
    return path.name.endswith((codec.ZST_SUFFIX, codec.META_SUFFIX))


def _candidates(archive):
    scratch = archive / "scratch"
    if not scratch.exists():
        return []
    if scratch.resolve() != scratch or not scratch.is_dir():
        raise ValueError("unsafe scratch directory")
    paths = []
    for path in sorted(scratch.rglob("*")):
        if _disposable(path, scratch) and not _variant(path):
            info = _regular(path).stat()
            if info.st_nlink != 1:
                raise ValueError("multiply linked scratch file")
            paths.append((path, info.st_size, info.st_blocks * 512))
    return paths


def _expected(item):
    return item["sha256"], item["bytes"]


def _prepare(archive, mode):
    """Hash and compress all candidates before a plan exists or bytes change."""
    if mode != ARCHIVE_MODE:
        return {}
    prepared = {}
    try:
        for path, size, _ in _candidates(archive):
            frame_path = path.with_name(path.name + codec.ZST_SUFFIX)
            meta_path = path.with_name(path.name + codec.META_SUFFIX)
            if frame_path.is_file() or meta_path.is_file():
                # An interrupted install may leave a completed pair beside its
                # source. Both variants must still prove the same bytes.
                if not (frame_path.is_file() and meta_path.is_file()):
                    raise ValueError("incomplete scratch proof")
                if codec.logical_digest(
                        path, format=codec.SCRATCH_FORMAT) != (_sha(path), size):
                    raise ValueError("archived scratch changed")
                continue
            frame, proof = codec.prepare_scratch(path)
            proof_bytes = len(json.dumps(proof, sort_keys=True).encode()) + 1
            if proof["compressed_size"] + proof_bytes >= size:
                raise ValueError("compression does not reduce scratch size")
            prepared[path] = (frame, proof)
    except Exception:
        for frame, _ in prepared.values():
            codec.discard_scratch_frame(frame)
        raise
    return prepared


def _seal(archive, prior, mode, source):
    if (archive / SEAL).exists() or (archive / SEAL).is_symlink():
        return
    files = [{"path": str(p.relative_to(archive)), "sha256": _sha(p),
              "bytes": size, "allocated": allocated}
             for p, size, allocated in _candidates(archive)]
    seal_terminal_evidence(archive, {"failure": prior, "files": files,
                                     "storage_mode": mode}, source, name=SEAL)


def _verified_entries(archive, prior, source, mode):
    """Reload the immutable seal and recheck every remaining source file."""
    evidence = _load_sealed_evidence(archive / SEAL, source)
    if evidence.get("failure") != prior:
        raise ValueError("sealed failure receipt differs")
    if evidence.get("storage_mode") != mode:
        raise ValueError("sealed storage mode differs")
    entries = evidence.get("files")
    if not isinstance(entries, list):
        raise ValueError("missing disposable manifest")
    planned = {}
    for item in entries:
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str)
                or not isinstance(item.get("sha256"), str)
                or not isinstance(item.get("bytes"), int)):
            raise ValueError("invalid sealed disposable entry")
        path = archive / item["path"]
        if (path.resolve() != path or not path.is_relative_to(archive / "scratch")
                or _variant(path) or not _disposable(path, archive / "scratch")
                or path in planned):
            raise ValueError("unsafe sealed disposable path")
        planned[path] = item
    present = {p for p, _, _ in _candidates(archive)}
    if not present.issubset(planned):
        raise ValueError("scratch changed after seal")
    for path in present:
        if mode == ARCHIVE_MODE:
            digest, size = codec.logical_digest(path, format=codec.SCRATCH_FORMAT)
        else:
            digest, size = _sha(path), path.stat().st_size
        if (digest, size) != _expected(planned[path]):
            raise ValueError("sealed disposable file changed")
    return planned, present


def _archive_one(path, item, prepared):
    """Install a proven frame at the logical path, or finish an interrupted one."""
    expected = _expected(item)
    frame_path = path.with_name(path.name + codec.ZST_SUFFIX)
    meta_path = path.with_name(path.name + codec.META_SUFFIX)
    frame, proof = prepared.pop(path, (None, None))
    if frame is None:
        if meta_path.is_file() or frame_path.is_file():
            if not (meta_path.is_file() and frame_path.is_file()):
                raise ValueError("incomplete scratch proof")
            if codec.logical_digest(path, format=codec.SCRATCH_FORMAT) != expected:
                raise ValueError("archived scratch changed")
            path.unlink()
            return
        frame, proof = codec.prepare_scratch(path)
        try:
            if (proof["original_sha256"], proof["original_size"]) != expected:
                raise ValueError("prepared scratch differs from seal")
            codec.install_scratch(path, frame, proof)
        finally:
            codec.discard_scratch_frame(frame)
        return
    if (proof["original_sha256"], proof["original_size"]) != expected:
        raise ValueError("prepared scratch differs from seal")
    codec.install_scratch(path, frame, proof)


def _apply(archive, prior, cid, source, dead, root, *, mode):
    if mode not in MODES:
        raise ValueError("unknown storage mode")
    if not dead(root, cid):
        raise ValueError("exact CID absence not freshly observed")
    prepared = _prepare(archive, mode)
    try:
        _seal(archive, prior, mode, source)
        planned, present = _verified_entries(archive, prior, source, mode)
        reclaimed = 0
        for path in sorted(present):
            before = path.stat().st_blocks * 512
            if mode == ARCHIVE_MODE:
                _archive_one(path, planned[path], prepared)
                after = sum(p.stat().st_blocks * 512 for p in (
                    path.with_name(path.name + codec.ZST_SUFFIX),
                    path.with_name(path.name + codec.META_SUFFIX)))
            else:
                path.unlink()
                after = 0
            reclaimed += before - after
        return reclaimed
    finally:
        for frame, _ in prepared.values():
            codec.discard_scratch_frame(frame)


def _scan(root, *, apply, only, dead, mode):
    output = {"mode": mode, "eligible": [], "skipped": [], "reclaimed_bytes": 0}
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
                    archive, prior, cid, source, dead, root, mode=mode)
            output["eligible"].append({"archive": archive.name, "bytes": size})
        except (ValueError, OSError, KeyError, TypeError, RuntimeError,
                codec.TableError) as exc:
            output["skipped"].append({"archive": archive.name, "reason": str(exc)})
    return output


def _lock(root):
    """Hold the actual shared worker lock, rejecting a replaced inode."""
    lock_path = _regular(root / ".global-worker.lock")
    lock = lock_path.open("r+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not os.path.samestat(os.fstat(lock.fileno()),
                                _regular(lock_path).stat()):
            raise ValueError("worker lock inode changed")
    except Exception:
        lock.close()
        raise
    return lock


def retire(root, *, apply=False, only=None, dead=_observed_dead,
           mode=ARCHIVE_MODE):
    root = Path(root).resolve(strict=True)
    if not apply:
        return _scan(root, apply=False, only=only, dead=dead, mode=mode)
    if mode not in MODES:
        raise ValueError("unknown storage mode")
    with _lock(root):
        return _scan(root, apply=True, only=only, dead=dead, mode=mode)


def _restore_entries(archive, evidence):
    """Rebuild each proven frame at its original path and retire the frame."""
    restored = []
    for item in evidence["files"]:
        path = archive / item["path"]
        if (path.resolve() != path or not path.is_relative_to(archive / "scratch")
                or _variant(path) or not _disposable(path, archive / "scratch")):
            raise ValueError("unsafe sealed disposable path")
        expected = _expected(item)
        if path.is_file():
            if codec.logical_digest(path, format=codec.SCRATCH_FORMAT) != expected:
                raise ValueError("archived scratch changed")
            continue
        meta_path = path.with_name(path.name + codec.META_SUFFIX)
        frame_path = path.with_name(path.name + codec.ZST_SUFFIX)
        if not (meta_path.is_file() and frame_path.is_file()):
            raise ValueError("archived scratch is missing")
        proof = codec.load_meta(meta_path, format=codec.SCRATCH_FORMAT)
        if (proof["original_sha256"], proof["original_size"]) != expected:
            raise ValueError("archived proof differs from seal")
        handle, temp_name = tempfile.mkstemp(
            prefix="." + path.name + ".restore.", dir=path.parent)
        os.close(handle)
        temp = Path(temp_name)
        try:
            digest, size = hashlib.sha256(), 0
            with temp.open("wb") as target:
                for block in codec.logical_bytes(path, format=codec.SCRATCH_FORMAT):
                    target.write(block)
                    digest.update(block)
                    size += len(block)
            if (digest.hexdigest(), size) != expected:
                raise ValueError("restored scratch differs from seal")
            os.replace(temp, path)
            frame_path.unlink()
            meta_path.unlink()
            restored.append(str(path))
        finally:
            temp.unlink(missing_ok=True)
    return restored


def restore(root, *, only=None):
    """Restore proven archived scratch at its original logical paths."""
    root = Path(root).resolve(strict=True)
    archives = root / "outputs" / "attempts"
    if not archives.exists():
        return {"restored": [], "skipped": []}
    if archives.resolve() != archives or not archives.is_dir():
        raise ValueError("unsafe attempt archive root")
    reports, leases = _reports(root), _leases(root)
    restored, skipped = [], []
    with _lock(root):
        for archive in sorted(archives.iterdir()):
            if only is not None and archive.name != only:
                continue
            try:
                prior, _, source = _bind(root, archive, reports, leases)
                seal = archive / SEAL
                if not seal.exists() or seal.is_symlink():
                    continue
                evidence = _load_sealed_evidence(seal, source)
                if (evidence.get("failure") != prior
                        or evidence.get("storage_mode") != ARCHIVE_MODE):
                    raise ValueError("seal does not describe archived scratch")
                restored.extend(_restore_entries(archive, evidence))
            except (ValueError, OSError, KeyError, TypeError, RuntimeError,
                    codec.TableError) as exc:
                skipped.append({"archive": archive.name, "reason": str(exc)})
    return {"restored": restored, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", help="one exact attempt archive name")
    parser.add_argument("--mode", choices=sorted(MODES), default=ARCHIVE_MODE)
    parser.add_argument("--restore", action="store_true",
                        help="rebuild archived scratch at its original path")
    args = parser.parse_args()
    if args.restore:
        print(json.dumps(restore(args.root, only=args.only), indent=2))
    else:
        print(json.dumps(retire(args.root, apply=args.apply, only=args.only,
                                mode=args.mode), indent=2))


if __name__ == "__main__":
    main()
