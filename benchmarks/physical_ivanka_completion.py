"""Finish the physical cohort's deferred Ivanka arm, never rerun six rivals.

The authentic physical MiCall runner and every source image are kept at
their original frozen commits. This orchestration code adds the final
198 Ivanka attempts and issues a source-bound completion certificate.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path

SIX = ("iva", "haploflow", "megahit", "abyss", "spades", "velvet")
SCHEMA = "ivanka.physical.ivanka-completion.v1"
BASE = "8458f9e5d34c39a6694b1fb6a40e055d7ce89553"
ORIGINAL = "ivanka.expanded.comparators_first_real.v1"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def six_completed(root, images):
    root = Path(root)
    path = root / "run_manifest.json"
    done = root / "attempt_summary.json"
    if not path.is_file() or not done.is_file():
        return False
    origin, summary = json.loads(path.read_text()), json.loads(done.read_text())
    if (origin.get("schema") != ORIGINAL
            or origin.get("expected_samples") != 198
            or origin.get("ivanka_deferred") is not True
            or set(origin.get("images", {})) != set(SIX)
            or any(origin["images"].get(name) != images.get(name) for name in SIX)
            or summary.get("schema") != ORIGINAL
            or summary.get("samples") != 198
            or set(summary.get("tools", ())) != set(SIX)
            or summary.get("ivanka_deferred") is not True
            or summary.get("manifest_sha256") != digest(path)):
        raise ValueError("physical six-way source/completion evidence changed")
    for name in SIX:
        if len(list((root / name / "checkpoints").glob("*.json"))) != 198:
            raise ValueError("physical six-way summary lacks 198 checkpoints: " + name)
    return True


def completed(root, images):
    root = Path(root)
    if not six_completed(root, images):
        return False
    final = root / "ivanka/attempt_summary.json"
    if not final.is_file():
        return False
    proof = json.loads(final.read_text())
    journal = root / "ivanka/results.jsonl"
    checkpoints = root / "ivanka/checkpoints"
    if (proof.get("schema") != SCHEMA
            or proof.get("samples") != 198
            or proof.get("terminal_count") != 198
            or proof.get("image_sha256") != images.get("ivanka")
            or proof.get("original_manifest_sha256")
               != digest(root / "run_manifest.json")
            or proof.get("completion_source_sha256")
               != digest(Path(__file__))
            or not journal.is_file()
            or proof.get("journal_sha256") != digest(journal)
            or len(list(checkpoints.glob("*.json"))) != 198):
        raise ValueError("physical Ivanka completion certificate changed")
    rows = [json.loads(line) for line in journal.read_text().splitlines()
            if line.strip()]
    if (len(rows) != 198
            or len({item.get("sample") for item in rows}) != 198
            or any(item.get("status") != "finished"
                   or item.get("tool") != "ivanka"
                   or item.get("image_id") != images["ivanka"]
                   or type(item.get("failed")) is not bool for item in rows)):
        raise ValueError("physical Ivanka terminal matrix incomplete")
    return True


def execute(data, output, images, source_roots, attestation, jobs=10):
    if not 1 <= jobs <= 10:
        raise ValueError("physical Ivanka parallelism must be 1..10")
    from benchmarks.expanded import comparators_first_real as original
    from benchmarks.expanded.fork_micall_synthetic import checked_images
    from benchmarks.expanded.micall_lock import exclusive_lock
    from benchmarks.expanded.physical_inputs import attest
    import podman_full_micall as pmm
    from project_references import final_max_sequences
    from reference_panel import (
        best_panel_alignment, build_reference_panel, panel_sha256)
    from Bio import SeqIO

    output = Path(output).resolve()
    if not six_completed(output, images):
        raise ValueError("six physical comparator arms must finish first")
    with exclusive_lock(output):
        if completed(output, images):
            return "ALREADY_COMPLETE"
        checked_images(images, attestation, source_roots, BASE)
        attest(data)
        records = original.rows(data)
        if len(records) != 198:
            raise ValueError("missing original physical read pairs")
        pmm.DATA = Path(data).resolve()
        pmm.RESULTS = output / "artifacts"
        pmm.final_max_sequences = final_max_sequences
        pmm.best_panel_alignment = best_panel_alignment
        hxb2 = next(SeqIO.parse(str(Path(data) / "hxb2.fasta"), "fasta")).seq
        projects, _ = pmm.load_micall_projects(images["iva"])
        panel = build_reference_panel(projects, hxb2)
        original_manifest = original.manifest(
            data, images, attestation, panel_sha256(panel))
        if json.loads((output / "run_manifest.json").read_text()) != original_manifest:
            raise ValueError("physical source/reference panel drift")

        folder = output / "ivanka"
        (folder / "checkpoints").mkdir(parents=True, exist_ok=True)
        recovered = original.replay(
            folder, records, "ivanka", images["ivanka"], panel, pmm)
        missing = [row for row in records if row["sample"] not in recovered]
        by_name = {row["sample"]: row for row in records}
        print("PHYSICAL_IVANKA_RESUMED", len(recovered), "remaining", len(missing),
              flush=True)
        with (folder / "results.jsonl").open("a", buffering=1) as journal:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                futures = [pool.submit(original.execute, row, "ivanka", images,
                                       hxb2, panel, pmm, output)
                           for row in missing]
                for future in as_completed(futures):
                    record = future.result()
                    original.verify(record, by_name[record["sample"]],
                                    "ivanka", images["ivanka"], panel, pmm)
                    journal.write(json.dumps(record, sort_keys=True) + "\n")
                    print("PHYSICAL_IVANKA_TERMINAL", record["sample"],
                          "failed" if record["failed"] else "success",
                          flush=True)

        verified = original.replay(
            folder, records, "ivanka", images["ivanka"], panel, pmm)
        if len(verified) != 198:
            raise ValueError("physical Ivanka missing authenticated terminal results")
        proof = {
            "schema": SCHEMA, "samples": 198, "terminal_count": len(verified),
            "successful": sum(not row["failed"] for row in verified.values()),
            "failed": sum(row["failed"] for row in verified.values()),
            "image_sha256": images["ivanka"],
            "original_manifest_sha256": digest(output / "run_manifest.json"),
            "journal_sha256": digest(folder / "results.jsonl"),
            "completion_source_sha256": digest(Path(__file__)),
        }
        original.atomic(folder / "attempt_summary.json", proof)
        if not completed(output, images):
            raise ValueError("physical completion certificate failed recheck")
        print("PHYSICAL_SEVEN_WAY_COHORT_TERMINAL", proof["successful"],
              "successful", proof["failed"], "failed", flush=True)
        return "COMPLETE"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--check-complete", action="store_true")
    parser.add_argument("--data", type=Path)
    parser.add_argument("--fork", type=Path)
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--jobs", type=int, default=10)
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    if args.check_complete:
        ready = completed(args.out, images)
        print("PHYSICAL_COHORT_COMPLETE" if ready else "PHYSICAL_COHORT_PENDING")
        return 0 if ready else 1
    if not all((args.data, args.fork, args.attestation)):
        parser.error("running the physical Ivanka stage requires frozen sources")
    print(execute(args.data, args.out, images, args.fork,
                  args.attestation, jobs=args.jobs), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
