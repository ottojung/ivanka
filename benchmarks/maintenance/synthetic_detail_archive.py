"""Lossless, source-attested archives for successful synthetic400 MiCall arms.

Never change frozen synthetic source, failed attempts or their diagnostics.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import time

from .comparator_detail_storage import (
    ARCHIVE, DETAILS, PROOF, make_archive, preserve_files, restore_to,
    retire_originals, select_details, sha_bytes, sha_file, write_json,
)
from benchmarks.expanded.comparator_first import TOOLS, verify_record
from benchmarks.expanded.micall_checkpoint import identity

SOURCE = "d4a60b39328dfee6f2cb0b05f0d01bdd8a42ba8b"
PREFLIGHT_SHA = "1788ec6864535583d68199f365f242fed67fb8db904aa54ee52711c9425cb66f"
IMAGES_SHA = "93a30fd1cc8fdcb15a6e8c46d5dcacbdee39d44cb690cf9109cc30aad807b145"
REQUIRED = ("conseq.csv", "execution.json")
MIN_AGE = 180
MIN_FREE = 7 * 1024**3


def source_proof(root, data, images, preflight):
    """Cross-check independent 400-case preflight against actual source."""
    if any(p.is_symlink() for p in (root, data, images, preflight)):
        raise ValueError("redirected source attestation")
    if (not root.is_dir() or not data.is_dir()
            or sha_file(preflight) != PREFLIGHT_SHA
            or sha_file(images) != IMAGES_SHA):
        raise ValueError("untrusted original synthetic prelaunch proof")
    proof = json.loads(preflight.read_text())
    frozen = proof["manifest"]
    if (proof.get("qualified") is not False
            or frozen.get("qualified") is not False
            or frozen.get("source_commit") != SOURCE
            or frozen.get("schema")
            != "ivanka.comparator_first.stitched_counts_400.v1"
            or frozen.get("expected_samples") != 400
            or frozen.get("expected_arms") != 2400
            or not frozen.get("truth_validation", {}).get("valid")
            or set(frozen.get("images", {})) != set(TOOLS)
            or frozen["image_manifest_sha256"] != IMAGES_SHA):
        raise ValueError("changed synthetic original preflight requirements")
    image_catalog = json.loads(images.read_text())
    if (frozen["images"] != image_catalog["images"]
            or frozen["patched_micall_tree"] != image_catalog["source_tree"]):
        raise ValueError("changed independently pinned six comparator images")
    manifest = root / "run_manifest.json"
    if (not manifest.is_file() or manifest.is_symlink()
            or json.loads(manifest.read_text()) != frozen):
        raise ValueError("real synthetic result source differs from preflight")
    cohort_file = data / "cohort.json"
    if (sha_file(cohort_file) != frozen["original_cohort_manifest_sha256"]):
        raise ValueError("original 400-sample HXB2 cohort manifest changed")
    cohort = json.loads(cohort_file.read_text())
    entries = cohort["cases"]
    if (len(entries) != 400 or len({x["id"] for x in entries}) != 400
            or {x["id"] for x in entries} != set(proof["sample_ids"])):
        raise ValueError("not the source-attested 400 synthetic samples")
    return frozen, {x["id"]: x for x in entries}, sha_file(manifest)


def finished(root, data, frozen, entries):
    journal = root / "results.jsonl"
    raw = journal.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("incomplete synthetic source checkpoint line")
    records = {}
    for line in raw.splitlines():
        record = json.loads(line)
        identifier = record.get("id")
        if identifier not in entries:
            raise ValueError("nonfrozen synthetic sample in results")
        source = data / identifier / "manifest.json"
        if source.is_symlink() or not source.is_file():
            raise ValueError("synthetic case source manifest absent")
        metadata = json.loads(source.read_text())
        if metadata.get("sha256") != entries[identifier]["sha256"]:
            raise ValueError("altered original HXB2-v2 case manifest")
        fields = identity(identifier, metadata, frozen["truth_validation"])
        tool = verify_record(record, fields, root, frozen["images"])
        key = (identifier, tool)
        if key in records:
            raise ValueError("duplicate synthetic comparator terminal arm")
        records[key] = (record, sha_bytes(line), sha_file(source))
    return records, raw


def relative_arm(root, record):
    return root / record["id"] / record["assembler"]


def estimate_bytes(root, item):
    (sample, tool), (record, _, _) = item
    arm = root / sample / tool
    proof = arm / PROOF
    if proof.is_file() and not proof.is_symlink():
        return sum(v["bytes"] for v in json.loads(
            proof.read_text()).get("details", {}).values())
    return sum((arm / name).stat().st_size for name in DETAILS
               if (arm / name).is_file() and not (arm / name).is_symlink())


def archive_one(root, frozen, manifest_sha, record, row_sha, sample_sha, cutoff):
    if record["result"]["status"] != "success":
        return None
    fields = {key: record[key] for key in (
        "id", "cohort", "family", "truth_validation", "input_sha256")}
    verify_record(record, fields, root, frozen["images"])
    arm = relative_arm(root, record)
    if arm.is_symlink() or not arm.is_dir():
        raise ValueError("absent original synthetic MiCall output")
    proof_file = arm / PROOF
    expected = {
        "schema": "ivanka.synthetic400.successful-details.cold-archive.v1",
        "qualified": False,
        "source_commit": SOURCE, "frozen_manifest_sha256": manifest_sha,
        "original_sample_manifest_sha256": sample_sha,
        "truth_validation_sha256": sha_bytes(json.dumps(
            frozen["truth_validation"], sort_keys=True).encode()),
        "input_sha256": record["input_sha256"],
        "image_id": frozen["images"][record["assembler"]],
        "record_jsonl_sha256": row_sha,
        "sample": record["id"], "assembler": record["assembler"],
    }
    if proof_file.exists():
        if proof_file.is_symlink() or not proof_file.is_file():
            raise ValueError("untrusted archived proof path")
        proof = json.loads(proof_file.read_text())
        if any(proof.get(k) != v for k, v in expected.items()):
            raise ValueError("archived sample/source validation changed")
    else:
        if (arm / ARCHIVE).exists() or (arm / ARCHIVE).is_symlink():
            raise ValueError("archive without authenticated original proof")
        details = select_details(arm, cutoff)
        if not details:
            return None
        proof = {**expected, "details": details,
                 "protected": preserve_files(arm, details, REQUIRED)}
        write_json(proof_file, proof)
    if not proof.get("details") or not isinstance(proof.get("protected"), dict):
        raise ValueError("archive proof has missing original evidence")
    archive_sha = make_archive(arm, proof, REQUIRED)
    verify_record(record, fields, root, frozen["images"])
    retire_originals(arm, proof, REQUIRED)
    verify_record(record, fields, root, frozen["images"])
    return {
        "schema": "ivanka.synthetic400.successful-details.action.v1",
        "sample": record["id"], "assembler": record["assembler"],
        "record_jsonl_sha256": row_sha,
        "archive_sha256": archive_sha,
        "raw_detail_bytes": sum(x["bytes"] for x in proof["details"].values()),
        "archive_bytes": (arm / ARCHIVE).stat().st_size,
        "files": len(proof["details"]), "failed_arm": False,
        "final_score_and_truth_unchanged": True,
    }


def run(root, data, images, preflight, audit, maximum=20):
    root, data, images, preflight, audit = map(
        Path, (root, data, images, preflight, audit))
    if maximum < 1 or root.is_symlink() or audit.is_symlink():
        raise ValueError("unsafe synthetic archival parameters")
    audit.mkdir(parents=True, exist_ok=True)
    with (audit / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        frozen, entries, manifest_sha = source_proof(
            root, data, images, preflight)
        records, before = finished(root, data, frozen, entries)
        ledger = audit / "actions.jsonl"
        done = {}
        if ledger.is_file():
            raw = ledger.read_bytes()
            if raw and not raw.endswith(b"\n"):
                raise ValueError("partial synthetic archival action journal")
            for line in raw.splitlines():
                action = json.loads(line)
                key = (action["sample"], action["assembler"])
                if (key in done or key not in records
                        or records[key][0]["result"]["status"] != "success"
                        or action.get("failed_arm") is not False
                        or action["record_jsonl_sha256"] != records[key][1]):
                    raise ValueError("foreign or changed archived synthetic arm")
                done[key] = action
        pending = [(key, value) for key, value in records.items()
                   if value[0]["result"]["status"] == "success" and key not in done]
        pending.sort(key=lambda item: estimate_bytes(root, item), reverse=True)
        count = 0
        cutoff = time.time() - MIN_AGE
        for key, (record, sha, sample_sha) in pending:
            if shutil.disk_usage(root).free < MIN_FREE + 512*1024**2:
                break
            action = archive_one(root, frozen, manifest_sha,
                                 record, sha, sample_sha, cutoff)
            if action is None:
                continue
            with ledger.open("a") as output:
                output.write(json.dumps(action, sort_keys=True) + "\n")
                output.flush()
                os.fsync(output.fileno())
            done[key] = action
            count += 1
            print("SYNTHETIC_DETAIL_LOSSLESS_ARCHIVED", len(done),
                  record["assembler"], record["id"], flush=True)
            if count >= maximum:
                break
        after = (root / "results.jsonl").read_bytes()
        if not after.startswith(before):
            raise ValueError("synthetic source journal changed nonappend")
        return {"new_arms": count, "archived_arms": len(done),
                "original_attempts": len(records),
                "raw_bytes": sum(x["raw_detail_bytes"] for x in done.values()),
                "compressed_bytes": sum(x["archive_bytes"] for x in done.values()),
                "source_manifest_sha256": manifest_sha,
                "original_journal_snapshot_sha256": sha_bytes(before)}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--results", type=Path, required=True)
    cli.add_argument("--cohort", type=Path, required=True)
    cli.add_argument("--images", type=Path, required=True)
    cli.add_argument("--preflight", type=Path, required=True)
    cli.add_argument("--audit", type=Path, required=True)
    cli.add_argument("--max-new", type=int, default=20)
    cli.add_argument("--loop", action="store_true")
    cli.add_argument("--interval-seconds", type=int, default=90)
    cli.add_argument("--restore-arm", type=Path)
    cli.add_argument("--restore-to", type=Path)
    args = cli.parse_args()
    if args.restore_arm:
        if (args.restore_to is None or len(args.restore_arm.parts) != 2
                or ".." in args.restore_arm.parts):
            cli.error("need exact sample/assembler and independent restore target")
        frozen, entries, _ = source_proof(
            args.results, args.cohort, args.images, args.preflight)
        sample, tool = args.restore_arm.parts
        if sample not in entries or tool not in TOOLS:
            cli.error("untrusted sample/assembler identity")
        print("RESTORED_SYNTHETIC_DETAILS",
              restore_to(args.results / sample / tool, args.restore_to))
        return
    if args.interval_seconds < 30:
        cli.error("synthetic archival interval must be >=30 seconds")
    while True:
        try:
            status = run(args.results, args.cohort, args.images,
                         args.preflight, args.audit, args.max_new)
            print("SYNTHETIC_DETAILS_ARCHIVE_STATUS",
                  json.dumps(status, sort_keys=True), flush=True)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print("SYNTHETIC_DETAILS_ARCHIVE_WAIT_OR_FAIL_CLOSED",
                  repr(exc), flush=True)
            if not args.loop:
                raise
        if not args.loop:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
