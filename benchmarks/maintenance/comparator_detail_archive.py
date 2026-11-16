"""Archive only durable successful fixed physical MiCall diagnostic details.

Never touch changed or incomplete source, failed arms, final MAX, coverage
maps, original reads, benchmark execution JSON, timing or main nuc metrics.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import time

from .comparator_detail_storage import (
    ARCHIVE, PROOF, make_archive, preserve_files, restore_to,
    retire_originals, select_details, sha_bytes, sha_file, write_json,
)
from benchmarks.expanded.comparator_first import TOOLS
from benchmarks.expanded.comparator_real_first import INVOCATION, validate


EXPECTED_SOURCE = "b634bce15f6f1dfae0cf482de35436ffd5af72e0"
EXPECTED_MANIFEST_SHA = "3dc341c2e49e2e3ed7fbcec73bbf5984566e6c55e7549999cc3cdcca6ca8231e"
EXPECTED_IMAGES_SHA = "93a30fd1cc8fdcb15a6e8c46d5dcacbdee39d44cb690cf9109cc30aad807b145"
MIN_FREE = 7 * 1024**3
MIN_AGE = 180


def frozen_source(root, images_file):
    manifest_file = root / "run_manifest.json"
    image_bytes = Path(images_file).read_bytes()
    image_manifest = json.loads(image_bytes)
    if (root.is_symlink() or not root.is_dir()
            or not manifest_file.is_file() or manifest_file.is_symlink()):
        raise ValueError("missing genuine physical comparator results")
    frozen = json.loads(manifest_file.read_text())
    if (sha_file(manifest_file) != EXPECTED_MANIFEST_SHA
            or sha_bytes(image_bytes) != EXPECTED_IMAGES_SHA
            or frozen.get("source_commit") != EXPECTED_SOURCE
            or frozen.get("schema")
            != "ivanka.comparator_first.stitched_counts_real198.v1"
            or frozen.get("qualified") is not False
            or frozen.get("expected_samples") != 198
            or frozen.get("expected_arms") != 1188
            or len(frozen.get("original_inputs", {})) != 198
            or set(frozen.get("images", {})) != set(TOOLS)
            or frozen.get("images") != image_manifest.get("images")
            or frozen.get("patched_micall_tree")
            != image_manifest.get("source_tree")
            or frozen.get("image_manifest_sha256") != sha_bytes(image_bytes)):
        raise ValueError("invalid independent physical comparator provenance")
    return frozen, sha_file(manifest_file)


def completed_rows(root, frozen):
    journal = root / "results.jsonl"
    raw = journal.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("physical source journal has a partial last line")
    items = {}
    for line in raw.splitlines():
        record = json.loads(line)
        key = validate(record, frozen, root)
        if key in items:
            raise ValueError("duplicate terminal physical comparator record")
        items[key] = (record, sha_bytes(line))
    return items, raw


def proof_for(root, frozen, manifest_sha, arm, record, line_sha, cutoff):
    selected = select_details(arm, cutoff)
    if not selected:
        return None
    return {
        "schema": "ivanka.comparator.successful-details.cold-archive.v1",
        "qualified": False,
        "source_commit": EXPECTED_SOURCE,
        "frozen_manifest_sha256": manifest_sha,
        "input_sha256": frozen["original_inputs"][record["sample"]],
        "image_id": frozen["images"][record["assembler"]],
        "record_jsonl_sha256": line_sha,
        "sample": record["sample"], "assembler": record["assembler"],
        "details": selected,
        "protected": preserve_files(arm, selected),
    }


def archive_arm(root, frozen, manifest_sha, record, line_sha, cutoff):
    if record["status"] != "success":
        return None
    validate(record, frozen, root)
    arm = root / INVOCATION / record["sample"] / record["assembler"]
    if arm.is_symlink() or not arm.is_dir():
        raise ValueError("missing original successful arm directory")
    proof_file = arm / PROOF
    if proof_file.exists():
        if proof_file.is_symlink() or not proof_file.is_file():
            raise ValueError("untrusted archived source proof")
        proof = json.loads(proof_file.read_text())
        expected = {
            "schema": "ivanka.comparator.successful-details.cold-archive.v1",
            "source_commit": EXPECTED_SOURCE,
            "frozen_manifest_sha256": manifest_sha,
            "input_sha256": frozen["original_inputs"][record["sample"]],
            "image_id": frozen["images"][record["assembler"]],
            "record_jsonl_sha256": line_sha,
            "sample": record["sample"],
            "assembler": record["assembler"],
            "qualified": False,
        }
        if any(proof.get(k) != v for k, v in expected.items()):
            raise ValueError("archived proof no longer belongs to the arm")
    else:
        if (arm / ARCHIVE).exists() or (arm / ARCHIVE).is_symlink():
            raise ValueError("archive exists without authenticated proof")
        proof = proof_for(root, frozen, manifest_sha, arm,
                          record, line_sha, cutoff)
        if not proof:
            return None
        write_json(proof_file, proof)
    if not proof.get("details") or not isinstance(proof.get("protected"), dict):
        raise ValueError("archive proof lacks original scientific inventory")
    archived_sha = make_archive(arm, proof)
    validate(record, frozen, root)
    retire_originals(arm, proof)
    validate(record, frozen, root)
    return {
        "schema": "ivanka.comparator.successful-details.action.v1",
        "sample": record["sample"], "assembler": record["assembler"],
        "record_jsonl_sha256": line_sha,
        "archive_sha256": archived_sha,
        "archive_bytes": (arm / ARCHIVE).stat().st_size,
        "raw_detail_bytes": sum(x["bytes"] for x in proof["details"].values()),
        "files": len(proof["details"]), "failed_arm": False,
        "final_score_and_metrics_unchanged": True,
    }


def run(root, images_file, audit, maximum=10, cutoff_seconds=MIN_AGE):
    original_root, audit = Path(root), Path(audit)
    if original_root.is_symlink():
        raise ValueError("refusing redirected physical comparator source")
    root = original_root.resolve()
    if maximum < 1 or cutoff_seconds < MIN_AGE:
        raise ValueError("unsafe comparator archiver budget/age")
    if audit.is_symlink():
        raise ValueError("unsafe source attestation audit directory")
    audit.mkdir(parents=True, exist_ok=True)
    with (audit / "lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        frozen, manifest_sha = frozen_source(root, images_file)
        records, journal_raw = completed_rows(root, frozen)
        ledger = audit / "actions.jsonl"
        done = {}
        if ledger.exists():
            rows = ledger.read_bytes()
            if rows and not rows.endswith(b"\n"):
                raise ValueError("truncated archiver action journal")
            for line in rows.splitlines():
                item = json.loads(line)
                key = (item["sample"], item["assembler"])
                if (key in done or key not in records
                        or records[key][0]["status"] != "success"
                        or item.get("failed_arm") is not False):
                    raise ValueError("duplicate, failed, or foreign archival action")
                if records[key][1] != item["record_jsonl_sha256"]:
                    raise ValueError("original comparator result changed")
                done[key] = item
        archived = 0
        now = time.time()
        for key, (record, line_sha) in records.items():
            if record["status"] != "success" or key in done:
                continue
            if shutil.disk_usage(root).free < MIN_FREE + 512 * 1024**2:
                break
            action = archive_arm(root, frozen, manifest_sha, record,
                                 line_sha, now - cutoff_seconds)
            if action is None:
                continue
            with ledger.open("a") as out:
                out.write(json.dumps(action, sort_keys=True) + "\n")
                out.flush()
                os.fsync(out.fileno())
            done[key] = action
            archived += 1
            print("DETAILS_LOSSLESS_ARCHIVED", len(done),
                  record["assembler"], record["sample"],
                  "raw", action["raw_detail_bytes"],
                  "compressed", action["archive_bytes"], flush=True)
            if archived >= maximum:
                break
        # Original journal may only append newer arms, never rewrite existing.
        after = (root / "results.jsonl").read_bytes()
        if not after.startswith(journal_raw):
            raise ValueError("original physical comparator journal was rewritten")
        return {"processed_new_arms": archived,
                "total_archived_arms": len(done),
                "raw_bytes": sum(x["raw_detail_bytes"] for x in done.values()),
                "archive_bytes": sum(x["archive_bytes"] for x in done.values()),
                "root_journal_snapshot_sha256": sha_bytes(journal_raw),
                "source_manifest_sha256": manifest_sha}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--results", type=Path, required=True)
    cli.add_argument("--images", type=Path, required=True)
    cli.add_argument("--audit", type=Path, required=True)
    cli.add_argument("--max-new", type=int, default=10)
    cli.add_argument("--loop", action="store_true")
    cli.add_argument("--interval-seconds", type=int, default=90)
    cli.add_argument("--restore-arm", type=Path)
    cli.add_argument("--restore-to", type=Path)
    args = cli.parse_args()
    if args.restore_arm:
        if args.restore_to is None:
            cli.error("--restore-arm requires --restore-to")
        arm = args.results / INVOCATION / args.restore_arm
        if (len(args.restore_arm.parts) != 2
                or ".." in args.restore_arm.parts
                or arm.is_symlink() or not arm.is_dir()):
            cli.error("restore only a known sample/assembler")
        frozen, _ = frozen_source(args.results, args.images)
        if (args.restore_arm.parts[0] not in frozen["original_inputs"]
                or args.restore_arm.parts[1] not in TOOLS):
            cli.error("restore record is not in the frozen real198 cohort")
        print("DETAILS_RESTORED", restore_to(arm, args.restore_to))
        return
    if args.interval_seconds < 30:
        cli.error("minimum archiver interval is 30 seconds")
    while True:
        try:
            progress = run(args.results, args.images, args.audit, args.max_new)
            print("DETAILS_LOSSLESS_ARCHIVE_STATUS",
                  json.dumps(progress, sort_keys=True), flush=True)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print("DETAILS_LOSSLESS_ARCHIVE_PAUSED", repr(exc), flush=True)
            if not args.loop:
                raise
        if not args.loop:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
