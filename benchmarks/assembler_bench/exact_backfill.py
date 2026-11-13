"""Compute full and interior exact-read coverage after MiCall timers stop."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from benchmarks.generate_exact_sidecars import sha256
from benchmarks.produce_exact_coverage import generate
from micall.utils import exact_coverage
from .exact_cache import sidecar


def source_proof(fastqs, conseq, expected, image):
    if not conseq.is_file() or not expected or sha256(conseq) != expected:
        raise ValueError("final MAX consensus source digest mismatch")
    if not all(path.is_file() for path in fastqs):
        raise FileNotFoundError("original paired read files unavailable")
    if len(image) != 64:
        raise ValueError("missing immutable source image")
    return [sha256(path) for path in fastqs]


def generate_one(cache, cohort, sample, tool, candidate, fastqs,
                 conseq, expected, image, fork):
    folder = sidecar(cache, cohort, sample, tool, candidate)
    report_file = folder / "provenance.json"
    csv_file = folder / "exact_coverage.csv"
    if report_file.exists() and csv_file.exists():
        item = json.loads(report_file.read_text())
        if (item["source_conseq_sha256"] == expected
                and item["source_image_sha256"] == image
                and item["exact_coverage_sha256"] == sha256(csv_file)):
            return False
        raise ValueError("immutable exact-coverage report changed")
    if report_file.exists() != csv_file.exists():
        raise ValueError("partial exact-coverage sidecar")
    fastq_sha = source_proof(fastqs, conseq, expected, image)
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / (str(os.getpid()) + ".pending.csv")
    try:
        outcome = generate(*fastqs, conseq, temp, overlap_size=70)
        outcome.update({
            "method": "micall-longest-final-MAX-exact-v2",
            "source_conseq_sha256": expected,
            "source_image_sha256": image,
            "source_fastq_sha256": fastq_sha,
            "micall_exact_coverage_module_sha256": sha256(exact_coverage.__file__),
            "micall_fork_source_commit": fork,
            "exact_coverage_sha256": sha256(temp),
            "qualification_effect": "none",
        })
        metadata = folder / (str(os.getpid()) + ".pending.json")
        metadata.write_text(json.dumps(outcome, sort_keys=True) + "\n")
        temp.replace(csv_file)
        metadata.replace(report_file)
    finally:
        temp.unlink(missing_ok=True)
    return True


def synthetic_tasks(root, data, cache):
    images = json.loads((root / "run_manifest.json").read_text())["images"]
    for line in (root / "results.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sample = row["id"]
        reads = (data / sample / "reads")
        fastqs = [reads / f"R{i}.fastq.gz" for i in (1, 2)]
        for name, part in row["results"].items():
            if part["status"] != "success":
                continue
            evidence = part.get("final_dominant") or {}
            if part["sha256"] != images[name]:
                raise ValueError("synthetic benchmark image identity mismatch")
            yield (cache, "synthetic", sample, name, None, fastqs,
                   root / sample / name / "conseq.csv",
                   evidence.get("conseq_csv_sha256"), images[name])


def physical_tasks(root, data, cache):
    images = json.loads((root / "run_manifest.json").read_text())["images"]
    for candidate in ("ivanka", "haploflow", "megahit",
                      "abyss", "spades", "velvet"):
        results = root / candidate / "results.jsonl"
        if not results.is_file():
            continue
        for line in results.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("status") != "finished":
                continue
            sample = record["sample"]
            base = data / "samples" / sample
            fastqs = [base / f"{sample}_L001_R{i}_001.fastq.gz"
                      for i in (1, 2)]
            expected_reads = record["provenance"]["fastq_sha256"]
            for arm in ("iva", "ivanka"):
                part = record.get(arm) or {}
                if part.get("exit_code") != 0:
                    continue
                name = "iva" if arm == "iva" else candidate
                if part.get("image_id") != images[name]:
                    raise ValueError("physical benchmark image identity mismatch")
                evidence = (part.get("metrics") or {}).get("outputs") or {}
                output = evidence.get("conseq.csv") or {}
                yield (cache, "real", sample, arm, candidate, fastqs,
                       Path(part["artifact_dir"]) / "conseq.csv",
                       output.get("sha256"), images[name], expected_reads)


def unavailable_report(folder, expected, image, error):
    """Record the distinction between a missing consensus and zero depth."""
    output = folder / "unavailable.json"
    item = {"status": "unavailable", "reason": str(error),
            "source_conseq_sha256": expected,
            "source_image_sha256": image}
    if output.exists():
        if json.loads(output.read_text()) != item:
            raise ValueError("unavailable evidence changed")
        return
    folder.mkdir(parents=True, exist_ok=True)
    with output.open("x") as file:
        json.dump(item, file, sort_keys=True)
        file.write("\n")


def run(args):
    fork = subprocess.check_output(
        ["git", "-C", str(args.micall), "rev-parse", "HEAD"],
        text=True).strip()
    tasks = (synthetic_tasks(args.root, args.data, args.out)
             if args.cohort == "synthetic" else
             physical_tasks(args.root, args.data, args.out))
    generated = examined = 0
    for task in tasks:
        args_in = task[:9]
        report = sidecar(args.out, task[1], task[2], task[3], task[4])
        if (report / "provenance.json").is_file():
            # Verify existing cache before attempting any new work.
            generate_one(*args_in, fork)
            continue
        if (report / "unavailable.json").is_file():
            data = json.loads((report / "unavailable.json").read_text())
            if (data["source_conseq_sha256"] != task[7]
                    or data["source_image_sha256"] != task[8]):
                raise ValueError("unavailable sidecar source changed")
            continue
        if generated >= args.max_new:
            break
        if len(task) == 10:
            expected_reads = task[9]
            read_shas = [sha256(fq) for fq in task[5]]
            if read_shas != expected_reads:
                raise ValueError("physical FASTQ hashes changed")
        try:
            if generate_one(*args_in, fork):
                generated += 1
        except ValueError as error:
            if str(error) != "no final MAX consensus available for exact coverage":
                raise
            unavailable_report(report, task[7], task[8], error)
            print("EXACT_UNAVAILABLE_NO_FINAL_MAX", args.cohort,
                  "source_sha256", task[7][:12], flush=True)
        examined += 1
    print("EXACT_SIDECARS_VERIFIED", args.cohort,
          "new", generated, "examined", examined, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=("synthetic", "real"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--micall", type=Path, required=True)
    parser.add_argument("--max-new", type=int, default=12)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
