"""Losslessly archive coverage maps of an immutable, completed historical cohort.

The output journal, provenance and direct MiCall metrics remain byte-identical.
Never use on an active cohort or raw FASTQ directory.
"""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile


FINAL = ("execution.json", "conseq.csv", "nuc.csv", "remap_counts.csv",
         "micall_internal_timing.json", "timing.json", "stderr.log")


def digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def hash_file(path):
    with path.open("rb") as stream:
        return digest(stream)


def write_json(path, value):
    temp = path.with_name(path.name + ".partial")
    if temp.exists():
        temp.unlink()
    with temp.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def source_proof(root, expected, cutoff):
    if not root.is_dir() or root.is_symlink():
        raise ValueError("cohort root is missing or redirected")
    names = ("run_manifest.json", "results.jsonl", "attempt_summary.json")
    for name in names:
        path = root / name
        if not path.is_file() or path.is_symlink() or path.stat().st_mtime >= cutoff:
            raise ValueError("unfrozen cohort evidence: " + str(path))
    summary = json.loads((root / "attempt_summary.json").read_text())
    raw = (root / "results.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.splitlines()]
    if (summary.get("cases_attempted") != expected or
            summary.get("expected_cases") != expected or
            summary.get("result_sha256") != hashlib.sha256(raw).hexdigest() or
            len(rows) != expected or len({r["id"] for r in rows}) != expected):
        raise ValueError("not a complete, matching immutable cohort")
    return {name: hash_file(root / name) for name in names}, {r["id"] for r in rows}


def paths_to_archive(root, ids, cutoff):
    paths = []
    for case in sorted(root.iterdir()):
        if not case.is_dir() or case.is_symlink() or case.name not in ids:
            continue
        for arm in sorted(case.iterdir()):
            if not arm.is_dir() or arm.is_symlink():
                continue
            maps = arm / "coverage_maps"
            if maps.is_dir():
                if maps.is_symlink() or maps.stat().st_mtime >= cutoff:
                    raise ValueError("unfrozen coverage maps: " + str(maps))
                paths.append(str(maps.relative_to(root)))
    return paths


def original_files(folder):
    result = {}
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("missing or redirected original maps")
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlink in coverage maps")
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = hash_file(path)
        elif not path.is_dir():
            raise ValueError("unsupported coverage-map entry")
    return result


def final_files(parent):
    if (not (parent / "execution.json").is_file() or
            (parent / "execution.json").is_symlink()):
        raise ValueError("missing final execution evidence")
    if any((parent / name).is_symlink() for name in FINAL):
        raise ValueError("redirected final evidence")
    return {name: hash_file(parent / name) for name in FINAL
            if (parent / name).is_file()}


def verify_archive(archive, expected):
    actual = {}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != "coverage_maps" or ".." in parts:
                raise ValueError("unsafe archive member")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("unexpected non-file archive member")
            rel = PurePosixPath(*parts[1:]).as_posix()
            if rel in actual:
                raise ValueError("duplicate archive member")
            actual[rel] = digest(tar.extractfile(member))
    if actual != expected:
        raise ValueError("coverage archive differs from source bytes")


def archive_one(root, audit, rel, cutoff):
    folder = root / rel
    parent = folder.parent
    key = hashlib.sha256(rel.encode()).hexdigest()
    proof_file = audit / (key + ".proof.json")
    archive = parent / "coverage_maps.tar.gz"
    partial = parent / "coverage_maps.tar.gz.partial"
    if proof_file.exists():
        proof = json.loads(proof_file.read_text())
        if proof["source"] != rel:
            raise ValueError("archive proof belongs to another source")
    else:
        if archive.exists() or not folder.is_dir():
            raise ValueError("archive exists without source proof")
        if folder.stat().st_mtime >= cutoff:
            raise ValueError("source changed since cohort freeze")
        proof = {"source": rel, "files": original_files(folder),
                 "final": final_files(parent)}
        write_json(proof_file, proof)
    if final_files(parent) != proof["final"]:
        raise ValueError("original final metrics were modified")
    if folder.exists() and original_files(folder) != proof["files"]:
        raise ValueError("original coverage maps were modified")
    if not archive.exists():
        if not folder.is_dir():
            raise ValueError("neither source nor archive exists")
        if partial.exists():
            partial.unlink()
        with tarfile.open(partial, "w:gz", compresslevel=1) as tar:
            tar.add(folder, arcname="coverage_maps")
        verify_archive(partial, proof["files"])
        partial.replace(archive)
    verify_archive(archive, proof["files"])
    if folder.exists():
        shutil.rmtree(folder)
    if final_files(parent) != proof["final"]:
        raise ValueError("final metrics changed during archival")
    return {"source": rel, "archive_sha256": hash_file(archive),
            "archive_bytes": archive.stat().st_size, "files": len(proof["files"]),
            "final_metrics_preserved": True}


def run(root, audit, expected, cutoff, max_new=None):
    audit.mkdir(parents=True, exist_ok=True)
    with (audit / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        hashes, ids = source_proof(root, expected, cutoff)
        plan_file = audit / "plan.json"
        if plan_file.exists():
            plan = json.loads(plan_file.read_text())
            if plan["source"] != str(root) or plan["hashes"] != hashes:
                raise ValueError("frozen cohort changed since archival plan")
        else:
            plan = {"schema": "ivanka.coverage-archive-plan.v1",
                    "source": str(root), "hashes": hashes,
                    "items": paths_to_archive(root, ids, cutoff)}
            write_json(plan_file, plan)
        ledger = audit / "actions.jsonl"
        completed = {}
        if ledger.exists():
            for line in ledger.read_text().splitlines():
                row = json.loads(line)
                if row["source"] in completed or row["source"] not in plan["items"]:
                    raise ValueError("duplicate or foreign archival ledger entry")
                completed[row["source"]] = row
        for rel in plan["items"]:
            if rel in completed:
                archive = (root / rel).with_name("coverage_maps.tar.gz")
                if ((root / rel).exists() or not archive.is_file() or
                        hash_file(archive) != completed[rel]["archive_sha256"]):
                    raise ValueError("archival ledger contradicts filesystem")
                continue
            if max_new is not None and max_new <= 0:
                break
            record = archive_one(root, audit, rel, cutoff)
            with ledger.open("a") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            completed[rel] = record
            if max_new is not None:
                max_new -= 1
            print("ARCHIVED", len(completed), "/", len(plan["items"]), rel, flush=True)
        if source_proof(root, expected, cutoff)[0] != hashes:
            raise ValueError("cohort changed during archival")
        if len(completed) == len(plan["items"]):
            write_json(audit / "completed.json", {
                "schema": "ivanka.coverage-archive-complete.v1",
                "source": str(root), "items": len(completed),
                "journal_sha256": hashes["results.jsonl"],
                "ledger_sha256": hash_file(ledger),
                "raw_inputs_untouched": True, "final_metrics_preserved": True})
        return len(completed), len(plan["items"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--modified-before", required=True)
    parser.add_argument("--max-new", type=int)
    args = parser.parse_args()
    date = datetime.fromisoformat(args.modified_before.replace("Z", "+00:00"))
    if date.tzinfo is None or args.expected < 1:
        parser.error("need a timezone-aware freeze cutoff and positive case count")
    done, total = run(args.source, args.audit, args.expected, date.timestamp(),
                      args.max_new)
    print("ARCHIVE_PROGRESS", done, total, flush=True)


if __name__ == "__main__":
    main()
