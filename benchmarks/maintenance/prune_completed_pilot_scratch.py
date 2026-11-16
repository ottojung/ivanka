"""Delete only expendable MiCall scratch from a completed, source-attested pilot.

Never remove original FASTQs, coverage maps, failed-arm scratch, metrics,
journals, container source IDs, or incomplete/unverified results.
"""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil

from .archive_completed_coverage import hash_file, write_json

PRESERVE = (
    "execution.json", "conseq.csv", "nuc.csv", "remap_counts.csv",
    "timing.json", "coverage_scores.csv",
)
SOURCE = ("pilot-manifest.json", "pilot-results.jsonl", "pilot-finished.json")


def seal(root, expected, cutoff):
    if not root.is_dir() or root.is_symlink():
        raise ValueError("pilot source is missing or redirected")
    for name in SOURCE:
        file = root / name
        if not file.is_file() or file.is_symlink() or file.stat().st_mtime >= cutoff:
            raise ValueError("pilot source journal is not frozen: " + name)
    manifest = json.loads((root / SOURCE[0]).read_text())
    raw = (root / SOURCE[1]).read_bytes()
    marker = json.loads((root / SOURCE[2]).read_text())
    if not raw.endswith(b"\n"):
        raise ValueError("truncated pilot journal")
    records = [json.loads(line) for line in raw.splitlines()]
    ids = [r.get("id") for r in records]
    if (len(records) != expected or len(set(ids)) != expected
            or manifest.get("qualified") is not False
            or sorted(manifest.get("case_names", [])) != sorted(ids)
            or not manifest.get("truth_validation", {}).get("valid")
            or marker.get("sample_count") != expected
            or marker.get("failed_cases") != 0
            or marker.get("source_commit") != manifest.get("source_commit")
            or marker.get("pilot_manifest_sha256") != hash_file(root / SOURCE[0])
            or marker.get("results_sha256") != hashlib.sha256(raw).hexdigest()):
        raise ValueError("pilot is not a sealed, successful source-attested cohort")
    for row in records:
        ident = row["id"]
        if (not isinstance(ident, str) or not ident
                or any(c not in "abcdefghijklmnopqrstuvwxyz"
                       "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in ident)):
            raise ValueError("unsafe sample identifier")
        arm = row.get("ivanka", {})
        folder = root / ident / "ivanka"
        final = arm.get("final_dominant", {})
        if (not folder.is_dir() or folder.is_symlink()
                or arm.get("status") != "success" or arm.get("exit_code") != 0
                or arm.get("sha256") != manifest.get("images", {}).get("ivanka")
                or final.get("source_output") != "conseq.csv"
                or not (folder / "execution.json").is_file()
                or json.loads((folder / "execution.json").read_text()) != arm
                or hash_file(folder / "conseq.csv")
                != final.get("conseq_csv_sha256")):
            raise ValueError("incomplete or modified successful pilot arm: " + ident)
        for filename in PRESERVE:
            path = folder / filename
            if not path.is_file() or path.is_symlink():
                raise ValueError("missing protected MiCall evidence: " + str(path))
        maps = folder / "coverage_maps"
        if not maps.is_dir() or maps.is_symlink():
            raise ValueError("missing protected exact-coverage map: " + ident)
    return records, {name: hash_file(root / name) for name in SOURCE}


def preserved(folder):
    evidence = {name: hash_file(folder / name) for name in PRESERVE}
    maps = folder / "coverage_maps"
    if not maps.is_dir() or maps.is_symlink():
        raise ValueError("missing protected coverage maps")
    for file in sorted(maps.rglob("*")):
        if file.is_symlink():
            raise ValueError("redirected protected coverage evidence")
        if file.is_file():
            evidence[file.relative_to(folder).as_posix()] = hash_file(file)
        elif not file.is_dir():
            raise ValueError("unsupported protected coverage evidence")
    if not any(name.startswith("coverage_maps/") for name in evidence):
        raise ValueError("missing contents of protected coverage maps")
    return evidence


def check_scratch(path, cutoff):
    if not path.is_dir() or path.is_symlink() or path.stat().st_mtime >= cutoff:
        raise ValueError("scratch is active, too recent or redirected")
    count, size = 0, 0
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError("scratch includes links outside its own directory")
        if item.is_file():
            count += 1
            size += item.stat().st_size
        elif not item.is_dir():
            raise ValueError("unsupported scratch entry")
    return {"file_count": count, "logical_bytes": size}


def one(root, audit, row, cutoff):
    name = row["id"]
    folder = root / name / "ivanka"
    scratch = folder / "scratch"
    proof_file = audit / (name + ".proof.json")
    if proof_file.exists():
        proof = json.loads(proof_file.read_text())
        if proof["sample"] != name or preserved(folder) != proof["preserved"]:
            raise ValueError("resumed scratch deletion lacks matching final evidence")
    else:
        if not scratch.exists():
            raise ValueError("scratch absent without crash-recovery proof: " + name)
        proof = {
            "sample": name, "preserved": preserved(folder),
            "scratch": check_scratch(scratch, cutoff),
        }
        write_json(proof_file, proof)
    if scratch.exists():
        if check_scratch(scratch, cutoff) != proof["scratch"]:
            raise ValueError("scratch changed after pruner proof")
        shutil.rmtree(scratch)
    if preserved(folder) != proof["preserved"]:
        raise ValueError("MiCall metrics changed during scratch cleanup")
    if not (folder / "coverage_maps").is_dir():
        raise ValueError("coverage maps disappeared during scratch cleanup")
    return {"sample": name, "scratch_deleted": True, **proof["scratch"]}


def run(root, audit, expected, cutoff, max_new=None):
    if root.is_symlink() or audit.is_symlink():
        raise ValueError("source or audit must not be redirected")
    root, audit = root.resolve(), audit.resolve()
    audit.mkdir(parents=True, exist_ok=True)
    with (audit / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        records, hashes = seal(root, expected, cutoff)
        plan_file = audit / "plan.json"
        plan = {"schema": "ivanka.completed-pilot-scratch-prune.v1",
                "source": str(root), "sources": hashes,
                "case_names": sorted(r["id"] for r in records)}
        if plan_file.exists():
            if json.loads(plan_file.read_text()) != plan:
                raise ValueError("pilot sources changed since cleanup plan")
        else:
            write_json(plan_file, plan)
        ledger = audit / "actions.jsonl"
        completed = {}
        if ledger.exists():
            for line in ledger.read_text().splitlines():
                row = json.loads(line)
                sample = row["sample"]
                if sample in completed or sample not in plan["case_names"]:
                    raise ValueError("duplicate or foreign cleanup record")
                completed[sample] = row
        for row in sorted(records, key=lambda r: r["id"]):
            name = row["id"]
            if name in completed:
                folder = root / name / "ivanka"
                proof_file = audit / (name + ".proof.json")
                if (folder / "scratch").exists() or not proof_file.is_file():
                    raise ValueError("scratch reappeared or prior proof disappeared")
                proof = json.loads(proof_file.read_text())
                if (proof["sample"] != name
                        or proof["preserved"] != preserved(folder)
                        or proof["scratch"] != {
                            "file_count": completed[name]["file_count"],
                            "logical_bytes": completed[name]["logical_bytes"],
                        }):
                    raise ValueError("completed scratch cleanup proof changed")
                continue
            if max_new is not None and max_new <= 0:
                break
            entry = one(root, audit, row, cutoff)
            with ledger.open("a") as stream:
                stream.write(json.dumps(entry, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            completed[name] = entry
            if max_new is not None:
                max_new -= 1
            print("VERIFIED_SCRATCH_REMOVED", len(completed), expected, name,
                  entry["logical_bytes"], flush=True)
        if seal(root, expected, cutoff)[1] != hashes:
            raise ValueError("original cohort changed during scratch cleanup")
        if len(completed) == expected:
            marker = {
                "schema": "ivanka.completed-pilot-scratch-prune.v1",
                "status": "TEMP_SCRATCH_REMOVED_FINAL_EVIDENCE_UNCHANGED",
                "sample_count": expected,
                "source_journal_sha256": hashes["pilot-results.jsonl"],
                "ledger_sha256": hash_file(ledger),
                "logical_bytes_reclaimed":
                    sum(x["logical_bytes"] for x in completed.values()),
                "raw_fastqs_untouched": True,
                "coverage_maps_untouched": True,
            }
            completed_file = audit / "completed.json"
            if completed_file.exists():
                if json.loads(completed_file.read_text()) != marker:
                    raise ValueError("previous cleanup marker contradicts ledger")
            else:
                write_json(completed_file, marker)
        return len(completed), expected


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
        parser.error("expected positive cases and timezone-aware freeze cutoff")
    done, total = run(args.source, args.audit, args.expected,
                      date.timestamp(), args.max_new)
    print("COMPLETED_PILOT_SCRATCH_RECLAIM", done, total, flush=True)


if __name__ == "__main__":
    main()
