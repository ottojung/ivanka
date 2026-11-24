"""Retire attested scratch archives after promoting their retained evidence.

The tool is deliberately narrow: it only consumes case directories whose
original archiver wrote a complete attestation, it verifies every tar member
against that attestation before any deletion, and it never writes discarded
members to disk. A retention receipt records the old archive hash, every
member hash and the bytes actually reclaimed, so the archive attestation can
remain as historical provenance after the archive itself is gone.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import tarfile
from pathlib import Path

SCHEMA = "ivanka.existing-scratch-retention-receipt.v1"
ATTESTATION_SCHEMA = "ivanka.p0.frozen-rust-only-reversible-scratch-archive.v1"
CANDIDATE_IMAGE = "73f29f0233da2ecd1ab126178cba4deb9e246bff5a6f770ab021a8f36d71081b"
REFERENCE_PANEL = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
RETAINED_SUBDIR = "retained-scratch"
SAMPLE_NAME = re.compile(r"[0-9a-f]{64}\Z")
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")
ATTESTATION_NAME = "scratch-archive-attestation.json"
ARCHIVE_NAME = "scratch.tar.gz"
RECEIPT_NAME = "scratch-retention-receipt.json"
VISUAL_SUFFIXES = frozenset((
    ".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif",
    ".tiff", ".avif", ".eps", ".pdf",
))
DISCARD_SUFFIXES = VISUAL_SUFFIXES | frozenset((
    ".fastq", ".fq", ".sam", ".bam", ".cram", ".bt2", ".bt2l", ".bai",
    ".idx", ".fai",
))
DISCARD_NAMES = frozenset((
    "temp.fasta", "temp.fa", "aligned.csv", "remap.csv",
    "unstitched_aligned.csv", "unstitched_remap.csv",
))
DISCARD_PREFIXES = ("alignments", "unstitched_alignments")


class MigrationError(RuntimeError):
    """A fail-closed preflight, attestation or receipt inconsistency."""


def sha_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _regular(path, label):
    if path.is_symlink() or not path.is_file():
        raise MigrationError(f"{label} is not a regular file: {path}")
    return path


def _safe_relative(name):
    path = Path(name)
    if not name or path.is_absolute() or ".." in path.parts or name.endswith("/"):
        raise MigrationError(f"unsafe archive member path: {name}")
    if not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise MigrationError(f"unsafe archive member path: {name}")
    return path


def _discard_reason(name):
    path = _safe_relative(name)
    if path.suffix.lower() in DISCARD_SUFFIXES:
        return "disposable_suffix"
    if path.name in DISCARD_NAMES:
        return "named_intermediate"
    if path.name.startswith(DISCARD_PREFIXES):
        return "read_level_table"
    return None


def _active_fds(root, own_pid):
    needle = str(Path(root).resolve())
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal() or int(proc.name) == own_pid:
            continue
        try:
            nodes = [proc / "cwd"] + list((proc / "fd").iterdir())
            for node in nodes:
                try:
                    ref = str(node.resolve(strict=False))
                except OSError:
                    continue
                if ref == needle or ref.startswith(needle + "/"):
                    return proc.name
        except OSError:
            continue
    return None


def _require_capacity(args):
    stat = os.statvfs(args.root)
    available = stat.f_bavail * stat.f_frsize
    if available < args.free_floor_bytes + args.reserve_bytes:
        raise MigrationError(
            f"insufficient free space: {available} < "
            f"{args.free_floor_bytes + args.reserve_bytes}")
    return available


def _read_json(path, label):
    doc = json.loads(_regular(path, label).read_text())
    if not isinstance(doc, dict):
        raise MigrationError(f"{label} is not an object")
    return doc


def _verify_terminal(case, image, panel):
    receipt = _read_json(case / "prospective-execution.json", "execution receipt")
    score = _read_json(case / "posthoc_score.json", "posthoc score")
    conseq = sha_file(_regular(case / "conseq.csv", "final conseq.csv"))
    expected = {
        "status": "success",
        "sample_sha256": case.name,
        "candidate_image_id": image,
        "final_conseq_sha256": conseq,
        "timing_origin": "micall_in_container_monotonic_v1",
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise MigrationError(f"execution receipt {key} mismatch in {case.name}")
    if receipt.get("violation") is not None:
        raise MigrationError(f"execution receipt has violation in {case.name}")
    if receipt.get("wall_seconds", float("inf")) > 2400:
        raise MigrationError(f"execution receipt wall cap exceeded in {case.name}")
    if receipt.get("sampled_rss_peak_bytes", float("inf")) > 4_000_000_000:
        raise MigrationError(f"execution receipt RSS cap exceeded in {case.name}")
    if score.get("case_sha256") != case.name:
        raise MigrationError(f"posthoc score case mismatch in {case.name}")
    if score.get("candidate_execution_receipt_sha256") != sha_file(case / "prospective-execution.json"):
        raise MigrationError(f"posthoc score receipt hash mismatch in {case.name}")
    if score.get("candidate_conseq_sha256") != conseq:
        raise MigrationError(f"posthoc score conseq hash mismatch in {case.name}")
    if score.get("reference_panel_sha256") != panel:
        raise MigrationError(f"posthoc score panel mismatch in {case.name}")
    for key in ("score_floor_90pct_best_available", "score_floor_90pct_iva"):
        if score.get(key) is not True:
            raise MigrationError(f"posthoc score floor {key} not passed in {case.name}")
    return {
        "execution_receipt_sha256": sha_file(case / "prospective-execution.json"),
        "posthoc_score_sha256": sha_file(case / "posthoc_score.json"),
        "final_conseq_sha256": conseq,
    }


def _attestation_members(case, image):
    att = _read_json(case / ATTESTATION_NAME, "archive attestation")
    if att.get("schema") != ATTESTATION_SCHEMA:
        raise MigrationError(f"unknown attestation schema in {case.name}")
    if att.get("status") != "complete":
        raise MigrationError(f"attestation not complete in {case.name}")
    if att.get("candidate_image_id") != image:
        raise MigrationError(f"attestation image mismatch in {case.name}")
    if att.get("qualification") is not False:
        raise MigrationError(f"attestation qualification flag set in {case.name}")
    if not HEX_SHA.fullmatch(str(att.get("sha256_archive", ""))):
        raise MigrationError(f"attestation archive hash missing in {case.name}")
    listed = att.get("files")
    if not isinstance(listed, list) or not listed:
        raise MigrationError(f"attestation member list empty in {case.name}")
    members = {}
    for item in listed:
        if not isinstance(item, dict):
            raise MigrationError(f"malformed attestation member in {case.name}")
        name = item.get("relative_path")
        _safe_relative(name)
        if name in members:
            raise MigrationError(f"duplicate attestation member in {case.name}: {name}")
        size = item.get("bytes")
        digest = item.get("sha256")
        if not isinstance(size, int) or size < 0 or not HEX_SHA.fullmatch(str(digest)):
            raise MigrationError(f"malformed attestation member hash in {case.name}: {name}")
        members[name] = {"bytes": size, "sha256": digest}
    for key in ("source_execution_receipt_sha256", "source_posthoc_score_sha256",
                "candidate_final_conseq_sha256"):
        if not HEX_SHA.fullmatch(str(att.get(key, ""))):
            raise MigrationError(f"attestation {key} missing in {case.name}")
    return att, members


def _cleanup_staged(staged):
    for item in staged:
        temp = item.get("temp_path")
        if temp:
            Path(temp).unlink(missing_ok=True)


def _stream_archive(case, attestation, listed, temp_dir, max_temp_bytes, stage):
    archive = _regular(case / ARCHIVE_NAME, "scratch archive")
    observed_archive_sha = sha_file(archive)
    if observed_archive_sha != attestation["sha256_archive"]:
        raise MigrationError(f"archive hash differs from attestation in {case.name}")
    seen = set()
    staged = []
    temp_total = 0
    hasher = hashlib.sha256()
    complete = False
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for info in tar:
                name = info.name
                _safe_relative(name)
                if not info.isfile() or info.islnk() or info.issym():
                    raise MigrationError(f"non-regular archive member in {case.name}: {name}")
                if name not in listed:
                    raise MigrationError(f"unattested archive member in {case.name}: {name}")
                if name in seen:
                    raise MigrationError(f"duplicate archive member in {case.name}: {name}")
                seen.add(name)
                expected = listed[name]
                if info.size != expected["bytes"]:
                    raise MigrationError(f"archive member size mismatch in {case.name}: {name}")
                member = tar.extractfile(info)
                if member is None:
                    raise MigrationError(f"unreadable archive member in {case.name}: {name}")
                reason = _discard_reason(name)
                temp_path = None
                if reason is None:
                    temp_total += info.size
                    if temp_total > max_temp_bytes:
                        raise MigrationError(f"bounded temp budget exceeded in {case.name}")
                    if stage:
                        temp_path = temp_dir / f".{case.name}.{len(staged)}.part"
                        if temp_path.exists():
                            raise MigrationError(f"stale temp file: {temp_path}")
                with member:
                    if temp_path is None:
                        for chunk in iter(lambda m=member: m.read(1024 * 1024), b""):
                            hasher.update(chunk)
                    else:
                        with temp_path.open("xb") as sink:
                            for chunk in iter(lambda m=member: m.read(1024 * 1024), b""):
                                hasher.update(chunk)
                                sink.write(chunk)
                            sink.flush()
                            os.fsync(sink.fileno())
                if hasher.hexdigest() != expected["sha256"]:
                    raise MigrationError(f"archive member hash mismatch in {case.name}: {name}")
                hasher = hashlib.sha256()
                staged.append({
                    "relative_path": name,
                    "bytes": info.size,
                    "sha256": expected["sha256"],
                    "disposition": "discard" if reason else "retain",
                    "reason": reason,
                    "temp_path": str(temp_path) if temp_path else None,
                })
        missing = set(listed) - seen
        if missing:
            raise MigrationError(
                f"archive missing attested members in {case.name}: {sorted(missing)[:3]}")
        complete = True
        return staged, observed_archive_sha, temp_total
    finally:
        if not complete:
            _cleanup_staged(staged)


def _resume_plan(case, args, receipt):
    """Recover after a crash between the pre-delete receipt and finalisation."""
    _verify_terminal(case, args.image, args.panel)
    if sha_file(case / ATTESTATION_NAME) != receipt.get("attestation_sha256"):
        raise MigrationError(f"attestation drift while resuming {case.name}")
    for item in receipt.get("retained_members", []):
        dest = case / item["destination"]
        if dest.is_symlink() or not dest.is_file() or sha_file(dest) != item["sha256"]:
            raise MigrationError(f"retained member missing while resuming {case.name}: {dest}")
    holder = _active_fds(case, os.getpid())
    if holder is not None:
        raise MigrationError(f"case has active file descriptors in {case.name}: pid {holder}")
    status = "already_migrated" if receipt.get("archive_removed") else "finalize_pending"
    return {"case": case.name, "status": status, "existing_receipt": receipt}


def inspect_case(case, args):
    if not SAMPLE_NAME.fullmatch(case.name) or case.is_symlink() or not case.is_dir():
        raise MigrationError(f"unsafe case directory: {case}")
    receipt_path = case / RECEIPT_NAME
    existing = None
    if receipt_path.exists():
        existing = _read_json(receipt_path, "retention receipt")
        if existing.get("schema") != SCHEMA:
            raise MigrationError(f"unknown retention receipt schema in {case.name}")
    if existing is not None and not (case / ARCHIVE_NAME).exists():
        return _resume_plan(case, args, existing)
    att, members = _attestation_members(case, args.image)
    terminal = _verify_terminal(case, args.image, args.panel)
    listed_receipts = {
        "source_execution_receipt_sha256": terminal["execution_receipt_sha256"],
        "source_posthoc_score_sha256": terminal["posthoc_score_sha256"],
        "candidate_final_conseq_sha256": terminal["final_conseq_sha256"],
    }
    for key, digest in listed_receipts.items():
        if att.get(key) != digest:
            raise MigrationError(f"attestation receipt hash drift in {case.name}: {key}")
    holder = _active_fds(case, os.getpid())
    if holder is not None:
        raise MigrationError(f"case has active file descriptors in {case.name}: pid {holder}")
    available = _require_capacity(args)
    staged, archive_sha, temp_bytes = _stream_archive(
        case, att, members, args.temp_dir, args.max_temp_bytes, bool(args.apply))
    retained = [item for item in staged if item["disposition"] == "retain"]
    discarded = [item for item in staged if item["disposition"] == "discard"]
    return {
        "case": case.name,
        "attestation_sha256": sha_file(case / ATTESTATION_NAME),
        "archive_sha256": archive_sha,
        "archive_bytes": (case / ARCHIVE_NAME).stat().st_size,
        "terminal": terminal,
        "members": staged,
        "retained_count": len(retained),
        "retained_bytes": sum(item["bytes"] for item in retained),
        "discarded_count": len(discarded),
        "discarded_bytes": sum(item["bytes"] for item in discarded),
        "temp_bytes": temp_bytes,
        "free_bytes_before": available,
        "existing_receipt": existing,
    }


def _ensure_destination(case, name):
    parts = _safe_relative(name).parts
    parent = case / RETAINED_SUBDIR
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        raise MigrationError(f"unsafe retained destination root in {case.name}")
    parent.mkdir(exist_ok=True)
    for part in parts[:-1]:
        parent = parent / part
        if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
            raise MigrationError(f"unsafe retained destination path in {case.name}: {part}")
        parent.mkdir(exist_ok=True)
    dest = parent / parts[-1]
    if dest.is_symlink() or (dest.exists() and not dest.is_file()):
        raise MigrationError(f"unsafe retained destination in {case.name}: {name}")
    return dest


def _promote(case, plan):
    actions = []
    try:
        for item in plan["members"]:
            if item["disposition"] != "retain":
                continue
            source = Path(item["temp_path"])
            dest = _ensure_destination(case, item["relative_path"])
            if dest.exists():
                if sha_file(dest) != item["sha256"]:
                    raise MigrationError(f"conflicting retained file in {case.name}: {dest}")
                action = "already_present"
                source.unlink()
            else:
                os.replace(source, dest)
                action = "promoted"
            actions.append({
                "relative_path": item["relative_path"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "destination": str(dest.relative_to(case)),
                "action": action,
            })
    finally:
        for item in plan["members"]:
            if item["temp_path"] and Path(item["temp_path"]).exists():
                Path(item["temp_path"]).unlink()
    return actions


def _write_receipt(path, doc):
    # A killed writer can leave a partial temp file; stale copies must never
    # prevent a later worker from finalising an already-retired case.
    for stale in path.parent.glob(f".{path.name}.tmp*"):
        stale.unlink(missing_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("x") as stream:
        json.dump(doc, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _visual_record(removed, existing):
    if removed:
        return removed
    if existing and isinstance(existing.get("visuals_removed"), list):
        return existing["visuals_removed"]
    return []


def _remove_visuals(case):
    removed = []
    for parent, dirs, files in os.walk(case, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(parent) / name).is_symlink()]
        for name in files:
            path = Path(parent) / name
            if path.suffix.lower() not in VISUAL_SUFFIXES or path.is_symlink():
                continue
            if not path.is_file():
                continue
            removed.append({
                "path": str(path.relative_to(case)),
                "bytes": path.stat().st_size,
                "sha256": sha_file(path),
            })
            path.unlink()
    return removed


def apply_case(case, plan, args):
    receipt_path = case / RECEIPT_NAME
    existing = plan["existing_receipt"]
    archive = case / ARCHIVE_NAME
    if plan.get("status") == "already_migrated":
        if archive.exists():
            raise MigrationError(f"receipt says retired but archive exists in {case.name}")
        return {"case": case.name, "status": "already_migrated"}
    if plan.get("status") == "finalize_pending":
        if archive.exists():
            raise MigrationError(f"finalization expected absent archive in {case.name}")
        visuals = _visual_record(_remove_visuals(case), existing)
        stat = os.statvfs(args.root)
        existing.update({
            "archive_removed": True,
            "visuals_removed": visuals,
            "visuals_bytes": sum(item["bytes"] for item in visuals),
            "free_bytes_after": stat.f_bavail * stat.f_frsize,
            "completed_utc": dt.datetime.now(dt.UTC).isoformat(),
        })
        _write_receipt(receipt_path, existing)
        return {"case": case.name, "status": "finalized",
                "visuals_bytes": existing["visuals_bytes"]}
    if existing is not None and existing.get("archive_sha256") != plan["archive_sha256"]:
        raise MigrationError(f"receipt archive hash drift in {case.name}")
    holder = _active_fds(case, os.getpid())
    if holder is not None:
        raise MigrationError(f"case became active in {case.name}: pid {holder}")
    available = _require_capacity(args)
    retained = _promote(case, plan)
    discarded = [{
        "relative_path": item["relative_path"],
        "bytes": item["bytes"],
        "sha256": item["sha256"],
        "reason": item["reason"],
    } for item in plan["members"] if item["disposition"] == "discard"]
    receipt = {
        "schema": SCHEMA,
        "case_sha256": case.name,
        "root": str(case.parent),
        "attestation_name": ATTESTATION_NAME,
        "attestation_sha256": plan["attestation_sha256"],
        "archive_name": ARCHIVE_NAME,
        "archive_sha256": plan["archive_sha256"],
        "archive_bytes": plan["archive_bytes"],
        "member_count": len(plan["members"]),
        "retained_members": retained,
        "retained_bytes": sum(item["bytes"] for item in retained),
        "discarded_members": discarded,
        "discarded_bytes": sum(item["bytes"] for item in discarded),
        "terminal_receipts": plan["terminal"],
        "free_bytes_before": available,
        "archive_removed": False,
        "owner": args.owner,
        "started_utc": dt.datetime.now(dt.UTC).isoformat(),
    }
    _write_receipt(receipt_path, receipt)
    if sha_file(archive) != plan["archive_sha256"]:
        raise MigrationError(f"archive changed before removal in {case.name}")
    archive.unlink()
    dir_fd = os.open(str(case), os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    visuals = _visual_record(_remove_visuals(case), existing)
    stat = os.statvfs(args.root)
    receipt.update({
        "archive_removed": True,
        "visuals_removed": visuals,
        "visuals_bytes": sum(item["bytes"] for item in visuals),
        "free_bytes_after": stat.f_bavail * stat.f_frsize,
        "completed_utc": dt.datetime.now(dt.UTC).isoformat(),
    })
    _write_receipt(receipt_path, receipt)
    return {
        "case": case.name,
        "status": "migrated",
        "archive_bytes": plan["archive_bytes"],
        "retained_bytes": receipt["retained_bytes"],
        "discarded_bytes": receipt["discarded_bytes"],
        "visuals_bytes": receipt["visuals_bytes"],
        "free_bytes_before": available,
        "free_bytes_after": receipt["free_bytes_after"],
    }


def _cases(root, selected):
    if selected:
        for name in selected:
            if not SAMPLE_NAME.fullmatch(name):
                raise MigrationError(f"invalid case selector: {name}")
            yield root / name
        return
    for entry in sorted(root.iterdir()):
        if (SAMPLE_NAME.fullmatch(entry.name) and entry.is_dir()
                and not entry.is_symlink()
                and (entry / ARCHIVE_NAME).is_file()
                and (entry / ATTESTATION_NAME).is_file()):
            yield entry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[], dest="cases")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--temp-dir", type=Path,
                        help="staging directory on the same filesystem as --root")
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--max-temp-bytes", type=int, default=256 * 1024 ** 2)
    parser.add_argument("--free-floor-bytes", type=int, default=24 * 1024 ** 3)
    parser.add_argument("--reserve-bytes", type=int, default=512 * 1024 ** 2)
    parser.add_argument("--image", default=CANDIDATE_IMAGE)
    parser.add_argument("--panel", default=REFERENCE_PANEL)
    parser.add_argument("--owner", default="existing-scratch-migration")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    if not args.root.is_dir() or args.root.is_symlink():
        raise MigrationError(f"unsafe case root: {args.root}")
    if args.temp_dir is None:
        args.temp_dir = args.root / ".scratch-migration-tmp"
    args.temp_dir.mkdir(parents=True, exist_ok=True)
    lock = args.lock or args.root / ".existing-scratch-migration.lock"
    results = []
    with lock.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MigrationError(f"another migration worker holds {lock}")
        for case in _cases(args.root, args.cases):
            if args.limit and len(results) >= args.limit:
                break
            try:
                plan = inspect_case(case, args)
                if plan.get("status") in ("already_migrated", "finalize_pending"):
                    summary = {"case": case.name, "status": plan["status"]}
                    if args.apply:
                        summary.update(apply_case(case, plan, args))
                    results.append(summary)
                    continue
                summary = {
                    "case": case.name,
                    "archive_sha256": plan["archive_sha256"],
                    "archive_bytes": plan["archive_bytes"],
                    "retained_count": plan["retained_count"],
                    "retained_bytes": plan["retained_bytes"],
                    "discarded_count": plan["discarded_count"],
                    "discarded_bytes": plan["discarded_bytes"],
                }
                if args.apply:
                    summary.update(apply_case(case, plan, args))
                else:
                    summary["status"] = "planned"
                results.append(summary)
            except (MigrationError, OSError, ValueError, TypeError,
                    tarfile.TarError) as exc:
                results.append({"case": case.name, "status": "error",
                                "error": f"{type(exc).__name__}: {exc}"})
    report = {"mode": "apply" if args.apply else "dry_run",
              "root": str(args.root), "cases": results}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(item.get("status") != "error" for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
